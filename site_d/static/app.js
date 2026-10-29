(function () {
  var D = window.FRIDGE;
  var STAPLES = {};
  D.staples.forEach(function (s) { STAPLES[s] = true; });
  var alias = {};
  Object.keys(D.aliases).forEach(function (canon) {
    D.aliases[canon].forEach(function (a) { alias[a.replace(/\s/g, "").toLowerCase()] = canon; });
  });
  var bySlug = {};
  D.recipes.forEach(function (r) { bySlug[r.slug] = r; });
  var have = {};
  var staplesOn = true;
  var undo = {};       // 한 번에 담기 버튼별로 '그 버튼이 새로 담은' 재료(해제하면 이것만 뺀다)
  var openIdx = 0;     // 지금 열려 있는 냉장고 칸

  function store(get, val) {
    try { if (get) { return JSON.parse(localStorage.getItem("fridge_v1") || "null"); } localStorage.setItem("fridge_v1", JSON.stringify(val)); } catch (e) {}
    return null;
  }
  var saved = store(true);
  if (saved) { (saved.have || []).forEach(function (n) { have[n] = true; }); if (saved.staplesOn === false) { staplesOn = false; } undo = saved.undo || {}; }
  function persist() { store(false, { have: Object.keys(have), staplesOn: staplesOn, undo: undo }); }

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) { e.className = cls; } if (text != null) { e.textContent = text; } return e; }
  function resolve(text) {
    var k = text.replace(/\s/g, "").toLowerCase();
    if (!k) { return null; }
    if (alias[k]) { return alias[k]; }
    var found = null;
    Object.keys(alias).forEach(function (a) { if (!found && a.length >= 2 && k.length >= 2 && (a.indexOf(k) === 0 || k.indexOf(a) === 0)) { found = alias[a]; } });
    return found;
  }

  var $q = document.getElementById("q");
  var $sel = document.getElementById("selected");
  var $cats = document.getElementById("cats");
  var $res = document.getElementById("results");
  var $staples = document.getElementById("staples");
  var $sug = document.getElementById("sug");
  var $quick = document.getElementById("quick");
  var $bar = document.getElementById("bar");
  var $barText = document.getElementById("barText");
  document.getElementById("stapleList").textContent = D.staples.filter(function (s) { return s !== "물"; }).join(", ");
  $staples.checked = staplesOn;

  function toggle(name) { if (have[name]) { delete have[name]; } else { have[name] = true; } persist(); render(); }

  // ---- 한 번에 담기: 누르면 눌린 상태, 다시 누르면 그 버튼이 담았던 재료만 빠지고 원래대로 돌아간다 ----
  function allOn(items) { return items.length > 0 && items.every(function (n) { return have[n]; }); }
  function togglePack(key, items) {
    if (allOn(items)) {
      (undo[key] || items).forEach(function (n) { delete have[n]; });
      delete undo[key];
    } else {
      var added = [];
      items.forEach(function (n) { if (!have[n]) { have[n] = true; added.push(n); } });
      undo[key] = added;
    }
    persist();
    render();
  }
  function recipeItems(r) {
    return r.ingredients.filter(function (i) { return !i.opt && !STAPLES[i.n]; }).map(function (i) { return i.n; });
  }

  function packButton(key, label, items, icon, extra) {
    var b = el("button", "preset" + (allOn(items) ? " on" : ""));
    b.type = "button";
    b.setAttribute("aria-pressed", allOn(items) ? "true" : "false");
    if (icon) { b.appendChild(el("span", "pi", icon)); }
    b.appendChild(document.createTextNode(label));
    if (extra) { b.appendChild(el("small", null, " " + extra)); }
    b.addEventListener("click", function () { togglePack(key, items); });
    return b;
  }

  function seededPick(count) {
    var d = new Date();
    var seed = d.getFullYear() * 400 + d.getMonth() * 31 + d.getDate();
    var order = D.recipes.map(function (r, i) { return { r: r, k: ((i + 1) * 2654435761 + seed * 40503) % 1009 }; });
    order.sort(function (a, b) { return a.k - b.k; });
    return order.slice(0, count).map(function (o) { return o.r; });
  }

  function buildQuick() {
    $quick.textContent = "";
    function row(label, note) {
      var wrap = el("div", "qrow");
      var l = el("p", "qlabel", label);
      if (note) { l.appendChild(el("small", null, " " + note)); }
      wrap.appendChild(l);
      var box = el("div", "presets");
      wrap.appendChild(box);
      $quick.appendChild(wrap);
      return box;
    }
    var r1 = row("한 번에 담기");
    D.presets.forEach(function (p) { r1.appendChild(packButton("p:" + p.name, p.name, p.items)); });
    var d = new Date();
    var r2 = row("오늘의 추천 메뉴", (d.getMonth() + 1) + "/" + d.getDate() + " · 누르면 재료가 담겨요");
    seededPick(3).forEach(function (r) { r2.appendChild(packButton("r:" + r.slug, r.name, recipeItems(r), r.icon)); });
    if (D.popular && D.popular.length) {
      var r3 = row("많이 찾는 요리", (D.popularUpdated ? D.popularUpdated + " 기준 · " : "") + "네이버 월간 검색량 순");
      D.popular.slice(0, 6).forEach(function (slug, i) {
        var r = bySlug[slug];
        if (r) { r3.appendChild(packButton("r:" + r.slug, r.name, recipeItems(r), String(i + 1))); }
      });
    }
  }

  // ---- 냉장고 칸: 한 칸씩 열린다. '다음'을 누르면 다음 칸이 열리고 이전 칸은 접혀 고른 재료만 보인다 ----
  function buildCats() {
    $cats.textContent = "";
    var cats = Object.keys(D.categories);
    cats.forEach(function (cat, idx) {
      var names = D.categories[cat];
      var picked = names.filter(function (n) { return have[n]; });
      var shelf = el("div", "shelf" + (idx === openIdx ? " open" : "") + (picked.length ? " done" : ""));
      var head = el("button", "shelf-head");
      head.type = "button";
      head.setAttribute("aria-expanded", idx === openIdx ? "true" : "false");
      head.appendChild(el("span", "no", String(idx + 1)));
      head.appendChild(el("span", null, cat));
      head.appendChild(el("span", "sum", picked.length ? picked.map(function (n) { return (D.emoji[n] || "") + n; }).join(" ") : "눌러서 열기"));
      head.appendChild(el("span", "chev", "▾"));
      head.addEventListener("click", function () { openIdx = (openIdx === idx) ? -1 : idx; buildCats(); });
      shelf.appendChild(head);
      var body = el("div", "shelf-body");
      var box = el("div", "tiles");
      names.forEach(function (n) {
        var b = el("button", "tile" + (have[n] ? " on" : ""));
        b.type = "button";
        b.setAttribute("aria-pressed", have[n] ? "true" : "false");
        b.appendChild(el("span", "em", D.emoji[n] || "•"));
        b.appendChild(el("span", "tn", n));
        b.addEventListener("click", function () { toggle(n); });
        box.appendChild(b);
      });
      body.appendChild(box);
      var last = idx === cats.length - 1;
      var next = el("button", "btn ghost next", last ? "다 골랐어요 → 결과 보기" : "다음: " + cats[idx + 1] + " ▶");
      next.type = "button";
      next.addEventListener("click", function () {
        if (last) { openIdx = -1; buildCats(); $res.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
        openIdx = idx + 1;
        buildCats();
        var h = $cats.querySelectorAll(".shelf")[openIdx];
        if (h) { h.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
      });
      body.appendChild(next);
      shelf.appendChild(body);
      $cats.appendChild(shelf);
    });
  }

  function buildSelected() {
    $sel.textContent = "";
    var names = Object.keys(have);
    if (!names.length) { $sel.appendChild(el("span", "sel-empty", "위에서 재료를 눌러 담아 보세요")); return; }
    names.forEach(function (n) {
      var b = el("button", "chip on", (D.emoji[n] || "") + " " + n + " ✕");
      b.type = "button";
      b.setAttribute("aria-label", n + " 빼기");
      b.addEventListener("click", function () { toggle(n); });
      $sel.appendChild(b);
    });
  }

  function evaluate(r) {
    var need = r.ingredients.filter(function (i) { return !i.opt && !(staplesOn && STAPLES[i.n]); });
    var missing = need.filter(function (i) { return !have[i.n]; });
    var used = r.ingredients.filter(function (i) { return have[i.n] && !STAPLES[i.n]; }).length;
    return { r: r, missing: missing, used: used };
  }

  function thumb(r) {
    var ic = el("div", "ic");
    if (r.img) {
      var im = el("img");
      im.src = r.img; im.alt = r.name; im.loading = "lazy";
      ic.appendChild(im);
    } else { ic.textContent = r.icon; }
    return ic;
  }

  function card(ev) {
    var a = el("div", "card");
    a.appendChild(thumb(ev.r));
    var body = el("div", "body");
    var h3 = el("h3");
    var title = el("a", null, ev.r.name);
    title.href = "recipes/" + ev.r.slug + ".html";
    h3.appendChild(title);
    body.appendChild(h3);
    body.appendChild(el("div", "meta", ev.r.minutes + "분 · 1인분 " + ev.r.kcal + "kcal"));
    if (ev.missing.length) {
      var row = el("div", "miss-row");
      ev.missing.forEach(function (m) {
        row.appendChild(el("span", "chip miss", m.n + " 없음"));
        var url = D.affiliate[m.n];
        if (url) {
          var buy = el("a", "buy", "쿠팡");
          buy.href = url;
          buy.target = "_blank";
          buy.rel = "sponsored nofollow noopener noreferrer";
          row.appendChild(buy);
        }
      });
      body.appendChild(row);
    } else {
      body.appendChild(el("span", "chip have", "재료 다 있어요"));
    }
    a.appendChild(body);
    return a;
  }

  function group(title, cls, list, openAll) {
    if (!list.length) { return; }
    var h = el("div", "group-title");
    h.appendChild(document.createTextNode(title + " "));
    h.appendChild(el("span", "badge " + cls, list.length + "개"));
    $res.appendChild(h);
    list.forEach(function (ev, i) { if (openAll || i < 10) { $res.appendChild(card(ev)); } });
    if (!openAll && list.length > 10) { $res.appendChild(el("p", "meta", "…외 " + (list.length - 10) + "개는 재료를 더 고르면 좁혀져요.")); }
  }

  function render() {
    buildQuick();
    buildCats();
    buildSelected();
    $res.textContent = "";
    var count = Object.keys(have).length;
    if (!count) {
      $bar.hidden = true;
      $res.appendChild(el("div", "empty", "재료를 고르면 만들 수 있는 요리가 여기에 나와요."));
      return;
    }
    var evs = D.recipes.map(evaluate).filter(function (e) { return e.used >= 1; });
    function sortFn(a, b) { return b.used - a.used || a.r.minutes - b.r.minutes; }
    var zero = evs.filter(function (e) { return e.missing.length === 0; }).sort(sortFn);
    var one = evs.filter(function (e) { return e.missing.length === 1; }).sort(sortFn);
    var two = evs.filter(function (e) { return e.missing.length === 2; }).sort(sortFn);
    $barText.textContent = "재료 " + count + "개 · 바로 " + zero.length + "개 · 1가지만 더 " + one.length + "개";
    $bar.hidden = false;
    if (!zero.length && !one.length && !two.length) {
      $res.appendChild(el("div", "empty", "딱 맞는 요리를 못 찾았어요. 재료를 한두 개 더 골라 보세요."));
      return;
    }
    group("지금 바로 만들 수 있어요", "", zero, true);
    group("재료 1가지만 더 있으면", "one", one, true);
    group("재료 2가지가 더 필요해요", "one", two, false);
  }

  function addFromText() {
    var raw = $q.value.split(/[,\s]+/).filter(Boolean);
    var unknown = [];
    raw.forEach(function (t) { var c = resolve(t); if (c) { have[c] = true; } else { unknown.push(t); } });
    $q.value = unknown.join(" ");
    persist();
    render();
    $sug.textContent = "";
    if (unknown.length) { $sug.appendChild(el("span", null, "아직 모르는 재료예요: " + unknown.join(", "))); }
  }

  document.getElementById("add").addEventListener("click", addFromText);
  $q.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addFromText(); } });
  document.getElementById("clear").addEventListener("click", function () { have = {}; undo = {}; persist(); render(); });
  document.getElementById("barGo").addEventListener("click", function () { $res.scrollIntoView({ behavior: "smooth", block: "start" }); });
  $staples.addEventListener("change", function () { staplesOn = $staples.checked; persist(); render(); });

  // 결과가 화면에 보이면 아래 고정 바는 숨긴다
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      document.body.classList.toggle("res-visible", entries[0].isIntersecting);
    }, { threshold: 0.05 }).observe($res);
  }
  render();
})();

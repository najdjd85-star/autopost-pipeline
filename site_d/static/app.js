(function () {
  var D = window.FRIDGE;
  var STAPLES = {};
  D.staples.forEach(function (s) { STAPLES[s] = true; });
  STAPLES["물"] = true;
  var PANTRY = D.staples.filter(function (s) { return s !== "물"; });   // 양념통에 보여 줄 양념(물은 늘 있다고 본다)
  var alias = {};
  Object.keys(D.aliases).forEach(function (canon) {
    D.aliases[canon].forEach(function (a) { alias[a.replace(/\s/g, "").toLowerCase()] = canon; });
  });
  var bySlug = {};
  D.recipes.forEach(function (r) { bySlug[r.slug] = r; });
  var have = {};
  var undo = {};       // 한 번에 담기 버튼별로 '그 버튼이 새로 담은' 재료(해제하면 이것만 뺀다)
  var openIdx = 0;     // 지금 열려 있는 냉장고 칸

  function store(get, val) {
    try { if (get) { return JSON.parse(localStorage.getItem("fridge_v2") || "null"); } localStorage.setItem("fridge_v2", JSON.stringify(val)); } catch (e) {}
    return null;
  }
  var saved = store(true);
  if (saved) { (saved.have || []).forEach(function (n) { have[n] = true; }); undo = saved.undo || {}; }
  else { (D.stapleDefaults || []).forEach(function (n) { have[n] = true; }); }   // 처음 열면 흔한 양념만 미리 켜 둔다
  function persist() { store(false, { have: Object.keys(have), undo: undo }); }

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) { e.className = cls; } if (text != null) { e.textContent = text; } return e; }
  function foods() { return Object.keys(have).filter(function (n) { return !STAPLES[n]; }); }
  function resolve(text) {
    var k = text.replace(/\s/g, "").toLowerCase();
    if (!k) { return null; }
    if (alias[k]) { return alias[k]; }
    var found = null;
    Object.keys(alias).forEach(function (a) { if (!found && a.length >= 2 && k.length >= 2 && (a.indexOf(k) === 0 || k.indexOf(a) === 0)) { found = alias[a]; } });
    if (!found) { PANTRY.forEach(function (p) { if (p.replace(/\s/g, "") === k) { found = p; } }); }
    return found;
  }

  var $q = document.getElementById("q");
  var $sel = document.getElementById("selected");
  var $cats = document.getElementById("cats");
  var $res = document.getElementById("results");
  var $sug = document.getElementById("sug");
  var $quick = document.getElementById("quick");
  var $bar = document.getElementById("bar");
  var $barText = document.getElementById("barText");

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

  function packButton(key, label, items, icon) {
    var b = el("button", "preset" + (allOn(items) ? " on" : ""));
    b.type = "button";
    b.setAttribute("aria-pressed", allOn(items) ? "true" : "false");
    if (icon) { b.appendChild(el("span", "pi", icon)); }
    b.appendChild(document.createTextNode(label));
    b.addEventListener("click", function () { togglePack(key, items); });
    return b;
  }

  // ---- 인기 요리 한 줄: 누르면 그 요리의 재료가 담기고, 다시 누르면 원래대로 돌아간다 ----
  function buildQuick() {
    $quick.textContent = "";
    var t = D.trending;
    if (!t || !t.slugs || !t.slugs.length) { return; }
    var daily = t.kind === "daily";
    var wrap = el("div", "qrow");
    var l = el("p", "qlabel", daily ? "오늘 많이 찾은 요리" : "많이 찾는 요리");
    var note = daily ? (t.date ? t.date.slice(5).replace("-", "/") + " 기준 · 네이버 검색 · 누르면 재료가 담겨요" : "네이버 검색 · 누르면 재료가 담겨요")
                     : "네이버 월간 검색량 순 · 누르면 재료가 담겨요";
    l.appendChild(el("small", null, " " + note));
    wrap.appendChild(l);
    var box = el("div", "presets");
    t.slugs.forEach(function (slug, i) {
      var r = bySlug[slug];
      if (r) { box.appendChild(packButton("r:" + r.slug, r.name, recipeItems(r), String(i + 1))); }
    });
    wrap.appendChild(box);
    $quick.appendChild(wrap);
  }

  // ---- 냉장고 칸: 한 칸씩 열린다. 마지막 칸은 '양념통'이고, 집에 있는 양념을 직접 고른다 ----
  function shelves() {
    var list = Object.keys(D.categories).map(function (c) { return { name: c, items: D.categories[c], pantry: false }; });
    list.push({ name: "양념통", items: PANTRY, pantry: true });
    return list;
  }

  function buildCats() {
    $cats.textContent = "";
    var all = shelves();
    all.forEach(function (sh, idx) {
      var picked = sh.items.filter(function (n) { return have[n]; });
      var shelf = el("div", "shelf" + (idx === openIdx ? " open" : "") + (picked.length ? " done" : ""));
      var head = el("button", "shelf-head");
      head.type = "button";
      head.setAttribute("aria-expanded", idx === openIdx ? "true" : "false");
      head.appendChild(el("span", "no", String(idx + 1)));
      head.appendChild(el("span", null, sh.name));
      var sum = sh.pantry ? (picked.length + "개 있음") : (picked.length ? picked.map(function (n) { return (D.emoji[n] || "") + n; }).join(" ") : "눌러서 열기");
      head.appendChild(el("span", "sum", sum));
      head.appendChild(el("span", "chev", "▾"));
      head.addEventListener("click", function () { openIdx = (openIdx === idx) ? -1 : idx; buildCats(); });
      shelf.appendChild(head);
      var body = el("div", "shelf-body");
      if (sh.pantry) { body.appendChild(el("p", "shelf-note", "집에 있는 양념을 눌러 주세요. 없는 양념이 필요한 요리는 '없음'으로 표시돼요. (소금·설탕·간장·식용유·후추는 미리 켜 뒀어요)")); }
      var box = el("div", "tiles");
      sh.items.forEach(function (n) {
        var b = el("button", "tile" + (have[n] ? " on" : "") + (sh.pantry ? " staple" : ""));
        b.type = "button";
        b.setAttribute("aria-pressed", have[n] ? "true" : "false");
        b.appendChild(el("span", "em", D.emoji[n] || "•"));
        b.appendChild(el("span", "tn", n));
        b.addEventListener("click", function () { toggle(n); });
        box.appendChild(b);
      });
      body.appendChild(box);
      var last = idx === all.length - 1;
      var next = el("button", "btn ghost next", last ? "다 골랐어요 → 결과 보기" : "다음: " + all[idx + 1].name + " ▶");
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
    var names = foods();
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
    var need = r.ingredients.filter(function (i) { return !i.opt && i.n !== "물"; });   // 양념도 집에 있는 것만 인정한다
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

  function buyLink(url, label) {
    var buy = el("a", "buy", label);
    buy.href = url;
    buy.target = "_blank";
    buy.rel = "sponsored nofollow noopener noreferrer";
    return buy;
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
      var links = [];
      ev.missing.forEach(function (m) {
        row.appendChild(el("span", "chip miss", m.n + " 없음"));
        if (D.affiliate[m.n]) { links.push({ n: m.n, url: D.affiliate[m.n] }); }
      });
      body.appendChild(row);
      if (links.length === 1) {   // 링크가 하나면 바로 연결, 여럿이면 눌러서 펼친다
        body.appendChild(buyLink(links[0].url, "없는 재료 사러가기"));
      } else if (links.length > 1) {
        var det = el("details", "buylist");
        det.appendChild(el("summary", "buy", "없는 재료 사러가기 ▾"));
        var inner = el("div", "buyinner");
        links.forEach(function (l) { inner.appendChild(buyLink(l.url, l.n + " 사러가기")); });
        det.appendChild(inner);
        body.appendChild(det);
      }
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
    var count = foods().length;
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
      $res.appendChild(el("div", "empty", "딱 맞는 요리를 못 찾았어요. 재료나 양념을 한두 개 더 골라 보세요."));
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
  // 모두 지우기: 재료만 지우고, 고른 양념은 그대로 둔다
  document.getElementById("clear").addEventListener("click", function () {
    Object.keys(have).forEach(function (n) { if (!STAPLES[n]) { delete have[n]; } });
    undo = {}; persist(); render();
  });
  document.getElementById("barGo").addEventListener("click", function () { $res.scrollIntoView({ behavior: "smooth", block: "start" }); });

  // 결과가 화면에 보이면 아래 고정 바는 숨긴다
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      document.body.classList.toggle("res-visible", entries[0].isIntersecting);
    }, { threshold: 0.05 }).observe($res);
  }
  render();

  // 매일 갱신되는 trending.json 을 직접 읽어 최신으로 바꾼다(없거나 실패하면 빌드에 들어 있던 값을 그대로 쓴다)
  try {
    fetch("trending.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d || !d.items || !d.items.length) { return; }
      var slugs = d.items.map(function (i) { return i.slug; }).filter(function (s) { return bySlug[s]; }).slice(0, 8);
      if (slugs.length) { D.trending = { kind: "daily", slugs: slugs, date: d.date || "", updated: d.updated || "" }; buildQuick(); }
    }).catch(function () {});
  } catch (e) {}

  // ---- 모든 레시피: 초성 필터 + 검색(초성만 입력해도 됨) ----
  var $rq = document.getElementById("rq");
  if ($rq) {
    var curI = "";
    var items = [].slice.call(document.querySelectorAll("#rl li"));
    var groups = [].slice.call(document.querySelectorAll("#rl .rgroup"));
    var $none = document.getElementById("rnone");
    var onlyCons = function (t) { return /^[ㄱ-ㅎ]+$/.test(t); };
    var filterList = function () {
      var q = $rq.value.replace(/\s/g, "");
      var shown = 0;
      items.forEach(function (li) {
        var n = li.getAttribute("data-n");
        var okQ = !q || (onlyCons(q) ? li.getAttribute("data-c").indexOf(q) > -1 : n.indexOf(q) > -1);
        var okI = !curI || li.parentNode.parentNode.getAttribute("data-i") === curI;
        li.hidden = !(okQ && okI);
        if (!li.hidden) { shown++; }
      });
      groups.forEach(function (g) { g.hidden = !g.querySelector("li:not([hidden])"); });
      $none.hidden = shown > 0;
    };
    $rq.addEventListener("input", filterList);
    document.getElementById("ri").addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button") : null;
      if (!b) { return; }
      curI = b.getAttribute("data-i") || "";
      [].forEach.call(document.querySelectorAll("#ri .chip"), function (c) { c.classList.toggle("on", c === b); });
      filterList();
    });
  }
})();

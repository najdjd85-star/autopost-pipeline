(function () {
  var D = window.FRIDGE;
  var STAPLES = {};
  D.staples.forEach(function (s) { STAPLES[s] = true; });
  var alias = {};
  Object.keys(D.aliases).forEach(function (canon) {
    D.aliases[canon].forEach(function (a) { alias[a.replace(/\s/g, "").toLowerCase()] = canon; });
  });
  var have = {};
  var staplesOn = true;

  function store(get, val) {
    try { if (get) { return JSON.parse(localStorage.getItem("fridge_v1") || "null"); } localStorage.setItem("fridge_v1", JSON.stringify(val)); } catch (e) {}
    return null;
  }
  var saved = store(true);
  if (saved) { (saved.have || []).forEach(function (n) { have[n] = true; }); if (saved.staplesOn === false) { staplesOn = false; } }
  function persist() { store(false, { have: Object.keys(have), staplesOn: staplesOn }); }

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
  var $presets = document.getElementById("presets");
  var $bar = document.getElementById("bar");
  var $barText = document.getElementById("barText");
  document.getElementById("stapleList").textContent = D.staples.filter(function (s) { return s !== "물"; }).join(", ");
  $staples.checked = staplesOn;

  function toggle(name) { if (have[name]) { delete have[name]; } else { have[name] = true; } persist(); render(); }

  function buildPresets() {
    $presets.textContent = "";
    D.presets.forEach(function (p) {
      var b = el("button", "preset", p.name);
      b.type = "button";
      b.addEventListener("click", function () { p.items.forEach(function (n) { have[n] = true; }); persist(); render(); });
      $presets.appendChild(b);
    });
  }

  function buildCats() {
    $cats.textContent = "";
    Object.keys(D.categories).forEach(function (cat) {
      var shelf = el("div", "shelf");
      shelf.appendChild(el("p", "shelf-title", cat));
      var box = el("div", "tiles");
      D.categories[cat].forEach(function (n) {
        var b = el("button", "tile" + (have[n] ? " on" : ""));
        b.type = "button";
        b.setAttribute("aria-pressed", have[n] ? "true" : "false");
        b.appendChild(el("span", "em", D.emoji[n] || "•"));
        b.appendChild(el("span", "tn", n));
        b.addEventListener("click", function () { toggle(n); });
        box.appendChild(b);
      });
      shelf.appendChild(box);
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
  document.getElementById("clear").addEventListener("click", function () { have = {}; persist(); render(); });
  document.getElementById("barGo").addEventListener("click", function () { $res.scrollIntoView({ behavior: "smooth", block: "start" }); });
  $staples.addEventListener("change", function () { staplesOn = $staples.checked; persist(); render(); });

  // 결과가 화면에 보이면 아래 고정 바는 숨긴다
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      document.body.classList.toggle("res-visible", entries[0].isIntersecting);
    }, { threshold: 0.05 }).observe($res);
  }
  buildPresets();
  render();
})();

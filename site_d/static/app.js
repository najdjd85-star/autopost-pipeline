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
    Object.keys(alias).forEach(function (a) { if (!found && a.length >= 2 && (a.indexOf(k) === 0 || k.indexOf(a) === 0) && k.length >= 2) { found = alias[a]; } });
    return found;
  }

  var $q = document.getElementById("q");
  var $sel = document.getElementById("selected");
  var $cats = document.getElementById("cats");
  var $res = document.getElementById("results");
  var $staples = document.getElementById("staples");
  var $sug = document.getElementById("sug");
  var $stapleList = document.getElementById("stapleList");
  $stapleList.textContent = D.staples.filter(function (s) { return s !== "물"; }).join(", ");
  $staples.checked = staplesOn;

  function toggle(name) { if (have[name]) { delete have[name]; } else { have[name] = true; } persist(); render(); }

  function buildCats() {
    $cats.textContent = "";
    Object.keys(D.categories).forEach(function (cat) {
      $cats.appendChild(el("div", "cat", cat));
      var box = el("div", "chips");
      D.categories[cat].forEach(function (n) {
        var b = el("button", "chip" + (have[n] ? " on" : ""), n);
        b.type = "button";
        b.setAttribute("aria-pressed", have[n] ? "true" : "false");
        b.addEventListener("click", function () { toggle(n); });
        box.appendChild(b);
      });
      $cats.appendChild(box);
    });
  }

  function buildSelected() {
    $sel.textContent = "";
    var names = Object.keys(have);
    if (!names.length) { $sel.appendChild(el("span", "sel-empty", "아직 고른 재료가 없어요. 위에서 눌러 추가해 보세요.")); return; }
    names.forEach(function (n) {
      var b = el("button", "chip on", n + " ✕");
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
    var optHave = r.ingredients.filter(function (i) { return i.opt && have[i.n]; }).map(function (i) { return i.n; });
    return { r: r, missing: missing, used: used, optHave: optHave };
  }

  function card(ev) {
    var a = el("div", "card");
    var h3 = el("h3");
    var title = el("a", null, ev.r.name);
    title.href = "recipes/" + ev.r.slug + ".html";
    h3.appendChild(title);
    a.appendChild(h3);
    a.appendChild(el("div", "meta", ev.r.minutes + "분 · " + ev.r.level + " · 내 재료 " + ev.used + "개 사용"));
    a.appendChild(el("p", null, ev.r.desc));
    if (ev.missing.length) {
      var row = el("div", "miss-row");
      row.appendChild(el("span", "meta", "부족한 재료"));
      ev.missing.forEach(function (m) {
        row.appendChild(el("span", "chip miss", m.n));
        var url = D.affiliate[m.n];
        if (url) {
          var buy = el("a", "buy", "쿠팡에서 보기");
          buy.href = url;
          buy.target = "_blank";
          buy.rel = "sponsored nofollow noopener noreferrer";
          row.appendChild(buy);
        }
      });
      a.appendChild(row);
    }
    if (ev.optHave.length) {
      var o = el("div", "miss-row");
      o.appendChild(el("span", "meta", "있으면 더 좋은 재료 보유"));
      ev.optHave.forEach(function (n) { o.appendChild(el("span", "chip have", n + " ✓")); });
      a.appendChild(o);
    }
    var go = el("a", "more", "레시피 보기 →");
    go.href = "recipes/" + ev.r.slug + ".html";
    a.appendChild(go);
    return a;
  }

  function group(title, cls, list, openAll) {
    if (!list.length) { return; }
    var h = el("div", "group-title");
    h.appendChild(document.createTextNode(title + " "));
    h.appendChild(el("span", "badge " + cls, list.length + "개"));
    $res.appendChild(h);
    list.forEach(function (ev, i) { if (openAll || i < 12) { $res.appendChild(card(ev)); } });
    if (!openAll && list.length > 12) { $res.appendChild(el("p", "meta", "…외 " + (list.length - 12) + "개는 재료를 더 고르면 좁혀져요.")); }
  }

  function render() {
    buildCats();
    buildSelected();
    $res.textContent = "";
    var $jump = document.getElementById("jump");
    $jump.style.display = "none";
    if (!Object.keys(have).length) { $res.appendChild(el("div", "empty", "재료를 고르면 만들 수 있는 요리가 여기에 나와요.")); return; }
    var evs = D.recipes.map(evaluate).filter(function (e) { return e.used >= 1; });
    function sortFn(a, b) { return b.used - a.used || a.r.minutes - b.r.minutes; }
    var zero = evs.filter(function (e) { return e.missing.length === 0; }).sort(sortFn);
    var one = evs.filter(function (e) { return e.missing.length === 1; }).sort(sortFn);
    var two = evs.filter(function (e) { return e.missing.length === 2; }).sort(sortFn);
    if (!zero.length && !one.length && !two.length) {
      $res.appendChild(el("div", "empty", "딱 맞는 요리를 못 찾았어요. 재료를 한두 개 더 골라 보세요."));
      return;
    }
    $jump.textContent = "만들 수 있는 요리 " + zero.length + "개 · 1가지만 더 있으면 " + one.length + "개 보기 ↓";
    $jump.style.display = "inline-block";
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
    if (unknown.length) { $sug.textContent = ""; $sug.appendChild(el("span", "meta", "아직 모르는 재료예요: " + unknown.join(", "))); } else { $sug.textContent = ""; }
  }

  document.getElementById("add").addEventListener("click", addFromText);
  $q.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addFromText(); } });
  document.getElementById("clear").addEventListener("click", function () { have = {}; persist(); render(); });
  $staples.addEventListener("change", function () { staplesOn = $staples.checked; persist(); render(); });
  render();
})();

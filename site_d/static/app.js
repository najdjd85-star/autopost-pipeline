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
  var recent = [];     // 최근에 고른 재료(다음에 한 번에 다시 담을 수 있게 맨 위에 보여 준다)
  var focus = "";      // 방금 눌러 담은 인기 요리(결과 맨 위에 따로 보여 준다)
  var pantryOpen = false;
  var TOP = 10;        // 칸마다 먼저 보여 주는 재료 수(레시피에 많이 쓰이는 순)
  var moreOpen = {};   // '더 보기'를 펼친 칸
  var usage = {};      // 재료별로 쓰이는 레시피 수
  D.recipes.forEach(function (r) { r.ingredients.forEach(function (i) { usage[i.n] = (usage[i.n] || 0) + 1; }); });

  function store(get, val) {
    try { if (get) { return JSON.parse(localStorage.getItem("fridge_v2") || "null"); } localStorage.setItem("fridge_v2", JSON.stringify(val)); } catch (e) {}
    return null;
  }
  var saved = store(true);
  if (saved) { (saved.have || []).forEach(function (n) { have[n] = true; }); undo = saved.undo || {}; recent = saved.recent || []; }
  else { (D.stapleDefaults || []).forEach(function (n) { have[n] = true; }); }   // 처음 열면 흔한 양념만 미리 켜 둔다
  function persist() { store(false, { have: Object.keys(have), undo: undo, recent: recent }); }
  function markRecent(n) { if (STAPLES[n]) { return; } recent = [n].concat(recent.filter(function (x) { return x !== n; })).slice(0, 10); }

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) { e.className = cls; } if (text != null) { e.textContent = text; } return e; }
  function foods() { return Object.keys(have).filter(function (n) { return !STAPLES[n]; }); }
  function resolve(text) {
    var k = text.replace(/\s/g, "").toLowerCase();
    if (!k) { return null; }
    if (alias[k]) { return alias[k]; }
    var found = null;
    Object.keys(alias).forEach(function (a) { if (!found && a.length >= 2 && k.length >= 2 && k.indexOf(a) === 0) { found = alias[a]; } });
    if (!found) { PANTRY.forEach(function (p) { if (p.replace(/\s/g, "") === k) { found = p; } }); }
    var SYN = { "마늘": "다진마늘", "들깨": "들깨가루", "깨": "통깨", "머스타드": "머스터드", "깨소금": "통깨", "참깨": "통깨", "기름": "식용유", "후춧가루": "후추", "미림": "맛술", "물엿": "올리고당", "케찹": "케첩", "토마토케첩": "케첩", "멸치액젓": "액젓", "까나리액젓": "액젓", "치킨스톡": "다시다", "육수코인": "다시다", "스테이크소스": "돈가스소스", "고추냉이": "와사비", "허니": "꿀" };
    if (!found && SYN[k]) { found = SYN[k]; }
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

  function toggle(name) { if (have[name]) { delete have[name]; } else { have[name] = true; markRecent(name); } focus = ""; persist(); render(); }

  // ---- 한 번에 담기: 누르면 눌린 상태, 다시 누르면 그 버튼이 담았던 재료만 빠지고 원래대로 돌아간다 ----
  function allOn(items) { return items.length > 0 && items.every(function (n) { return have[n]; }); }
  function togglePack(key, items) {
    if (allOn(items)) {
      (undo[key] || items).forEach(function (n) { delete have[n]; });
      delete undo[key];
      focus = "";
    } else {
      var added = [];
      items.forEach(function (n) { if (!have[n]) { have[n] = true; added.push(n); } });
      undo[key] = added;
      focus = key.indexOf("r:") === 0 ? key.slice(2) : "";
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

  // ---- 재료판: 칸을 일일이 열지 않도록 모든 재료를 한 화면에 쭉 보여 준다(양념통만 접어 둔다) ----
  function shelves() {
    return Object.keys(D.categories).map(function (c) { return { name: c, items: D.categories[c] }; });
  }

  function tile(n, extra) {
    var b = el("button", "tile" + (have[n] ? " on" : "") + (extra || ""));
    b.type = "button";
    b.setAttribute("aria-pressed", have[n] ? "true" : "false");
    b.appendChild(el("span", "em", D.emoji[n] || "•"));
    b.appendChild(el("span", "tn", n));
    b.addEventListener("click", function () { toggle(n); });
    return b;
  }

  function buildCats() {
    $cats.textContent = "";
    // 맨 위 한 줄 안내: 양념은 대부분 집에 있으니 요약만 보여 주고, 누르면 양념통이 열린다
    var mine = PANTRY.filter(function (n) { return have[n]; });
    var det = el("details", "pantry-line");
    det.open = pantryOpen;
    det.addEventListener("toggle", function () { pantryOpen = det.open; });
    var sm = el("summary", "pl-sum");
    sm.appendChild(el("span", "pl-em", "🧂"));
    sm.appendChild(el("span", "pl-txt", mine.length ? "기본 양념 " + mine.length + "개 있음 (" + mine.slice(0, 3).join("·") + (mine.length > 3 ? " 외" : "") + ")" : "집에 있는 양념을 알려 주세요"));
    sm.appendChild(el("span", "pl-btn", "바꾸기"));
    det.appendChild(sm);
    det.appendChild(el("p", "shelf-note", "집에 있는 양념을 눌러 주세요. 없는 양념이 필요한 요리는 '양념만 더 필요해요'로 따로 보여 드려요."));
    var pbox = el("div", "tiles");
    PANTRY.forEach(function (n) { pbox.appendChild(tile(n, " staple")); });
    det.appendChild(pbox);
    $cats.appendChild(det);
    var redo = recent.filter(function (n) { return !have[n]; }).slice(0, 8);
    if (redo.length) {   // 자주 쓰는 재료는 맨 위에서 한 번에 다시 담는다
      var rr = el("section", "aisle recent");
      var rh = el("h2", "aisle-h", "최근에 고른 재료");
      var all = el("button", "linkbtn", "모두 담기");
      all.type = "button";
      all.addEventListener("click", function () { redo.forEach(function (n) { have[n] = true; }); focus = ""; persist(); render(); });
      rh.appendChild(all);
      var wipe = el("button", "linkbtn linkbtn2", "모두 비우기");
      wipe.type = "button";
      wipe.setAttribute("aria-label", "최근에 고른 재료 기록 모두 지우기");
      wipe.addEventListener("click", function () { recent = []; persist(); buildCats(); });
      rh.appendChild(wipe);
      rr.appendChild(rh);
      var rbox = el("div", "tiles");
      redo.forEach(function (n) {
        var cell = el("div", "rtile");   // 타일 하나마다 ✕ 를 달아 기록에서 하나씩 지운다
        cell.appendChild(tile(n));
        var x = el("button", "rx", "✕");
        x.type = "button";
        x.setAttribute("aria-label", n + " 기록에서 지우기");
        x.addEventListener("click", function (e) { e.stopPropagation(); recent = recent.filter(function (m) { return m !== n; }); persist(); buildCats(); });
        cell.appendChild(x);
        rbox.appendChild(cell);
      });
      rr.appendChild(rbox);
      $cats.appendChild(rr);
    }
    shelves().forEach(function (sh, idx) {
      var picked = sh.items.filter(function (n) { return have[n]; }).length;
      var sec = el("section", "aisle");
      var h = el("h2", "aisle-h");
      h.appendChild(el("span", "no", String(idx + 1)));
      h.appendChild(document.createTextNode(sh.name));
      if (picked) { h.appendChild(el("small", "cnt", picked + "개 선택")); }
      sec.appendChild(h);
      // 자주 쓰이는 재료 위주로 먼저 보여 주고, 나머지는 '더 보기'로 펼친다(고른 재료는 늘 보인다)
      var sorted = sh.items.slice().sort(function (a, b) { return (usage[b] || 0) - (usage[a] || 0); });
      var open = !!moreOpen[sh.name];
      var shown = sorted.filter(function (n, i) { return open || i < TOP || have[n]; });
      var hidden = sh.items.length - shown.length;
      var box = el("div", "tiles");
      shown.forEach(function (n) { box.appendChild(tile(n)); });
      sec.appendChild(box);
      if (hidden > 0 || (open && sh.items.length > TOP)) {
        var more = el("button", "morelink", open ? "접기 ▴" : "다른 재료 " + hidden + "개 더 보기 ▾");
        more.type = "button";
        more.addEventListener("click", function () { moreOpen[sh.name] = !open; buildCats(); });
        sec.appendChild(more);
      }
      $cats.appendChild(sec);
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
    var need = r.ingredients.filter(function (i) { return !i.opt && i.n !== "물"; });
    var missing = need.filter(function (i) { return !have[i.n]; });
    var mf = missing.filter(function (i) { return !STAPLES[i.n]; });   // 부족한 재료(채소·고기·면 등)
    var ms = missing.filter(function (i) { return STAPLES[i.n]; });    // 부족한 양념(없어도 요리는 보여 주고, 따로 알려 준다)
    var used = r.ingredients.filter(function (i) { return have[i.n] && !STAPLES[i.n]; }).length;
    return { r: r, mf: mf, ms: ms, used: used };
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

  function card(ev, pick) {
    var a = el("div", "card" + (pick ? " pick" : ""));
    a.appendChild(thumb(ev.r));
    var body = el("div", "body");
    if (pick) { body.appendChild(el("span", "pickbadge", "방금 고른 요리")); }
    var h3 = el("h3");
    var title = el("a", null, ev.r.name);
    title.href = "recipes/" + ev.r.slug + ".html";
    h3.appendChild(title);
    body.appendChild(h3);
    body.appendChild(el("div", "meta", ev.r.minutes + "분 · 1인분 " + ev.r.kcal + "kcal · 약 " + ev.r.cost.toLocaleString("ko-KR") + "원"));
    var lack = ev.mf.concat(ev.ms);
    if (lack.length) {
      var row = el("div", "miss-row");
      var links = [];
      ev.mf.forEach(function (m) { row.appendChild(el("span", "chip miss", m.n + " 없음")); });
      ev.ms.forEach(function (m) { row.appendChild(el("span", "chip miss soft", m.n + " 없음")); });
      lack.forEach(function (m) {
        if (!D.affiliate[m.n]) { return; }
        var link = { n: (D.labels && D.labels[m.n]) || m.n, url: D.affiliate[m.n] };
        ((D.variants && D.variants[m.n]) || []).some(function (v) {
          if (new RegExp(v.when).test(ev.r.name)) { link = { n: v.label, url: v.url }; return true; }
          return false;
        });
        links.push(link);
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

  function group(title, cls, list) {
    if (!list.length) { return; }
    var h = el("div", "group-title");
    h.appendChild(document.createTextNode(title + " "));
    h.appendChild(el("span", "badge " + cls, list.length + "개"));
    $res.appendChild(h);
    var box = el("div", "glist");
    $res.appendChild(box);
    var shown = 0;
    var more = el("button", "btn ghost morebtn");
    more.type = "button";
    function fill() {
      list.slice(shown, shown + 12).forEach(function (ev) { box.appendChild(card(ev)); });
      shown = Math.min(list.length, shown + 12);
      if (shown >= list.length) { more.remove(); } else { more.textContent = "더 보기 (" + (list.length - shown) + "개)"; }
    }
    more.addEventListener("click", fill);
    fill();
    if (shown < list.length) { $res.appendChild(more); }
  }

  var rafId = 0;
  function render() {
    if (rafId) { return; }
    rafId = setTimeout(function () { rafId = 0; renderNow(); }, 0);
  }
  function renderNow() {
    buildQuick();
    buildCats();
    buildSelected();
    $res.textContent = "";
    var count = foods().length;
    if (!count) {
      $bar.hidden = true;
      var empty = el("div", "empty withmascot");
      var pic = el("img", "mascot");
      pic.src = "assets/mascot/open.png"; pic.alt = ""; pic.width = 132; pic.height = 147; pic.loading = "lazy";
      empty.appendChild(pic);
      empty.appendChild(el("p", null, "재료를 고르면 만들 수 있는 요리가 여기에 나와요."));
      $res.appendChild(empty);
      return;
    }
    var evs = D.recipes.filter(function (r) { return !r.pet; }).map(evaluate).filter(function (e) { return e.used >= 1; });
    function sortFn(a, b) { return b.used - a.used || a.ms.length - b.ms.length || a.r.minutes - b.r.minutes; }
    var picked = focus ? evs.filter(function (e) { return e.r.slug === focus; })[0] : null;
    var rest = picked ? evs.filter(function (e) { return e !== picked; }) : evs;
    var zero = rest.filter(function (e) { return !e.mf.length && !e.ms.length; }).sort(sortFn);
    var stap = rest.filter(function (e) { return !e.mf.length && e.ms.length; }).sort(sortFn);
    var one = rest.filter(function (e) { return e.mf.length === 1; }).sort(sortFn);
    var two = rest.filter(function (e) { return e.mf.length === 2; }).sort(sortFn);
    var nowCount = zero.length + (picked && !picked.mf.length && !picked.ms.length ? 1 : 0);
    $barText.textContent = "재료 " + count + "개 · 바로 " + nowCount + "개 · 양념만 더 " + stap.length + "개 · 1가지만 더 " + one.length + "개";
    $bar.hidden = false;
    if (picked) { $res.appendChild(card(picked, true)); }
    if (!picked && !zero.length && !stap.length && !one.length && !two.length) {
      $res.appendChild(el("div", "empty", "딱 맞는 요리를 못 찾았어요. 재료나 양념을 한두 개 더 골라 보세요."));
      return;
    }
    group("지금 바로 만들 수 있어요", "", zero);
    group("재료는 다 있어요 · 양념만 더 필요해요", "one", stap);
    group("재료 1가지만 더 있으면", "one", one);
    group("재료 2가지가 더 필요해요", "one", two);
  }

  function suggestFor(text) {
    var k = text.replace(/\s/g, "").toLowerCase();
    var out = [];
    if (!k) { return out; }
    Object.keys(D.aliases).concat(PANTRY).forEach(function (c) {
      var hit = c.indexOf(k) > -1 || (D.aliases[c] || []).some(function (a) { return a.replace(/\s/g, "").toLowerCase().indexOf(k) > -1; });
      if (hit && out.indexOf(c) < 0 && !have[c]) { out.push(c); }
    });
    return out.slice(0, 6);
  }

  // ---- 요리 이름으로도 찾는다(초성도 됨). 누르면 그 요리의 재료가 담기고 결과 맨 위에 나온다 ----
  function findRecipes(text, limit) {
    var k = text.replace(/\s/g, "").toLowerCase();
    if (!k) { return []; }
    var cons = /^[ㄱ-ㅎ]+$/.test(k);
    if (cons) { k = k.replace(/ㄲ/g, "ㄱ").replace(/ㄸ/g, "ㄷ").replace(/ㅃ/g, "ㅂ").replace(/ㅆ/g, "ㅅ").replace(/ㅉ/g, "ㅈ"); }
    var hits = D.recipes.filter(function (r) { return cons ? (r.ini || "").indexOf(k) > -1 : r.name.replace(/\s/g, "").toLowerCase().indexOf(k) > -1; });
    hits.sort(function (a, b) {
      var ea = a.name === text ? 0 : 1, eb = b.name === text ? 0 : 1;
      var sa = a.name.indexOf(text) === 0 ? 0 : 1, sb = b.name.indexOf(text) === 0 ? 0 : 1;
      return (ea - eb) || (sa - sb) || (a.name.length - b.name.length);
    });
    return hits.slice(0, limit || 5);
  }
  function pickRecipe(r) {
    if (r.pet) { location.href = "recipes/" + r.slug + ".html"; return; }   // 반려동물·유아식은 사람 재료 선택 결과에 섞지 않고 레시피로 바로 간다
    recipeItems(r).forEach(function (n) { have[n] = true; markRecent(n); });
    focus = r.slug;
    $q.value = ""; $sug.textContent = "";
    persist(); renderNow();
    $res.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function showSuggest() {
    $sug.textContent = "";
    var last = $q.value.split(/[,\s]+/).filter(Boolean).pop() || "";
    suggestFor(last).forEach(function (c) {
      var b = el("button", "sugchip", (D.emoji[c] || "") + " " + c);
      b.type = "button";
      b.addEventListener("click", function () {
        have[c] = true; markRecent(c); focus = "";
        var parts = $q.value.split(/[,\s]+/).filter(Boolean); parts.pop();
        $q.value = parts.join(" ");
        persist(); render(); showSuggest(); $q.focus();
      });
      $sug.appendChild(b);
    });
    findRecipes(last, 5).forEach(function (r) {
      var b = el("button", "sugchip rec", "🍳 " + r.name);
      b.type = "button";
      b.title = r.pet ? "레시피 보기" : "이 요리 재료 담기";
      b.addEventListener("click", function () { pickRecipe(r); });
      $sug.appendChild(b);
    });
  }
  function addFromText() {
    var raw = $q.value.split(/[,\s]+/).filter(Boolean);
    var unknown = [];
    var picked = null;
    raw.forEach(function (t) {
      var c = resolve(t);
      if (c) { have[c] = true; markRecent(c); return; }
      var rs = findRecipes(t, 1);
      if (rs.length) { picked = rs[0]; return; }
      unknown.push(t);
    });
    $q.value = unknown.join(" ");
    $sug.textContent = "";
    if (picked) {
      if (picked.pet) { persist(); location.href = "recipes/" + picked.slug + ".html"; return; }
      recipeItems(picked).forEach(function (n) { have[n] = true; markRecent(n); });
      focus = picked.slug;
    } else { focus = ""; }
    persist();
    renderNow();
    if (picked) { $res.scrollIntoView({ behavior: "smooth", block: "start" }); }
    if (unknown.length) { $sug.appendChild(el("span", "sugnote", "아직 모르는 재료·요리예요: " + unknown.join(", "))); }
  }

  document.getElementById("add").addEventListener("click", addFromText);
  $q.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addFromText(); } });
  $q.addEventListener("input", showSuggest);
  // 모두 지우기: 재료만 지우고, 고른 양념은 그대로 둔다
  function clearFoods() {
    Object.keys(have).forEach(function (n) { if (!STAPLES[n]) { delete have[n]; } });
    undo = {}; focus = ""; $q.value = ""; $sug.textContent = ""; persist(); render();
  }
  document.getElementById("clear").addEventListener("click", clearFoods);
  document.getElementById("clear2").addEventListener("click", clearFoods);
  document.getElementById("barGo").addEventListener("click", function () { $res.scrollIntoView({ behavior: "smooth", block: "start" }); });

  // 결과가 화면에 보이면 아래 고정 바는 숨긴다
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      document.body.classList.toggle("res-visible", entries[0].isIntersecting);
    }, { threshold: 0.05 }).observe($res);
  }
  renderNow();

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

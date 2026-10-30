(function () {
  var D = window.FRIDGE;
  var U = D.ui || {};
  var EN = !!D.lang && D.lang !== "ko";   // 영어판: 여러 단어 재료(soy sauce)와 쉼표 구분 입력을 처리한다
  function L(k, v) { var s = U[k] != null ? U[k] : k; if (v) { Object.keys(v).forEach(function (n) { s = s.split("{" + n + "}").join(v[n]); }); } return s; }
  function nm(n) { return (D.names && D.names[n]) || n; }   // 재료 표시 이름(한국어판은 그대로)
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
    var l = el("p", "qlabel", daily ? L("qDaily") : L("qMonthly"));
    var note = daily ? (t.date ? L("qNoteD", { d: t.date.slice(5).replace("-", "/") }) : L("qNote"))
                     : L("qNoteM");
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
    b.appendChild(el("span", "tn", nm(n)));
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
    var plist = mine.slice(0, 3).map(nm).join(L("sep")) + (mine.length > 3 ? L("pantryMore") : "");
    sm.appendChild(el("span", "pl-txt", mine.length ? L("pantryHave", { n: mine.length, list: plist }) : L("pantryNone")));
    sm.appendChild(el("span", "pl-btn", L("change")));
    det.appendChild(sm);
    det.appendChild(el("p", "shelf-note", L("shelfNote")));
    var acts = el("div", "pl-acts");   // 양념을 한 번에 비우거나 처음 상태로 되돌린다
    var wipeS = el("button", "linkbtn", L("wipeAll"));
    wipeS.type = "button";
    wipeS.addEventListener("click", function () { PANTRY.forEach(function (n) { delete have[n]; }); focus = ""; pantryOpen = true; persist(); render(); });
    var baseS = el("button", "linkbtn", L("baseSpice"));
    baseS.type = "button";
    baseS.addEventListener("click", function () { PANTRY.forEach(function (n) { delete have[n]; }); (D.stapleDefaults || []).forEach(function (n) { have[n] = true; }); focus = ""; pantryOpen = true; persist(); render(); });
    acts.appendChild(wipeS); acts.appendChild(baseS);
    det.appendChild(acts);
    var pbox = el("div", "tiles");
    PANTRY.forEach(function (n) { pbox.appendChild(tile(n, " staple")); });
    det.appendChild(pbox);
    $cats.appendChild(det);
    var redo = recent.filter(function (n) { return !have[n]; }).slice(0, 8);
    if (redo.length) {   // 자주 쓰는 재료는 맨 위에서 한 번에 다시 담는다
      var rr = el("section", "aisle recent");
      var rh = el("h2", "aisle-h", L("recentH"));
      var all = el("button", "linkbtn", L("addAll"));
      all.type = "button";
      all.addEventListener("click", function () { redo.forEach(function (n) { have[n] = true; }); focus = ""; persist(); render(); });
      rh.appendChild(all);
      var wipe = el("button", "linkbtn linkbtn2", L("wipeAll"));
      wipe.type = "button";
      wipe.setAttribute("aria-label", L("recentWipeAria"));
      wipe.addEventListener("click", function () { recent = []; persist(); buildCats(); });
      rh.appendChild(wipe);
      rr.appendChild(rh);
      var rbox = el("div", "tiles");
      redo.forEach(function (n) {
        var cell = el("div", "rtile");   // 타일 하나마다 ✕ 를 달아 기록에서 하나씩 지운다
        cell.appendChild(tile(n));
        var x = el("button", "rx", "✕");
        x.type = "button";
        x.setAttribute("aria-label", L("removeRecentAria", { n: nm(n) }));
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
      if (picked) { h.appendChild(el("small", "cnt", L("nSelected", { n: picked }))); }
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
        var more = el("button", "morelink", open ? L("less") : L("more", { n: hidden }));
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
    if (!names.length) { $sel.appendChild(el("span", "sel-empty", L("selEmpty"))); return; }
    names.forEach(function (n) {
      var b = el("button", "chip on", (D.emoji[n] || "") + " " + nm(n) + " ✕");
      b.type = "button";
      b.setAttribute("aria-label", L("removeAria", { n: nm(n) }));
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
    if (pick) { body.appendChild(el("span", "pickbadge", L("justPicked"))); }
    var h3 = el("h3");
    var title = el("a", null, ev.r.name);
    title.href = "recipes/" + ev.r.slug + ".html";
    h3.appendChild(title);
    body.appendChild(h3);
    body.appendChild(el("div", "meta", L("meta", { m: ev.r.minutes, k: ev.r.kcal, won: L("won", { c: ev.r.cost.toLocaleString(D.loc || "ko-KR") }) })));
    var lack = ev.mf.concat(ev.ms);
    if (lack.length) {
      var row = el("div", "miss-row");
      var links = [];
      ev.mf.forEach(function (m) { row.appendChild(el("span", "chip miss", L("lack", { n: nm(m.n) }))); });
      ev.ms.forEach(function (m) { row.appendChild(el("span", "chip miss soft", L("lack", { n: nm(m.n) }))); });
      lack.forEach(function (m) {
        if (!D.affiliate[m.n]) { return; }
        var link = { n: (D.labels && D.labels[m.n]) || nm(m.n), url: D.affiliate[m.n] };
        ((D.variants && D.variants[m.n]) || []).some(function (v) {
          if (new RegExp(v.when).test(ev.r.name)) { link = { n: v.label, url: v.url }; return true; }
          return false;
        });
        links.push(link);
      });
      body.appendChild(row);
      if (links.length === 1) {   // 링크가 하나면 바로 연결, 여럿이면 눌러서 펼친다
        body.appendChild(buyLink(links[0].url, L("buyMissing")));
      } else if (links.length > 1) {
        var det = el("details", "buylist");
        det.appendChild(el("summary", "buy", L("buyMissingMore")));
        var inner = el("div", "buyinner");
        links.forEach(function (l) { inner.appendChild(buyLink(l.url, L("buyOne", { n: l.n }))); });
        det.appendChild(inner);
        body.appendChild(det);
      }
    } else {
      body.appendChild(el("span", "chip have", L("allHave")));
    }
    a.appendChild(body);
    return a;
  }

  function group(title, cls, list) {
    if (!list.length) { return; }
    var h = el("div", "group-title");
    h.appendChild(document.createTextNode(title + " "));
    h.appendChild(el("span", "badge " + cls, L("nItems", { n: list.length })));
    $res.appendChild(h);
    var box = el("div", "glist");
    $res.appendChild(box);
    var shown = 0;
    var more = el("button", "btn ghost morebtn");
    more.type = "button";
    function fill() {
      list.slice(shown, shown + 12).forEach(function (ev) { box.appendChild(card(ev)); });
      shown = Math.min(list.length, shown + 12);
      if (shown >= list.length) { more.remove(); } else { more.textContent = L("moreN", { n: list.length - shown }); }
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
      pic.src = (D.asset || "") + "assets/mascot/open.png"; pic.alt = ""; pic.width = 132; pic.height = 147; pic.loading = "lazy";
      empty.appendChild(pic);
      empty.appendChild(el("p", null, L("emptyHint")));
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
    $barText.textContent = L("barText", { a: count, b: nowCount, c: stap.length, d: one.length });
    $bar.hidden = false;
    if (picked) { $res.appendChild(card(picked, true)); }
    if (!picked && !zero.length && !stap.length && !one.length && !two.length) {
      $res.appendChild(el("div", "empty", L("nothing")));
      return;
    }
    group(L("g0"), "", zero);
    group(L("g1"), "one", stap);
    group(L("g2"), "one", one);
    group(L("g3"), "one", two);
  }

  // 한글을 쓰는 도중(예: '두부조리'까지만 친 상태)에도 '두부조림'을 찾도록, 글자를 자음·모음으로 풀어서 비교한다
  var jcache = {};
  function jn(t) {
    var v = jcache[t];
    if (v === undefined) { v = t.replace(/\s/g, "").toLowerCase().normalize("NFKD"); jcache[t] = v; }
    return v;
  }
  function suggestFor(text) {
    var k = jn(text);
    var out = [];
    if (!k) { return out; }
    Object.keys(D.aliases).concat(PANTRY).forEach(function (c) {
      var hit = jn(c).indexOf(k) > -1 || (D.aliases[c] || []).some(function (a) { return jn(a).indexOf(k) > -1; });
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
    var jk = jn(text);
    var hits = D.recipes.filter(function (r) { return cons ? (r.ini || "").indexOf(k) > -1 : (jn(r.name).indexOf(jk) > -1 || (r.ko && jn(r.ko).indexOf(jk) > -1)); });
    hits.sort(function (a, b) {
      var ea = a.name === text ? 0 : 1, eb = b.name === text ? 0 : 1;
      var sa = jn(a.name).indexOf(jk) === 0 ? 0 : 1, sb = jn(b.name).indexOf(jk) === 0 ? 0 : 1;
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

  // 영어판: 쉼표로 나눈 마지막 덩어리에서 뒤쪽 1~3단어 중 추천이 나오는 가장 긴 것을 입력 중인 낱말로 본다("soy sa" → soy sauce)
  function lastQuery() {
    var v = $q.value;
    if (!EN) { return v.split(/[,\s]+/).filter(Boolean).pop() || ""; }
    var words = (v.match(/[^,;\n]*$/)[0] || "").trim().split(/\s+/).filter(Boolean);
    for (var n = Math.min(3, words.length); n >= 1; n--) {
      var q = words.slice(-n).join(" ");
      if (suggestFor(q).length || findRecipes(q, 1).length) { return q; }
    }
    return words.slice(-1).join(" ");
  }
  function dropTail(q) {
    if (!EN) { var parts = $q.value.split(/[,\s]+/).filter(Boolean); parts.pop(); return parts.join(" "); }
    var i = $q.value.toLowerCase().lastIndexOf(q.toLowerCase());
    return (i < 0 ? "" : $q.value.slice(0, i)).replace(/[\s,;]+$/, "");
  }
  function showSuggest() {
    $sug.textContent = "";
    var last = lastQuery();
    suggestFor(last).forEach(function (c) {
      var b = el("button", "sugchip", (D.emoji[c] || "") + " " + nm(c));
      b.type = "button";
      b.addEventListener("click", function () {
        have[c] = true; markRecent(c); focus = "";
        $q.value = dropTail(last);
        persist(); render(); showSuggest(); $q.focus();
      });
      $sug.appendChild(b);
    });
    findRecipes(last, 5).forEach(function (r) {
      var b = el("button", "sugchip rec", "🍳 " + r.name);
      b.type = "button";
      b.title = r.pet ? L("viewRecipe") : L("addIngs");
      b.addEventListener("click", function () { pickRecipe(r); });
      $sug.appendChild(b);
    });
    revealSuggest();
  }
  // 폰에서 키보드가 올라오면 아래쪽 추천이 가려지므로, 입력창을 화면 맨 위(고정 바 아래)로 올려 추천이 키보드 위에 보이게 한다
  function revealSuggest() {
    if (!$sug.children.length || document.activeElement !== $q || !window.matchMedia("(max-width: 760px)").matches) { return; }
    var box = $q.parentNode;
    var top = box.getBoundingClientRect().top;
    if (top > 90 || top < 50) { box.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }
  function exactAlias(p) { return alias[p.replace(/\s/g, "").toLowerCase()] || null; }
  function addFromText() {
    var unknown = [];
    var picked = null;
    if (EN) {   // 영어: "soy sauce, tofu"처럼 쉼표로 나누고, 덩어리 안에서는 긴 재료 이름부터 맞춰 본다
      $q.value.split(/[,;\n]+/).map(function (s) { return s.trim(); }).filter(Boolean).forEach(function (ch) {
        var rs0 = findRecipes(ch, 1);
        if (rs0.length && jn(rs0[0].name) === jn(ch)) { picked = rs0[0]; return; }   // 요리 이름을 그대로 쳤다
        var words = ch.split(/\s+/);
        var i = 0;
        while (i < words.length) {
          var hit = false;
          for (var j = Math.min(words.length, i + 4); j > i; j--) {
            var c2 = j - i > 1 ? exactAlias(words.slice(i, j).join(" ")) : resolve(words[i]);
            if (c2) { have[c2] = true; markRecent(c2); i = j; hit = true; break; }
          }
          if (!hit) {
            var r1 = findRecipes(words[i], 1);
            if (r1.length) { picked = r1[0]; } else { unknown.push(words[i]); }
            i++;
          }
        }
      });
    } else {
    $q.value.split(/[,\s]+/).filter(Boolean).forEach(function (t) {
      var c = resolve(t);
      if (c) { have[c] = true; markRecent(c); return; }
      var rs = findRecipes(t, 1);
      if (rs.length) { picked = rs[0]; return; }
      unknown.push(t);
    });
    }
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
    if (unknown.length) { $sug.appendChild(el("span", "sugnote", L("unknown", { list: unknown.join(", ") }))); }
  }

  document.getElementById("add").addEventListener("click", addFromText);
  $q.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addFromText(); } });
  $q.addEventListener("input", showSuggest);
  $q.addEventListener("focus", function () { setTimeout(revealSuggest, 300); });
  if (window.visualViewport) { window.visualViewport.addEventListener("resize", function () { setTimeout(revealSuggest, 100); }); }
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
    fetch((D.asset || "") + "trending.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
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

(function () {
  // 오늘의 추천식단: 날짜·요일·날씨·계절·명절·먹는 사람 수를 함께 따져 아침·점심·저녁(+곁들임)을 고르고 목표 열량에 맞춘다.
  // 같은 날·같은 지역·같은 식단 종류면 누구에게나 같은 식단이 나온다(날짜로 정한 무작위 씨앗).
  var M = window.MEAL;
  var U = M.ui;
  var items = M.items;
  var NAMES = M.names || {};
  var SLOTS = ["b", "l", "d"];
  var SLOT_ICON = { b: "🌅", l: "☀️", d: "🌙" };
  var SLOT_KEY = { b: "mealB", l: "mealL", d: "mealD" };

  function L(k, v) { var s = U[k] != null ? U[k] : k; if (v) { Object.keys(v).forEach(function (n) { s = s.split("{" + n + "}").join(v[n]); }); } return s; }
  function nm(n) { return NAMES[n] || n; }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) { e.className = cls; } if (text != null) { e.textContent = text; } return e; }
  function fmt(n) { return Number(n).toLocaleString(M.loc); }
  function has(it, x) { return (it.tg || "").indexOf(x) > -1; }

  // ---- 저장된 선택 ----
  var state = { people: 2, mode: "normal", city: 0, span: "day", meals: "all" };
  try {
    var sv = JSON.parse(localStorage.getItem("fridge_meal") || "null");
    if (sv && sv.people >= 1 && sv.people <= 5) { state.people = sv.people; }
    if (sv && (sv.mode === "normal" || sv.mode === "diet")) { state.mode = sv.mode; }
    if (sv && sv.city >= 0 && sv.city < M.cities.length) { state.city = sv.city; }
    if (sv && sv.span === "week") { state.span = "week"; }
    if (sv && sv.meals === "d") { state.meals = "d"; }
  } catch (e) {}
  if (location.hash === "#week") { state.span = "week"; }
  function save() { try { localStorage.setItem("fridge_meal", JSON.stringify(state)); } catch (e) {} }

  // ---- 날짜로 정하는 무작위 ----
  function seedOf(str) {
    var h = 1779033703 ^ str.length;
    for (var i = 0; i < str.length; i++) { h = Math.imul(h ^ str.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
    h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909);
    return (h ^ (h >>> 16)) >>> 0;
  }
  function rng(a) { return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; var t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  var now = new Date();
  var dateKey = now.getFullYear() + "-" + (now.getMonth() + 1) + "-" + now.getDate();
  var offset = 0;
  var hour = now.getHours();
  var NOW_SLOT = hour < 10 ? "b" : (hour < 15 ? "l" : "d");

  function riceOf() { return M.rice[state.mode]; }
  function kcOf(it) { return it.k + (it.r ? riceOf().k : 0); }
  function targets() { return M.target[state.mode]; }
  function dayTarget() { var t = targets(); return t.b + t.l + t.d; }

  // ---- 날씨 ----
  var CTX = null;
  function weatherIcon(w) {
    if (!w) { return "🍽️"; }
    var c = w.code;
    if (c === 0) { return "☀️"; }
    if (c <= 2) { return "🌤️"; }
    if (c === 3) { return "☁️"; }
    if (c === 45 || c === 48) { return "🌫️"; }
    if ((c >= 71 && c <= 77) || c === 85 || c === 86) { return "❄️"; }
    if (c >= 95) { return "⛈️"; }
    return "🌧️";
  }
  // 기상청 예보 요약(weather.json, 매일 갱신)에서 지역·오늘 날짜의 날씨를 읽는다. 파일이 없거나 오늘 날짜가 없으면 null(계절·요일로 추천)
  var wxFile = null;
  function wxFor(date) {
    var key = date.getFullYear() + ("0" + (date.getMonth() + 1)).slice(-2) + ("0" + date.getDate()).slice(-2);
    var c = wxFile && wxFile.cities && wxFile.cities[M.cities[state.city].k];
    var w = c && c[key];
    if (!w) { return null; }
    return { tmax: w.tmax, tmin: w.tmin, fmax: w.tmax, pop: w.pop, rain: w.rain, snow: w.snow, code: w.code };
  }
  function fetchWeather(cb) {
    if (wxFile) { cb(wxFor(now)); return; }
    var done = false;
    function fin(j) { if (done) { return; } done = true; wxFile = j || {}; cb(wxFor(now)); }
    setTimeout(function () { fin(null); }, 4000);
    try {
      fetch((M.asset || "") + "weather.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(fin).catch(function () { fin(null); });
    } catch (e) { fin(null); }
  }
  function buildCtx(w, date) {
    var day = date || now, m = day.getMonth() + 1, d = day.getDate(), dow = day.getDay();
    var c = {
      m: m, d: d, dow: dow, w: w, workday: dow >= 1 && dow <= 5, monday: dow === 1, friday: dow === 5, weekend: dow === 0 || dow === 6,
      summer: m >= 6 && m <= 8, winter: m === 12 || m <= 2,
      hol: { y: m === 1 && d <= 3, z: m === 12 && d >= 20 && d <= 24, b: (m === 7 && d >= 10) || (m === 8 && d <= 20), s: m === 3 && d === 3, r: m === 11 && d === 11 },
      hot: false, warm: false, cold: false, chilly: false, rain: false, snow: false, tmax: null, tmin: null
    };
    if (w) {
      var t = (w.tmax + (w.fmax != null ? w.fmax : w.tmax)) / 2;   // 체감온도를 함께 본다
      c.tmax = t; c.tmin = w.tmin;
      c.hot = t >= 28; c.warm = t >= 24 && t < 28; c.cold = t <= 4; c.chilly = t > 4 && t <= 11;
      c.snow = (w.code >= 71 && w.code <= 77) || w.code === 85 || w.code === 86 || w.snow > 0.3;
      c.rain = !c.snow && ((w.code >= 51 && w.code <= 67) || (w.code >= 80 && w.code <= 82) || w.code >= 95 || (w.pop >= 60 && w.rain >= 1));
    } else {   // 날씨를 못 받으면 계절로 짐작한다
      c.warm = c.summer; c.chilly = c.winter;
    }
    return c;
  }
  // 이 요리가 오늘 상황에 얼마나 어울리나(클수록 좋다)
  function fit(it, slot) {
    var c = CTX, f = 0;
    if (c.hot) { if (has(it, "c")) { f += 14; } if (has(it, "h") && !has(it, "b")) { f -= 12; } if (it.k > 650) { f -= 4; } }
    else if (c.warm) { if (has(it, "c")) { f += 7; } if (has(it, "h") && !has(it, "b")) { f -= 5; } }
    if (c.cold) { if (has(it, "h")) { f += 12; } if (has(it, "c")) { f -= 14; } }
    else if (c.chilly) { if (has(it, "h")) { f += 6; } if (has(it, "c")) { f -= 6; } }
    if (c.rain || c.snow) { if (has(it, "j") && slot !== "b") { f += 12; } if (has(it, "n")) { f += 9; } if (has(it, "h")) { f += 3; } }
    if (c.snow && has(it, "h")) { f += 5; }
    if (slot === "b" && c.tmin !== null && c.tmin <= 0 && has(it, "h")) { f += 8; }
    if (c.workday) {
      if (slot === "b") { f += it.m <= 15 ? 7 : (it.m > 30 ? -7 : 0); }
      else if (slot === "d") { f += it.m <= 30 ? 3 : (it.m > 45 ? -5 : 0); }
      else { f += it.m <= 25 ? 2 : 0; }
    } else if (slot !== "b" && it.m >= 35) { f += 4; }
    if (c.monday && it.k <= 500 && slot !== "b") { f += 2; }
    if (c.friday && slot === "d" && (has(it, "j") || has(it, "g"))) { f += 5; }
    if (c.dow === 0 && slot === "d" && has(it, "g")) { f += 3; }
    if (state.people >= 3 && slot !== "b") { f += has(it, "g") ? 6 : -2; }
    if (state.people === 1 && slot !== "b" && has(it, "g")) { f -= 2; }
    if (c.hol.y && has(it, "y")) { f += 40; }
    if (c.hol.z && has(it, "z")) { f += 40; }
    if (c.hol.b && has(it, "b")) { f += 30; }
    if (c.hol.s && slot === "d" && has(it, "s")) { f += 35; }
    if (c.hol.r && has(it, "r")) { f += 25; }
    if (c.summer && has(it, "c")) { f += 3; }
    if (c.winter && has(it, "h")) { f += 3; }
    return f;
  }

  // ---- 식단 고르기 ----
  // 일주일 식단의 점심·저녁 주메뉴는 끼니가 되는 종류로만 고른다(와플·전·무침이 저녁이 되지 않게). 영어판은 요리 이름이 달라 종류(t)로 먼저 거른다.
  var WEEK_MAIN = /^(면·국수|구이·튀김|볶음|조림·찜|밥|탕|찌개·전골|덮밥|볶음밥|국밥|비빔밥|김밥·주먹밥·초밥|국·수프)$/;
  var WEEK_MAIN_NAME = /카레|curry|육개장|닭개장|샤브샤브/i;
  var weekBuilding = false;
  function poolFor(slot) {
    var t = targets()[slot];
    var lo = 0.55, hi = 1.35;
    var out = [];
    for (var pass = 0; pass < 2 && out.length < 8; pass++) {
      out = items.filter(function (it) { var k = kcOf(it); return it.sl.indexOf(slot) > -1 && k >= t * lo && k <= t * hi; });
      lo = 0.3; hi = 2;
    }
    if (weekBuilding && slot !== "b") { out = out.filter(function (it) { return WEEK_MAIN.test(it.t) || WEEK_MAIN_NAME.test(it.n); }); }
    return out;
  }
  function pick(rand, arr) { return arr[Math.floor(rand() * arr.length)]; }
  function sidesFor(remaining, rand, used) {
    var c = items.filter(function (it) { return it.sd && used.indexOf(it.s) < 0 && it.k <= remaining + 30 && it.k >= 20; });
    if (!c.length) { return null; }
    c.sort(function (a, b) { return Math.abs(a.k - remaining) - Math.abs(b.k - remaining); });
    return c[Math.floor(rand() * Math.min(3, c.length))];
  }
  function mealOf(main, slot, rand, used) {
    var side = null;
    var rem = targets()[slot] - kcOf(main);
    if (slot !== "b" && rem >= 70) { side = sidesFor(rem, rand, used.concat([main.s])); }
    return { main: main, side: side };
  }
  function mealKcal(m) { return kcOf(m.main) + (m.side ? m.side.k : 0); }
  function variety(plan) {
    var p = 0, mains = SLOTS.map(function (s) { return plan[s].main; });
    for (var i = 0; i < mains.length; i++) {
      if (state.mode === "diet" && !mains[i].dt) { p += 4; }
      for (var j = i + 1; j < mains.length; j++) {
        if (mains[i].t === mains[j].t) { p += 12; }
        if (mains[i].g.some(function (g) { return mains[j].g.indexOf(g) > -1; })) { p += 8; }
      }
    }
    return p;
  }
  function score(plan) {
    var t = targets(), tot = 0, s = 0, fits = 0;
    SLOTS.forEach(function (sl) { var k = mealKcal(plan[sl]); tot += k; s += Math.abs(k - t[sl]) / t[sl] * 60; fits += fit(plan[sl].main, sl) + (plan[sl].side ? fit(plan[sl].side, sl) * 0.3 : 0); });
    var na = totalsOf(plan).na;
    var naLimit = state.mode === "diet" ? 1900 : 2300;
    return s + Math.abs(tot - dayTarget()) / dayTarget() * 160 + Math.max(0, na - naLimit) / 40 + variety(plan) - fits;
  }
  function dayKcal(plan) { return totalsOf(plan).k; }
  function makePlan() {
    return searchPlan(rng(seedOf(dateKey + "|" + state.mode + "|" + state.city + "|" + offset)), 600, [], null);
  }
  function searchPlan(rand, tries_, taken, extra) {
    var pools = {};
    SLOTS.forEach(function (s) { pools[s] = poolFor(s); });
    if (!pools.b.length || !pools.l.length || !pools.d.length) { return null; }
    var best = null, bestScore = 1e9, anyBest = null, anyScore = 1e9;
    for (var n = 0; n < tries_; n++) {
      var used = taken.slice(), plan = {};
      var ok = true;
      for (var i = 0; i < SLOTS.length; i++) {
        var sl = SLOTS[i], main = null;
        for (var tries = 0; tries < 8; tries++) { var c = pick(rand, pools[sl]); if (used.indexOf(c.s) < 0) { main = c; break; } }
        if (!main) { ok = false; break; }
        plan[sl] = mealOf(main, sl, rand, used);
        used.push(main.s);
        if (plan[sl].side) { used.push(plan[sl].side.s); }
      }
      if (!ok) { continue; }
      var sc = score(plan) + (extra ? extra(plan) : 0);
      var inRange = Math.abs(dayKcal(plan) - dayTarget()) / dayTarget() <= 0.12;
      if (inRange && sc < bestScore) { bestScore = sc; best = plan; }
      if (sc < anyScore) { anyScore = sc; anyBest = plan; }
    }
    return best || anyBest;
  }
  var plan = null;
  var swaps = 0;
  function swapSlot(slot) {
    swaps++;
    var rand = rng(seedOf(dateKey + "|" + state.mode + "|" + state.city + "|" + offset + "|" + slot + "|" + swaps));
    var pool = poolFor(slot);
    var used = [];
    SLOTS.forEach(function (s) { if (s !== slot) { used.push(plan[s].main.s); if (plan[s].side) { used.push(plan[s].side.s); } } });
    var cur = plan[slot].main.s;
    var best = null, bestScore = 1e9;
    for (var n = 0; n < 120; n++) {
      var c = pick(rand, pool);
      if (!c || used.indexOf(c.s) > -1 || c.s === cur) { continue; }
      var trial = { b: plan.b, l: plan.l, d: plan.d };
      trial[slot] = mealOf(c, slot, rand, used);
      var sc = score(trial);
      if (sc < bestScore) { bestScore = sc; best = trial[slot]; }
    }
    if (best) { plan[slot] = best; }
  }

  // ---- 일주일 식단 ----
  // 한 번 짠 식단은 7일 동안 폰에 저장해 둔다(매일 바뀌면 장 본 재료와 어긋난다). 이미 산 재료를 쓰는 요리를 골라 장보기 가짓수를 줄인다.
  var week = null;
  var bySlug = {};
  items.forEach(function (it) { bySlug[it.s] = it; });
  function dayDate(i) { return new Date(week.start[0], week.start[1], week.start[2] + i); }
  function dishesOf(day) {
    var out = [];
    SLOTS.forEach(function (s) { if (day[s]) { out.push(day[s].main); if (day[s].side) { out.push(day[s].side); } } });
    return out;
  }
  function weekUsed(skip) {
    var used = [], have = {}, types = {};
    week.days.forEach(function (day, i) {
      if (i === skip || !day) { return; }
      dishesOf(day).forEach(function (it) { used.push(it.s); it.ing.forEach(function (x) { have[x[0]] = 1; }); });
      SLOTS.forEach(function (s) { if (day[s]) { types[day[s].main.t] = (types[day[s].main.t] || 0) + 1; } });
    });
    return { used: used, have: have, types: types };
  }
  function weekPenalty(day, u, prev) {
    var p = 0;
    dishesOf(day).forEach(function (it) { p += it.w / 100; it.ing.forEach(function (x) { p += u.have[x[0]] ? -3 : 6; }); });
    // 일주일 안에서 같은 종류의 주메뉴가 쌓일수록 피한다
    SLOTS.forEach(function (s) { if (day[s]) { p += (u.types[day[s].main.t] || 0) * 12; } });
    if (prev) {
      SLOTS.forEach(function (s) {
        if (!day[s] || !prev[s]) { return; }
        var a = day[s].main, b = prev[s].main;
        if (a.t === b.t) { p += 6; }
        if (a.g.some(function (g) { return b.g.indexOf(g) > -1; })) { p += 4; }
      });
    }
    return p;
  }
  function bestDinner(rand, u, prev) {
    var used = u.used, pool = poolFor("d").filter(function (it) { return used.indexOf(it.s) < 0; });
    var best = null, bestScore = 1e9, t = targets().d;
    for (var n = 0; n < 300 && pool.length; n++) {
      var main = pick(rand, pool), day = { d: mealOf(main, "d", rand, used) };
      var sc = Math.abs(mealKcal(day.d) - t) / t * 60 - fit(main, "d") + weekPenalty(day, u, prev);
      if (sc < bestScore) { bestScore = sc; best = day; }
    }
    return best;
  }
  function makeDay(i, salt) {
    var u = weekUsed(i), prev = week.days[i - 1], date = dayDate(i), keep = CTX;
    if (week.days[i]) { dishesOf(week.days[i]).forEach(function (it) { u.used.push(it.s); }); }
    CTX = buildCtx(wxFor(date), date);
    weekBuilding = true;
    var rand = rng(seedOf(dateKey + "|week|" + state.mode + "|" + state.meals + "|" + state.city + "|" + offset + "|" + i + "|" + salt));
    var day = state.meals === "d" ? bestDinner(rand, u, prev) : searchPlan(rand, 400, u.used, function (p) { return weekPenalty(p, u, prev); });
    CTX = keep;
    weekBuilding = false;
    return day;
  }
  function saveWeek() {
    var days = week.days.map(function (day) {
      var o = {};
      SLOTS.forEach(function (s) { if (day[s]) { o[s] = [day[s].main.s, day[s].side ? day[s].side.s : ""]; } });
      return o;
    });
    try { localStorage.setItem("fridge_week", JSON.stringify({ start: week.start, mode: state.mode, meals: state.meals, days: days })); } catch (e) {}
  }
  function readWeek() {
    try {
      var w = JSON.parse(localStorage.getItem("fridge_week") || "null");
      if (!w || w.mode !== state.mode || w.meals !== state.meals) { return null; }
      var age = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(w.start[0], w.start[1], w.start[2])) / 864e5);
      if (age < 0 || age > 6) { return null; }
      var ok = true;
      var days = w.days.map(function (d) {
        var o = {};
        SLOTS.forEach(function (s) { if (d[s]) { if (!bySlug[d[s][0]]) { ok = false; } o[s] = { main: bySlug[d[s][0]], side: bySlug[d[s][1]] || null }; } });
        return o;
      });
      return ok ? { start: w.start, days: days } : null;
    } catch (e) { return null; }
  }
  function makeWeek() {
    week = { start: [now.getFullYear(), now.getMonth(), now.getDate()], days: [] };
    for (var i = 0; i < 7; i++) {
      week.days[i] = makeDay(i, 0);
      if (!week.days[i]) { week = null; return; }
    }
    saveWeek();
  }
  function refresh() {
    if (state.span === "week") { week = readWeek(); if (!week) { makeWeek(); } } else { plan = makePlan(); }
    draw();
  }

  // ---- 계산 ----
  function riceAdd(it, key) { return it.r ? riceOf()[key] : 0; }
  function totalsOf(pl) {
    var t = { k: 0, c: 0, p: 0, f: 0, na: 0, w: 0 };
    SLOTS.forEach(function (s) {
      if (!pl[s]) { return; }
      [pl[s].main, pl[s].side].forEach(function (it) {
        if (!it) { return; }
        t.k += it.k + riceAdd(it, "k"); t.c += it.c + riceAdd(it, "c"); t.p += it.p + riceAdd(it, "p"); t.f += it.f + riceAdd(it, "f");
        t.na += it.na + riceAdd(it, "na"); t.w += it.w + riceAdd(it, "w");
      });
    });
    return t;
  }
  function totals() { return totalsOf(plan); }
  // 오늘 이렇게 고른 이유(실제로 식단에 반영된 것만)
  function reasons() {
    var c = CTX, out = [];
    var all = [];
    SLOTS.forEach(function (s) { all.push({ it: plan[s].main, s: s }); if (plan[s].side) { all.push({ it: plan[s].side, s: s }); } });
    function used(tag, slots) { return all.some(function (x) { return has(x.it, tag) && (!slots || slots.indexOf(x.s) > -1); }); }
    var t = c.tmax !== null ? Math.round(c.tmax) : "";
    if (c.hot && used("c")) { out.push(L("rHot", { t: t })); }
    else if (c.warm && c.w && used("c")) { out.push(L("rWarm", { t: t })); }
    if (c.cold && used("h")) { out.push(L("rCold", { t: t })); }
    else if (c.chilly && c.w && used("h")) { out.push(L("rChilly", { t: t })); }
    if (c.rain && (used("j") || used("n"))) { out.push(L("rRain")); }
    if (c.snow && used("h")) { out.push(L("rSnow")); }
    if (c.w && c.tmin <= 0 && has(plan.b.main, "h")) { out.push(L("rColdMorning", { t: Math.round(c.tmin) })); }
    if (c.workday && plan.b.main.m <= 15) { out.push(L("rBusy")); }
    if (c.monday && SLOTS.some(function (s) { return plan[s].main.k <= 500; })) { out.push(L("rMonday")); }
    if (c.friday && (has(plan.d.main, "j") || has(plan.d.main, "g"))) { out.push(L("rFriday")); }
    if (!c.workday && SLOTS.some(function (s) { return s !== "b" && plan[s].main.m >= 35; })) { out.push(L("rWeekend")); }
    if (state.people >= 3 && used("g", ["l", "d"])) { out.push(L("rFamily", { n: state.people })); }
    if (state.mode === "diet") { out.push(L("rDiet")); }
    if (c.hol.y && used("y")) { out.push(L("rYear")); }
    if (c.hol.z && used("z")) { out.push(L("rDongji")); }
    if (c.hol.b && used("b")) { out.push(L("rBok")); }
    if (c.hol.s && used("s")) { out.push(L("rSam")); }
    if (c.hol.r && used("r")) { out.push(L("rGarae")); }
    if (!c.w) { out.push(L("noWeather")); }
    return out;
  }

  // ---- 그리기 ----
  var $span = document.getElementById("mspan");
  var $meals = document.getElementById("mmeals");
  var $people = document.getElementById("mpeople");
  var $mode = document.getElementById("mmode");
  var $wx = document.getElementById("mwx");
  var $sum = document.getElementById("msummary");
  var $plan = document.getElementById("mplan");
  var $shop = document.getElementById("mshop");
  var $note = document.getElementById("mnote");
  var $other = document.getElementById("mother");

  function seg($box, defs, current, onPick) {
    $box.textContent = "";
    defs.forEach(function (d) {
      var b = el("button", "segb" + (d.v === current ? " on" : ""), d.t);
      b.type = "button";
      b.setAttribute("aria-pressed", d.v === current ? "true" : "false");
      b.addEventListener("click", function () { onPick(d.v); });
      $box.appendChild(b);
    });
  }
  function controls() {
    seg($span, [{ v: "day", t: L("spanDay") }, { v: "week", t: "📅 " + L("spanWeek") }], state.span, function (v) { state.span = v; save(); refresh(); });
    seg($people, [1, 2, 3, 4, 5].map(function (n) { return { v: n, t: L("p" + n) }; }), state.people, function (v) { state.people = v; save(); if (state.span === "day") { plan = makePlan(); } draw(); });
    seg($mode, [{ v: "normal", t: L("modeNormal") }, { v: "diet", t: "🥗 " + L("modeDiet") }], state.mode, function (v) { state.mode = v; offset = 0; swaps = 0; save(); refresh(); });
    $meals.hidden = state.span !== "week";
    seg($meals, [{ v: "all", t: L("mealsAll") }, { v: "d", t: L("mealsDinner") }], state.meals, function (v) { state.meals = v; offset = 0; swaps = 0; save(); refresh(); });
  }

  function dishLine(it, rice) {
    var a = el("a", "mdish");
    a.href = "recipes/" + it.s + ".html";
    var pic = el("span", "mpic");
    if (it.i) { var im = el("img"); im.src = it.i; im.alt = ""; im.loading = "lazy"; im.width = 72; im.height = 54; pic.appendChild(im); } else { pic.textContent = "🍽️"; }
    a.appendChild(pic);
    var box = el("span", "mtxt");
    box.appendChild(el("b", null, it.n));
    var meta = L("min", { m: it.m }) + " · " + L("perServ", { k: it.k + (rice && it.r ? riceOf().k : 0) }) + " · " + L("won", { c: fmt(it.w + (rice && it.r ? riceOf().w : 0)) });
    box.appendChild(el("small", null, meta));
    if (rice && it.r) { box.appendChild(el("small", "mrice", "+ " + L("rice", { g: riceOf().g }))); }
    a.appendChild(box);
    return a;
  }
  function drawWeather(loading) {
    $wx.textContent = "";
    var box = el("div", "mwbox");
    var top = el("div", "mwtop");
    var sel = el("select", "mcity");
    sel.setAttribute("aria-label", L("city"));
    M.cities.forEach(function (c, i) { var o = el("option", null, "📍 " + c.n); o.value = i; if (i === state.city) { o.selected = true; } sel.appendChild(o); });
    sel.addEventListener("change", function () { state.city = +sel.value; offset = 0; swaps = 0; save(); load(); });
    if (loading) {
      top.appendChild(el("span", "mwic", "⏳"));
      top.appendChild(el("span", "mwtxt", L("loading")));
    } else {
      var w = CTX && CTX.w;
      top.appendChild(el("span", "mwic", weatherIcon(w)));
      top.appendChild(el("span", "mwtxt", w ? L("wLine", { tmax: Math.round(w.tmax), tmin: Math.round(w.tmin), pop: Math.round(w.pop) }) : L("noWeatherShort")));
    }
    top.appendChild(sel);
    box.appendChild(top);
    if (!loading && plan && state.span === "day") {
      var rs = reasons();
      if (rs.length) {
        box.appendChild(el("p", "mwhy", L("why")));
        var ul = el("ul", "mwl");
        rs.forEach(function (r) { ul.appendChild(el("li", null, r)); });
        box.appendChild(ul);
      }
    }
    $wx.appendChild(box);
  }
  function drawPlan() {
    $plan.textContent = "";
    SLOTS.forEach(function (s) {
      var m = plan[s];
      var card = el("article", "mcard" + (s === NOW_SLOT ? " now" : ""));
      var head = el("div", "mhead");
      head.appendChild(el("b", null, SLOT_ICON[s] + " " + L(SLOT_KEY[s])));
      if (s === NOW_SLOT) { head.appendChild(el("span", "mnow", L("wNow"))); }
      head.appendChild(el("span", "mk", fmt(mealKcal(m)) + " " + L("kcalUnit")));
      var sw = el("button", "linkbtn", "🔁 " + L("swap"));
      sw.type = "button";
      sw.addEventListener("click", function () { swapSlot(s); draw(); });
      head.appendChild(sw);
      card.appendChild(head);
      card.appendChild(dishLine(m.main, true));
      if (m.side) {
        var sl = el("div", "mside");
        sl.appendChild(el("span", "mtag", L("side")));
        sl.appendChild(dishLine(m.side, false));
        card.appendChild(sl);
      }
      var n = state.people;
      card.appendChild(el("p", "mcost", L("costMeal", { n: n, won: L("won", { c: fmt((m.main.w + riceAdd(m.main, "w") + (m.side ? m.side.w : 0)) * n) }) })));
      $plan.appendChild(card);
    });
  }
  function drawSummary() {
    var t = totals();
    $sum.textContent = "";
    var box = el("div", "msum");
    var top = el("div", "mtop");
    top.appendChild(el("span", "mlabel", L("perPerson")));
    var big = el("div", "mbig");
    big.appendChild(el("strong", null, fmt(Math.round(t.k / 5) * 5)));
    big.appendChild(el("span", null, " " + L("kcalUnit") + " · " + L("target", { k: fmt(dayTarget()) })));
    top.appendChild(big);
    box.appendChild(top);
    var kc = t.c * 4 + t.p * 4 + t.f * 9 || 1;
    var bar = el("div", "mbar");
    [["c", t.c * 4], ["p", t.p * 4], ["f", t.f * 9]].forEach(function (x) {
      var seg_ = el("span", "mseg " + x[0]);
      seg_.style.width = (x[1] / kc * 100).toFixed(1) + "%";
      bar.appendChild(seg_);
    });
    box.appendChild(bar);
    var legend = el("div", "mlegend");
    [["c", t.c, "carb"], ["p", t.p, "protein"], ["f", t.f, "fat"]].forEach(function (x) {
      var s_ = el("span", "lg " + x[0]);
      s_.textContent = L(x[2]) + " " + Math.round(x[1]) + "g";
      legend.appendChild(s_);
    });
    box.appendChild(legend);
    box.appendChild(el("p", "mna", L("sodium") + " " + fmt(Math.round(t.na / 10) * 10) + "mg · " + L("sodiumPct", { p: Math.round(t.na / 2000 * 100) })));
    box.appendChild(el("p", "mcostday", L("costDay", { n: state.people }) + ": " + L("won", { c: fmt(Math.round(t.w * state.people / 100) * 100) })));
    $sum.appendChild(box);
  }
  function drawWeekSummary() {
    var n = state.people, t = { k: 0, na: 0, w: 0 }, foods = {};
    week.days.forEach(function (day) {
      var x = totalsOf(day);
      t.k += x.k; t.na += x.na; t.w += x.w;
      dishesOf(day).forEach(function (it) { it.ing.forEach(function (i) { foods[i[0]] = 1; }); });
    });
    $sum.textContent = "";
    var box = el("div", "msum");
    var top = el("div", "mtop");
    top.appendChild(el("span", "mlabel", L("costWeek", { n: n })));
    var big = el("div", "mbig");
    big.appendChild(el("strong", null, L("won", { c: fmt(Math.round(t.w * n / 100) * 100) })));
    top.appendChild(big);
    box.appendChild(top);
    box.appendChild(el("p", "mna", L("weekFoods", { c: Object.keys(foods).length })));
    box.appendChild(el("p", "mna", L(state.meals === "d" ? "weekAvgDinner" : "weekAvgDay", { k: fmt(Math.round(t.k / 7 / 5) * 5) }) + " · " + L("sodium") + " " + fmt(Math.round(t.na / 7 / 10) * 10) + "mg"));
    $sum.appendChild(box);
  }
  function weekDish(it) {
    var a = el("a", null, it.n);
    a.href = "recipes/" + it.s + ".html";
    return a;
  }
  function drawWeekPlan() {
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    $plan.textContent = "";
    week.days.forEach(function (day, i) {
      var date = dayDate(i), isToday = date.getTime() === today.getTime();
      var card = el("article", "mcard wday" + (isToday ? " now" : (date < today ? " past" : "")));
      var head = el("div", "mhead");
      head.appendChild(el("b", null, date.toLocaleDateString(M.loc, { month: "numeric", day: "numeric", weekday: "short" })));
      if (isToday) { head.appendChild(el("span", "mnow", L("wToday"))); }
      head.appendChild(el("span", "mk", L("won", { c: fmt(Math.round(totalsOf(day).w * state.people / 100) * 100) })));
      var sw = el("button", "linkbtn", "🔁 " + L("swapDay"));
      sw.type = "button";
      sw.addEventListener("click", function () {
        swaps++;
        var d = makeDay(i, swaps);
        if (d) { week.days[i] = d; saveWeek(); draw(); }
      });
      head.appendChild(sw);
      card.appendChild(head);
      SLOTS.forEach(function (s) {
        if (!day[s]) { return; }
        var row = el("div", "wrow");
        row.appendChild(el("span", "wslot", SLOT_ICON[s] + " " + L(SLOT_KEY[s])));
        var box = el("div", "wdish");
        box.appendChild(weekDish(day[s].main));
        if (day[s].side) { box.appendChild(document.createTextNode(" + ")); box.appendChild(weekDish(day[s].side)); }
        row.appendChild(box);
        card.appendChild(row);
      });
      $plan.appendChild(card);
    });
  }
  function drawShop() {
    var n = state.people, agg = {}, staples = {};
    (state.span === "week" ? week.days : [plan]).forEach(function (pl) {
      dishesOf(pl).forEach(function (it) {
        var f = n / it.sv;
        it.ing.forEach(function (x) { agg[x[0]] = (agg[x[0]] || 0) + x[1] * f; });
        it.st.forEach(function (x) { staples[x] = true; });
        if (it.r) { agg["밥"] = (agg["밥"] || 0) + riceOf().g * n; }
      });
    });
    var names = Object.keys(agg).sort(function (a, b) { return agg[b] - agg[a]; });
    $shop.textContent = "";
    $shop.appendChild(el("h2", null, L("shop")));
    $shop.appendChild(el("p", "mut", L(state.span === "week" ? "shopSubWeek" : "shopSub", { n: n })));
    var ul = el("ul", "mlist");
    names.forEach(function (k) {
      var li = el("li");
      li.appendChild(el("span", null, nm(k)));
      var g = Math.max(5, Math.round(agg[k] / 5) * 5);
      li.appendChild(el("b", null, fmt(g) + " g"));
      if (M.aff[k]) {
        var a = el("a", "buy", "🛒 " + L("buy"));
        a.href = M.aff[k]; a.target = "_blank"; a.rel = "sponsored nofollow noopener noreferrer";
        li.appendChild(a);
      }
      ul.appendChild(li);
    });
    $shop.appendChild(ul);
    var st = Object.keys(staples);
    if (st.length) {
      $shop.appendChild(el("h3", "mst", L("staples")));
      var box = el("div", "chips");
      st.forEach(function (k) { box.appendChild(el("span", "chip", nm(k))); });
      $shop.appendChild(box);
    }
  }
  function draw() {
    var isWeek = state.span === "week";
    controls();
    drawWeather(false);
    $other.textContent = L(isWeek ? "otherWeek" : "other");
    document.getElementById("mtitle").textContent = (isWeek ? "📅 " : "🍱 ") + L(isWeek ? "weekTitle" : "title");
    document.getElementById("mdate").textContent = isWeek && week
      ? L("weekDate", { d: dayDate(0).toLocaleDateString(M.loc, { month: "long", day: "numeric" }) })
      : L("todayDate", { d: now.toLocaleDateString(M.loc, { month: "long", day: "numeric", weekday: "long" }) });
    if (!(isWeek ? week : plan)) { $plan.textContent = ""; $sum.textContent = ""; $shop.textContent = ""; $plan.appendChild(el("p", "empty", L("empty"))); return; }
    if (isWeek) { drawWeekSummary(); drawWeekPlan(); } else { drawSummary(); drawPlan(); }
    drawShop();
    $note.textContent = (state.mode === "diet" ? L("dietNote", { k: fmt(dayTarget()) }) : L("normalNote", { k: fmt(dayTarget()) })) + (isWeek ? " " + L("weekNote") : "");
  }
  // 지역의 오늘 날씨를 받아 그 날씨로 식단을 짠다(못 받아도 계절·요일로 짠다)
  function load() {
    drawWeather(true);
    fetchWeather(function (w) { CTX = buildCtx(w); refresh(); });
  }
  $other.addEventListener("click", function () {
    offset++; swaps = 0;
    if (state.span === "week") { makeWeek(); } else { plan = makePlan(); }
    draw();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  controls();
  CTX = buildCtx(null);
  load();
})();

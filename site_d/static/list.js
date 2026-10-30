(function () {
  // 모든 레시피 페이지: 초성 필터 + 이름·재료 검색(초성만 입력해도 됨)
  var $rq = document.getElementById("rq");
  if (!$rq) { return; }
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
      var k = li.getAttribute("data-k") || "";
      var okQ = !q || (onlyCons(q) ? li.getAttribute("data-c").indexOf(q) > -1 : (n.indexOf(q) > -1 || k.indexOf(q) > -1));
      var okI = !curI || li.parentNode.parentNode.getAttribute("data-i") === curI;
      li.hidden = !(okQ && okI);
      if (!li.hidden) { shown++; }
    });
    groups.forEach(function (g) { g.hidden = !g.querySelector("li:not([hidden])"); });
    $none.hidden = shown > 0;
  };
  $rq.addEventListener("input", function () { filterList(); suggest(); });

  // ---- 자동완성: 입력하면 요리 이름 후보를 아래에 보여 준다(초성·재료로도 찾는다). 방향키·Enter·Esc 지원 ----
  var $box = document.createElement("ul");
  $box.className = "ac"; $box.hidden = true; $box.setAttribute("role", "listbox");
  $rq.parentNode.style.position = "relative";
  $rq.parentNode.appendChild($box);
  var cur = -1;
  var norm = function (t) { return t.replace(/\s/g, "").toLowerCase(); };
  var baseCons = function (t) { return t.replace(/ㄲ/g, "ㄱ").replace(/ㄸ/g, "ㄷ").replace(/ㅃ/g, "ㅂ").replace(/ㅆ/g, "ㅅ").replace(/ㅉ/g, "ㅈ"); };
  var closeBox = function () { $box.hidden = true; $box.textContent = ""; cur = -1; };
  var mark = function (name, q) {
    var i = name.replace(/\s/g, "").toLowerCase().indexOf(q);
    if (i < 0) { return document.createTextNode(name); }
    if (name.indexOf(" ") > -1) { i = name.toLowerCase().indexOf(q); if (i < 0) { return document.createTextNode(name); } }
    var f = document.createDocumentFragment();
    f.appendChild(document.createTextNode(name.slice(0, i)));
    var b = document.createElement("b"); b.textContent = name.slice(i, i + q.length); f.appendChild(b);
    f.appendChild(document.createTextNode(name.slice(i + q.length)));
    return f;
  };
  function suggest() {
    var q = norm($rq.value);
    if (!q) { closeBox(); return; }
    var cons = onlyCons(q);
    if (cons) { q = baseCons(q); }
    var byName = [], byIng = [];
    items.forEach(function (li) {
      var n = li.getAttribute("data-n");
      var nn = norm(n);
      var hit = cons ? (li.getAttribute("data-c") || "").indexOf(q) > -1 : nn.indexOf(q) > -1;
      if (hit) { byName.push({ li: li, pre: cons ? (li.getAttribute("data-c") || "").indexOf(q) === 0 : nn.indexOf(q) === 0, n: n }); }
      else if (!cons && (li.getAttribute("data-k") || "").indexOf(q) > -1) { byIng.push({ li: li, n: n }); }
    });
    byName.sort(function (a, b) { return (a.pre ? 0 : 1) - (b.pre ? 0 : 1) || a.n.length - b.n.length; });
    var rows = byName.slice(0, 7).map(function (x) { return { x: x, tag: "" }; });
    byIng.slice(0, Math.max(0, 8 - rows.length)).forEach(function (x) { rows.push({ x: x, tag: "재료" }); });
    $box.textContent = ""; cur = -1;
    if (!rows.length) { $box.hidden = true; return; }
    rows.forEach(function (r) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      var a = document.createElement("a");
      a.href = r.x.li.querySelector("a").getAttribute("href");
      var nm = document.createElement("span"); nm.appendChild(mark(r.x.n, q)); a.appendChild(nm);
      if (r.tag) { var t = document.createElement("small"); t.textContent = q + " 포함"; a.appendChild(t); }
      li.appendChild(a);
      $box.appendChild(li);
    });
    $box.hidden = false;
  }
  var setCur = function (i) {
    var rows = [].slice.call($box.children);
    if (!rows.length) { return; }
    cur = (i + rows.length) % rows.length;
    rows.forEach(function (r, k) { r.classList.toggle("on", k === cur); });
  };
  $rq.addEventListener("keydown", function (e) {
    if ($box.hidden) { return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setCur(cur + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCur(cur - 1); }
    else if (e.key === "Enter" && cur > -1) { e.preventDefault(); location.href = $box.children[cur].querySelector("a").href; }
    else if (e.key === "Escape") { closeBox(); }
  });
  $rq.addEventListener("focus", function () { if ($rq.value) { suggest(); } });
  document.addEventListener("click", function (e) { if (!$rq.parentNode.contains(e.target)) { closeBox(); } });
  document.getElementById("ri").addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("button") : null;
    if (!b) { return; }
    curI = b.getAttribute("data-i") || "";
    [].forEach.call(document.querySelectorAll("#ri .chip"), function (c) { c.classList.toggle("on", c === b); });
    filterList();
  });
})();

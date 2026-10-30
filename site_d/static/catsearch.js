(function () {
  // 카테고리 페이지: 이 카테고리 안에서 이름·재료·초성으로 찾고, 입력하면 자동완성 후보를 보여 준다
  var $q = document.getElementById("cq");
  if (!$q) { return; }
  var cards = [].slice.call(document.querySelectorAll(".rlistc .rcard"));
  var $none = document.getElementById("cnone");
  var $cnt = document.getElementById("ccount");
  var total = cards.length;
  var norm = function (t) { return t.replace(/\s/g, "").toLowerCase(); };
  var onlyCons = function (t) { return /^[ㄱ-ㅎ]+$/.test(t); };
  var baseCons = function (t) { return t.replace(/ㄲ/g, "ㄱ").replace(/ㄸ/g, "ㄷ").replace(/ㅃ/g, "ㅂ").replace(/ㅆ/g, "ㅅ").replace(/ㅉ/g, "ㅈ"); };

  function filterCards() {
    var q = norm($q.value), shown = 0;
    var cons = onlyCons(q);
    if (cons) { q = baseCons(q); }
    cards.forEach(function (a) {
      var ok = !q || (cons ? (a.getAttribute("data-c") || "").indexOf(q) > -1 : (norm(a.getAttribute("data-n") || "").indexOf(q) > -1 || (a.getAttribute("data-k") || "").indexOf(q) > -1));
      a.hidden = !ok;
      if (ok) { shown++; }
    });
    if ($none) { $none.hidden = shown > 0; }
    if ($cnt) { $cnt.textContent = q ? "검색 결과 " + shown + "개 (전체 " + total + "개)" : ""; }
  }

  // ---- 자동완성 ----
  var $box = document.createElement("ul");
  $box.className = "ac"; $box.hidden = true; $box.setAttribute("role", "listbox");
  $q.parentNode.style.position = "relative";
  $q.parentNode.appendChild($box);
  var cur = -1;
  var closeBox = function () { $box.hidden = true; $box.textContent = ""; cur = -1; };
  function suggest() {
    var q = norm($q.value);
    if (!q) { closeBox(); return; }
    var cons = onlyCons(q);
    if (cons) { q = baseCons(q); }
    var byName = [], byIng = [];
    cards.forEach(function (a) {
      var n = a.getAttribute("data-n") || "", nn = norm(n);
      var hit = cons ? (a.getAttribute("data-c") || "").indexOf(q) > -1 : nn.indexOf(q) > -1;
      if (hit) { byName.push({ a: a, n: n, pre: nn.indexOf(q) === 0 || (cons && (a.getAttribute("data-c") || "").indexOf(q) === 0) }); }
      else if (!cons && (a.getAttribute("data-k") || "").indexOf(q) > -1) { byIng.push({ a: a, n: n }); }
    });
    byName.sort(function (x, y) { return (x.pre ? 0 : 1) - (y.pre ? 0 : 1) || x.n.length - y.n.length; });
    var rows = byName.slice(0, 7).map(function (x) { return { x: x, tag: false }; });
    byIng.slice(0, Math.max(0, 8 - rows.length)).forEach(function (x) { rows.push({ x: x, tag: true }); });
    $box.textContent = ""; cur = -1;
    if (!rows.length) { $box.hidden = true; return; }
    rows.forEach(function (r) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      var a = document.createElement("a");
      a.href = r.x.a.getAttribute("href");
      var nm = document.createElement("span");
      var i = r.x.n.toLowerCase().indexOf(q);
      if (i > -1 && !cons) {
        nm.appendChild(document.createTextNode(r.x.n.slice(0, i)));
        var b = document.createElement("b"); b.textContent = r.x.n.slice(i, i + q.length); nm.appendChild(b);
        nm.appendChild(document.createTextNode(r.x.n.slice(i + q.length)));
      } else { nm.textContent = r.x.n; }
      a.appendChild(nm);
      if (r.tag) { var t = document.createElement("small"); t.textContent = q + " 포함"; a.appendChild(t); }
      li.appendChild(a); $box.appendChild(li);
    });
    $box.hidden = false;
  }
  var setCur = function (i) {
    var rows = [].slice.call($box.children);
    if (!rows.length) { return; }
    cur = (i + rows.length) % rows.length;
    rows.forEach(function (r, k) { r.classList.toggle("on", k === cur); });
  };
  $q.addEventListener("input", function () { filterCards(); suggest(); });
  $q.addEventListener("keydown", function (e) {
    if ($box.hidden) { return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setCur(cur + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCur(cur - 1); }
    else if (e.key === "Enter" && cur > -1) { e.preventDefault(); location.href = $box.children[cur].querySelector("a").href; }
    else if (e.key === "Escape") { closeBox(); }
  });
  $q.addEventListener("focus", function () { if ($q.value) { suggest(); } });
  document.addEventListener("click", function (e) { if (!$q.parentNode.contains(e.target)) { closeBox(); } });
})();

(function () {
  // 모든 레시피 페이지: 이름·재료·초성 검색 + 종류·재료·초성 칩 + 정렬(가나다순 기본). 입력하면 목록이 바로 걸러진다
  var UI = window.LISTUI || {};
  var LOC = UI.loc || "ko";
  var fmt = function (s, v) { Object.keys(v).forEach(function (k) { s = s.split("{" + k + "}").join(v[k]); }); return s; };
  var $rq = document.getElementById("rq");
  if (!$rq) { return; }
  var $rl = document.getElementById("rl");
  var items = [].slice.call(document.querySelectorAll("#rl li"));
  var groups = [].slice.call(document.querySelectorAll("#rl .rgroup"));
  var $none = document.getElementById("rnone");
  var $cnt = document.getElementById("rcount");
  var $sort = document.getElementById("rsort");
  var $ini = document.getElementById("ri");
  var $types = document.getElementById("rtypes");
  var $ings = document.getElementById("rings");
  var curI = "", curT = "", curG = "", total = items.length;
  var orig = items.map(function (li) { li.setAttribute("data-gi", li.parentNode.parentNode.getAttribute("data-i") || ""); return { li: li, ul: li.parentNode }; });
  var $flat = null;
  var onlyCons = function (t) { return /^[ㄱ-ㅎ]+$/.test(t); };
  // 한글을 쓰는 도중(예: '두부조리')에도 '두부조림'이 나오도록 자음·모음으로 풀어서 비교한다
  var jn = function (t) { return t.replace(/\s/g, "").toLowerCase().normalize("NFKD"); };
  items.forEach(function (li) { li._n = jn(li.getAttribute("data-n") || ""); li._k = jn(li.getAttribute("data-k") || ""); });
  var baseCons = function (t) { return t.replace(/ㄲ/g, "ㄱ").replace(/ㄸ/g, "ㄷ").replace(/ㅃ/g, "ㅂ").replace(/ㅆ/g, "ㅅ").replace(/ㅉ/g, "ㅈ"); };

  function filterList() {
    var q = $rq.value.replace(/\s/g, "").toLowerCase();
    var cons = onlyCons(q);
    if (cons) { q = baseCons(q); }
    var jq = jn(q);
    var shown = 0;
    items.forEach(function (li) {
      var okQ = !q || (cons ? (li.getAttribute("data-c") || "").indexOf(q) > -1 : (li._n.indexOf(jq) > -1 || li._k.indexOf(jq) > -1));
      var okI = !curI || li.getAttribute("data-gi") === curI;
      var okT = !curT || li.getAttribute("data-t") === curT;
      var okG = !curG || (li.getAttribute("data-g") || "").indexOf("|" + curG + "|") > -1;
      li.hidden = !(okQ && okI && okT && okG);
      if (!li.hidden) { shown++; }
    });
    groups.forEach(function (g) { g.hidden = !g.querySelector("li:not([hidden])"); });
    if ($none) { $none.hidden = shown > 0; }
    if ($cnt) { $cnt.textContent = (q || curI || curT || curG) ? fmt(UI.shownOf || "{s}개 보이는 중 (전체 {t}개)", { s: shown, t: total }) : fmt(UI.total || "전체 {t}개", { t: total }); }
  }

  // 가나다순이 아니면 초성 묶음을 풀어 한 줄로 늘어놓고 정렬한다. 가나다순으로 돌아오면 원래 묶음으로 되돌린다
  function sortList() {
    var key = $sort ? $sort.value : "n";
    if (key === "n") {
      if ($flat) { $flat.parentNode.removeChild($flat); $flat = null; }
      $rl.classList.remove("flat");
      orig.forEach(function (o) { o.ul.appendChild(o.li); });
    } else {
      if (!$flat) { $flat = document.createElement("ul"); $flat.className = "rlist"; $rl.appendChild($flat); }
      $rl.classList.add("flat");
      var arr = items.slice().sort(function (a, b) {
        var d = (parseFloat(a.getAttribute("data-" + key)) || 0) - (parseFloat(b.getAttribute("data-" + key)) || 0);
        return d || (a.getAttribute("data-n") || "").localeCompare(b.getAttribute("data-n") || "", LOC);
      });
      arr.forEach(function (li) { $flat.appendChild(li); });
    }
    filterList();
  }

  // 폰에서는 키보드가 목록을 가리므로, 글자를 치면 필터 버튼을 접고 검색창을 맨 위로 올려 결과가 바로 보이게 한다
  function focusResults() {
    var typing = $rq.value.trim().length > 0;
    document.body.classList.toggle("csearching", typing && !curI && !curT && !curG);
    if (typing && window.matchMedia("(max-width: 760px)").matches) {
      var box = $rq.parentNode, top = box.getBoundingClientRect().top;
      if (top > 90 || top < 40) { box.scrollIntoView({ behavior: "smooth", block: "start" }); }
    }
  }

  function wire($box, set, attr) {
    if (!$box) { return; }
    $box.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button") : null;
      if (!b) { return; }
      set(b.getAttribute(attr) || "");
      [].forEach.call($box.querySelectorAll(".chip"), function (c) { c.classList.toggle("on", c === b); });
      filterList();
    });
  }
  $rq.addEventListener("input", function () { filterList(); focusResults(); });
  wire($ini, function (v) { curI = v; }, "data-i");
  wire($types, function (v) { curT = v; }, "data-v");
  wire($ings, function (v) { curG = v; }, "data-v");
  if ($sort) { $sort.addEventListener("change", sortList); }
  filterList();
})();

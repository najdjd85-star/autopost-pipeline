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
  $rq.addEventListener("input", filterList);
  document.getElementById("ri").addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("button") : null;
    if (!b) { return; }
    curI = b.getAttribute("data-i") || "";
    [].forEach.call(document.querySelectorAll("#ri .chip"), function (c) { c.classList.toggle("on", c === b); });
    filterList();
  });
})();

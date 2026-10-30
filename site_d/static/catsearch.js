(function () {
  // 카테고리 페이지: 이름·재료·초성 검색 + 요리 종류 칩 + 정렬(가나다순 기본). 입력하면 목록이 바로 걸러진다
  var $q = document.getElementById("cq");
  if (!$q) { return; }
  var $list = document.getElementById("clist");
  var cards = [].slice.call($list.querySelectorAll(".rcard"));
  var $none = document.getElementById("cnone");
  var $cnt = document.getElementById("ccount");
  var $sort = document.getElementById("csort");
  var $types = document.getElementById("ctypes");
  var $ings = document.getElementById("cings");
  var total = cards.length, curType = "", curIng = "";
  var norm = function (t) { return t.replace(/\s/g, "").toLowerCase(); };
  var onlyCons = function (t) { return /^[ㄱ-ㅎ]+$/.test(t); };
  var baseCons = function (t) { return t.replace(/ㄲ/g, "ㄱ").replace(/ㄸ/g, "ㄷ").replace(/ㅃ/g, "ㅂ").replace(/ㅆ/g, "ㅅ").replace(/ㅉ/g, "ㅈ"); };

  function apply() {
    var q = norm($q.value), shown = 0;
    var cons = onlyCons(q);
    if (cons) { q = baseCons(q); }
    cards.forEach(function (a) {
      var okQ = !q || (cons ? (a.getAttribute("data-c") || "").indexOf(q) > -1 : (norm(a.getAttribute("data-n") || "").indexOf(q) > -1 || (a.getAttribute("data-k") || "").indexOf(q) > -1));
      var okT = !curType || a.getAttribute("data-t") === curType;
      var okI = !curIng || (a.getAttribute("data-i") || "").indexOf("|" + curIng + "|") > -1;
      a.hidden = !(okQ && okT && okI);
      if (!a.hidden) { shown++; }
    });
    if ($none) { $none.hidden = shown > 0; }
    if ($cnt) { $cnt.textContent = (q || curType || curIng) ? shown + "개 보이는 중 (전체 " + total + "개)" : "전체 " + total + "개"; }
  }

  function sortCards() {
    var key = $sort.value;
    var arr = cards.slice();
    arr.sort(function (a, b) {
      if (key === "n") { return (a.getAttribute("data-n") || "").localeCompare(b.getAttribute("data-n") || "", "ko"); }
      var d = (parseFloat(a.getAttribute("data-" + key)) || 0) - (parseFloat(b.getAttribute("data-" + key)) || 0);
      return d || (a.getAttribute("data-n") || "").localeCompare(b.getAttribute("data-n") || "", "ko");
    });
    arr.forEach(function (a) { $list.appendChild(a); });
  }

  // 폰에서는 키보드가 목록을 가리므로, 글자를 치면 필터 버튼을 접고 검색창을 맨 위로 올려 결과가 바로 보이게 한다
  function focusResults() {
    var typing = $q.value.trim().length > 0;
    document.body.classList.toggle("csearching", typing && !curType && !curIng);
    if (typing && window.matchMedia("(max-width: 760px)").matches) {
      var box = $q.parentNode, top = box.getBoundingClientRect().top;
      if (top > 90 || top < 40) { box.scrollIntoView({ behavior: "smooth", block: "start" }); }
    }
  }
  $q.addEventListener("input", function () { apply(); focusResults(); });
  $sort.addEventListener("change", sortCards);
  $types.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("button") : null;
    if (!b) { return; }
    curType = b.getAttribute("data-t") || "";
    [].forEach.call($types.querySelectorAll(".chip"), function (c) { c.classList.toggle("on", c === b); });
    apply();
  });
  if ($ings) {
    $ings.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("button") : null;
      if (!b) { return; }
      curIng = b.getAttribute("data-i") || "";
      [].forEach.call($ings.querySelectorAll(".chip"), function (c) { c.classList.toggle("on", c === b); });
      apply();
    });
  }
  apply();
})();

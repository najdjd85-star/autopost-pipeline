/* 레시피 순서: 끝낸 단계를 눌러 체크한다(요리하다 어디까지 했는지 헷갈리지 않게). */
(function () {
  var ol = document.querySelector("ol.steps");
  if (!ol) { return; }
  [].forEach.call(ol.children, function (li) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "scheck";
    b.textContent = "✓";
    b.setAttribute("aria-label", ol.dataset.check);
    b.setAttribute("aria-pressed", "false");
    li.querySelector(".shead").appendChild(b);
    li.addEventListener("click", function () {
      if (String(window.getSelection())) { return; }   // 글자를 고르는 중이면 체크하지 않는다
      b.setAttribute("aria-pressed", String(li.classList.toggle("done")));
    });
  });
})();

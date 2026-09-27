/* Paramètres : choix direct du thème (mémorisé comme le bouton de la barre latérale). */
(function () {
  "use strict";
  var grid = document.getElementById("theme-grid");
  if (!grid || !window.GATheme) return;

  function mark() {
    var current = window.GATheme.get();
    grid.querySelectorAll("[data-theme-set]").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-theme-set") === current);
      btn.setAttribute(
        "aria-pressed",
        btn.getAttribute("data-theme-set") === current ? "true" : "false"
      );
    });
  }

  grid.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-theme-set]");
    if (!btn) return;
    window.GATheme.set(btn.getAttribute("data-theme-set"));
    mark();
    var name = btn.querySelector(".theme-name");
    window.toast &&
      window.toast(
        "Thème « " + (name ? name.textContent.trim() : btn.getAttribute("data-theme-set")) + " » appliqué.",
        "success"
      );
  });

  document.addEventListener("ga:theme", mark);
  mark();
})();

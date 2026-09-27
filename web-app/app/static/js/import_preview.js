/* Prévisualisation d'import : cocher/décocher toutes les feuilles. */
(function () {
  "use strict";
  function setAll(state) {
    document
      .querySelectorAll('input[name="selected"]')
      .forEach(function (box) { box.checked = state; });
  }
  var all = document.getElementById("check-all");
  var none = document.getElementById("check-none");
  if (all) all.addEventListener("click", function () { setAll(true); });
  if (none) none.addEventListener("click", function () { setAll(false); });

  var form = document.getElementById("import-commit");
  if (form) {
    form.addEventListener("submit", function (event) {
      var any = form.querySelectorAll('input[name="selected"]:checked').length;
      if (!any) {
        event.preventDefault();
        window.toast && window.toast("Cochez au moins une feuille.", "error");
      }
    });
  }
})();

/* Rapport : changement d'exercice = rechargement immédiat. */
(function () {
  "use strict";
  var select = document.getElementById("label");
  if (!select) return;
  select.addEventListener("change", function () {
    if (select.form) select.form.submit();
  });
})();

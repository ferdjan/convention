/* Historique : recherche instantanée (soumission différée) et raccourcis. */
(function () {
  "use strict";
  var form = document.getElementById("history-filters");
  if (!form) return;
  var input = document.getElementById("q");
  var selects = form.querySelectorAll("select");
  var timer = null;

  function submit(dropPreview) {
    if (dropPreview) {
      var link = form.querySelector('input[name="doc"]');
      if (link) link.remove();
    }
    form.submit();
  }

  if (input) {
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { submit(true); }, 420);
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        clearTimeout(timer);
        submit(true);
      }
    });
  }
  selects.forEach(function (select) {
    select.addEventListener("change", function () { submit(true); });
  });
})();

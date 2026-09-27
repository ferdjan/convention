/* Conventions : dialogue d'exercice (création/édition), import, suppression. */
(function () {
  "use strict";
  var panel = document.getElementById("exercices-panel");
  var dlg = document.getElementById("exercice-dialog");
  var form = document.getElementById("exercice-form");
  if (!dlg || !form) return;

  function open(dialog) {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "open");
  }
  function closeAll() {
    document.querySelectorAll("dialog[open]").forEach(function (d) { d.close(); });
  }
  document.querySelectorAll("dialog [data-close]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var d = btn.closest("dialog");
      if (d) d.close();
    });
  });

  function suggestLabel(start, end) {
    if (!start || !end) return "";
    return start.slice(0, 4) + "-" + end.slice(0, 4);
  }

  var title = document.getElementById("exercice-dialog-title");
  var labelField = document.getElementById("label-field");
  var labelInput = document.getElementById("ex-label");
  var startInput = document.getElementById("ex-start");
  var endInput = document.getElementById("ex-end");
  var plafondInput = document.getElementById("ex-plafond");
  var closeWrap = document.getElementById("close-current-wrap");
  var notice = document.getElementById("edit-notice");
  var actionUrl = document.getElementById("exercice-action-url");

  var createBtn = document.getElementById("new-exercice-btn");
  if (createBtn && panel) {
    createBtn.addEventListener("click", function () {
      form.reset();
      var start = panel.getAttribute("data-suggest-start") || "";
      startInput.value = start;
      endInput.value = start;
      labelInput.value = "";
      title.textContent = "Ouvrir un exercice";
      labelField.hidden = false;
      labelInput.required = true;
      closeWrap.hidden = false;
      notice.hidden = true;
      actionUrl.value = panel.getAttribute("data-create-url") || "";
      var keep = form.querySelector('input[name="keep_plafond"]');
      if (keep) keep.remove();
      labelInput.removeAttribute("disabled");
      open(dlg);
      labelInput.focus();
    });
  }

  document.querySelectorAll("[data-edit-exercice]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      form.reset();
      title.textContent = "Modifier l'exercice " + btn.getAttribute("data-label");
      labelField.hidden = true;
      labelInput.disabled = true;
      labelInput.value = btn.getAttribute("data-label") || "";
      startInput.value = btn.getAttribute("data-start") || "";
      endInput.value = btn.getAttribute("data-end") || "";
      plafondInput.value = btn.getAttribute("data-plafond") || "";
      closeWrap.hidden = true;
      notice.hidden = false;
      document.getElementById("edit-label-out").textContent =
        btn.getAttribute("data-label") || "";
      actionUrl.value = btn.getAttribute("data-url") || "";
      if (!form.querySelector('input[name="keep_plafond"]')) {
        var keep = document.createElement("input");
        keep.type = "hidden";
        keep.name = "keep_plafond";
        keep.value = "on";
        form.appendChild(keep);
      }
      open(dlg);
      startInput.focus();
    });
  });

  // Date glissante : début = lendemain de la fin active, fin = +1 an.
  if (panel && startInput) {
    var anchor = panel.getAttribute("data-suggest-start");
    if (anchor) {
      var next = new Date(anchor + "T00:00:00");
      startInput.addEventListener("change", function () {
        if (!startInput.value) return;
        var s = new Date(startInput.value + "T00:00:00");
        var e = new Date(s.getTime());
        e.setFullYear(e.getFullYear() + 1);
        e.setDate(e.getDate() - 1);
        endInput.value = e.toISOString().slice(0, 10);
        if (!labelInput.disabled && !labelInput.value) {
          labelInput.value = suggestLabel(startInput.value, endInput.value);
        }
      });
      void next;
    }
  }

  form.addEventListener("submit", function (event) {
    var url = actionUrl.value;
    if (!url) {
      event.preventDefault();
      return;
    }
    form.action = url;
    var label = (labelInput.value || "").trim();
    if (!labelInput.disabled && !label) {
      event.preventDefault();
      labelInput.focus();
      return;
    }
    if (startInput.value && endInput.value && endInput.value < startInput.value) {
      event.preventDefault();
      endInput.focus();
      return;
    }
    setTimeout(closeAll, 0);
  });

  // Suppression de la liste : exige le nom exact.
  var deleteBtn = document.getElementById("delete-list-btn");
  var deleteDialog = document.getElementById("delete-dialog");
  if (deleteBtn && deleteDialog) {
    deleteBtn.addEventListener("click", function () {
      var field = deleteDialog.querySelector("#confirm-name");
      if (field) field.value = "";
      open(deleteDialog);
      if (field) field.focus();
    });
  }

  // Import Excel : le fichier est envoyé dès sa sélection.
  // Le sélecteur est associé au formulaire via form="import-form"
  // (pas de copie DataTransfer : le fichier part tel quel, en multipart).
  var picker = document.getElementById("import-file");
  var importForm = document.getElementById("import-form");
  if (picker && importForm) {
    picker.addEventListener("change", function () {
      if (!picker.files || !picker.files.length) return;
      importForm.submit();
    });
  }
})();

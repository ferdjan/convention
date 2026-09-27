/* Comportements généraux : thème, messages, toasts, dialogues, formulaires. */
(function () {
  "use strict";

  /* ------------------------------------------------------------ toasts */
  function toast(message, type) {
    var region = document.getElementById("toast-region");
    if (!region) return;
    var node = document.createElement("div");
    node.className = "toast " + (type || "info");
    node.setAttribute("role", "status");
    var text = document.createElement("span");
    text.textContent = message;
    node.appendChild(text);
    /* Clic = fermer tout de suite (sinon disparition auto : 6 s / 10 s). */
    node.addEventListener("click", function () {
      node.remove();
    });
    region.appendChild(node);
    setTimeout(function () {
      node.style.opacity = "0";
      node.style.transition = "opacity .3s";
      setTimeout(function () {
        node.remove();
      }, 320);
    }, type === "error" ? 10000 : 6000);
  }
  window.toast = toast;

  /* -------------------------------------------------------------- thème */
  var themeBtn = document.getElementById("theme-toggle");
  function syncTheme() {
    if (!themeBtn || !window.GATheme) return;
    var dark = window.GATheme.isDark();
    var label = document.getElementById("theme-toggle-label");
    var icon = themeBtn.querySelector(".icon-theme");
    if (label) label.textContent = dark ? "Thème clair" : "Thème sombre";
    if (icon) {
      icon.innerHTML = dark
        ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M4.9 4.9l1.4 1.4"/><path d="M17.7 17.7l1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M4.9 19.1l1.4-1.4"/><path d="M17.7 6.3l1.4-1.4"/>'
        : '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>';
    }
    themeBtn.setAttribute("aria-pressed", dark ? "true" : "false");
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      window.GATheme.toggle();
      syncTheme();
    });
    document.addEventListener("ga:theme", syncTheme);
    syncTheme();
  }

  /* ------------------------------------------------------------- flash */
  document.addEventListener("click", function (event) {
    var dismiss = event.target.closest("[data-dismiss]");
    if (dismiss) {
      var flash = dismiss.closest(".flash");
      if (flash) flash.remove();
    }
    var closer = event.target.closest("[data-close]");
    if (closer) {
      var dialog = closer.closest("dialog");
      if (dialog) dialog.close();
    }
  });

  /* ------------------------------------------- formulaires de confirmation */
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  /* ------------------------------------------------ API JSON + CSRF ----- */
  function readCsrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  /* Relit le jeton depuis une page fraîche (jeton de session expiré). */
  window.refreshCsrf = function () {
    return fetch("/", { credentials: "same-origin" })
      .then(function (response) {
        return response.ok ? response.text() : "";
      })
      .then(function (html) {
        var match = /<meta name="csrf-token" content="([^"]+)"/.exec(html || "");
        if (!match) return false;
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) meta.setAttribute("content", match[1]);
        var app = document.getElementById("document-app");
        if (app) app.dataset.csrf = match[1];
        return true;
      })
      .catch(function () {
        return false;
      });
  };

  function gaFetchOnce(url, options, csrf, isRetry) {
    options = options || {};
    var headers = options.headers || {};
    headers["X-CSRF-Token"] = isRetry
      ? csrf || readCsrf()
      : options.csrf || csrf || readCsrf();
    if (options.json !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.json);
    }
    /* Un corps JSON impose POST : fetch() refuse sinon (GET + body). */
    if (options.body !== undefined && !options.method) {
      options.method = "POST";
    }
    options.headers = headers;
    options.credentials = "same-origin";
    return fetch(url, options).then(function (response) {
      if (!response.ok) {
        return response
          .json()
          .catch(function () {
            return {};
          })
          .then(function (payload) {
            var error = new Error(
              payload.message || "Une erreur est survenue (" + response.status + ")."
            );
            error.payload = payload;
            error.status = response.status;
            if (payload.error === "csrf" && !isRetry) {
              /* Jeton périmé : on le rafraîchit puis on rejoue une fois. */
              return window.refreshCsrf().then(function (renewed) {
                if (!renewed) throw error;
                return gaFetchOnce(url, options, readCsrf(), true);
              });
            }
            throw error;
          });
      }
      return response.json();
    });
  }

  window.gaFetch = function (url, options) {
    return gaFetchOnce(url, options || {}, "", false);
  };
})();

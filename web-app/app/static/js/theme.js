/* Thème : appliqué avant le premier rendu (aucun flash), 2 thèmes : clair/sombre. */
(function () {
  "use strict";
  var KEY = "ga-theme";
  var LIGHT = "clair";
  var DARK = "sombre";
  /* Anciens noms (5 thèmes) rabattus sur les deux conservés. */
  var LEGACY = { nuit: DARK, cockpit: DARK, aube: LIGHT, classique: LIGHT };
  var DEFAULT = LIGHT;

  function preferred() {
    try {
      if (window.matchMedia &&
          window.matchMedia("(prefers-color-scheme: dark)").matches) {
        return DARK;
      }
    } catch (err) {
      /* matchMedia indisponible */
    }
    return DEFAULT;
  }

  function read() {
    var stored = null;
    try {
      stored = localStorage.getItem(KEY);
    } catch (err) {
      stored = null;
    }
    if (LEGACY[stored]) return LEGACY[stored];
    if (stored === LIGHT || stored === DARK) return stored;
    return preferred();
  }

  function apply(name) {
    if (name !== LIGHT && name !== DARK) name = DEFAULT;
    document.documentElement.setAttribute("data-theme", name);
    try {
      localStorage.setItem(KEY, name);
    } catch (err) {
      /* stockage indisponible : le thème reste valable pour la session */
    }
    document.dispatchEvent(new CustomEvent("ga:theme", { detail: name }));
  }

  window.GATheme = {
    get: function () {
      return document.documentElement.getAttribute("data-theme") || DEFAULT;
    },
    set: apply,
    isDark: function () {
      return this.get() === DARK;
    },
    toggle: function () {
      var next = this.isDark() ? LIGHT : DARK;
      apply(next);
      return next;
    }
  };

  apply(read());
})();

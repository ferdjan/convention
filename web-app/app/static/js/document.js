/* Saisie et modification d'une commande : recherche, panier, plafond, sauvegarde.
   Le serveur reste la seule source de vérité : totaux et plafond sont
   recalculés à chaque enregistrement (les prix viennent de la base). */
(function () {
  "use strict";
  var app = document.getElementById("document-app");
  if (!app) return;

  var CFG = {
    mode: app.dataset.mode,
    previewUrl: app.dataset.previewUrl,
    saveUrl: app.dataset.saveUrl,
    articlesUrl: app.dataset.articlesUrl,
    budgetUrl: app.dataset.budgetUrl,
    historyUrl: app.dataset.historyUrl,
    detailUrl: app.dataset.detailUrl,
    csrf: app.dataset.csrf,
    exclude: app.dataset.exclude || "",
    number: app.dataset.number || "",
    category: app.dataset.category || ""
  };

  var cart = [];
  try {
    cart = JSON.parse(app.dataset.initialCart || "[]");
  } catch (err) {
    cart = [];
  }

  var results = [];
  var activeIndex = -1;
  var category = CFG.category;
  var busy = false;
  var blocked = false;
  var searchTimer = null;
  var budgetTimer = null;

  var $ = function (id) { return document.getElementById(id); };

  /* Jeton toujours lu sur le DOM : app.js le renouvelle après expiration. */
  function currentCsrf() {
    return app.dataset.csrf || CFG.csrf || "";
  }

  var searchInput = $("article-search");
  var resultsBox = $("article-results");
  var qtyInput = $("qty");
  var cartBody = $("cart-body");
  var saveBtn = $("save-btn");
  var clearBtn = $("clear-btn");
  var priceDialog = $("price-dialog");
  /* Libellé d'origine du bouton de vérification (restauré après chaque rendu). */
  var saveLabel = saveBtn ? saveBtn.innerHTML : "";

  /* ------------------------------------------------- assistant 3 étapes */
  var maxVisited = CFG.mode === "edit" ? 2 : 1;
  var step = CFG.mode === "edit" ? 2 : 1;

  function goStep(next) {
    step = next;
    if (next > maxVisited) maxVisited = next;
    document.querySelectorAll("[data-step-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-step-panel") !== String(next);
    });
    document.querySelectorAll("[data-step-nav]").forEach(function (item) {
      var num = parseInt(item.getAttribute("data-step-nav"), 10);
      item.classList.toggle("done", num < next);
      item.classList.toggle("current", num === next);
      if (num === next) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
      item.classList.toggle("back", num < maxVisited && num !== next);
    });
    if (next === 2) {
      loadArticles();
      refreshBudget();
    }
    app.scrollIntoView({ block: "start" });
  }

  document.querySelectorAll("[data-step-nav]").forEach(function (item) {
    item.addEventListener("click", function () {
      var num = parseInt(item.getAttribute("data-step-nav"), 10);
      if (num < step) goStep(num);
    });
  });

  function selectedConvention() {
    var checked = app.querySelector('input[name="convention"]:checked:not([disabled])');
    return checked ? checked.value : "";
  }

  function syncStep1() {
    var next = $("to-step2");
    if (!next) return;
    if (CFG.mode === "edit") {
      next.disabled = false;
      return;
    }
    var choice = selectedConvention();
    next.disabled = !choice;
    var notice = $("step1-notice");
    if (notice) {
      notice.innerHTML = choice
        ? ""
        : '<div class="notice warn">Choisissez une convention avec un exercice actif pour continuer.</div>';
    }
  }

  app.querySelectorAll('input[name="convention"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      category = radio.value;
      app.dataset.category = category;
      var name = $("current-category-name");
      if (name) name.textContent = category;
      syncStep1();
    });
  });

  var toStep2 = $("to-step2");
  if (toStep2) {
    toStep2.addEventListener("click", function () {
      if (CFG.mode !== "edit") {
        var choice = selectedConvention();
        if (!choice) {
          syncStep1();
          return;
        }
        category = choice;
        app.dataset.category = category;
        var name = $("current-category-name");
        if (name) name.textContent = category;
      }
      goStep(2);
    });
  }

  var backTo1 = $("back-to-1");
  if (backTo1) {
    backTo1.addEventListener("click", function () {
      if (cart.length && !window.confirm(
        "Revenir à l'étape Convention ? Le panier est conservé, mais changez " +
        "de convention uniquement après l'avoir vidé."
      )) return;
      goStep(1);
    });
  }

  var changeCategory = $("change-category");
  if (changeCategory) {
    changeCategory.addEventListener("click", function () {
      if (cart.length) {
        window.toast(
          "Videz la commande avant de changer de convention.", "error"
        );
        return;
      }
      goStep(1);
    });
  }

  var backTo2 = $("back-to-2");
  if (backTo2) {
    backTo2.addEventListener("click", function () { goStep(2); });
  }

  function money(value) {
    if (value === null || value === undefined || value === "") return "—";
    return Number(value).toLocaleString("fr-FR", {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
  }

  function qtyValue() {
    var raw = (qtyInput && qtyInput.value ? qtyInput.value : "1")
      .replace(/\u00a0/g, "").replace(/\s/g, "").replace(",", ".");
    var value = parseFloat(raw);
    if (!isFinite(value) || value <= 0) value = 1;
    return value;
  }

  function lineTotal(item) {
    return Math.round(item.quantity * item.unit_price_ht * 100) / 100;
  }

  function totals() {
    var ht = 0;
    cart.forEach(function (item) { ht += lineTotal(item); });
    ht = Math.round(ht * 100) / 100;
    var tva = Math.round(ht * 0.19 * 100) / 100;
    return { ht: ht, tva: tva, ttc: Math.round((ht + tva) * 100) / 100 };
  }

  /* --------------------------------------------------------- catalogue */
  function loadArticles() {
    if (resultsBox) {
      resultsBox.innerHTML =
        '<div class="results-state"><span class="spinner"></span> Chargement du catalogue…</div>';
    }
    var url = CFG.articlesUrl + "?category=" + encodeURIComponent(category) +
      "&q=" + encodeURIComponent(searchInput ? searchInput.value : "");
    fetch(url, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (rows) {
        results = rows || [];
        activeIndex = results.length ? 0 : -1;
        renderResults();
      })
      .catch(function () {
        results = [];
        activeIndex = -1;
        if (resultsBox) {
          resultsBox.innerHTML =
            '<div class="results-state results-error">Catalogue indisponible ' +
            "(connexion au serveur locale perdue).<br>Vérifiez que l'application " +
            "tourne toujours, puis rechargez la page.</div>";
        }
        var count = $("result-count");
        if (count) count.textContent = "erreur de chargement";
        window.toast
          ? window.toast("Recherche impossible : serveur injoignable.", "error")
          : null;
      });
  }

  function renderResults() {
    if (!resultsBox) return;
    var count = $("result-count");
    if (count) {
      count.textContent = results.length
        ? results.length + " article(s)"
        : "aucun résultat";
    }
    if (!results.length) {
      resultsBox.innerHTML =
        '<div class="results-state"><strong>Aucun article</strong>' +
        "<span>Vérifiez la convention sélectionnée ou importez la liste " +
        '<a href="/conventions">depuis Conventions</a>.</span></div>';
      return;
    }
    var html = "";
    results.slice(0, 80).forEach(function (a, index) {
      html += '<div class="result' + (index === activeIndex ? " active" : "") +
        '" role="option" data-index="' + index + '"' +
        (index === activeIndex ? ' aria-selected="true"' : "") + ">" +
        '<span class="code">' + escapeHtml(a.code) + "</span>" +
        '<span class="desig" title="' + escapeHtml(a.designation) + '">' +
        escapeHtml(a.designation) + "</span>" +
        '<span class="unit muted">' + escapeHtml(a.unit) + "</span>" +
        '<span class="price">' + money(a.unit_price_ht) + "</span>" +
        '<button type="button" class="result-add" data-add="' + index +
        '" title="Ajouter à la commande" aria-label="Ajouter ' +
        escapeHtml(a.designation) + ' à la commande">' +
        '<svg class="icon icon-sm" viewBox="0 0 24 24" aria-hidden="true">' +
        '<path d="M12 5v14"/><path d="M5 12h14"/></svg></button>' +
        "</div>";
    });
    resultsBox.innerHTML = html;
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function addArticle(article, quantity) {
    var existing = null;
    cart.forEach(function (item) {
      if (item.article_id === article.id) existing = item;
    });
    if (existing) {
      existing.quantity = Math.round((existing.quantity + quantity) * 10000) / 10000;
    } else {
      cart.push({
        item_id: null,
        article_id: article.id,
        code: article.code,
        designation: article.designation,
        unit: article.unit,
        unit_price_ht: article.unit_price_ht,
        quantity: quantity,
        frozen: false
      });
    }
    if (qtyInput) qtyInput.value = "1";
    renderCart();
    refreshBudget();
  }

  /* ------------------------------------------------------------- panier */
  function renderCart() {
    if (!cartBody) return;
    if (!cart.length) {
      cartBody.innerHTML =
        '<tr><td colspan="6" class="muted" style="text-align:center;padding:22px">' +
        "Commande vide — recherchez un article à gauche pour commencer.</td></tr>";
    } else {
      var html = "";
      cart.forEach(function (item, index) {
        html += "<tr>" +
          '<td class="mono">' + escapeHtml(item.code) + "</td>" +
          "<td>" + escapeHtml(item.designation) +
          '<div class="hint">' + escapeHtml(item.unit) +
          (item.frozen ? " · prix figé" : "") + "</div></td>" +
          '<td class="num">' + money(item.unit_price_ht) + "</td>" +
          '<td class="num"><input class="qty-input" type="text" inputmode="decimal" ' +
          'value="' + String(item.quantity).replace(".", ",") + '" data-qty="' + index +
          '" aria-label="Quantité"></td>' +
          '<td class="num">' + money(lineTotal(item)) + "</td>" +
          '<td class="right"><button type="button" class="icon-btn" data-remove="' +
          index + '" title="Retirer la ligne" aria-label="Retirer">' +
          '<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M18 6 6 18"/>' +
          '<path d="m6 6 12 12"/></svg></button></td>' +
          "</tr>";
      });
      cartBody.innerHTML = html;
    }

    var t = totals();
    $("t-ht").textContent = money(t.ht);
    $("t-tva").textContent = money(t.tva);
    $("t-ttc").textContent = money(t.ttc);
    var count = $("line-count");
    if (count) {
      var units = cart.reduce(function (sum, i) { return sum + i.quantity; }, 0);
      count.textContent = cart.length + " ligne(s) · " +
        String(Math.round(units * 100) / 100).replace(".", ",") + " u.";
    }
    syncSaveButton();
  }

  function refreshBudget() {
    if (!CFG.budgetUrl) return;
    var t = totals();
    var url = CFG.budgetUrl + "?category=" + encodeURIComponent(category) +
      "&amount=" + encodeURIComponent(t.ht);
    if (CFG.exclude) url += "&exclude=" + encodeURIComponent(CFG.exclude);

    fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) { renderBudget(data); })
      .catch(function () { /* statistique non critique */ });
  }

  function renderBudget(data) {
    var stateLabels = {
      ok: "Sain", warn: "Alerte 80 %", critical: "Critique 90 %",
      over: "Plafond atteint", none: "Sans plafond"
    };
    var badge = $("budget-state");
    var gauge = $("budget-gauge");
    var state = data.state || "none";
    badge.className = "badge " + state;
    badge.textContent = stateLabels[state] || "—";
    gauge.dataset.state = state;

    var rate = data.rate === null || data.rate === undefined ? 0 : data.rate;
    var width = Math.min(100, Math.max(0, rate * 100));
    var fill = gauge.querySelector("span");
    if (fill) fill.style.width = width.toFixed(1) + "%";

    $("b-plafond").textContent =
      data.plafond === null || data.plafond === undefined ? "Illimité" : money(data.plafond);
    $("b-consumed").textContent = money(data.consumed);
    $("b-document").textContent = money(data.document);
    $("b-remaining").textContent =
      data.remaining === null || data.remaining === undefined ? "—" : money(data.remaining);

    var notice = $("budget-notice");
    notice.innerHTML = "";
    if (!data.has_exercice) {
      blocked = true;
      notice.innerHTML =
        '<div class="notice block"><strong>Aucun exercice actif</strong> pour ' +
        "cette convention : l'enregistrement est bloqué tant qu'un exercice " +
        "n'est pas ouvert." +
        '<div style="margin-top:10px">' +
        '<a class="btn btn-primary btn-sm" href="/conventions?category=' +
        encodeURIComponent(category) + '">Ouvrir un exercice</a></div></div>';
    } else if (data.blocked) {
      blocked = true;
      notice.innerHTML =
        '<div class="notice block"><strong>Blocage plafond :</strong> ' +
        "consommé (" + money(data.consumed) + " DA) + cette commande (" +
        money(data.document) + " DA) atteint ou dépasse le plafond (" +
        money(data.plafond) + " DA). L'enregistrement est refusé.</div>";
    } else {
      blocked = false;
      if (state === "critical" || state === "warn") {
        notice.innerHTML =
          '<div class="notice warn">Attention : il ne reste que ' +
          money(data.remaining) + " DA sur cet exercice.</div>";
      }
    }
    syncSaveButton();
  }

  function syncSaveButton() {
    if (!saveBtn) return;
    var hint = $("save-hint");
    var empty = cart.length === 0;
    saveBtn.disabled = blocked || empty;
    if (!busy) saveBtn.innerHTML = saveLabel;
    if (hint) {
      if (empty) hint.textContent = "Ajoutez au moins une ligne.";
      else if (blocked) hint.textContent = "Enregistrement bloqué (plafond ou exercice).";
      else hint.textContent = "";
    }
  }

  /* ------------------------------------------------- interactions DOM */
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(loadArticles, 160);
    });
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        moveSelection(event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Enter") {
        event.preventDefault();
        addActive();
      }
    });
  }

  if (resultsBox) {
    resultsBox.addEventListener("dblclick", function (event) {
      if (event.target.closest("[data-add]")) return;
      var row = event.target.closest(".result");
      if (row) addIndex(parseInt(row.dataset.index, 10));
    });
    resultsBox.addEventListener("click", function (event) {
      var add = event.target.closest("[data-add]");
      if (add) {
        addIndex(parseInt(add.dataset.add, 10));
        if (searchInput) searchInput.focus();
        return;
      }
      var row = event.target.closest(".result");
      if (row) {
        activeIndex = parseInt(row.dataset.index, 10);
        renderResults();
      }
    });
  }

  if (cartBody) {
    cartBody.addEventListener("input", function (event) {
      var input = event.target.closest("[data-qty]");
      if (!input) return;
      var index = parseInt(input.dataset.qty, 10);
      var value = parseFloat(
        String(input.value).replace(/\u00a0/g, "").replace(/\s/g, "").replace(",", ".")
      );
      if (!isFinite(value) || value <= 0) return;
      cart[index].quantity = value;
      var row = input.closest("tr");
      if (row) {
        var cell = row.children[4];
        if (cell) cell.textContent = money(lineTotal(cart[index]));
      }
      var t = totals();
      $("t-ht").textContent = money(t.ht);
      $("t-tva").textContent = money(t.tva);
      $("t-ttc").textContent = money(t.ttc);
      clearTimeout(budgetTimer);
      budgetTimer = setTimeout(refreshBudget, 300);
    });
    cartBody.addEventListener("change", function () { refreshBudget(); });
    cartBody.addEventListener("click", function (event) {
      var button = event.target.closest("[data-remove]");
      if (!button) return;
      cart.splice(parseInt(button.dataset.remove, 10), 1);
      renderCart();
      refreshBudget();
    });
  }

  /* (choix de la convention : voir l'assistant étape 1 ci-dessus) */

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      if (!cart.length) return;
      if (!window.confirm("Vider la commande (toutes les lignes) ?")) return;
      cart = [];
      renderCart();
      refreshBudget();
    });
  }

  function moveSelection(delta) {
    if (!results.length) return;
    activeIndex = (activeIndex + delta + results.length) % results.length;
    renderResults();
    var node = resultsBox.querySelector(".result.active");
    if (node) node.scrollIntoView({ block: "nearest" });
  }

  function addIndex(index) {
    var article = results[index];
    if (!article) return;
    addArticle(article, qtyValue());
  }

  function addActive() { addIndex(activeIndex); }

  /* ------------------------------------------------------- sauvegarde */
  function payload(acceptNewPrices) {
    return {
      category: category,
      items: cart.map(function (item) {
        return {
          article_id: item.article_id,
          item_id: item.item_id || null,
          code: item.code,
          designation: item.designation,
          unit: item.unit,
          unit_price_ht: item.unit_price_ht,
          quantity: item.quantity
        };
      }),
      accept_new_prices: !!acceptNewPrices
    };
  }

  function showError(error, context) {
    var notice = $("form-notice");
    var type = error.payload && error.payload.type;
    if (type === "price_conflict") {
      openPriceDialog(error.payload.conflicts || []);
      return;
    }
    if (type === "missing_articles") {
      var missingIds = (error.payload.missing || []).map(function (m) {
        return m.article_id;
      });
      cart = cart.filter(function (item) {
        return missingIds.indexOf(item.article_id) === -1;
      });
      renderCart();
      refreshBudget();
      if (notice) {
        notice.innerHTML = '<div class="notice warn">Article(s) retiré(s) : ' +
          "ils n'existent plus dans la liste. Vérifiez puis ré-enregistrez.</div>";
      }
      window.toast("Certains articles ont disparu de la liste et ont été retirés.",
        "error");
      return;
    }
    if (type === "missing_exercice") {
      var target = error.payload.category || category;
      var label = error.payload.exercice_label || "";
      if (notice) {
        notice.innerHTML = '<div class="notice block">' +
          "<strong>Exercice indisponible :</strong> " + escapeHtml(error.message) +
          '<div style="margin-top:10px">' +
          '<a class="btn btn-primary btn-sm" href="/conventions?category=' +
          encodeURIComponent(target) + '">Ouvrir / choisir un exercice</a>' +
          "</div></div>";
      }
      window.toast(error.message, "error");
      void label;
      return;
    }
    if (notice) {
      notice.innerHTML = '<div class="notice block">' +
        escapeHtml(error.message) + "</div>";
    }
    if (error.status === 400 && error.payload && error.payload.error === "csrf") {
      window.toast(
        "Session expirée : jeton de sécurité renouvelé, réessayez.", "error"
      );
    } else if (context === "preview" && error.status === 409) {
      /* message déjà affiché */
    } else {
      window.toast(error.message, "error");
    }
  }

  function openPriceDialog(conflicts) {
    var body = $("price-body");
    var rows = conflicts.map(function (c) {
      return "<tr><td class='mono'>" + escapeHtml(c.code) + "</td>" +
        "<td>" + escapeHtml(c.designation) + "</td>" +
        "<td class='num'>" + money(c.old_price) + "</td>" +
        "<td class='num'>" + money(c.new_price) + "</td></tr>";
    }).join("");
    body.innerHTML =
      '<div class="notice warn">Les prix de certains articles ont changé ' +
      "depuis la création de la commande. Choisissez si vous souhaitez reprendre " +
      "les prix de la liste actuelle.</div>" +
      '<div class="table-wrap"><table class="table"><thead><tr><th>N°</th>' +
      "<th>Désignation</th><th class='num'>Ancien prix</th>" +
      "<th class='num'>Nouveau prix</th></tr></thead><tbody>" + rows +
      "</tbody></table></div>";
    priceDialog.showModal();
  }

  var acceptPrices = $("price-accept");
  if (acceptPrices) {
    acceptPrices.addEventListener("click", function () {
      priceDialog.close();
      doPreview(true);
    });
  }

  function doPreview(acceptNewPrices) {
    if (busy) return;
    busy = true;
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="spinner"></span> Vérification…';
    }
    gaFetch(CFG.previewUrl, { json: payload(!!acceptNewPrices), csrf: currentCsrf() })
      .then(function (preview) {
        busy = false;
        renderCart();
        renderRecap(preview);
        goStep(3);
      })
      .catch(function (error) {
        busy = false;
        renderCart();
        showError(error, "preview");
      });
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      if (!cart.length || saveBtn.disabled || busy) return;
      doPreview(false);
    });
  }

  function renderRecap(preview) {
    var badge = $("recap-number");
    var body = $("recap-body");
    var number = preview.number || CFG.number;
    if (badge) badge.textContent = number || "—";
    var rows = preview.lines.map(function (line) {
      return "<tr><td class='mono'>" + escapeHtml(line.code) + "</td>" +
        "<td>" + escapeHtml(line.designation) +
        '<div class="hint">' + escapeHtml(line.unit) + "</div></td>" +
        '<td class="num">' + money(line.unit_price_ht) + "</td>" +
        '<td class="num">' + String(line.quantity).replace(".", ",") + "</td>" +
        '<td class="num">' + money(Math.round(line.quantity * line.unit_price_ht * 100) / 100) +
        "</td></tr>";
    }).join("");

    body.innerHTML =
      '<div class="recap-meta">' +
      '<div class="field"><label>N° de commande</label><strong class="mono">' +
      escapeHtml(number || "—") + "</strong></div>" +
      '<div class="field"><label>Date</label><strong>' +
      escapeHtml(new Date().toLocaleDateString("fr-FR")) + "</strong></div>" +
      '<div class="field"><label>Convention</label><strong>' +
      escapeHtml(preview.category) + "</strong></div>" +
      '<div class="field"><label>Exercice</label><strong>' +
      escapeHtml(preview.exercice_label) + "</strong></div>" +
      "</div>" +
      '<div class="table-wrap"><table class="table"><thead><tr><th scope="col">N°</th>' +
      "<th scope='col'>Désignation</th><th scope='col' class='num'>PU HT</th>" +
      "<th scope='col' class='num'>Qté</th>" +
      "<th scope='col' class='num'>Total HT</th></tr></thead><tbody>" + rows +
      "</tbody></table></div>" +
      '<div class="totals" style="max-width:320px;margin-left:auto">' +
      '<div class="line"><span>Total HT</span><strong>' + money(preview.total_ht) + " DA</strong></div>" +
      '<div class="line"><span>TVA ' + Math.round(0.19 * 100) + " %</span><strong>" +
      money(preview.tva_amount) + " DA</strong></div>" +
      '<div class="line grand"><span>Total TTC</span><strong>' +
      money(preview.total_ttc) + " DA</strong></div>" +
      "</div>" +
      '<div class="notice info">L\'enregistrement écrit dans l\'historique et ' +
      "génère le PDF et l'Excel dans le dossier documents_pdf/web. " +
      (CFG.mode === "new"
        ? "Vérifiez les lignes : le retour en arrière conserve le panier."
        : "Vérifiez les modifications avant de confirmer.") + "</div>";

    var confirm = $("confirm-btn");
    if (confirm) {
      confirm.innerHTML = (CFG.mode === "new" ? "Confirmer et enregistrer la commande" : "Confirmer les modifications");
    }
  }

  var confirmBtn = $("confirm-btn");
  if (confirmBtn) {
    confirmBtn.addEventListener("click", function () {
      doSave(false);
    });
  }

  function doSave(acceptNewPrices) {
    if (busy) return;
    busy = true;
    var actionBtn = $("confirm-btn") || saveBtn;
    var actionLabel = actionBtn ? actionBtn.innerHTML : "";
    if (actionBtn) {
      actionBtn.disabled = true;
      actionBtn.innerHTML = '<span class="spinner"></span> Enregistrement…';
    }
    if (saveBtn && actionBtn !== saveBtn) saveBtn.disabled = true;
    gaFetch(CFG.saveUrl, { json: payload(acceptNewPrices), csrf: currentCsrf() })
      .then(function (result) {
        busy = false;
        window.toast(
          "Commande " + result.number + " enregistrée (PDF + Excel).", "success"
        );
        if (CFG.mode === "new") {
          window.location.href =
            CFG.historyUrl + "?doc=" + encodeURIComponent(result.id);
        } else {
          window.location.href = CFG.detailUrl ||
            CFG.historyUrl + "?doc=" + encodeURIComponent(result.id);
        }
      })
      .catch(function (error) {
        busy = false;
        if (actionBtn) {
          actionBtn.disabled = false;
          actionBtn.innerHTML = actionLabel;
        }
        renderCart();
        showError(error, "save");
        goStep(2);
      });
  }

  /* ------------------------------------------------------------- départ */
  syncStep1();
  goStep(step);
  renderCart();
  loadArticles();
  refreshBudget();
  if (qtyInput) {
    qtyInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        addActive();
        if (searchInput) searchInput.focus();
      }
    });
  }
})();

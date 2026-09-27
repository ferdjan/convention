# Contexte projet — édition web « Gestion Articles »

> Document de reprise pour un assistant IA (ou un développeur) qui reprendrait le
> projet. Pour l'utilisateur final, voir [`README.md`](README.md).
>
> État au 27/09/2026 — phases 1 → 7 terminées, puis phases correctives :
> Ph1 (déblocage ajout document : gaFetch POST, bouton +, ExerciceManquant),
> Ph2 (suivi : dashboard segmenté, fiche convention, rapports année civile +
> année convention, assistant 3 étapes), Ph3 (2 thèmes clair/sombre, CSS/a11y),
> puis correctifs d'import : `enctype="multipart/form-data"` manquant sur le
> formulaire (aucun fichier n'arrivait au serveur) + `sheet_map` inversée dans
> `import_commit` (cible ≠ feuille → « Feuille introuvable »).
> Puis vocabulaire « document » → « commande » dans toute l'interface
> (URLs, base et code technique inchangés) + correctif du bouton de
> vérification vidé par `saveLabel` capturé avant l'assignation de `saveBtn`.
> Vérifications vertes (smoke 83/83, E2E Chrome headless sans erreur).

---

## 1. Objectif
Réimplémenter en web l'application de bureau *Gestion Articles — Conventions & Commandes*
(dépôt `C:\Users\FERDJANI\Desktop\convention`) dans le sous-dossier `web-app/`.

Contraintes validées avec l'utilisateur :

- **Flask + Jinja + CSS/JS locaux** (aucun CDN, aucun build npm) ;
- **100 % hors-ligne**, **monoposte** : serveur sur `127.0.0.1:8765` ;
- **aucun mot de passe** ni compte (l'accès est physique) ;
- base **dédiée** `web_app.db`, créée vide puis peuplée par import de
  `source_listes.xlsx` (pas de migration des données du poste de bureau) ;
- documents produits dans `documents_pdf/web/` (PDF + Excel).

Phases 1 → 7 (structure/DB, layout/dashboard, saisie document, historique/édition,
conventions/imports, rapports/paramètres, sécurité/tests/README) : **terminées**.

## 2. Stack & environnement
- Python `C:\Python314\python.exe` (3.14) — **installé** : Flask 3.1.3, Werkzeug,
  Jinja2, openpyxl 3.1.5, reportlab 4.5.1, itsdangerous, **pyflakes 4.0.0**,
  **node v24.19.1**.
- **Non installés / à ne pas utiliser** : `waitress`, `pytest`
  (les tests passent par `flask.test_client()`).

## 3. Arborescence (fichiers clés)
```
web-app/
├─ run.bat              # LANCEUR (CRLF obligatoires, ASCII sans BOM)
├─ serve.py             # serveur local ; refus de tout hôte ≠ 127.0.0.1/localhost/::1
├─ requirements.txt  README.md  .gitignore
├─ web_app.db           # base SQLite (393 articles importés)
├─ .session.key         # clé de session locale
├─ app/
│  ├─ __init__.py       # create_app(), filtres Jinja, globals, handlers erreurs, CLI
│  ├─ config.py         # chemins, TVA_RATE=0.19, seuils, 5 THEMES, HOST/PORT
│  ├─ security.py       # CSRF, en-têtes, safe_export_path, filename_safe
│  ├─ database.py       # ~1475 l. : schéma, règles métier, contrôles
│  ├─ importer.py       # lecture/écriture .xlsx (zipfile + XML, pas openpyxl en lecture)
│  ├─ utils.py          # parse_price/quantity, compute_totals, format_*
│  ├─ routes/           # api, conventions, dashboard, documents, files, history,
│  │                    #        reports, settings
│  ├─ services/documents.py  # create/update_document, free_number, exports
│  ├─ reports/          # pdf.py, excel.py, annual.py (copiés de l'édition bureau)
│  ├─ templates/        # base, dashboard, document_form, document_detail, history,
│  │                    #          conventions, import_preview, reports, settings,
│  │                    #          error, _icons
│  └─ static/           # css/{themes,app}.css, js/{theme,app,document,history,
│                       #        conventions,import_preview,reports,settings}.js,
│                       #        img/favicon.svg
├─ tests/smoke_test.py  # 61 vérifications, executed dans un dossier temporaire
└─ tools/gen_themes.py  # régénère static/css/themes.css
```

## 4. Règles métier (à préserver)
- **Prix figés** : le prix est toujours relu en base ; écart > 0.0001 → `ConflitPrix`
  → dialogue « les prix ont changé » + `accept_new_prices`.
- **Numérotation** `PRÉFIXE-EXERCICE-0001` via `free_number()` (libre en base **et**
  sur disque, avec incrément).
- **Plafond** : blocage si `consommé + document >= plafond` (égalité incluse) ;
  message écrit **une seule fois** (`Database._assert_within_plafond`).
- **Un seul exercice actif** par convention ; la clôture archive
  `consumed_at_close` / `remaining_at_close`.
- **Convention fermée ou expirée** → refus côté base (`_validate_category_open`,
  `effective_status`).
- **Totaux** : HT = somme des totaux de ligne **arrondis** (garantit la cohérence
  affichage / PDF / Excel) ; TVA 19 %.
- **Séquence d'écriture** : `preview_document` (validation, zéro écriture) →
  génération en `.tmp` → remplacement → base en une transaction ; en cas d'échec,
  suppression des nouveaux fichiers (création) ou restauration des `.bak`
  (modification) — jamais de divergence fichier / base.

## 5. Points d'implémentation importants (pièges connus)
1. **Attributs sur dictionnaires dans Jinja** : `dict.x` fonctionne, **sauf si `x`
   est une méthode** (`items`, `values`, `get`…). Écrire `preview["items"]`.
2. **CSP stricte** (`script-src 'self'`) : **interdits** — `onclick=`, `onchange=`,
   `href="javascript:…"`, `<script>` inline, tout CDN. Passer par un fichier JS
   local. Les styles inline (`style="…"`) sont tolérés (`style-src 'unsafe-inline'`).
3. **`sqlite3.Row`** : pas d'attributs ; Jinja retombe sur `row["col"]` — mais
   `row.items` casserait (cf. point 1).
4. **Chemins figés à l'import** : `services/documents.py` fait
   `from app.config import EXPORT_DIR` ; les tests doivent patcher `cfg.EXPORT_DIR`
   **et** `documents_service.EXPORT_DIR/TMP_DIR`.
5. **`run.bat`** : fins de ligne **CRLF** + ASCII sans BOM. Une parenthèse `)`
   dans un `echo` placé dans un bloc `if ( … )` ferme le bloc (bug déjà rencontré
   et corrigé).
6. **Console Windows cp1252** : `serve.py` et `tests/smoke_test.py` forcent
   `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` ; ne pas afficher
   `→` ailleurs.
7. **Shell de travail = PowerShell** : pas d'heredoc `<<` ; préférer les outils
   `write`/`edit` aux cmdlets de contenu.

## 6. Sécurité
- **CSRF** sur **toutes** mutations (meta `csrf-token` + en-tête `X-CSRF-Token`
  ou champ `csrf_token` du body).
- En-têtes : CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`,
  `Permissions-Policy`, `COOP`.
- Cookie de session HttpOnly / SameSite=Lax ; clé dans `.session.key` local.
- Téléchargements uniquement via `/files/<id>/<kind>` avec `safe_export_path`
  (chemins **relatifs** en base, refus de `..`, des absolus et des traversées).
- `serve.py` refuse tout hôte non local ; `debug=False` par défaut.

## 7. Commandes de vérification
```bat
python -m pyflakes app serve.py tests      :: propre
python -m compileall -q app serve.py tests
node --check app\static\js\*.js             :: 8 fichiers OK
python tests\smoke_test.py                 :: 61/61
python serve.py                            :: http://127.0.0.1:8765
```
Le test de fumée couvre : pages, en-têtes de sécurité, refus CSRF, API
articles/budget/prévisualisation, création (PDF + Excel réellement produits),
téléchargements, anti-traversée de chemin, blocage de plafond (409), modification,
clôture d'exercice, rapports, sauvegarde, modèle vierge, import Excel indexé,
suppressions, formulaires conventions.

## 8. État & points non validés
- **Validé** : `pyflakes` / `compileall` / `node --check` propres, smoke test
  61/61, serveur réel répondant 200 sur `/`, `/conventions`, `/settings`, `run.bat`
  exécuté sans erreur (code 0).
- **Non validé visuellement** : aucun navigateur ni Playwright n'est disponible
  → le rendu, les dialogues `<dialog>`, la grille de thèmes, le pré-remplissage de
  `conventions.js` (édition d'exercice) et la navigation clavier du catalogue
  **n'ont pas été testés à l'écran**. À vérifier en priorité en cas de reprise.
- Rappel de cohérence : en mode **édition**, ré-enregistrer un document dont le
  total atteint exactement le plafond est refusé (comportement identique à
  l'édition bureau).
- `init_schema()` crée toujours deux conventions par défaut (`Informatique`,
  `Bureautique`) ; le bouton « Importer source_listes.xlsx » de l'écran
  Conventions n'apparaît que si `article_count() == 0`.

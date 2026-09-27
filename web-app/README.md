# Gestion Articles — édition web

Équivalent web de l'application de bureau *Gestion Articles — Conventions & Commandes* :
même métier, même vocabulaire, interface moderne, **monoposte et 100 % hors-ligne**
(aucun CDN, aucun service externe, aucun compte).

- Serveur local uniquement : `http://127.0.0.1:8765`
- Base SQLite dédiée : `web_app.db`
- Commandes produites : `documents_pdf/web/` (PDF + Excel)
- Aucun mot de passe : l'accès est physique (la machine)

---

## 1. Démarrage rapide

Prérequis : **Python 3.10+** avec les paquets de `requirements.txt`
(Flask, openpyxl, reportlab).

```bat
run.bat
```

Le script détecte Python, installe les dépendances si besoin, crée la base au
premier lancement, importe `source_listes.xlsx` puis ouvre le navigateur.

Démarrage manuel équivalent :

```bat
python -m flask --app app init-db
python -m flask --app app import-seed
python serve.py
```

Options utiles :

```bat
python serve.py --port 8080      # autre port
python serve.py --dev            # rechargement automatique (développement)
```

`serve.py` refuse tout hôte autre que `127.0.0.1` / `localhost` / `::1`.

---

## 2. Ce que fait l'application

| Écran | Adresse | Rôle |
| --- | --- | --- |
| Tableau de bord | `/` | jauges de plafond par convention, alertes 80/90 %, raccourcis |
| Nouvelle commande | `/documents/new` | recherche d'articles, panier, totaux, récapitulatif, enregistrement |
| Historique | `/history` | filtres, aperçu de la commande, PDF / Excel / export, modification, suppression |
| Conventions | `/conventions` | statut, échéance, exercices, plafonds, import Excel, modèle vierge |
| Rapport | `/reports` | consommation par convention pour un exercice + export Excel |
| Paramètres | `/settings` | thème, compteurs, sauvegarde de la base, à propos |

### Règles métier (reprises de l'édition bureau)

- **Prix figés** : le prix est toujours relu en base ; un écart déclenche le
  dialogue « Les prix ont changé » (reprendre les prix actuels ou annuler).
- **Numérotation** : `PRÉFIXE-EXERCICE-0001`, libre en base **et** sur le disque.
- **Plafond** : `consommé + commande >= plafond` **bloque** l'enregistrement
  (égalité incluse). Les alertes s'affichent à 80 % et 90 %.
- **Exercice actif unique** par convention ; un exercice clôturé archive son
  consommé et interdit toute nouvelle saisie.
- **Convention fermée ou expirée** : saisie refusée côté serveur.
- **Totaux** : total HT = somme des totaux de ligne arrondis, identique à
  l'affichage, au PDF et à l'Excel. TVA 19 %.
- **Séquence d'écriture** : validation sans écriture → génération des fichiers →
  base en une transaction ; en cas d'échec, les fichiers sont supprimés ou
  restaurés (jamais de divergence fichier / base).

---

## 3. Structure du projet

```
web-app/
├── run.bat                 # lancement double-clique (Windows)
├── serve.py                # serveur local 127.0.0.1:8765
├── requirements.txt
├── web_app.db              # base SQLite (créée au premier lancement)
├── app/
│   ├── __init__.py         # fabrique Flask, filtres Jinja, erreurs, CLI
│   ├── config.py           # chemins, TVA, seuils, thèmes, port
│   ├── security.py         # CSRF, en-têtes, résolution de fichiers
│   ├── database.py         # schéma, règles métier, contrôles
│   ├── importer.py         # lecture/écriture des classeurs Excel
│   ├── routes/             # blueprints (pages + API JSON)
│   ├── services/documents.py  # création/modification, PDF, Excel, numéros
│   ├── reports/            # générateurs PDF, Excel, rapport annuel
│   ├── templates/          # Jinja (thème unique `base.html`)
│   └── static/             # CSS et JS locaux (aucun CDN)
├── tests/smoke_test.py     # test de fumée complet (aucune dépendance)
├── tools/gen_themes.py     # régénère static/css/themes.css
└── CONTEXTE.md             # contexte projet / architecture (reprise par un tiers ou une IA)
```

---

## 4. Import des listes de prix

Feuilles attendues (en-têtes exacts) :

| N° | Désignation | Unité de mesure | Prix unitaire HT |
| --- | --- | --- | --- |

Deux façons d'importer :

1. **Conventions → Importer une liste** : choix du classeur, prévisualisation des
   feuilles, convention de destination par feuille.
   Une feuille vers une convention existante **remplace** sa liste ; une feuille
   vers une convention inconnue **crée** une nouvelle liste.
2. **Paramètres → Importer `source_listes.xlsx`** : import direct du classeur
   fourni avec le projet.

Le **modèle Excel vierge** (`Conventions → Modèle Excel`) respecte ces en-têtes.

---

## 5. Sécurité

- Liaison **127.0.0.1 uniquement**, `debug` désactivé en production.
- **CSRF** obligatoire sur toute mutation (formulaires et API JSON) : le jeton est
  porté par le balise `<meta name="csrf-token">` et envoyé en en-tête
  `X-CSRF-Token` ou dans le corps.
- **En-têtes** : CSP stricte (`script-src 'self'`), `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `COOP`.
- **Fichiers** : téléchargements via `/files/<id>/<kind>` ; les chemins stockés en
  base sont relatifs et vérifiés contre le dossier d'export (anti-`../`).
- **Clé de session** : fichier local `.session.key`, jamais versionné.
- Aucune donnée n'est envoyée hors de la machine.

---

## 6. Tests et contrôles

```bat
python tests\smoke_test.py     :: 61 vérifications (pages, CSRF, plafond, import…)
python -m pyflakes app serve.py tests
node --check app\static\js\*.js
```

Le test de fumée utilise `flask.test_client()` dans un dossier temporaire :
aucune donnée réelle n'est touchée.

---

## 7. Sauvegarde et restauration

- **Paramètres → Sauvegarde de la base** : copie SQLite cohérente (`VACUUM INTO`)
  téléchargée immédiatement.
- **CLI** : `python -m flask --app app backup` crée
  `web_app-backup-AAAAMMJJ-HHMMSS.db` à côté de l'application.
- Restauration : arrêter l'application, remplacer `web_app.db` par la copie,
  relancer.

Les PDF/Excel générés sont de simples fichiers : ils peuvent être copiés tels quels.

---

## 8. Dépannage

| Symptôme | Cause probable | Solution |
| --- | --- | --- |
| `Address already in use` | port 8765 occupé | `python serve.py --port 8766` |
| Page blanche / `TemplateNotFound` | dossier `app/templates` incomplet | vérifier l'intégrité des fichiers |
| « Aucun exercice actif » | convention sans exercice | Conventions → *Ouvrir un exercice* |
| Enregistrement bloqué | plafond atteint | augmenter le plafond ou clôturer l'exercice |
| Import refusé | en-têtes de colonnes différents | utiliser le modèle Excel fourni |
| Dépendances manquantes | `pip` absent | `python -m pip install -r requirements.txt` |

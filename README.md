# Gestion Articles — Conventions & Commandes

Application **Windows hors ligne** de gestion des conventions et de leurs commandes
d'articles. Chaque **convention** possède une liste d'articles à **prix figés**
pendant toute sa période, se découpe en **exercices annuels** (périodes
configurables, ex. du 15-08-2026 au 14-08-2027) avec un **plafond** à ne pas
dépasser. L'application enregistre chaque commande, en assure la traçabilité
(n° unique, date, lignes, PDF + Excel archivés) et déclenche des **alertes** à
80 %, 90 % et 100 % du plafond, **par exercice** — y compris consultation des
exercices passés. Aucune connexion Internet n'est requise.

---

## 1. Objectif

Le besoin fonctionnel :

1. Importer la liste des articles d'une convention depuis Excel.
2. Choisir la convention, puis l'exercice courant (période + plafond).
3. Rechercher un article par N°, désignation ou unité.
4. Ajouter plusieurs articles au document, saisir une quantité.
5. Calculer automatiquement :

```text
Total ligne = Prix unitaire HT × Quantité
Total document HT = Somme des totaux de lignes
TVA (19 %) = Total HT × 0,19
Total TTC = Total HT + TVA
```

6. Contrôler le plafond de l'exercice : alertes à 80 % / 90 %, **blocage ferme à 100 %**.
7. Enregistrer le document (PDF + Excel + historique) en une transaction.
8. Consulter l'historique, filtré par convention et exercice.
9. Générer un rapport de consommation par exercice (Excel).

Les prix d'une convention sont **figés pendant tout l'exercice** : ils ne changent
que par import d'une nouvelle liste, au nouvel exercice.

---

## 2. Technologies

- **Python 3.11+**
- **Tkinter / ttk** : interface graphique Windows (barre latérale + écrans)
- **SQLite** : base de données locale
- **ReportLab** : génération des PDF
- **Open XML / XLSX** : lecture directe du classeur Excel sans Microsoft Excel
- **openpyxl** : génération des fichiers `.xlsx` (documents, modèle, rapports)
- **PyInstaller** : création d'une version `.exe`

Ni serveur web, ni connexion Internet, ni base distante.

---

## 3. Structure du projet

```text
GestionArticles/
│
├── main.py                 # Point d'entrée (démarre app.ui.app)
├── seed_db.py              # Import manuel du fichier source dans SQLite
│
├── app/
│   ├── config.py           # Configuration (chemins, TVA, seuils, thèmes)
│   ├── database.py         # SQLite : schéma, exercices, migration, documents
│   ├── utils.py            # Prix, dates, totaux et formats
│   ├── reports/
│   │   ├── pdf.py          # Documents PDF
│   │   ├── excel.py        # Documents Excel (.xlsx)
│   │   └── annual.py       # Rapport de consommation par exercice (.xlsx)
│   ├── services/
│   │   └── importer.py     # Lecture/import Excel + génération du modèle vierge
│   └── ui/
│       ├── app.py          # Fenêtre : barre latérale, en-tête, orchestration
│       ├── theme.py        # Style ttk, thèmes clair/sombre, jauge budget
│       ├── common.py       # Utilitaires UI (montants, dates, fichiers)
│       ├── views/
│       │   ├── dashboard.py    # Tableau de bord (cartes par convention)
│       │   ├── document.py     # Nouveau document (panier, exercice, blocage)
│       │   ├── history.py      # Historique (filtres convention + exercice)
│       │   ├── conventions.py  # Conventions et exercices (intégré)
│       │   ├── reports.py      # Rapport de consommation
│       │   └── settings.py     # Thème, TVA, à propos
│       └── dialogs/        # Fenêtres modales autonomes
│           ├── confirm.py       # Récapitulatif + blocage plafond
│           ├── conventions.py   # Édition statut / exercice / clôture
│           ├── categories.py    # Suppression d'une liste
│           ├── importer.py      # Choix de la feuille et du nom de liste
│           ├── documents.py     # Détail des lignes d'un document
│           ├── edition.py       # Modification des lignes d'un document
│           └── help.py          # Rappel du format Excel
│
├── source_listes.xlsx      # Classeur Excel contenant les listes initiales
├── gestion_articles.db     # Base SQLite locale (créée/utilisée par l'application)
├── documents_pdf/          # PDF et Excel générés par l'application
│
├── run.bat                 # Lance l'application en mode Python
├── build.bat               # Construit la version Windows avec PyInstaller
├── requirements.txt        # Dépendances Python
└── README.md               # Documentation du projet
```

### Rôle des fichiers principaux

#### `main.py`
Point d'entrée minimal : il appelle `run()` depuis `app/ui/app.py` et affiche
l'écran « Démarrage impossible » si la base ne peut pas être ouverte ou migrée.

#### `app/ui/app.py`
Fenêtre principale : **barre latérale** de navigation (6 écrans), en-tête avec
titre/sous-titre, bascule clair/sombre, et orchestration des vues.

#### `app/ui/views/dashboard.py` — Tableau de bord
Une carte par convention active : exercice courant (libellé + période), jauge
colorée, plafond/consommé/reste, état d'alerte et bouton « Nouveau document ».

#### `app/ui/views/document.py` — Nouveau document
Tient l'état du document en cours : recherche, panier, calcul HT/TVA/TTC,
contrôle du plafond de l'exercice courant, et enregistrement (PDF + Excel +
base) en une opération. **Le bouton d'enregistrement se désactive quand
« consommé + ce document » atteint le plafond.**

#### `app/ui/views/history.py` — Historique
Recherche, filtres par convention et exercice, aperçu du document sélectionné,
ouverture PDF/Excel, export, **modification** et suppression.

#### `app/ui/dialogs/edition.py` — Modification d'un document
Fenêtre modale autonome : édition de la quantité au double-clic, retrait de ligne,
recherche / ajout d'articles, bandeau plafond en direct, récapitulatif, puis
régénération du PDF/Excel. Bloquée en lecture seule (exercice ou convention
clôturé).

#### `app/ui/views/conventions.py` — Conventions
Tableau de **toutes** les conventions (statut actif / clôturé / expiré, échéance,
exercice actif, plafond, consommé, reste) et, pour la convention sélectionnée,
liste de ses exercices (ouverture / clôture / édition).

#### `app/database.py`
Centralise SQLite : schéma, migration transactionnelle, exercices, articles,
numérotation des documents, enregistrement transactionnel (document + lignes +
fichiers), historique, rapports.

---

## 4. Base de données

Base locale : `gestion_articles.db`.

### Listes (conventions)

```text
nom
feuille Excel
préfixe de numérotation (INF, BUR, ...)
statut (actif / clôturé / expiré)
échéance (facultative, AAAA-MM-JJ)
```

Le statut affiché est **actif**, **clôturé** ou **expiré**. Une convention active
dont la date d'échéance est dépassée est automatiquement **expirée**. Une
convention expirée ou clôturée n'accepte plus de nouveau document.

Deux conventions sont créées par défaut sur une base neuve : `Informatique`
(préfixe `INF`) et `Bureautique` (préfixe `BUR`).

### Exercices

Chaque convention se découpe en exercices annuels :

```text
convention (catégorie)
libellé (ex. « 2026-2027 »)
date de début (ex. 2026-08-15)
date de fin   (ex. 2027-08-14)
plafond (NULL = illimité)
statut (active / closed)
instantané de clôture : consommé / reste / date de clôture
```

- **Un seul exercice actif par convention.**
- Le **consommé courant** est calculé dynamiquement (somme des documents de
  l'exercice, en HT).
- La **clôture** archive le cumul (consommé / reste) ; le **reste ne se reporte
  pas** : le nouvel exercice repart de zéro.
- Les exercices passés restent **consultables en lecture seule**.

### Articles

```text
catégorie, code, désignation, unité, prix unitaire HT
```

L'identité d'un article est `(catégorie, code, désignation, unité)` ; le prix
est figé pendant l'exercice et remplacé par import.

### Documents

```text
numéro (ex. INF-2026-2027-0001)
date
catégorie
exercice (libellé)
total HT, taux TVA (19 %), montant TVA, total TTC
chemin du PDF, chemin du fichier Excel
```

Le numéro est propre à chaque couple (convention, exercice) :
`<préfixe>-<libellé exercice>-<séquence>` (ex. `INF-2026-2027-0001`).

### Lignes de document

Copie du code, de la désignation, de l'unité et du prix au moment de la création :
l'historique reste fidèle même si la liste évolue.

### Migration

La migration est **transactionnelle** : toute erreur annule l'opération et la
base reste inchangée. Elle convertit les anciennes tables `budgets` /
`budget_archives` en exercices, rattache les documents existants à leur exercice,
et retire les anciennes tables (`audit_log`, `price_history`, `budgets`,
`budget_archives`) issues de la version précédente.

---

## 5. Lancer le projet en développement

Prérequis : **Python 3.11 ou supérieur**.

```powershell
python --version
python -m pip install -r requirements.txt
```

Démarrer :

```text
run.bat
```

ou :

```powershell
python main.py
```

---

## 6. Création de l'exécutable Windows

```text
build.bat
```

Résultat dans `dist\GestionArticles\`, exécutable principal `GestionArticles.exe`.
Distribuer l'ensemble du dossier généré, pas seulement le `.exe`.

---

## 7. Import des listes Excel

Le fichier `source_listes.xlsx` sert de source initiale. Import depuis l'écran
« Conventions » ou au premier lancement.

Chaque feuille contient quatre colonnes, dans cet ordre :

```text
N° | Désignation | Unité de mesure | Prix unitaire HT
```

Les libellés `Article`, `Désignation de l'Article`, `Unité de mesure`,
`Prix Unitaire (HT)` et `Prix HT` sont acceptés. Les prix doivent être finis et
positifs ou nuls. La ligne `TOTAL` est ignorée.

- L'import **remplace** la liste concernée ; les autres listes sont conservées.
- La suppression d'une liste efface ses articles et ses exercices, mais conserve
  les documents de l'historique.
- Un modèle vierge est disponible (une feuille par liste).

---

## 8. Règles fonctionnelles

### Exercice et plafond

- Chaque convention a des exercices annuels (période configurable) et un plafond
  par exercice ; un plafond non défini = illimité.
- Pendant la saisie, l'application affiche en permanence : **Plafond — Consommé —
  Ce document — Reste disponible**, avec une jauge colorée.
- Seuils d'alerte : **vert < 80 %**, **orange ≥ 80 %**, **rouge ≥ 90 %**,
  **rouge foncé ≥ 100 %** (constants `BUDGET_WARN`, `BUDGET_CRITICAL`,
  `BUDGET_BLOCK` dans `app/config.py`).
- **Blocage ferme à 100 %** : si « consommé + ce document » atteint ou dépasse le
  plafond, l'enregistrement est **refusé** (aucune exception, aucune
  justification). Le bouton se désactive et la base rejette l'écriture
  (double contrôle).

### Statut et clôture

- Une convention est **active** (accepte des documents), **clôturée** (plus
  aucun nouveau document) ou **expirée** (échéance dépassée : plus aucun
  nouveau document).
- L'écran « Conventions » liste **toutes** les conventions (sans filtre) avec
  leur statut et leur échéance.
- Un exercice est **actif** (saisie autorisée) ou **clôturé** (lecture seule).
- La clôture d'un exercice archive le cumul ; l'ouverture d'un nouvel exercice
  propose des dates glissantes (fin de l'ancien + 1 an) et un libellé suggéré.

### Prix

- Le prix unitaire HT provient de la liste importée ; il est **figé** pendant
  tout l'exercice et **non modifiable** pendant la saisie.
- Il n'évolue que par import d'une nouvelle liste, au nouvel exercice.

### Recherche et sélection

- `↓` / `↑` : sélectionner l'article suivant / précédent ; `Entrée` : ajouter.
- La quantité est décimale et remise à 1 après chaque ajout.

### Total

```text
Total ligne = Prix HT × Quantité
Total HT = Somme(Totaux des lignes)
TVA 19 % = Total HT × 0,19
Total TTC = Total HT + TVA
```

La TVA de 19 % s'applique à toutes les conventions. Aucune remise.

### Contrôle avant enregistrement

- **Cohérence des prix** : si une ligne ne correspond plus à la liste active, un
  écran propose de mettre à jour les prix / retirer les articles supprimés.
- **Récapitulatif** : N°, date, liste, détail des lignes, HT/TVA/TTC, état du
  plafond — l'enregistrement n'a lieu qu'après validation.
- **Blocage plafond** : impossible de valider si le plafond est atteint.
- Les fichiers PDF et Excel sont d'abord générés en temporaire ; document, lignes
  et chemins sont enregistrés dans une **seule transaction** — jamais de document
  partiel.

### Modification d'un document enregistré

- Bouton **« Modifier le document »** dans l'écran Historique : fenêtre dédiée
  avec le détail des lignes et la synthèse du plafond en direct.
- Quantité modifiable par double-clic (puis `Entrée`, `Échap` ou perte du focus) ;
  retrait de ligne ; recherche et ajout d'articles (cumul de quantité).
- **Lecture seule** si la convention est clôturée / expirée ou si son exercice est
  clôturé : le bouton est désactivé, avec le motif affiché.
- **Prix figés** : les lignes existantes gardent leur prix ; une ligne ajoutée prend
  le prix de la liste de l'exercice.
- **Blocage plafond ferme** : impossible d'enregistrer si
  `consommé hors document + nouveau total ≥ plafond` (le bouton est désactivé et
  le récapitulatif le rappelle).
- Après confirmation, la base est mise à jour en **une transaction unique**
  (UPDATE des lignes existantes — leurs identifiants sont conservés —,
  DELETE des lignes retirées, INSERT des lignes ajoutées) puis le **PDF et l'Excel
  sont régénérés aux mêmes chemins** et écrasés. Si l'une des deux opérations
  échoue, les anciens fichiers sont restaurés.
- Aucune trace de modification n'est conservée (pas de colonne « modifié le »).

---

## 9. Historique

Chaque document possède un numéro unique, une date, une convention, un exercice,
des lignes détaillées, un total HT/TVA/TTC et des liens PDF/Excel.

L'écran **Historique** permet de :

- rechercher (texte) et **filtrer par convention et par exercice** ;
- prévisualiser le document sélectionné (lignes + synthèse HT/TVA/TTC) ;
- ouvrir le PDF ou l'Excel associé ;
- exporter un document en Excel ;
- **modifier un document** (quantités, lignes retirées, lignes ajoutées) puis
  enregistrer : les totaux et le plafond sont recalculés, le PDF/Excel régénéré ;
- supprimer un document (ses lignes sont supprimées, les fichiers restent sur le disque).

---

## 10. Où modifier le projet ?

| Besoin | Fichier principal |
|---|---|
| Barre latérale, en-tête, navigation, écrans | `app/ui/app.py` |
| Tableau de bord (cartes par convention) | `app/ui/views/dashboard.py` |
| Saisie d'un document (panier, plafond, totaux) | `app/ui/views/document.py` |
| Historique (filtres, aperçu) | `app/ui/views/history.py` |
| Modification d'un document enregistré | `app/ui/dialogs/edition.py` + `app/database.py` (`update_document`) |
| Conventions et exercices | `app/ui/views/conventions.py` + `app/ui/dialogs/conventions.py` |
| Rapport de consommation | `app/ui/views/reports.py` + `app/reports/annual.py` |
| Paramètres (thème, TVA) | `app/ui/views/settings.py` |
| Couleurs / thèmes | `app/ui/theme.py` + `app/config.py` (ajout d'un thème : `THEMES`) |
| Base de données / exercices / migration | `app/database.py` |
| Import Excel | `app/services/importer.py` |
| Mise en page PDF | `app/reports/pdf.py` |
| Mise en page Excel | `app/reports/excel.py` |
| Configuration / TVA / seuils | `app/config.py` |
| Utilitaires (prix, dates, totaux) | `app/utils.py` |
| Point d'entrée | `main.py` |
| Import initial | `seed_db.py` |
| Compilation EXE | `build.bat` |

---

## 11. Bonnes pratiques

1. Ne pas modifier `gestion_articles.db` sans sauvegarde préalable.
2. Conserver une copie de `source_listes.xlsx` avant tout nouvel import.
3. Sauvegarder `documents_pdf` et la base avant une évolution importante.
4. Ajouter les fonctionnalités par petites étapes, tester après chaque modification.
5. Mettre à jour ce README à chaque nouvelle fonctionnalité.

---

## 12. Principe général

```text
Excel
  ↓  import des articles (prix figés pour l'exercice)
SQLite (conventions, exercices, articles)
  ↓  choix de la convention + exercice courant
Recherche article
  ↓  quantité
Calcul Total HT / TVA 19 % / TTC
  ↓  contrôle du plafond (alertes 80/90 %, blocage 100 %)
Enregistrement transactionnel
  ↓
Historique SQLite + PDF + Excel
```

---

## 13. Version actuelle

**Version : 2.0**

Refonte majeure :

- **exercices annuels par convention** (période configurable, ex. 15-08-2026 →
  14-08-2027), un seul exercice actif, clôture avec archivage du cumul et reste
  remis à zéro ;
- **plafond par exercice** avec alertes 80 % / 90 % et **blocage ferme à 100 %**
  (aucune justification possible) ;
- numérotation `<préfixe>-<libellé exercice>-<séquence>` : `INF-2026-2027-0001` ;
- **suppression** du journal d'audit et de l'historique des prix ;
- **refonte visuelle** : barre latérale, tableau de bord, écrans Conventions /
  Rapport / Paramètres, thème **clair moderne par défaut** + mode sombre en un clic ;
- historique filtrable par convention et exercice ;
- **modification d'un document** depuis l'historique (quantités, retrait et ajout de
  lignes) avec recalcul du plafond et régénération du PDF/Excel ;
- rapport de consommation par exercice (Excel), ligne TOTAL corrigée.

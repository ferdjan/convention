# Gestion Articles — Informatique & Bureautique

Application **Windows hors ligne** permettant de sélectionner des articles à partir de plusieurs listes (Informatique, Bureautique, et toute autre liste ajoutée), de saisir les quantités, de calculer le total HT, la **TVA (19 %)** et le total TTC, d'enregistrer les documents dans un historique SQLite et de générer un **PDF et un fichier Excel**.

Le projet est volontairement simple et lisible afin de pouvoir être **repris, compris et amélioré** plus tard par un autre développeur ou par le propriétaire du projet.

---

## 1. Objectif du projet

Le besoin fonctionnel est le suivant :

1. Charger les articles des feuilles Excel `informatique` et `bureautique`.
2. Choisir la liste à utiliser avec une liste déroulante.
3. Rechercher un article par N°, désignation ou unité.
4. Ajouter plusieurs articles au document.
5. Saisir une quantité pour chaque article.
6. Calculer automatiquement :

```text
Total ligne = Prix unitaire HT × Quantité
Total document HT = Somme des totaux de lignes
TVA (19 %) = Total HT × 0,19
Total TTC = Total HT + TVA
```

7. Enregistrer le document dans l'historique.
8. Générer un **PDF** et un **fichier Excel** du document.
9. Ajouter d'autres listes et leur associer une feuille Excel (voir §7).
10. Fonctionner **sans Internet**.

### Données initiales

Le fichier fourni contient actuellement :

- **218 articles Informatique**
- **175 articles Bureautique**
- **393 articles exploitables au total**

La ligne `TOTAL` éventuelle en fin de feuille Bureautique n'est pas importée comme article.

---

## 2. Technologies utilisées

- **Python 3.11+**
- **Tkinter / ttk** : interface graphique Windows
- **SQLite** : base de données locale
- **ReportLab** : génération des PDF
- **Open XML / XLSX** : lecture directe du classeur Excel sans dépendre de Microsoft Excel
- **openpyxl** : génération des fichiers `.xlsx` (documents et modèle)
- **PyInstaller** : création d'une version `.exe`

Le projet ne nécessite ni serveur web, ni connexion Internet, ni base de données distante.

---

## 3. Structure du projet

```text
GestionArticles/
│
├── main.py                 # Interface graphique et logique principale
├── db.py                   # Accès à SQLite et gestion des données
├── xlsx_importer.py        # Lecture/import Excel + génération du modèle vierge
├── pdf_report.py           # Création des documents PDF
├── excel_report.py         # Création des documents Excel (.xlsx)
├── seed_db.py              # Import manuel du fichier source dans SQLite
│
├── source_listes.xlsx      # Classeur Excel contenant les listes initiales
├── gestion_articles.db     # Base SQLite locale (créée/utilisée par l'application)
│
├── documents_pdf/          # PDF et Excel générés par l'application
│
├── run.bat                 # Lance l'application en mode Python
├── build.bat               # Construit la version Windows avec PyInstaller
├── requirements.txt        # Dépendances Python
└── README.md               # Documentation du projet
```

### Rôle des fichiers principaux

#### `main.py`
Point d'entrée de l'application. Il contient notamment :

- la fenêtre principale ;
- les onglets **Nouveau document** et **Historique** ;
- la recherche des articles ;
- l'ajout/suppression de lignes ;
- le calcul du total HT ;
- l'enregistrement du document ;
- l'appel au générateur PDF.

#### `db.py`
Centralise les opérations SQLite :

- création des tables ;
- gestion des articles ;
- recherche des articles ;
- numérotation des documents ;
- enregistrement des documents et de leurs lignes ;
- consultation de l'historique.

#### `xlsx_importer.py`
Lit le classeur `.xlsx` directement (sans dépendre de Microsoft Excel). Il expose :

- `read_sheet_names()` : liste les feuilles du classeur ;
- `extract_articles(path, sheet_map)` : associe chaque liste (catégorie) à une feuille ;
- `write_template()` : génère un classeur modèle vierge (une feuille par liste).

Les quatre premières colonnes attendues sont :

```text
N° | Désignation | Unité de mesure | Prix unitaire HT
```

Le code contient également une normalisation des formats de prix (`parse_price`), notamment pour les écritures avec virgule et séparateurs de milliers.

#### `pdf_report.py`
Construit le PDF A4 contenant :

- numéro du document ;
- date ;
- liste utilisée ;
- détail des articles ;
- prix unitaires ;
- quantités ;
- total HT.

#### `excel_report.py`
Construit la version `.xlsx` du document (via `openpyxl`) avec la même
présentation : en-tête, tableau des articles, total HT. Ce module est utilisé à
l'enregistrement d'un document et lors de l'export d'un document depuis
l'historique.

---

## 4. Base de données

La base locale utilisée est :

```text
gestion_articles.db
```

Les données importantes sont organisées autour de quatre concepts :

### Listes (catégories)

Contient les listes disponibles et la feuille Excel associée :

```text
nom
feuille Excel
préfixe de numérotation
```

Deux listes sont créées par défaut : `Informatique` (préfixe `INF`) et
`Bureautique` (préfixe `BUR`). L'application migre automatiquement une base
existante (suppression de l'ancienne contrainte qui limitait les catégories,
ajout du préfixe).

Le numéro d'un document est propre à chaque liste :

```text
<préfixe>-<année>-<numéro>      ex. INF-2026-0001
```

### Articles

Contient les références importées depuis Excel :

```text
catégorie
code
désignation
unité
prix unitaire HT
```

### Documents

Contient l'en-tête des documents enregistrés :

```text
numéro
date
catégorie
total HT
taux de TVA (19 %)
montant TVA
total TTC
chemin du PDF
chemin du fichier Excel
```

### Lignes de document

Contient les articles utilisés dans chaque document :

```text
document
code
Désignation
unité
prix unitaire HT
quantité
total HT
```

Le prix est enregistré dans la ligne du document afin de conserver l'historique du prix utilisé au moment de la création du document.

---

## 5. Lancer le projet en développement

### Prérequis

Installer **Python 3.11 ou une version compatible**.

Vérifier :

```powershell
python --version
```

Puis installer les dépendances :

```powershell
python -m pip install -r requirements.txt
```

### Démarrer l'application

Double-cliquer sur :

```text
run.bat
```

ou :

```powershell
python main.py
```

---

## 6. Création de l'exécutable Windows

Pour créer une version sans console :

```text
build.bat
```

Le résultat est généré dans :

```text
dist\GestionArticles\
```

L'exécutable principal est :

```text
GestionArticles.exe
```

Pour distribuer l'application, conserver l'ensemble du dossier généré par PyInstaller, et pas seulement le fichier `.exe`.

---

## 7. Import des listes Excel

Le fichier :

```text
source_listes.xlsx
```

sert de source initiale.

L'application peut également importer un autre fichier Excel depuis le menu :

```text
Fichier → Importer des articles Excel...
```

L'import se fait simplement, une feuille à la fois :

1. Choisir le fichier `.xlsx`.
2. Sélectionner la **feuille** à importer.
3. Saisir le **nom de la liste** (proposé à partir du nom de la feuille).

La liste est créée si elle n'existe pas. Si elle existe déjà, ses articles sont
remplacés après confirmation. Chaque feuille doit contenir les quatre colonnes
attendues dans cet ordre :

```text
N° | Désignation | Unité de mesure | Prix unitaire HT
```

### Supprimer une liste

```text
Fichier → Supprimer une liste...
```

Une liste s'ajoute uniquement par import (voir ci-dessus). Le **modèle `.xlsx`**
vierge (une feuille par liste) et le rappel du format sont disponibles via :

```text
Fichier → Enregistrer un modèle Excel...
Aide → Format Excel attendu...
```

### Remplacement des données

À l'import, seule la liste concernée est remplacée ; les autres listes de la base
sont conservées. La suppression d'une liste efface ses articles mais **conserve**
les documents de l'historique (les lignes de document gardent une copie du code,
de la désignation et du prix).

---

## 8. Règles fonctionnelles actuelles

### Prix

Le prix unitaire HT provenant de la liste est la référence utilisée par l'application.

Le prix n'est **pas modifiable pendant la saisie du document**.

### Quantité

La quantité est saisie par l'utilisateur et peut être décimale. Elle est remise
à **1** dès que l'on choisit un autre article et après chaque ajout.

### Recherche et sélection

Dans la zone de recherche :

- `↓` / `↑` : sélectionner l'article suivant / précédent ;
- `Entrée` : ajouter l'article sélectionné au document.

Le focus revient dans la zone de recherche après chaque ajout.

### Total

```text
Total ligne = Prix HT × Quantité
Total HT = Somme(Totaux des lignes)
TVA 19 % = Total HT × 0,19
Total TTC = Total HT + TVA
```

La TVA de **19 %** s'applique à **toutes les listes**. Le taux et les montants
TVA/TTC sont enregistrés avec chaque document. Aucune remise n'est calculée.

---

## 9. Historique

Chaque document enregistré possède :

- un numéro automatique ;
- une date ;
- une catégorie ;
- un total HT, la TVA et le total TTC ;
- ses lignes détaillées ;
- un lien vers le PDF et le fichier Excel générés.

L'onglet **Historique** permet de rechercher les documents et de :

- voir leurs lignes (avec récapitulatif HT / TVA / TTC) ;
- ouvrir le PDF associé ;
- ouvrir le fichier Excel associé ;
- **exporter en Excel** le document sélectionné ;
- **supprimer le document** sélectionné (ses lignes sont supprimées, les fichiers
  PDF/Excel restent sur le disque).

La suppression d'une **liste d'articles** reste disponible via
`Fichier → Supprimer une liste...`.

---

## 10. Où modifier le projet ?

Pour éviter de chercher dans tout le code :

| Besoin | Fichier principal |
|---|---|
| Modifier l'interface | `main.py` |
| Modifier les articles / SQLite | `db.py` |
| Modifier l'import Excel | `xlsx_importer.py` |
| Modifier la mise en page PDF | `pdf_report.py` |
| Modifier la mise en page Excel | `excel_report.py` |
| Modifier la gestion des listes | `db.py` + `main.py` |
| Modifier l'import initial | `seed_db.py` |
| Modifier la compilation EXE | `build.bat` |
| Modifier les dépendances | `requirements.txt` |

---

## 11. Améliorations possibles

Le projet peut évoluer progressivement sans devoir être réécrit.

### Interface

- améliorer le thème visuel ;
- ajouter le logo de l'entreprise ;
- ajouter une barre d'outils ;
- améliorer la sélection des articles ;
- permettre le tri des colonnes.

### Documents

- ajouter fournisseur/client ;
- ajouter objet du document ;
- ajouter référence de commande ;
- personnaliser l'en-tête et le pied de page ;
- ajouter signature/cachet ;
- ajouter un modèle PDF proche d'un bon de commande ou d'une facture.

### Historique

- filtre par date ;
- filtre par catégorie ;
- export de tout l'historique en Excel ;
- duplication d'un ancien document ;
- suppression/annulation avec traçabilité.

### Données

- archivage des anciens prix ;
- gestion des fournisseurs ;
- gestion des unités de mesure ;
- export d'un modèle Excel pré-rempli depuis la base ;
- import/export de sauvegarde.

### Distribution

- créer un installeur Windows ;
- ajouter une sauvegarde automatique de SQLite ;
- séparer les données utilisateur des fichiers de programme ;
- signer l'exécutable si le projet est diffusé largement.

---

## 12. Bonnes pratiques pour continuer le développement

1. **Ne pas modifier directement `gestion_articles.db`** avec un éditeur SQLite sans sauvegarde préalable.
2. Conserver une copie de `source_listes.xlsx` avant tout nouvel import.
3. Faire une sauvegarde du dossier `documents_pdf` et de la base avant une évolution importante.
4. Ajouter les nouvelles fonctionnalités par petites étapes et tester après chaque modification.
5. Ne pas stocker de données sensibles ou de mots de passe en clair dans le code.
6. Lorsqu'une nouvelle fonctionnalité est ajoutée, mettre à jour ce README.

---

## 13. Feuille de route recommandée

L'ordre recommandé pour les prochaines versions est :

```text
V1  → Fonctionnement de base
V2  → Amélioration de l'interface
V3  → PDF professionnel avec identité de l'entreprise
V4  → Recherche/filtrage avancé de l'historique
V5  → Sauvegarde/restauration
V6  → Packaging et installation Windows
```

Cette progression permet d'améliorer l'application sans casser les fonctions déjà validées.

---

## 14. Principe général du projet

```text
Excel
  ↓
Import des articles
  ↓
SQLite
  ↓
Choix de la liste (Informatique / Bureautique / autres)
  ↓
Recherche article
  ↓
Quantité
  ↓
Calcul Total HT
  ↓
Enregistrement du document
  ↓
Historique SQLite + PDF + Excel
```

---

## 15. Version actuelle

**Version : 1.1**

Fonctionnalités ajoutées depuis la 1.0 :

- **thème moderne** : en-tête coloré, onglets en pastilles, cartes, boutons plats, tableaux soignés ;
- sélection d'article et panier **côte à côte** (panneau redimensionnable) ;
- **navigation clavier** dans la recherche (`↑`/`↓`, `Entrée`) et quantité remise à 1 ;
- **TVA 19 %** pour toutes les listes (affichage, PDF, Excel, historique) et total TTC ;
- suppression d'un **document** depuis l'onglet Historique ;
- listes dynamiques (ajout / suppression, une feuille Excel par liste) ;
- **numérotation par liste** avec préfixe (ex. `INF-2026-0001`, `BUR-2026-0001`) ;
- fenêtre d'aide au **format Excel** et génération d'un **modèle** `.xlsx` ;
- import Excel simplifié : feuille → nom de la liste ;
- export **PDF + Excel** automatique à l'enregistrement ;
- export Excel d'un document depuis l'historique ;
- migration automatique de la base (catégories libres, colonne `excel_path`).

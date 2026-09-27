# TODO — Prochaine session

État : la **refonte v2** est terminée et validée (phases 0 à 5) :

- exercices annuels par convention (période configurable, plafond, clôture) ;
- blocage ferme à 100 % du plafond, numérotation `INF-2026-2027-0001` ;
- suppression du journal d'audit et de l'historique des prix ;
- refonte visuelle : barre latérale, tableau de bord, thème clair par défaut
  + mode sombre ;
- historique filtré par convention/exercice, rapport de consommation par exercice.

Ajout récent, validé (session du 2026-09-27) :

- **modification d'un document** depuis l'historique : dialogue
  `app/ui/dialogs/edition.py` (quantités, retrait / ajout de lignes), lecture seule
  hors exercice actif, blocage ferme du plafond, `Database.update_document` en une
  transaction, régénération du PDF/Excel avec restauration en cas d'échec,
  aucune trace de modification (pas de migration de schéma).

Vérifications effectuées :

- `python -m compileall -q -f main.py seed_db.py app` → exit 0 ;
- `python -m pyflakes main.py seed_db.py app` → aucune erreur
  (interpréteur utilisé ici : `C:\Program Files\Python311\python.exe`,
  `pyflakes` installé via `pip`) ;
- scénarios : blocage à 100 % (égalité incluse), dépassement bloqué, numérotation,
  clôture + snapshot, exercice illimité, mise à jour de document (identifiants de
  lignes conservés, lignes retirées/supprimées, plafond bloqué en écriture) ;
- dialogue d'édition : édition de quantité, ajout / retrait de ligne, totaux et
  bandeau plafond, lecture seule, sauvegarde et régénération des fichiers ;
- instanciation de `App` + navigation sur les écrans + modification depuis
  l'historique + bascule de thème, sans exception.

## À faire par l'utilisateur

- [ ] Lancer l'application (`run.bat` ou `python main.py`) et tester
      **« Modifier le document »** sur un document de l'historique (ajustement d'une
      quantité, retrait et ajout de ligne) : vérifier les totaux, le plafond et le
      PDF/Excel régénérés.
- [ ] Vérifier visuellement : tableau de bord, saisie d'un document, blocage à
      100 %, clôture d'exercice, ouverture du suivant, historique filtré, rapport
      Excel, thème clair/sombre.

> Remarque : sur ce poste, `C:\Python314\python.exe` n'existe pas — l'application
> tourne avec `C:\Program Files\Python311\python.exe` (voir `run.bat`).

## Pistes d'amélioration (non engagées)

- Installateur Windows et sauvegarde automatique de SQLite.
- Séparer les données utilisateur des fichiers de programme.
- Export de tout l'historique en Excel, duplication d'un document.
- Personnalisation de l'en-tête / pied de page des PDF.

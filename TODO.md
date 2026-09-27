# TODO — Prochaine session

État : la **refonte v2** est terminée et validée (phases 0 à 5) :

- exercices annuels par convention (période configurable, plafond, clôture) ;
- blocage ferme à 100 % du plafond, numérotation `INF-2026-2027-0001` ;
- suppression du journal d'audit et de l'historique des prix ;
- refonte visuelle : barre latérale, tableau de bord, thème clair par défaut
  + mode sombre ;
- historique filtré par convention/exercice, rapport de consommation par exercice.

Vérifications effectuées (Python 3.14, `C:\Python314\python.exe`) :

- `python -m compileall -q -f main.py seed_db.py app` → exit 0 ;
- `python -m pyflakes main.py seed_db.py app` → aucune erreur ;
- migration testée sur **copie** de la base réelle (articles/documents/lignes
  conservés, exercices créés, anciennes tables supprimées, `foreign_key_check`
  vide) ;
- scénarios : blocage à 100 % (égalité incluse), dépassement bloqué, numérotation,
  clôture + snapshot, exercice illimité ;
- instanciation de `App` + navigation sur les 6 écrans + bascule de thème, sans
  exception.

## À faire par l'utilisateur

- [ ] Lancer l'application (`run.bat` ou `python main.py`) : la base réelle
      `gestion_articles.db` sera **migrée au premier lancement** (transactionnelle,
      réversible). Une sauvegarde fraîche `gestion_articles.backup-preV2-2026-09-26.db`
      est en place — en refaire une avant lancement par prudence.
- [ ] Vérifier visuellement : tableau de bord, saisie d'un document, blocage à
      100 %, clôture d'exercice, ouverture du suivant, historique filtré, rapport
      Excel, thème clair/sombre.

## Pistes d'amélioration (non engagées)

- Installateur Windows et sauvegarde automatique de SQLite.
- Séparer les données utilisateur des fichiers de programme.
- Export de tout l'historique en Excel, duplication d'un document.
- Personnalisation de l'en-tête / pied de page des PDF.

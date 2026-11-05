"""Point d'entrée gelé de l'API Opportune (OPP-190, PyInstaller).

PyInstaller analyse un **script**, pas un ``python -m``. Ce fichier se contente
d'appeler le ``main`` du serveur HTTP (le même point d'entrée que
``python -m api.server``). Les imports du cœur sont très majoritairement
**paresseux** (``from app.X import Y`` au sein des fonctions) et donc invisibles
à l'analyse statique : la collecte exhaustive des sous-modules est faite dans le
``.spec`` via ``collect_submodules``, pas ici.
"""

from api.server import main

if __name__ == "__main__":
    main()

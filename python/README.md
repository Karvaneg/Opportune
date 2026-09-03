# Opportune — stack cible Python (V2)

Ossature du futur projet Python d'Opportune (ticket **OPP-070**). À ce stade, le
dossier ne contient **que le squelette** : packaging, environnement et test de
fumée. Aucune logique métier, ni FastAPI, ni SQLAlchemy, ni Ollama, ni SQLite —
ces briques arriveront avec les tickets suivants (OPP-071 Docker/WSL, OPP-072
SQLite, OPP-073 Ollama).

Le MVP fonctionnel actuel reste la base **Node.js** à la racine du dépôt ; ce
dossier `python/` prépare la migration progressive sans la commencer.

## Structure

```
python/
├── pyproject.toml        # configuration & dépendances (PEP 621)
├── src/
│   └── app/
│       └── __init__.py   # package applicatif (version + healthcheck)
└── tests/
    └── test_smoke.py     # test de fumée pytest
```

## Prérequis

- Python ≥ 3.11

## Installation

Depuis le dossier `python/`, créer et activer un environnement virtuel, puis
installer le projet avec ses dépendances de développement :

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
```

## Exécution des tests

```bash
pytest
```

Le test de fumée vérifie simplement que le package s'importe et s'exécute — preuve
que l'environnement Python est correctement initialisé.

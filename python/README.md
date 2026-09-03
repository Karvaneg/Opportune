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
├── Dockerfile            # image de l'environnement Python
├── docker-compose.yml    # service de développement
├── .dockerignore
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

## Environnement Docker / WSL

Alternative à l'environnement virtuel local : un conteneur reproductible (OPP-071).
Aucun service externe n'est encore requis (SQLite → OPP-072, Ollama → OPP-073).

### Avec Docker seul

```bash
cd python
docker build -t opportune-py:dev .
docker run --rm opportune-py:dev      # lance la suite de tests
```

### Avec Docker Compose (développement)

Le code (`src/`, `tests/`) est monté en volume : les modifications sont prises en
compte sans reconstruire l'image.

```bash
cd python
docker compose run --rm app            # lance pytest (commande par défaut)
docker compose run --rm app python -c "import app; print(app.healthcheck())"
```

### Sous Windows / WSL2

- Installer **Docker Desktop** avec le backend **WSL2** activé, ou installer le moteur
  Docker directement dans la distribution WSL.
- Travailler depuis le système de fichiers Linux de WSL (par ex. `~/Opportune`) plutôt
  que `/mnt/c/...` : les montages de volumes y sont nettement plus rapides.
- Les commandes ci-dessus s'exécutent telles quelles dans le terminal WSL.

"""Runner de collecte RSS — déclenche une passe réelle (V1, OPP-122).

Câblage *runnable* qui **alimente le pipeline** avec le connecteur RSS : il compose la source
(``rss_source``), le client LLM local (Ollama, pour l'analyse d'intake) et le dépôt d'offres
SQLite, puis lance la passe générique via ``collection_runner``. Aucune logique métier neuve.

Exécution ::

    python -m app.rss_runner --feed https://exemple.fr/jobs.rss --feed https://autre/flux.xml
    # ou via l'environnement : RSS_FEED_URLS="url1,url2" python -m app.rss_runner

Les flux proviennent des options ``--feed`` (répétables) ou de la variable ``RSS_FEED_URLS``
(séparée par des virgules). Tout collaborateur est injectable (via ``collection_runner``) : une
passe se teste sans réseau ni Ollama.

Contrairement aux autres connecteurs, celui-ci **requiert l'extra ``scrape``** (BeautifulSoup) :
le contenu d'un article RSS est du HTML que ``rss_source`` nettoie avant l'intake. On le vérifie
en amont — faute de quoi *chaque* offre échouerait, et toute la passe remonterait en
``source_error`` avec un message peu parlant.
"""

from __future__ import annotations

import argparse
import os
import re
from importlib.util import find_spec
from typing import Mapping

from app.collection_runner import format_report, run_collection
from app.db import connect
from app.llm import resolve_llm_timeout
from app.llm_client import OllamaLLMClient
from app.rss_source import build_rss_source
from app.offer_store import OfferStore

# Séparateurs acceptés dans ``RSS_FEED_URLS`` : virgule, point-virgule ou espaces.
_FEED_SPLIT = re.compile(r"[,;\s]+")


def _feeds_from(args: argparse.Namespace, env: Mapping[str, str]) -> list[str]:
    """Flux à collecter : les options ``--feed``, sinon la variable ``RSS_FEED_URLS``."""
    if args.feed:
        return list(args.feed)
    raw = env.get("RSS_FEED_URLS", "")
    return [url for url in _FEED_SPLIT.split(raw) if url]


def _scrape_extra_missing() -> bool:
    """L'extra ``scrape`` (BeautifulSoup) — requis pour nettoyer le HTML des flux — est-il absent ?

    Sonde la disponibilité du module sans l'importer (``find_spec``), pour échouer vite et clair
    plutôt que de laisser ``extract_offer_text`` lever offre après offre.
    """
    return find_spec("bs4") is None


def main(argv: "list[str] | None" = None) -> int:
    """Point d'entrée CLI : assemble depuis les flux, lance la passe, affiche le bilan.

    Retourne un code non nul si aucun flux n'est fourni, ou si la source a échoué (réseau, XML
    malformé) — un échec de collecte doit être visible dans un ordonnanceur, pas masqué.
    """
    parser = argparse.ArgumentParser(description="Collecte d'offres depuis des flux RSS/Atom.")
    parser.add_argument(
        "--feed", action="append", default=[], help="URL d'un flux (répétable)"
    )
    parser.add_argument("--max", type=int, default=500, help="nombre max d'offres à collecter")
    args = parser.parse_args(argv)

    feeds = _feeds_from(args, os.environ)
    if not feeds:
        print("Aucun flux : passez --feed <url> ou définissez RSS_FEED_URLS.")
        return 1

    if _scrape_extra_missing():
        print(
            "Extra 'scrape' manquant : le nettoyage HTML du contenu RSS en dépend. "
            'Installez-le avec `pip install -e ".[scrape]"`.'
        )
        return 1

    source = build_rss_source(feeds, max_offers=args.max)
    llm_client = OllamaLLMClient(timeout=resolve_llm_timeout(os.environ))
    store = OfferStore(connect())
    report = run_collection(source, llm_client=llm_client, store=store)
    print(format_report(report))
    return 1 if report.source_error else 0


if __name__ == "__main__":  # pragma: no cover - point d'entrée
    raise SystemExit(main())

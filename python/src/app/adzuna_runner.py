"""Runner de collecte Adzuna — déclenche une passe réelle (V1, OPP-120).

Câblage *runnable* qui **alimente le pipeline** avec le connecteur actif : il compose la
source Adzuna (``adzuna_source``), le client LLM local (Ollama, pour l'analyse d'intake) et le
dépôt d'offres SQLite, puis lance la passe générique via ``collection_runner``. Aucune logique
métier neuve — uniquement de l'assemblage et la lecture de la configuration réelle.

Exécution ::

    python -m app.adzuna_runner --what "python" --where "Paris" --max 100

Tout collaborateur est injectable (``source``, ``llm_client``, ``store`` via
``collection_runner.run_collection``) : une passe se teste sans réseau ni Ollama. Seul
``_build_defaults`` touche à la configuration réelle (identifiants, timeout LLM, DB).
"""

from __future__ import annotations

import argparse
import os
from typing import Mapping

from app.adzuna_client import credentials_from_env
from app.adzuna_source import DEFAULT_MAX_OFFERS, build_adzuna_source
from app.collection_runner import format_report, run_collection
from app.db import connect
from app.llm import resolve_llm_timeout
from app.llm_client import LLMClient, OllamaLLMClient
from app.offer_source import SourceOffres
from app.offer_store import OfferRepository, OfferStore


def _filters_from_args(args: argparse.Namespace) -> dict[str, str]:
    """Traduit les options CLI en paramètres de recherche Adzuna (non vides seulement)."""
    mapping = {"what": args.what, "where": args.where}
    return {key: value for key, value in mapping.items() if value}


def _build_defaults(
    env: Mapping[str, str], args: argparse.Namespace
) -> "tuple[SourceOffres, LLMClient, OfferRepository]":
    """Assemble les collaborateurs réels depuis l'environnement (identifiants, timeout, DB)."""
    source = build_adzuna_source(
        credentials_from_env(env),
        filters=_filters_from_args(args) or None,
        max_offers=args.max,
        permanent=not args.tous_contrats,
    )
    llm_client = OllamaLLMClient(timeout=resolve_llm_timeout(env))
    store = OfferStore(connect())
    return source, llm_client, store


def main(argv: "list[str] | None" = None) -> int:
    """Point d'entrée CLI : assemble depuis l'environnement, lance la passe, affiche le bilan.

    Retourne un code de sortie non nul si la source elle-même a échoué (quota, réseau,
    identifiants) — un échec de collecte doit être visible dans un ordonnanceur, pas masqué.
    """
    parser = argparse.ArgumentParser(description="Collecte d'offres via l'API Adzuna.")
    parser.add_argument("--what", default="", help="mots-clés de recherche (what)")
    parser.add_argument("--where", default="", help="localisation (where), ex. Paris")
    parser.add_argument(
        "--max", type=int, default=DEFAULT_MAX_OFFERS, help="nombre max d'offres à collecter"
    )
    parser.add_argument(
        "--tous-contrats",
        action="store_true",
        help="ne pas restreindre aux CDI (par défaut : contrats permanents seulement)",
    )
    args = parser.parse_args(argv)

    source, llm_client, store = _build_defaults(os.environ, args)
    report = run_collection(source, llm_client=llm_client, store=store)
    print(format_report(report))
    return 1 if report.source_error else 0


if __name__ == "__main__":  # pragma: no cover - point d'entrée
    raise SystemExit(main())

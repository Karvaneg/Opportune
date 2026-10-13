"""Runner de collecte France Travail — déclenche une passe réelle (V1, OPP-120).

Câblage *runnable* qui **alimente le pipeline** : il compose la source France Travail
(``france_travail_source``), le client LLM local (Ollama, pour l'analyse d'intake) et le
dépôt d'offres SQLite, puis lance la passe générique ``collect_offers`` (OPP-119). Aucune
logique métier neuve — uniquement de l'assemblage et la lecture de la configuration réelle.

Exécution ::

    python -m app.france_travail_runner --mots-cles "python" --code-rome M1805 --max 300

Tout collaborateur est injectable (``source``, ``llm_client``, ``conn``) : une passe se teste
intégralement sans réseau ni Ollama (faux client LLM + base en mémoire + transport scripté).
Seul ``_build_defaults`` touche à la configuration réelle (identifiants, timeout LLM, DB).
"""

from __future__ import annotations

import argparse
import os
from typing import Mapping

from app.collection_runner import format_report, run_collection
from app.db import connect
from app.france_travail_client import WINDOW_MAX
from app.france_travail_source import build_france_travail_source
from app.llm import resolve_llm_timeout
from app.llm_client import LLMClient, OllamaLLMClient
from app.offer_source import SourceOffres
from app.offer_store import OfferRepository, OfferStore


def _filters_from_args(args: argparse.Namespace) -> dict[str, str]:
    """Traduit les options CLI en paramètres de recherche France Travail (non vides seulement)."""
    mapping = {
        "motsCles": args.mots_cles,
        "codeROME": args.code_rome,
        "commune": args.commune,
    }
    return {key: value for key, value in mapping.items() if value}


def _build_defaults(
    env: Mapping[str, str], args: argparse.Namespace
) -> "tuple[SourceOffres, LLMClient, OfferRepository]":
    """Assemble les collaborateurs réels depuis l'environnement (identifiants, timeout, DB)."""
    source = build_france_travail_source(
        env, filters=_filters_from_args(args) or None, max_offers=args.max
    )
    llm_client = OllamaLLMClient(timeout=resolve_llm_timeout(env))
    store = OfferStore(connect())
    return source, llm_client, store


def main(argv: "list[str] | None" = None) -> int:
    """Point d'entrée CLI : assemble depuis l'environnement, lance la passe, affiche le bilan.

    Retourne un code de sortie non nul si la source elle-même a échoué (quota, réseau,
    identifiants) — un échec de collecte doit être visible dans un ordonnanceur, pas masqué.
    """
    parser = argparse.ArgumentParser(description="Collecte d'offres CDI via l'API France Travail.")
    parser.add_argument("--mots-cles", default="", help="mots-clés de recherche (motsCles)")
    parser.add_argument("--code-rome", default="", help="code ROME (ex. M1805)")
    parser.add_argument("--commune", default="", help="code commune INSEE (ex. 75056)")
    parser.add_argument(
        "--max", type=int, default=WINDOW_MAX, help=f"nombre max d'offres (≤ {WINDOW_MAX})"
    )
    args = parser.parse_args(argv)

    source, llm_client, store = _build_defaults(os.environ, args)
    report = run_collection(source, llm_client=llm_client, store=store)
    print(format_report(report))
    return 1 if report.source_error else 0


if __name__ == "__main__":  # pragma: no cover - point d'entrée
    raise SystemExit(main())

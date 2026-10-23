"""CLI : pose le candidat de démonstration en base (V2, OPP-180).

Utilitaire local-first pour monter un candidat démo complet (profil + offres + décisions +
candidature + lettre) sur la base pointée par ``OPPORTUNE_DB_PATH``, sans réseau ni LLM.
Rejouable : relancer restaure l'état canonique du candidat démo.

Note (OPP-182) : l'API **seede déjà** sa base d'exemple au boot (``OPPORTUNE_DEMO_DB_PATH``,
servie via l'espace « Démo » de l'écran d'accueil). Cette CLI reste utile pour (re)seeder une
base arbitraire à la main.

Exécution : ``python -m hermes.seed_demo_candidate``
"""

from __future__ import annotations


def main() -> None:  # pragma: no cover - utilitaire CLI (touche la base sur disque)
    """Seed le candidat démo sur la base ``OPPORTUNE_DB_PATH`` (défaut) et affiche le bilan."""
    from app.db import DEFAULT_DB_PATH, connect
    from app.demo_candidate import seed_demo_candidate

    conn = connect()
    summary = seed_demo_candidate(conn)
    print(
        f"✅ Candidat démo {summary.candidate_id!r} prêt sur {DEFAULT_DB_PATH!r} : "
        f"{summary.offers} offre(s), {summary.decisions} décision(s), "
        f"{summary.applied} candidature(s), {summary.letters} lettre(s)."
    )
    print(
        "Dans l'app, l'espace « Démo » de l'écran d'accueil sert sa propre base d'exemple "
        "(OPPORTUNE_DEMO_DB_PATH), seedée automatiquement au démarrage de l'API."
    )


if __name__ == "__main__":  # pragma: no cover
    main()

"""Seed de démonstration — profil + offre en base (V2, OPP-132).

Utilitaire de **développement** (pas un chemin de prod) : pose en base un profil candidat
et une offre de démo **alignés** (score élevé → ``postuler``), pour qu'un
``python -m hermes.push_runner`` produise immédiatement une carte Discord sans saisie
manuelle. Sans profil, ``run_and_evaluate_for_candidate`` lèverait ``UnknownCandidateError`` :
ce seed lève cette dernière friction du dogfooding (cf. runbook OPP-126).

Aucune logique métier neuve : réutilise ``create_profile``, ``Offer`` et les dépôts
existants. Idempotent et rejouable sans doublon : l'offre est upsertée sur son id stable,
et le profil n'est posé **que s'il est absent** — on ne remplace jamais un profil réel par
les données de démo (``candidate_id`` est l'identité de prod, cf. ``OPPORTUNE_CANDIDATE_ID``).
"""

from __future__ import annotations

import os

from app.candidate_profile import CandidateProfile, create_profile
from app.offer import Offer
from app.offer_store import OfferRepository
from app.profile_store import ProfileStore

DEMO_OFFER_ID = "demo-offer-1"


def _demo_offer() -> Offer:
    """Offre de démo alignée sur le profil de démo (→ score maximal → ``postuler``)."""
    return Offer(
        id=DEMO_OFFER_ID,
        title="Développeur Python Senior",
        company="Acme",
        location="Paris",
        skills=["Python", "SQL"],
        seniority="Senior",
        contract_type="CDI",
        summary="Poste backend data : APIs Python, SQL, séniorité confirmée.",
        attention_points=[],
        source="demo",
        url="https://example.com/offre-demo",
        raw_text="Offre de démonstration (seed OPP-132).",
    )


def seed_demo(
    profiles: ProfileStore,
    offers: OfferRepository,
    *,
    candidate_id: str,
    name: str = "Marie",
) -> tuple[CandidateProfile, Offer]:
    """Pose un profil (si absent) et une offre de démo alignés ; retourne le couple en base.

    Le profil porte ``candidate_id`` (celui que ciblera le runner push) et des critères qui
    matchent l'offre de démo — le run produira une recommandation ``postuler``, donc une
    carte poussée. **Un profil déjà présent à cet id est préservé** : ``candidate_id`` est
    l'identité de prod, on ne remplace jamais des données réelles par de la démo. L'offre de
    démo, elle, est upsertée sur son id stable. Rejouable sans doublon.
    """
    # Le seed ne sert qu'à *combler l'absence* de profil : si un profil (réel ou déjà semé)
    # existe sous cet id, on le préserve tel quel plutôt que de l'écraser.
    profile = profiles.get(candidate_id)
    if profile is None:
        profile = create_profile(
            id=candidate_id,
            name=name,
            skills=["Python", "SQL"],
            contract_type="CDI",
            location="Paris",
            total_experience_years=6,
        )
        profiles.save(profile)

    offer = _demo_offer()
    offers.save(offer)
    return profile, offer


def main() -> None:  # pragma: no cover - utilitaire CLI (touche la base sur disque)
    """Seed la base pointée par ``OPPORTUNE_DB_PATH`` pour le candidat ``OPPORTUNE_CANDIDATE_ID``."""
    from app.db import connect
    from app.offer_store import OfferStore

    candidate_id = os.environ.get("OPPORTUNE_CANDIDATE_ID", "cand-marie")
    conn = connect()
    profile, offer = seed_demo(
        ProfileStore(conn), OfferStore(conn), candidate_id=candidate_id
    )
    print(
        f"✅ Seed OK : profil {profile.id!r} ({profile.name}) + offre {offer.id!r} "
        f"({offer.title}). Lance : python -m hermes.push_runner"
    )


if __name__ == "__main__":  # pragma: no cover
    main()

"""Correction humaine d'un profil extrait d'un CV (V2, OPP-138).

L'extraction LLM n'est pas la vérité (cf. OPP-137 : ministral a extrait *10 ans*
d'expérience pour Marie au lieu de *2*). Ce service expose la **correction d'un profil
déjà persisté** en réutilisant les primitives existantes — ``update_profile`` (re-validation)
et ``ProfileRepository`` (upsert) — sans re-passer par le CV.

``correct_profile`` ne rectifie que des **faits extraits** (cf. ``LOCKABLE_FIELDS``) : une
préférence est déjà saisie par l'utilisateur (source de vérité côté appelant) et serait de
toute façon réécrite à chaque ré-intake — la « corriger » ici serait un piège. Chaque fait
corrigé est **verrouillé** (``locked_fields``) : un ré-intake du même CV (``intake_profile``)
ne réécrasera plus une valeur rectifiée à la main. C'est le pendant, côté profil, de la
validation humaine préservée sur les décisions (OPP-131).
"""

from __future__ import annotations

from app.candidate_profile import (
    LOCKABLE_FIELDS,
    CandidateProfile,
    ProfileValidationError,
    update_profile,
)
from app.profile_store import ProfileRepository


class UnknownProfileError(Exception):
    """Aucun profil ne correspond à l'``id`` fourni."""


def correct_profile(
    profile_id: str, *, store: ProfileRepository, **changes: object
) -> CandidateProfile:
    """Corrige des **faits** d'un profil existant, les verrouille, persiste le profil.

    Les ``changes`` repassent par ``update_profile`` (même validation que
    ``create_profile`` : impossible de corrompre le profil) et chaque clé corrigée est
    ajoutée à ``locked_fields`` — cumulée avec les verrous déjà posés.

    Seuls les **faits** (cf. ``LOCKABLE_FIELDS``) sont corrigeables ici : une préférence
    (ou un nom de champ inconnu, p. ex. une faute de frappe) lève ``ProfileValidationError``
    plutôt que d'être silencieusement ignorée par ``create_profile``. Pour changer une
    préférence, l'appelant la re-fournit via l'intake (elle n'est pas extraite du CV).

    ``id`` et ``locked_fields`` fournis dans ``changes`` sont ignorés (l'identité est
    stable, les verrous sont dérivés des corrections). Lève ``ProfileValidationError`` si
    aucune correction n'est fournie, si une clé n'est pas un fait corrigeable, ou si une
    valeur est invalide ; ``UnknownProfileError`` si le profil est introuvable. Rien n'est
    persisté dans ces cas.
    """
    changes.pop("id", None)
    changes.pop("locked_fields", None)
    if not changes:
        raise ProfileValidationError("aucune correction fournie")

    invalid = [name for name in changes if name not in LOCKABLE_FIELDS]
    if invalid:
        raise ProfileValidationError(
            "correct_profile ne corrige que des faits extraits ("
            + ", ".join(sorted(LOCKABLE_FIELDS))
            + ") ; champ(s) refusé(s) : "
            + ", ".join(sorted(invalid))
        )

    current = store.get(profile_id)
    if current is None:
        raise UnknownProfileError(f"Profil introuvable : {profile_id!r}")

    # Toutes les clés sont des faits (validé ci-dessus) : on verrouille les nouvelles.
    newly_locked = [name for name in changes if name not in current.locked_fields]
    locked = list(current.locked_fields) + newly_locked
    corrected = update_profile(current, locked_fields=locked, **changes)
    store.save(corrected)
    return corrected

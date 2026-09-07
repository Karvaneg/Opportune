"""Composition de la boucle de candidature (V2) — décision → lettre → revue Discord.

La **glu** qui enchaîne les briques MVP : à partir d'une ``Decision`` (recommandation en
attente de validation, OPP-057) et de l'``Offer`` + ``CandidateProfile`` correspondants,
génère une lettre via un ``Redacteur`` (OPP-113) puis pousse le dossier en revue via un
``DiscordReviewer`` (OPP-117).

Ne dépend que de **contrats injectables** (``Redacteur``, ``DiscordReviewer``) : testable
de bout en bout sans réseau, sans Ollama ni Discord réels. La résolution de l'offre depuis
le store et la conversion d'un run Hermes en décisions restent du ressort de l'appelant —
ce module compose, il ne persiste ni ne va chercher les données.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from app.candidate_profile import CandidateProfile
from app.cover_letter import CoverLetter
from app.decision import PENDING, Decision
from app.discord_review import DiscordReviewer, ReviewSubmission
from app.offer import Offer
from app.redacteur import Redacteur


def _default_should_review(decision: Decision) -> bool:
    """Éligibilité par défaut : dossiers à candidater **encore en attente de validation**.

    On exclut les décisions déjà tranchées par un humain (``status`` ≠ ``pending``) :
    l'action automatique restant immuable (``postuler``), filtrer sur elle seule
    re-pousserait en revue un dossier déjà approuvé/rejeté/différé si l'appelant
    resoumet un lot. Le prédicat est ainsi **sûr aux re-runs**, sans dédoublonnage aval.
    """
    return decision.action == "postuler" and decision.status == PENDING


@dataclass(frozen=True)
class ReviewedCandidature:
    """Résultat de la boucle pour une décision : la lettre générée et le message de revue."""

    recommendation_id: str
    cover_letter: CoverLetter
    submission: ReviewSubmission


def prepare_and_submit_review(
    decision: Decision,
    offer: Offer,
    profile: CandidateProfile,
    *,
    redacteur: Redacteur,
    reviewer: DiscordReviewer,
) -> ReviewedCandidature:
    """Génère la lettre puis pousse le dossier en revue Discord (une décision).

    ``offer`` doit correspondre à ``decision.offer_id`` (résolu par l'appelant depuis le
    store) — un décalage lève ``ValueError`` **avant** tout appel, pour ne jamais rédiger
    ni pousser un dossier sur la mauvaise offre. Propage les erreurs du ``Redacteur``
    (``CoverLetterError`` / ``LLMError``) et du transport Discord ; si la rédaction échoue,
    aucun message n'est poussé (l'envoi est en aval de la génération).
    """
    if offer.id != decision.offer_id:
        raise ValueError(
            f"offre {offer.id!r} ne correspond pas à la décision ({decision.offer_id!r})"
        )
    letter = redacteur.write_cover_letter(offer, profile)
    submission = reviewer.submit_for_review(
        offer,
        letter,
        decision.id,
        score=decision.score,
        action=decision.action,
        justification=decision.justification,
    )
    return ReviewedCandidature(
        recommendation_id=decision.id, cover_letter=letter, submission=submission
    )


class BatchReviewError(Exception):
    """Un item du lot a échoué : porte la progression pour une reprise sans doublon.

    Le traitement étant séquentiel et à effet de bord (push Discord), une erreur laisse
    poussés les dossiers déjà soumis. ``results`` liste ces ``ReviewedCandidature`` (la
    frontière poussé/non-poussé) et ``failed`` la décision en échec — l'appelant peut
    reprendre le lot au bon endroit sans re-pousser. La cause d'origine est chaînée
    (``__cause__``).
    """

    def __init__(
        self, results: list[ReviewedCandidature], failed: Decision
    ) -> None:
        self.results = results
        self.failed = failed
        super().__init__(
            f"revue interrompue sur la décision {failed.id!r} après "
            f"{len(results)} dossier(s) poussé(s)"
        )


def submit_pending_reviews(
    items: Iterable[tuple[Decision, Offer]],
    profile: CandidateProfile,
    *,
    redacteur: Redacteur,
    reviewer: DiscordReviewer,
    should_review: Callable[[Decision], bool] = _default_should_review,
) -> list[ReviewedCandidature]:
    """Pousse en revue les décisions éligibles d'un lot de couples ``(décision, offre)``.

    Ordre d'entrée préservé. ``should_review`` filtre les décisions (défaut : dossiers
    ``postuler`` encore ``pending``). Traitement **séquentiel** : une erreur interrompt
    le lot en levant ``BatchReviewError``, qui porte les dossiers déjà poussés et la
    décision fautive — la progression n'est jamais perdue, la reprise reste sans doublon.
    """
    results: list[ReviewedCandidature] = []
    for decision, offer in items:
        if not should_review(decision):
            continue
        try:
            results.append(
                prepare_and_submit_review(
                    decision, offer, profile, redacteur=redacteur, reviewer=reviewer
                )
            )
        except Exception as exc:
            raise BatchReviewError(results, decision) from exc
    return results

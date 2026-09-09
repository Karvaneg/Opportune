"""Résolution amont : run Hermes → couples ``(Decision, Offer)`` (V2, OPP-127).

Le chaînon **amont** de la glu de revue (OPP-123) : à partir d'un ``HermesRun`` déjà
persisté, reconstitue les couples ``(Decision, Offer)`` que ``submit_pending_reviews``
sait consommer. Chaque ``OfferEvaluation`` du run y est convertie en :

- sa **décision persistée**, relue au courant depuis le dépôt (les validations humaines
  déjà posées sont donc respectées) ; à défaut — décision jamais persistée ou supprimée —
  elle est **recréée** à l'identique depuis le snapshot figé du run (action, score,
  justification immuables, cf. OPP-057) puis persistée, pour ne pas perdre l'item ;
- son **offre**, résolue via l'offer store.

Ne dépend que de **contrats injectables** (``DecisionRepository``, ``OfferRepository``) :
testable sans réseau. Une **offre introuvable** est tracée (``missing_offers``) et l'item
écarté du lot — jamais fatale au reste. L'ordre du run est préservé.

Ce module **résout**, il ne filtre ni ne pousse : le tri des dossiers éligibles (défaut :
``postuler`` encore ``pending``) et l'envoi restent le fait de ``submit_pending_reviews``.
Le câblage *runnable* (offer store réel, Ollama, Discord) est l'objet d'OPP-128.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decision import Clock, Decision, create_decision, decision_id
from app.decision_store import DecisionRepository
from app.offer import Offer
from app.offer_store import OfferRepository

from hermes.models import HermesRun


@dataclass(frozen=True)
class ResolvedRun:
    """Résultat de la résolution d'un run : couples prêts pour la revue + offres perdues.

    ``items`` liste les couples ``(Decision, Offer)`` dans l'ordre du run, prêts à passer à
    ``submit_pending_reviews``. ``missing_offers`` porte les ``offer_id`` dont l'offre n'a
    pu être résolue (tracés, non fatals) — l'appelant peut les signaler sans bloquer le lot.
    """

    items: list[tuple[Decision, Offer]]
    missing_offers: tuple[str, ...] = ()


def resolve_run_review_items(
    run: HermesRun,
    *,
    decisions: DecisionRepository,
    offers: OfferRepository,
    now: Clock | None = None,
) -> ResolvedRun:
    """Convertit les évaluations d'un ``run`` en couples ``(Decision, Offer)``.

    Pour chaque évaluation, dans l'ordre : résout l'offre via ``offers`` (introuvable →
    tracée dans ``missing_offers``, item sauté), puis relit la décision persistée du couple
    (candidat, offre) via ``decisions`` — ou la recrée depuis le snapshot figé et la
    persiste si elle est absente. La décision et l'offre partagent alors le même
    ``offer_id`` (garde-fou déjà revérifié en aval par la glu).

    Un même ``offer_id`` n'est **résolu qu'une fois** : si un run comporte plusieurs
    évaluations sur la même offre, seule la première produit un couple, pour ne pas pousser
    deux fois le même dossier en revue en aval.

    ``now`` (optionnel) injecte l'horloge de création des décisions recréées, pour des
    tests déterministes ; sinon l'horloge UTC par défaut de ``app.decision`` s'applique.
    """
    clock_kwargs: dict[str, Clock] = {} if now is None else {"now": now}

    items: list[tuple[Decision, Offer]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for evaluation in run.evaluations:
        if evaluation.offer_id in seen:
            continue
        seen.add(evaluation.offer_id)

        offer = offers.get(evaluation.offer_id)
        if offer is None:
            missing.append(evaluation.offer_id)
            continue

        stored_id = decision_id(run.candidate_id, evaluation.offer_id)
        decision = decisions.get(stored_id)
        if decision is None:
            decision = create_decision(
                candidate_id=run.candidate_id,
                offer_id=evaluation.offer_id,
                action=evaluation.action,
                score=evaluation.score,
                justification=evaluation.justification,
                **clock_kwargs,
            )
            decisions.save(decision)

        items.append((decision, offer))

    return ResolvedRun(items=items, missing_offers=tuple(missing))

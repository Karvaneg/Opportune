"""Runner de la boucle *push* — offre → run → lettre → carte Discord (V2, OPP-128).

Le **câblage runnable** qui rend la boucle push dogfoodable : il compose les briques déjà
testées en aval — sans réintroduire de logique métier — pour exécuter, de bout en bout ::

    (offre collée / lot) → intake LLM (OPP-037)      → offres persistées
        → run Hermes (OPP-060)                        → décisions persistées
        → résolution amont (OPP-127)                  → couples (Decision, Offer)
        → glu (OPP-123) : lettre (OPP-113) + push carte Discord (OPP-117)

``PushRunner`` ne porte **aucune** logique neuve : ses collaborateurs sont injectés, donc
il se teste intégralement sans réseau (``MockLLMClient`` + ``MockDiscordTransport`` + vrais
dépôts SQLite en mémoire). ``build_push_runner`` est l'unique endroit qui touche à la
configuration réelle : il lit l'environnement et **câble un timeout LLM généreux** — le
défaut 60 s ne suffit pas à générer une lettre (cf. OPP-113 et la mémoire ollama-wsl2).

C'est le pendant **push** du récepteur *receive* (OPP-125, live) : ici on **génère et
envoie** les cartes ; la validation des clics reste l'objet du gateway.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from app.candidate_profile import CandidateProfile
from app.decision_service import DecisionService
from app.decision_store import DecisionRepository, DecisionStore
from app.discord_review import DiscordReviewer
from app.discord_transport import HttpDiscordTransport
from app.llm_client import LLMClient, OllamaLLMClient
from app.offer import Offer
from app.offer_intake_service import intake_offer
from app.offer_store import OfferRepository, OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService, UnknownCandidateError
from app.redacteur import LLMRedacteur, Redacteur
from app.review_pipeline import (
    ReviewedCandidature,
    only_unsubmitted,
    submit_pending_reviews,
)
from app.submission_store import SubmissionRepository, SubmissionStore

from hermes.models import HermesRun
from hermes.orchestrator import HermesOrchestrator
from hermes.review_resolution import resolve_run_review_items
from hermes.run_store import RunStore

# Timeout LLM par défaut du runner (secondes) : nettement plus large que le défaut 60 s de
# ``app.llm`` — une lettre de motivation est bien plus longue qu'une analyse d'offre et
# dépasse 60 s à froid sur une machine modeste (cf. [[ollama-wsl2-acces]]).
DEFAULT_LLM_TIMEOUT = 300


def resolve_llm_timeout(env: Mapping[str, str]) -> int:
    """Lit ``OPPORTUNE_LLM_TIMEOUT`` (secondes) ; ``DEFAULT_LLM_TIMEOUT`` si absent.

    Absent/vide → défaut généreux. Toute valeur non entière ou non strictement positive →
    ``ValueError`` explicite : on refuse de démarrer sur un timeout ambigu plutôt que de
    recâbler silencieusement le défaut 60 s trop court d'``app.llm``.
    """
    raw = env.get("OPPORTUNE_LLM_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_LLM_TIMEOUT
    try:
        timeout = int(raw)
    except ValueError:
        raise ValueError(
            f"OPPORTUNE_LLM_TIMEOUT invalide ({raw!r}) : entier positif de secondes attendu."
        ) from None
    if timeout <= 0:
        raise ValueError(
            f"OPPORTUNE_LLM_TIMEOUT invalide ({timeout}) : doit être strictement positif."
        )
    return timeout


@dataclass(frozen=True)
class PushOutcome:
    """Résultat d'une passe de push pour un candidat.

    ``run`` est le run Hermes journalisé, ``reviewed`` la liste des dossiers effectivement
    poussés en revue (ordre préservé), ``missing_offers`` les offres du run non résolues
    dans le store (tracées par OPP-127, non fatales).
    """

    run: HermesRun
    reviewed: list[ReviewedCandidature]
    missing_offers: tuple[str, ...]


class PushRunner:
    """Compose Hermes + résolution amont + rédacteur + Discord (adaptateur mince).

    Tous les collaborateurs sont injectés : le runner enchaîne des appels déjà couverts par
    des tests unitaires, sans logique propre. ``decisions`` et ``offers`` sont les **mêmes**
    dépôts que ceux de l'orchestrateur — la résolution amont (OPP-127) les relit directement.
    """

    def __init__(
        self,
        *,
        orchestrator: HermesOrchestrator,
        decisions: DecisionRepository,
        offers: OfferRepository,
        profiles: ProfileStore,
        redacteur: Redacteur,
        reviewer: DiscordReviewer,
        intake_client: LLMClient,
        submissions: "SubmissionRepository | None" = None,
        limit: int = 10,
    ) -> None:
        self.orchestrator = orchestrator
        self.decisions = decisions
        self.offers = offers
        self.profiles = profiles
        self.redacteur = redacteur
        self.reviewer = reviewer
        self.intake_client = intake_client
        # Suivi des soumissions (OPP-131) : idempotence du re-run. Optionnel — sans lui, le
        # runner garde son comportement d'origine (peut re-pousser une carte encore pending).
        self.submissions = submissions
        self.limit = limit

    def ingest(self, raw_texts: list[str], *, source: str, url: str = "") -> list[Offer]:
        """Analyse et persiste des offres brutes (collées) ; retourne les ``Offer`` créées.

        Chaque texte passe par ``intake_offer`` (analyse LLM → normalisation → persistance).
        Propage les erreurs d'analyse/LLM sans les masquer : une offre mal analysée doit être
        visible, pas silencieusement absorbée.
        """
        return [
            intake_offer(
                text, source=source, client=self.intake_client, store=self.offers, url=url
            )
            for text in raw_texts
        ]

    def push_for_candidate(
        self, candidate_id: str, *, limit: int | None = None
    ) -> PushOutcome:
        """Exécute run → résolution amont → génération + push, pour un candidat.

        Lève ``UnknownCandidateError`` si le profil est introuvable, et propage
        ``BatchReviewError`` (OPP-123) en cas d'échec partiel du lot : le lot s'arrête à la
        première erreur en portant les dossiers déjà poussés (frontière poussé/non-poussé)
        et la décision fautive, pour ne pas perdre la progression.
        """
        return self._push(self._require_profile(candidate_id), limit=limit)

    def run(
        self,
        raw_texts: list[str],
        candidate_id: str,
        *,
        source: str,
        url: str = "",
        limit: int | None = None,
    ) -> PushOutcome:
        """Ingestion des offres collées **puis** push pour le candidat, d'un bloc.

        ``raw_texts`` vide → aucune ingestion, on pousse sur le stock existant. Vérifie que
        le candidat existe **avant** toute ingestion (échec net, rien de généré à vide).
        """
        profile = self._require_profile(candidate_id)
        if raw_texts:
            self.ingest(raw_texts, source=source, url=url)
        return self._push(profile, limit=limit)

    def _push(self, profile: CandidateProfile, *, limit: int | None) -> PushOutcome:
        """Cœur partagé : run → résolution amont → génération + push, profil déjà résolu.

        Avec un suivi des soumissions (OPP-131), écarte les dossiers déjà poussés et encore
        en attente (idempotence du re-run) et enregistre **chaque carte dès son envoi** — y
        compris avant un ``BatchReviewError`` — pour qu'une reprise ne les redouble jamais.
        """
        run = self.orchestrator.run_and_evaluate_for_candidate(
            profile.id, limit=self.limit if limit is None else limit
        )
        resolved = resolve_run_review_items(
            run, decisions=self.decisions, offers=self.offers
        )
        # Sans suivi : comportement d'origine (défaut de submit_pending_reviews, pas de
        # mémorisation). Avec suivi : filtre idempotent + enregistrement au grain de l'envoi.
        tracking: dict = {}
        if self.submissions is not None:
            tracking["should_review"] = only_unsubmitted(self.submissions)
            tracking["on_submitted"] = self._record
        reviewed = submit_pending_reviews(
            resolved.items,
            profile,
            redacteur=self.redacteur,
            reviewer=self.reviewer,
            **tracking,
        )
        return PushOutcome(
            run=run, reviewed=reviewed, missing_offers=resolved.missing_offers
        )

    def _record(self, candidature: ReviewedCandidature) -> None:
        """Persiste une carte poussée dans le suivi des soumissions (no-op sans suivi)."""
        if self.submissions is None:
            return
        self.submissions.record(
            candidature.recommendation_id,
            candidature.submission.message_id,
            candidature.submission.channel_id,
        )

    def _require_profile(self, candidate_id: str) -> CandidateProfile:
        profile = self.profiles.get(candidate_id)
        if profile is None:
            raise UnknownCandidateError(f"Candidat introuvable : {candidate_id!r}")
        return profile


def build_push_runner(
    conn,
    *,
    env: Mapping[str, str] | None = None,
    limit: int = 10,
) -> PushRunner:
    """Câble un ``PushRunner`` **de production** depuis une connexion SQLite et l'environnement.

    Lit ``DISCORD_CHANNEL_ID`` et ``DISCORD_BOT_TOKEN`` (obligatoires, validés **au
    démarrage** pour ne pas dérouler l'intake LLM et le run Hermes avant de crasher sur la
    première carte), ``OPPORTUNE_LLM_TIMEOUT`` (timeout LLM généreux, cf.
    ``resolve_llm_timeout``), et laisse ``app.llm`` résoudre le reste (``OLLAMA_HOST`` /
    ``OLLAMA_MODEL``). Le **même** ``OllamaLLMClient`` sert l'analyse d'offre et la rédaction
    de lettre, et le **même** ``DecisionStore`` est partagé entre l'orchestrateur et la
    résolution amont.
    """
    env = os.environ if env is None else env

    channel_id = env.get("DISCORD_CHANNEL_ID")
    if not channel_id:
        raise ValueError(
            "DISCORD_CHANNEL_ID manquant : le runner push ne sait pas où envoyer les cartes."
        )

    bot_token = env.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        raise ValueError(
            "DISCORD_BOT_TOKEN manquant : le runner push ne peut pas s'authentifier auprès "
            "de Discord (validé au démarrage plutôt qu'après l'intake et le run)."
        )

    timeout = resolve_llm_timeout(env)
    llm_client = OllamaLLMClient(timeout=timeout)

    offers = OfferStore(conn)
    decisions = DecisionStore(conn)
    profiles = ProfileStore(conn)
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        DecisionService(decisions),
        runs=RunStore(conn),
    )
    return PushRunner(
        orchestrator=orchestrator,
        decisions=decisions,
        offers=offers,
        profiles=profiles,
        redacteur=LLMRedacteur(llm_client),
        reviewer=DiscordReviewer(
            HttpDiscordTransport(token=bot_token), channel_id=channel_id
        ),
        intake_client=llm_client,
        submissions=SubmissionStore(conn),  # idempotence du re-run (OPP-131)
        limit=limit,
    )


def main() -> None:  # pragma: no cover - point d'entrée réseau (Ollama + Discord), non testé
    """Entrée CLI : pousse les cartes d'un candidat, offre collée lue sur stdin (optionnelle).

    Variables : ``OPPORTUNE_CANDIDATE_ID`` (obligatoire), ``DISCORD_CHANNEL_ID``,
    ``OPPORTUNE_LLM_TIMEOUT``, ``OPPORTUNE_OFFER_SOURCE`` (défaut ``collée``),
    ``OPPORTUNE_DB_PATH`` (via ``app.db.connect``). L'offre collée est lue sur l'entrée
    standard ; vide → on pousse sur le stock existant.
    """
    import sys

    from app.db import connect
    from app.review_pipeline import BatchReviewError

    candidate_id = os.environ.get("OPPORTUNE_CANDIDATE_ID")
    if not candidate_id:
        raise SystemExit("OPPORTUNE_CANDIDATE_ID manquant.")
    source = os.environ.get("OPPORTUNE_OFFER_SOURCE", "collée")

    pasted = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    raw_texts = [pasted] if pasted else []

    try:
        runner = build_push_runner(connect())
    except ValueError as err:
        raise SystemExit(str(err)) from err

    try:
        outcome = runner.run(raw_texts, candidate_id, source=source)
    except BatchReviewError as err:
        print(
            f"⚠️  Push interrompu : {len(err.results)} carte(s) poussée(s) avant l'échec "
            f"sur {err.failed.id!r} ({err.__cause__})."
        )
        raise SystemExit(1) from err

    print(
        f"✅ Run {outcome.run.run_id} : {len(outcome.reviewed)} carte(s) poussée(s)"
        + (f", {len(outcome.missing_offers)} offre(s) introuvable(s)" if outcome.missing_offers else "")
        + "."
    )


if __name__ == "__main__":  # pragma: no cover
    main()

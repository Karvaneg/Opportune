"""Actions sensibles d'Hermes : intention d'exécution confirmée (V2, OPP-096).

Une **action** matérialise une intention d'exécution *sortante* (candidater à une offre,
contacter quelqu'un) **explicitement confirmée** par un humain. C'est un concept **distinct
de la décision** : la décision (``app.decision``) dit *quoi penser* d'une offre ; l'action
dit *qu'on a confirmé vouloir agir*. Séparer les deux évite qu'un simple ``approved``
déclenche une candidature ou un message.

À ce stade V2, l'exécution reste **simulée/journalisée** (``status = "simulated"``) : aucune
intégration réseau réelle vers un ATS ou une messagerie. L'objet trace *qu'une confirmation
a eu lieu*, pas l'envoi effectif.
"""

from __future__ import annotations

from dataclasses import dataclass

# Types d'action (sert de clé d'idempotence « par cible ET type d'action »).
APPLICATION = "application"
MESSAGE = "message"

# Seul statut d'exécution possible en V2 : l'action est confirmée mais l'exécution réelle
# n'est pas branchée (elle est simulée).
SIMULATED = "simulated"


@dataclass(frozen=True)
class ApplicationAction:
    """Engagement de candidature pour une offre recommandée, avec son cycle de vie.

    Deux étapes **déclaratives** portées par le même objet (l'exécution reste simulée, cf.
    module) :

    - ``confirmed_at`` : l'humain a noté son **intention** de candidater (naissance de l'objet) ;
    - ``applied_at`` : l'humain déclare avoir **réellement candidaté** — ``None`` tant qu'il ne
      l'a pas fait. Opportune n'envoie rien : c'est un suivi saisi à la main.

    ``decision_status_at_confirmation`` fige l'état de la décision humaine au moment de la
    confirmation (``approved`` — seul état autorisé) : trace d'audit du « pourquoi c'était
    permis ». ``recommendation_id`` est la cible (couple candidat/offre encodé).
    """

    action_id: str
    recommendation_id: str
    candidate_id: str
    decision_status_at_confirmation: str
    confirmed_at: str  # ISO 8601
    created_at: str  # ISO 8601
    status: str = SIMULATED
    applied_at: str | None = None  # ISO 8601 ; None tant que non déclaré « candidaté »


@dataclass(frozen=True)
class OutboundMessageAction:
    """Intention **confirmée** d'envoyer un message de contact.

    ``contact_id`` identifie la cible. En V2, faute d'un domaine ``Contact`` défini, il vaut
    l'``recommendation_id`` (id stable candidat/offre) ; un vrai objet ``Contact`` pourra être
    introduit plus tard sans changer ce contrat.
    """

    action_id: str
    contact_id: str
    recommendation_id: str
    candidate_id: str
    confirmed_at: str  # ISO 8601
    created_at: str  # ISO 8601
    status: str = SIMULATED

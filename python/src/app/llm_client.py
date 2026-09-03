"""Contrat d'intégration LLM (V2, OPP-079).

Couche d'abstraction que le **métier** utilisera pour générer du texte, sans jamais
coupler l'application à Ollama : le métier dépend du protocole ``LLMClient`` (et de
``LLMResponse``), pas de ``app.llm`` ni de HTTP.

Ce module définit :
- ``LLMClient`` : le protocole d'appel (format de requête = ``prompt`` + ``model``
  optionnel ; format de réponse = ``LLMResponse``) ;
- ``LLMResponse`` : la réponse structurée (texte, modèle effectif, corps brut) ;
- ``OllamaLLMClient`` : l'implémentation réelle, adossée à ``app.llm`` (transport
  ``urllib`` injectable, zéro dépendance) et mappant les échecs réseau vers des
  erreurs typées ;
- ``MockLLMClient`` : l'implémentation de test, sans réseau, à réponses scriptées ;
- ``LLMError`` / ``LLMTimeoutError`` / ``LLMResponseError`` : les erreurs du contrat.

Aucun cas d'usage métier n'est branché ici (c'est l'objet du ticket suivant) : ce
module ne fait que fixer le contrat et prouver qu'il est testable sans Ollama.
"""

from __future__ import annotations

import logging
import urllib.error
from dataclasses import dataclass, field
from functools import partial
from typing import Protocol, runtime_checkable

from app import llm

logger = logging.getLogger("app.llm_client")


class LLMError(Exception):
    """Échec d'une génération LLM (erreur de base du contrat)."""


class LLMTimeoutError(LLMError):
    """Le serveur LLM n'a pas répondu dans le délai imparti."""


class LLMResponseError(LLMError):
    """Le serveur a répondu mais la réponse est inexploitable (champ manquant)."""


@dataclass(frozen=True)
class LLMResponse:
    """Réponse structurée d'une génération.

    ``text`` est le résultat directement exploitable par le métier ; ``model`` est le
    modèle effectivement sollicité ; ``raw`` conserve le corps brut renvoyé par le
    transport (utile pour le débogage / la journalisation), sans y coupler le métier.
    """

    text: str
    model: str
    raw: dict = field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    """Contrat d'accès au LLM consommé par le métier.

    Une seule opération : transformer un ``prompt`` (déjà structuré par l'appelant) en
    ``LLMResponse``. Les implémentations lèvent ``LLMError`` (ou une sous-classe) en cas
    d'échec, et ``ValueError`` si le prompt est vide.
    """

    def generate(self, prompt: str, *, model: str | None = None) -> LLMResponse: ...


class OllamaLLMClient:
    """Implémentation réelle du contrat, adossée à ``app.llm`` (Ollama / Ministral).

    Le ``transport`` est injectable — par défaut le POST ``urllib`` de ``app.llm`` (zéro
    dépendance, zéro réseau en test). Les échecs réseau sont convertis en erreurs
    typées du contrat, et une réponse dépourvue du champ ``response`` lève
    ``LLMResponseError`` (une chaîne vide, en revanche, est une réponse valide vide).
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        host: str | None = None,
        transport: llm.Transport | None = None,
        timeout: int = llm.DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.host = host
        self.timeout = timeout
        self._transport = transport or partial(llm._urllib_transport, timeout=timeout)

    def generate(self, prompt: str, *, model: str | None = None) -> LLMResponse:
        url, payload = llm.build_generate_request(
            prompt, model=model or self.model, host=self.host
        )
        logger.debug("Génération LLM (modèle=%s, url=%s)", payload["model"], url)
        try:
            raw = self._transport(url, payload)
        except TimeoutError as exc:  # socket.timeout est un alias de TimeoutError
            logger.warning("Timeout LLM après %ss (url=%s)", self.timeout, url)
            raise LLMTimeoutError(f"Délai dépassé ({self.timeout}s) pour {url}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                logger.warning("Timeout LLM (url=%s)", url)
                raise LLMTimeoutError(f"Délai dépassé pour {url}") from exc
            logger.warning("Échec réseau LLM (url=%s) : %s", url, exc)
            raise LLMError(f"Échec de l'appel LLM vers {url}") from exc
        except OSError as exc:
            logger.warning("Échec réseau LLM (url=%s) : %s", url, exc)
            raise LLMError(f"Échec de l'appel LLM vers {url}") from exc

        if "response" not in raw:
            raise LLMResponseError("Réponse LLM inexploitable : champ 'response' absent")
        return LLMResponse(text=raw["response"], model=payload["model"], raw=raw)


class MockLLMClient:
    """Implémentation de test du contrat, sans réseau.

    Rejoue des réponses scriptées (chaînes ou ``LLMResponse``) dans l'ordre, en
    enregistrant les prompts reçus dans ``calls``. On peut aussi lui passer une
    exception à lever (``error``) pour exercer la gestion d'erreur côté métier.
    """

    def __init__(
        self,
        responses: list[str | LLMResponse] | str | None = None,
        *,
        model: str = "mock",
        error: Exception | None = None,
    ) -> None:
        if responses is None:
            responses = []
        elif isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self.model = model
        self.error = error
        self.calls: list[dict] = []

    def generate(self, prompt: str, *, model: str | None = None) -> LLMResponse:
        # Valide le prompt comme le fait le vrai client (via build_generate_request).
        if not isinstance(prompt, str) or prompt.strip() == "":
            raise ValueError("Le prompt est requis")
        self.calls.append({"prompt": prompt, "model": model or self.model})
        if self.error is not None:
            raise self.error
        if not self._responses:
            raise LLMResponseError("MockLLMClient : plus aucune réponse scriptée")
        nxt = self._responses.pop(0)
        if isinstance(nxt, LLMResponse):
            return nxt
        return LLMResponse(text=nxt, model=model or self.model)

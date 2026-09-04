"""API HTTP de Hermes (V2, OPP-093).

Couche mince exposant l'orchestrateur Hermes à des clients (Discord, UI web, etc.). La
logique métier reste dans ``HermesOrchestrator`` ; l'HTTP n'est qu'un adaptateur. Le
dispatcher ``HermesApi.dispatch`` est indépendant du transport, donc testable sans réseau
et réutilisable par n'importe quel client. stdlib seule.
"""

from __future__ import annotations

from api.app import ApiError, HermesApi, Response

__all__ = ["HermesApi", "Response", "ApiError"]

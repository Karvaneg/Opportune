"""Canonicalisation d'URL pour le dédoublonnage (V2, OPP-119).

Fonction **pure** (aucune I/O) produisant une forme canonique d'URL stable : deux
URLs qui ne diffèrent que par des paramètres de tracking, l'ordre des paramètres, un
fragment, le port par défaut ou un slash final doivent produire la **même** chaîne. Sert
de discriminant à ``compute_offer_id`` (``app.offer``) : canonicaliser l'URL fait
dédoublonner « même offre, deux liens de tracking » sans dépendre d'aucune sortie du LLM
(leçon d'OPP-134 — l'identité reste déterministe).

Volontairement **conservateur** : on ne retire que des paramètres *non ambigus* de
tracking. Retirer par erreur un paramètre porteur de sens (identifiant d'offre dans la
query) fusionnerait deux offres distinctes — un écrasement silencieux bien pire qu'un
doublon manqué.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Paramètres de query purement analytiques, sans incidence sur le contenu servi. Match
# **casse-insensible** sur le nom. On évite sciemment les cas ambigus (``ref``, ``trk``…)
# qui portent parfois l'identité d'une offre.
_TRACKING_PARAMS = frozenset(
    {
        "gclid",
        "fbclid",
        "dclid",
        "msclkid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "_hsenc",
        "_hsmi",
    }
)
# Familles de tracking préfixées (Urchin/Google Analytics : ``utm_source``, ``utm_medium``…).
_TRACKING_PREFIXES = ("utm_",)

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(name: str) -> bool:
    """Vrai si ``name`` est un paramètre de tracking à retirer (casse-insensible)."""
    low = name.lower()
    return low in _TRACKING_PARAMS or low.startswith(_TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    """Forme canonique d'une URL pour servir de clé de dédoublonnage.

    Minuscule le schéma et l'hôte, retire le port par défaut, supprime le fragment et
    les paramètres de tracking, trie les paramètres restants (ordre non significatif) et
    retire un slash final de chemin. Chaîne vide → chaîne vide. Une entrée qui n'est pas
    une URL absolue exploitable (schéma ou hôte manquant) retombe sur un repli
    déterministe (minuscules), pour rester une clé stable sans jamais lever.
    """
    stripped = url.strip()
    if not stripped:
        return ""
    try:
        parts = urlsplit(stripped)
        # ``parts.port`` lève ``ValueError`` sur un port hors plage ou non numérique
        # (``:99999``, ``:abc``) : on le lit ici, sous garde, pour tenir la promesse
        # « ne jamais lever » même sur une URL mal formée émise par une source réelle.
        port = parts.port
    except ValueError:
        return stripped.lower()
    if not parts.scheme or not parts.netloc:
        return stripped.lower()

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if port is not None and _DEFAULT_PORTS.get(scheme) != port:
        netloc = f"{host}:{port}"
    else:
        netloc = host

    # Retire les slashs finaux, racine comprise : « /job/42/ », « /job/42 » et, pour la
    # racine, « / » vs « » ne doivent pas fabriquer des clés distinctes.
    path = parts.path.rstrip("/")

    kept = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(name)
    ]
    kept.sort()
    query = urlencode(kept)

    return urlunsplit((scheme, netloc, path, query, ""))

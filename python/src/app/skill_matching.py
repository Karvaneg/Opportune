"""Rapprochement de compétences moins littéral (V2, OPP-139).

``compare_skills`` (OPP-038) comparait les libellés par **égalité de chaîne stricte** : un
profil « TypeScript / React » ne matchait pas une offre demandant « JavaScript », et les
synonymes (js/javascript, postgres/postgresql…) passaient à côté. Ce module rend le
rapprochement plus juste, **sans LLM ni embeddings** :

- ``canonicalize`` : normalise (casse, espaces) puis applique une table d'**alias** ;
- ``expand_skills`` : canonicalise un jeu de compétences puis ajoute les **implications de
  familles** (maîtriser React implique JavaScript).

Principe de prudence : les implications sont **unidirectionnelles** (spécifique ⇒ général,
jamais l'inverse — savoir React implique JavaScript, pas le contraire) et les tables
volontairement conservatrices, pour ne jamais créditer une compétence non détenue.
"""

from __future__ import annotations

from collections.abc import Iterable

# Variante (en minuscules, espaces réduits) → forme canonique. La règle par défaut reste
# l'**équivalence franche** : même compétence, autre orthographe / abréviation / version
# (``js``→``javascript``, ``html5``→``html``). Une **exception assumée** (OPP-157) : la famille
# REST plus bas regroupe des libellés *sémantiquement* proches — pas de simples variantes
# orthographiques — pour tuer les quasi-doublons d'une même offre. C'est un choix produit (le
# dédoublonnage prime), à ne pas prendre comme feu vert pour y verser des rapprochements lâches :
# toute nouvelle entrée hors « même techno » doit rester une convergence évidente et commentée.
_ALIASES: dict[str, str] = {
    "js": "javascript",
    "ecmascript": "javascript",
    "ts": "typescript",
    "node": "node.js",
    "nodejs": "node.js",
    "node js": "node.js",
    "next": "next.js",
    "nextjs": "next.js",
    "nuxt": "nuxt.js",
    "nuxtjs": "nuxt.js",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "postgres": "postgresql",
    "postgre": "postgresql",
    "psql": "postgresql",
    "py": "python",
    "golang": "go",
    "k8s": "kubernetes",
    "gh actions": "github actions",
    "tailwindcss": "tailwind",
    "tailwind css": "tailwind",
    # Versions = même techno (HTML5 ≡ HTML, CSS3 ≡ CSS).
    "html5": "html",
    "css3": "css",
    # Variantes d'intégration/livraison continue → une seule forme canonique.
    "cicd": "ci/cd",
    "ci-cd": "ci/cd",
    "ci cd": "ci/cd",
    # Famille REST — convergence SÉMANTIQUE assumée (cf. note en tête de _ALIASES), pas
    # orthographique : « REST », « RESTful », « RESTful Design »… désignent le même domaine de
    # compétence côté recrutement. But premier = éviter qu'une même offre compte « REST API » ET
    # « RESTful Design » comme deux manques distincts. Effet de bord accepté : un profil nommant
    # l'un couvre l'autre.
    "rest": "rest api",
    "restful": "rest api",
    "rest apis": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",
    "restful design": "rest api",
    "api rest": "rest api",
}

# Compétence canonique → compétences qu'elle **implique** (spécifique ⇒ général). La
# fermeture transitive est calculée dans ``expand_skills`` (next.js ⇒ react ⇒ javascript).
_IMPLIES: dict[str, set[str]] = {
    "typescript": {"javascript"},
    "react": {"javascript"},
    "vue": {"javascript"},
    "angular": {"javascript"},
    "svelte": {"javascript"},
    "node.js": {"javascript"},
    "next.js": {"react"},
    "nuxt.js": {"vue"},
    "redux": {"react"},
    "github actions": {"github", "git", "ci/cd"},
    "gitlab ci": {"git", "ci/cd"},
    "jenkins": {"ci/cd"},
    "github": {"git"},
}


def canonicalize(skill: str) -> str:
    """Forme canonique d'une compétence : normalisée (casse/espaces) puis alias appliqué."""
    key = " ".join(skill.split()).lower()
    return _ALIASES.get(key, key)


def _implied_closure(canonical: str) -> set[str]:
    """Fermeture transitive des implications d'une compétence canonique (elle exclue)."""
    result: set[str] = set()
    stack = list(_IMPLIES.get(canonical, ()))
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(_IMPLIES.get(current, ()))
    return result


def expand_skills(skills: Iterable[str]) -> set[str]:
    """Ensemble canonique des compétences **étendu** par les implications de familles.

    Chaque compétence est canonicalisée puis complétée par ce qu'elle implique
    (transitivement). Le résultat sert de « ce que le profil sait faire » face aux
    compétences exigées par une offre.
    """
    owned: set[str] = set()
    for skill in skills:
        canonical = canonicalize(skill)
        if not canonical:
            continue
        owned.add(canonical)
        owned |= _implied_closure(canonical)
    return owned

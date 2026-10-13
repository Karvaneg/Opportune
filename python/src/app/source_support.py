"""Briques communes aux sources d'offres (V1, OPP-120).

Les connecteurs (France Travail, Adzuna — et d'autres à venir) partagent la même mécanique
d'adaptation, indépendante de l'API source : borner une taille de page / un plafond de
collecte dans des limites, et recomposer un ``raw_text`` lisible à partir de champs
structurés (titre, entreprise, lieu, contrat, description). Ces deux utilitaires sont donc
factorisés ici — à l'image de ``collection_runner`` pour les runners — pour que chaque source
concrète ne garde que l'extraction de ses propres champs.
"""

from __future__ import annotations


def clamp(value: int, low: int, high: int) -> int:
    """Ramène ``value`` dans ``[low, high]`` (bornes incluses)."""
    return max(low, min(value, high))


def assemble_raw_text(
    *, title: str, company: str, location: str, contract: str, description: str
) -> str:
    """Recompose un texte d'offre lisible à partir de champs déjà extraits et nettoyés.

    En-tête (``titre — entreprise``, puis lignes ``Lieu :`` / ``Type de contrat :``
    renseignées), puis la description, séparés par une ligne vide. Seules les lignes non vides
    sont conservées : une offre sans description reste exploitable (en-tête seul), et une offre
    entièrement vide produit un texte vide — que le socle traite comme un échec d'intake, pas
    comme une offre fantôme persistée.
    """
    titre = f"{title} — {company}" if title and company else title or company
    header = [
        ligne
        for ligne in (
            titre,
            f"Lieu : {location}" if location else "",
            f"Type de contrat : {contract}" if contract else "",
        )
        if ligne
    ]
    blocs = [bloc for bloc in ("\n".join(header), description) if bloc]
    return "\n\n".join(blocs).strip()

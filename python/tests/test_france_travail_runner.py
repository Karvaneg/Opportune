"""Tests spécifiques au runner France Travail (OPP-120).

Le lancement de passe et le rendu du bilan sont couverts par ``test_collection_runner`` (socle
partagé) ; ici on ne teste que ce qui est propre au runner FT : la traduction des options CLI
en filtres de recherche et la conformité de la source au port consommé.
"""

from app.france_travail_client import FranceTravailClient, FranceTravailCredentials
from app.france_travail_runner import _filters_from_args
from app.france_travail_source import FranceTravailSource
from app.offer_source import SourceOffres


class _Args:
    def __init__(self, mots_cles="", code_rome="", commune=""):
        self.mots_cles = mots_cles
        self.code_rome = code_rome
        self.commune = commune


def test_filters_from_args_keeps_only_non_empty():
    args = _Args(mots_cles="python", code_rome="", commune="75056")
    assert _filters_from_args(args) == {"motsCles": "python", "commune": "75056"}


def test_filters_from_args_empty_when_no_option():
    assert _filters_from_args(_Args()) == {}


def test_france_travail_source_is_a_valid_source_protocol():
    # Garde-fou : le type réel satisfait bien le port consommé par le runner.
    source = FranceTravailSource(
        FranceTravailClient(FranceTravailCredentials("c", "s"), transport=lambda *a: None)
    )
    assert isinstance(source, SourceOffres)

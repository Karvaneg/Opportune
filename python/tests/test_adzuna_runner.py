"""Tests spécifiques au runner Adzuna (OPP-120).

Le lancement de passe et le rendu du bilan sont couverts par ``test_collection_runner`` ; ici
on ne teste que ce qui est propre au runner Adzuna : la traduction des options CLI en filtres
de recherche et la conformité de la source au port consommé.
"""

from app.adzuna_client import AdzunaClient, AdzunaCredentials
from app.adzuna_runner import _filters_from_args
from app.adzuna_source import AdzunaSource
from app.offer_source import SourceOffres


class _Args:
    def __init__(self, what="", where=""):
        self.what = what
        self.where = where


def test_filters_from_args_keeps_only_non_empty():
    assert _filters_from_args(_Args(what="python", where="")) == {"what": "python"}


def test_filters_from_args_empty_when_no_option():
    assert _filters_from_args(_Args()) == {}


def test_adzuna_source_is_a_valid_source_protocol():
    source = AdzunaSource(AdzunaClient(AdzunaCredentials("a", "k"), transport=lambda url: None))
    assert isinstance(source, SourceOffres)

"""Tests du port de collecte ``SourceOffres`` et de ``RawOffer`` (OPP-119)."""

from app.offer_source import RawOffer, SourceOffres


def test_raw_offer_url_defaults_to_empty():
    raw = RawOffer(source="indeed", raw_text="texte")
    assert raw.url == ""
    assert raw.source == "indeed"
    assert raw.raw_text == "texte"


def test_source_protocol_is_satisfied_by_any_fetch_provider():
    class ListSource:
        def fetch(self):
            return [RawOffer(source="s", raw_text="t")]

    assert isinstance(ListSource(), SourceOffres)


def test_object_without_fetch_is_not_a_source():
    class NotASource:
        pass

    assert not isinstance(NotASource(), SourceOffres)

"""Tests de l'extraction de texte d'un PDF reçu en octets (OPP-137, OPP-174).

Aucune dépendance pypdf ni fichier réel : le lecteur de pages est injecté.
"""

import pytest

from hermes.pdf_extract import PdfExtractionError, extract_text_from_pdf_bytes


def test_bytes_joins_pages_and_strips():
    pages = ["  Marie\n", "Expérience : 6 ans", "  "]
    text = extract_text_from_pdf_bytes(b"%PDF-fake", read_pages=lambda _: pages)
    assert text == "Marie\nExpérience : 6 ans"


def test_bytes_passes_data_to_reader():
    seen = {}

    def reader(data):
        seen["data"] = data
        return ["texte"]

    extract_text_from_pdf_bytes(b"octets-pdf", read_pages=reader)
    assert seen["data"] == b"octets-pdf"


def test_bytes_empty_pages_raise_extraction_error():
    with pytest.raises(PdfExtractionError):
        extract_text_from_pdf_bytes(b"%PDF", read_pages=lambda _: ["", "  "])


def test_bytes_no_pages_raise_extraction_error():
    no_pages: list[str] = []

    with pytest.raises(PdfExtractionError):
        extract_text_from_pdf_bytes(b"%PDF", read_pages=lambda _: no_pages)


def test_bytes_empty_data_raises_value_error():
    with pytest.raises(ValueError):
        extract_text_from_pdf_bytes(b"", read_pages=lambda _: ["x"])

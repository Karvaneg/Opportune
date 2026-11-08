"""Tests du pipeline de collecte d'offres (OPP-119).

Source mockée + faux LLM (``MockLLMClient``) + fausse persistance : ni réseau ni SQLite.
On vérifie le bilan de collecte, le dédoublonnage **avant analyse** (aucun appel LLM pour
un doublon) et la résilience par offre.
"""

import json

import pytest

from app.llm_client import LLMError, MockLLMClient
from app.offer import Offer, compute_offer_id
from app.offer_collection import SOURCE_CAP_FACTOR, collect_offers, source_cap
from app.offer_source import RawOffer


def _response(title="Développeur Python", company="Acme"):
    return json.dumps(
        {
            "title": title,
            "company": company,
            "location": "Paris",
            "seniority": "Senior",
            "contract_type": "cdi",
            "summary": "Backend.",
            "skills": ["Python"],
            "attention_points": [],
        }
    )


class FakeOfferStore:
    """Fausse persistance en mémoire (contrat ``OfferRepository``)."""

    def __init__(self):
        self.offers: dict[str, Offer] = {}

    def save(self, offer: Offer) -> None:
        self.offers[offer.id] = offer

    def get(self, offer_id: str):
        return self.offers.get(offer_id)


class ListSource:
    """Source mockée rejouant une liste figée de ``RawOffer``."""

    def __init__(self, raws):
        self._raws = list(raws)

    def fetch(self):
        return list(self._raws)


def test_collects_normalizes_and_persists_new_offers():
    store = FakeOfferStore()
    client = MockLLMClient([_response("A"), _response("B")])
    source = ListSource(
        [
            RawOffer(source="indeed", raw_text="offre A", url="https://x.com/a"),
            RawOffer(source="indeed", raw_text="offre B", url="https://x.com/b"),
        ]
    )

    report = collect_offers(source, client=client, store=store)

    assert report.collected == 2
    assert report.stored == 2
    assert report.duplicates == 0
    assert report.failures == ()
    assert len(store.offers) == 2


def test_cancel_stops_between_offers_with_partial_report():
    # Arrêt coopératif (OPP-209) : should_cancel vrai au 2e tour → seule la 1re offre est
    # traitée, les suivantes ne sont pas consommées, et ce qui est persisté reste.
    store = FakeOfferStore()
    client = MockLLMClient([_response("A"), _response("B"), _response("C")])
    source = ListSource(
        [
            RawOffer(source="indeed", raw_text="offre A", url="https://x.com/a"),
            RawOffer(source="indeed", raw_text="offre B", url="https://x.com/b"),
            RawOffer(source="indeed", raw_text="offre C", url="https://x.com/c"),
        ]
    )
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 1  # False au 1er tour, True ensuite

    report = collect_offers(source, client=client, store=store, should_cancel=should_cancel)

    assert report.collected == 1  # une seule offre consommée avant l'arrêt
    assert report.stored == 1
    assert len(store.offers) == 1  # l'offre déjà persistée est conservée


def test_on_progress_emitted_once_per_offer_with_running_counts():
    # OPP-170 : le callback de progression est appelé après CHAQUE offre (neuve ou doublon),
    # avec les compteurs courants ; le dernier instantané reflète le bilan final.
    store = FakeOfferStore()
    client = MockLLMClient([_response("A")])  # 1 neuve puis 1 doublon
    raw = RawOffer(source="indeed", raw_text="même offre", url="https://x.com/j")
    source = ListSource([raw, raw])

    snapshots = []
    report = collect_offers(
        source, client=client, store=store, on_progress=snapshots.append
    )

    assert len(snapshots) == 2  # une émission par offre collectée
    # 1re offre neuve : collectée + persistée ; pas encore de doublon.
    assert (snapshots[0].collected, snapshots[0].stored, snapshots[0].duplicates) == (1, 1, 0)
    last = snapshots[-1]
    assert (last.collected, last.stored, last.duplicates) == (2, 1, 1)
    assert (report.collected, report.stored, report.duplicates) == (2, 1, 1)


def test_dedups_same_offer_within_one_pass_without_second_llm_call():
    store = FakeOfferStore()
    # Une seule réponse scriptée : si la 2e offre (doublon) appelait le LLM, ça lèverait.
    client = MockLLMClient([_response()])
    # Le texte mentionne « Python » pour que la compétence s'ancre (OPP-213) et évite de
    # déclencher l'enrichissement — ce test isole la dédup, pas le secours.
    raw = RawOffer(source="indeed", raw_text="même offre Python", url="https://x.com/j")
    source = ListSource([raw, raw])

    report = collect_offers(source, client=client, store=store)

    assert report.collected == 2
    assert report.stored == 1
    assert report.duplicates == 1
    assert len(store.offers) == 1
    assert len(client.calls) == 1  # dédup AVANT analyse : un seul appel LLM


def test_dedups_against_already_stored_offer():
    store = FakeOfferStore()
    client = MockLLMClient([_response()])
    raw = RawOffer(source="indeed", raw_text="offre connue", url="https://x.com/known")
    # Pré-remplit le dépôt avec cette offre.
    collect_offers(ListSource([raw]), client=client, store=store)

    # Nouvelle passe, LLM sans réponse : un ré-appel lèverait → le dédup doit l'éviter.
    report = collect_offers(ListSource([raw]), client=MockLLMClient([]), store=store)

    assert report.collected == 1
    assert report.stored == 0
    assert report.duplicates == 1
    assert len(store.offers) == 1


def test_dedups_same_url_differing_only_by_tracking_params():
    # Gain OPP-119 : deux liens vers la même offre (tracking + slash) → un seul stockage.
    store = FakeOfferStore()
    client = MockLLMClient([_response()])
    source = ListSource(
        [
            RawOffer(source="indeed", raw_text="texte 1", url="https://x.com/job/42?utm_source=li"),
            RawOffer(source="indeed", raw_text="texte 2 différent", url="https://x.com/job/42/#apply"),
        ]
    )

    report = collect_offers(source, client=client, store=store)

    assert report.stored == 1
    assert report.duplicates == 1
    assert len(store.offers) == 1
    assert len(client.calls) == 1


def test_per_offer_failure_is_recorded_and_pass_continues():
    store = FakeOfferStore()
    # 1re offre : analyse non conforme (JSON invalide) → échec consigné.
    # 2e offre : réponse valide → persistée.
    client = MockLLMClient(["pas du json", _response()])
    source = ListSource(
        [
            RawOffer(source="indeed", raw_text="offre KO", url="https://x.com/ko"),
            RawOffer(source="indeed", raw_text="offre OK", url="https://x.com/ok"),
        ]
    )

    report = collect_offers(source, client=client, store=store)

    assert report.collected == 2
    assert report.stored == 1
    assert report.duplicates == 0
    assert len(report.failures) == 1
    assert report.failures[0].raw.url == "https://x.com/ko"
    assert len(store.offers) == 1


def test_llm_error_is_captured_per_offer():
    store = FakeOfferStore()
    client = MockLLMClient(error=LLMError("réseau"))
    source = ListSource([RawOffer(source="indeed", raw_text="offre", url="https://x.com/j")])

    report = collect_offers(source, client=client, store=store)

    assert report.stored == 0
    assert len(report.failures) == 1
    assert "réseau" in report.failures[0].error
    assert store.offers == {}


def test_report_invariant_holds():
    store = FakeOfferStore()
    client = MockLLMClient([_response("A"), "pas du json", _response("C")])
    raw_dup = RawOffer(source="indeed", raw_text="A", url="https://x.com/a")
    source = ListSource(
        [
            raw_dup,
            raw_dup,  # doublon
            RawOffer(source="indeed", raw_text="KO", url="https://x.com/ko"),  # échec
            RawOffer(source="indeed", raw_text="C", url="https://x.com/c"),  # stockée
        ]
    )

    report = collect_offers(source, client=client, store=store)

    assert report.collected == report.stored + report.duplicates + len(report.failures)
    assert report.collected == 4
    assert report.stored == 2
    assert report.duplicates == 1
    assert len(report.failures) == 1


def test_offer_id_matches_precomputed_key():
    # La clé de dédup du pipeline est bien l'id que produira la persistance en aval.
    store = FakeOfferStore()
    client = MockLLMClient([_response()])
    raw = RawOffer(source="indeed", raw_text="texte", url="https://x.com/j?utm_source=li")
    collect_offers(ListSource([raw]), client=client, store=store)

    expected_id = compute_offer_id("indeed", "https://x.com/j?utm_source=li", "texte")
    assert expected_id in store.offers


def test_source_fetch_error_is_recorded_not_raised():
    # Une source qui échoue dès ``fetch`` (réseau indisponible) ne doit pas faire lever
    # collect_offers : l'erreur est consignée dans ``source_error``.
    class BrokenSource:
        def fetch(self):
            raise RuntimeError("502 Bad Gateway")

    report = collect_offers(BrokenSource(), client=MockLLMClient([]), store=FakeOfferStore())

    assert report.collected == 0
    assert report.stored == 0
    assert report.source_error is not None
    assert "502 Bad Gateway" in report.source_error


def test_source_error_mid_iteration_keeps_processed_offers():
    # La source émet une offre valide puis lève en cours d'itération : l'offre déjà
    # traitée reste persistée et comptée, l'erreur de source est consignée, pas d'exception.
    store = FakeOfferStore()
    client = MockLLMClient([_response()])

    class FlakySource:
        def fetch(self):
            yield RawOffer(source="indeed", raw_text="offre OK", url="https://x.com/ok")
            raise RuntimeError("connexion coupée")

    report = collect_offers(FlakySource(), client=client, store=store)

    assert report.collected == 1
    assert report.stored == 1
    assert report.source_error is not None
    assert "connexion coupée" in report.source_error
    assert len(store.offers) == 1


def test_source_error_is_none_on_clean_pass():
    store = FakeOfferStore()
    client = MockLLMClient([_response()])
    source = ListSource([RawOffer(source="indeed", raw_text="offre", url="https://x.com/j")])

    report = collect_offers(source, client=client, store=store)

    assert report.source_error is None


def test_collect_enriches_offer_without_skills_via_url():
    # OPP-169 : le snippet de la source ne produit aucune compétence ; la collecte récupère
    # la page complète (fetch/extract injectés) et ré-analyse → l'offre persistée porte les
    # compétences du texte enrichi. Vérifie que collect_offers câble bien l'enrichissement.
    from app.url_fetch import HtmlDocument as Doc

    store = FakeOfferStore()
    no_skills = json.dumps(
        {
            "title": "Développeur Web",
            "company": "WebCorp",
            "location": "Bordeaux",
            "seniority": "Non précisé",
            "contract_type": "cdi",
            "summary": "Poste.",
            "skills": [],
            "attention_points": [],
        }
    )
    client = MockLLMClient([no_skills, _response()])  # snippet vide, puis page complète
    source = ListSource([RawOffer(source="adzuna", raw_text="snippet", url="https://x.com/full")])

    fetched = []

    def fetch(url):
        fetched.append(url)
        return Doc(url=url, html="<html>offre complète</html>")

    report = collect_offers(
        source, client=client, store=store,
        fetch=fetch, extract=lambda html: "texte complet et riche en Python",
    )

    assert report.stored == 1
    assert report.enriched == 1  # une offre a déclenché l'enrichissement
    assert report.enriched_recovered == 1  # et a récupéré des compétences
    assert fetched == ["https://x.com/full"]
    stored = next(iter(store.offers.values()))
    assert stored.skills == ["Python"]  # issu de la ré-analyse du texte enrichi


def test_max_new_counts_new_offers_only_so_duplicates_do_not_use_up_the_cap():
    store = FakeOfferStore()
    known_raws = [RawOffer(source="ats", raw_text=f"Python connue {n}", url=f"https://x.com/k{n}") for n in range(3)]
    collect_offers(
        ListSource(known_raws),
        client=MockLLMClient([_response() for _ in known_raws]),
        store=store,
    )
    new_raws = [RawOffer(source="ats", raw_text=f"Python neuve {n}", url=f"https://x.com/n{n}") for n in range(3)]

    report = collect_offers(
        ListSource(known_raws + new_raws),
        client=MockLLMClient([_response(), _response()]),
        store=store,
        max_new=2,
    )

    assert report.duplicates == 3
    assert report.stored == 2
    assert report.collected == 5


def test_source_cap_leaves_room_for_duplicates():
    max_new = 10

    cap = source_cap(max_new)

    assert cap == max_new * SOURCE_CAP_FACTOR


# --- Recherche cible (OPP-186) ------------------------------------------------------------


class FakeLinks:
    """Faux dépôt des liens offre ↔ recherche (contrat ``CandidateOfferRepository``)."""

    def __init__(self, links=()):
        self.links: set[tuple[str, str]] = set(links)

    def link(self, candidate_id, offer_id):
        self.links.add((candidate_id, offer_id))

    def is_linked(self, candidate_id, offer_id):
        return (candidate_id, offer_id) in self.links


def _raw(name):
    return RawOffer(source="indeed", raw_text=f"offre {name}", url=f"https://x.com/{name}")


def _id(raw):
    return compute_offer_id(raw.source, raw.url, raw.raw_text)


def test_new_offer_is_linked_to_the_target_search():
    raw = _raw("a")
    links = FakeLinks()

    report = collect_offers(
        ListSource([raw]),
        client=MockLLMClient([_response("A")]),
        store=FakeOfferStore(),
        candidate_id="cand-a",
        memberships=links,
    )

    assert report.stored == 1
    assert links.links == {("cand-a", _id(raw))}


def test_offer_known_from_another_search_is_linked_as_new_without_llm():
    raw = _raw("a")
    store = FakeOfferStore()
    collect_offers(ListSource([raw]), client=MockLLMClient([_response("A")]), store=store)
    links = FakeLinks({("cand-a", _id(raw))})
    client = MockLLMClient([])

    report = collect_offers(
        ListSource([raw]), client=client, store=store, candidate_id="cand-b", memberships=links
    )

    assert (report.stored, report.duplicates) == (1, 0)
    assert ("cand-b", _id(raw)) in links.links
    assert client.calls == []


def test_offer_already_in_the_target_search_is_a_duplicate():
    raw = _raw("a")
    store = FakeOfferStore()
    collect_offers(ListSource([raw]), client=MockLLMClient([_response("A")]), store=store)
    links = FakeLinks({("cand-a", _id(raw))})

    report = collect_offers(
        ListSource([raw]),
        client=MockLLMClient([]),
        store=store,
        candidate_id="cand-a",
        memberships=links,
    )

    assert (report.stored, report.duplicates) == (0, 1)


def test_failed_intake_links_nothing():
    links = FakeLinks()

    report = collect_offers(
        ListSource([_raw("a")]),
        client=MockLLMClient(["pas du json"]),
        store=FakeOfferStore(),
        candidate_id="cand-a",
        memberships=links,
    )

    assert len(report.failures) == 1
    assert links.links == set()


def test_candidate_id_without_memberships_is_refused():
    with pytest.raises(ValueError):
        collect_offers(
            ListSource([]), client=MockLLMClient([]), store=FakeOfferStore(), candidate_id="c"
        )

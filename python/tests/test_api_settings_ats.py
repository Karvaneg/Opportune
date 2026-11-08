"""Tests des endpoints de saisie des entreprises ciblées (/settings/ats, OPP-226).

Store réel sur un fichier temporaire, client d'ATS factice (aucun réseau). On vérifie le contrat
HTTP : lecture, enregistrement avec vérification, erreurs 400/502/500, et 404 quand le store
n'est pas câblé.
"""

from api.app import HermesApi
from app.ats_client import AtsNotFoundError, AtsUnavailableError
from app.ats_companies_store import AtsCompaniesStore
from app.ats_company import LEVER, AtsCompany
from app.auth import LocalAuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

LOCAL_USER = User("moi", frozenset({"cand-1"}))


class FakeAtsClient:
    def __init__(self, jobs_by_slug: dict[str, object] | None = None) -> None:
        self._jobs_by_slug = jobs_by_slug or {}

    def list_jobs(self, company: AtsCompany, *, with_content: bool = True) -> list[dict]:
        jobs = self._jobs_by_slug.get(company.slug, [])
        if isinstance(jobs, Exception):
            raise jobs
        return jobs


def _api(store, *, client=None, user=LOCAL_USER) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(
        orchestrator,
        auth=LocalAuthProvider(user),
        ats_companies=store,
        ats_client=client or FakeAtsClient(),
    )


def test_get_lists_saved_companies_without_offer_counts(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    store.save([AtsCompany(LEVER, "swile")])

    response = _api(store).dispatch("GET", "/settings/ats", None, None)

    assert response.status == 200
    assert response.body == {
        "companies": [
            {
                "url": "https://jobs.lever.co/swile",
                "ats": "lever",
                "slug": "swile",
                "offers_in_france": None,
            }
        ]
    }


def test_put_saves_and_returns_offer_counts(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    client = FakeAtsClient({"swile": [{"country": "FR"}, {"country": "FR"}]})

    response = _api(store, client=client).dispatch(
        "PUT", "/settings/ats", {"companies": ["jobs.lever.co/swile/"]}
    )

    assert response.status == 200
    assert response.body["companies"][0]["offers_in_france"] == 2
    assert store.load() == [AtsCompany(LEVER, "swile")]


def test_put_empty_list_removes_every_company(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    store.save([AtsCompany(LEVER, "swile")])

    response = _api(store).dispatch("PUT", "/settings/ats", {"companies": []})

    assert response.status == 200
    assert response.body == {"companies": []}
    assert store.load() == []


def test_put_rejects_non_list_unknown_url_and_unknown_company(tmp_path):
    client = FakeAtsClient({"ghost": AtsNotFoundError("404")})
    api = _api(AtsCompaniesStore(tmp_path / "ats.json"), client=client)

    not_a_list = api.dispatch("PUT", "/settings/ats", {"companies": "jobs.lever.co/swile"})
    unknown_url = api.dispatch("PUT", "/settings/ats", {"companies": ["https://wttj.com/x"]})
    unknown_company = api.dispatch("PUT", "/settings/ats", {"companies": ["jobs.lever.co/ghost"]})

    assert not_a_list.status == 400
    assert unknown_url.status == 400
    assert unknown_company.status == 400


def test_put_answers_502_when_the_ats_cannot_be_reached(tmp_path):
    client = FakeAtsClient({"swile": AtsUnavailableError("réseau")})
    api = _api(AtsCompaniesStore(tmp_path / "ats.json"), client=client)

    response = api.dispatch("PUT", "/settings/ats", {"companies": ["jobs.lever.co/swile"]})

    assert response.status == 502


class _UnwritableStore(AtsCompaniesStore):
    def save(self, companies):
        raise PermissionError("lecture seule")


def test_put_answers_500_when_the_file_cannot_be_written(tmp_path):
    api = _api(_UnwritableStore(tmp_path / "ats.json"))

    response = api.dispatch("PUT", "/settings/ats", {"companies": ["jobs.lever.co/swile"]})

    assert response.status == 500
    assert "enregistrement des entreprises impossible" in response.body["error"]


def test_route_absent_without_store():
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator, auth=LocalAuthProvider(LOCAL_USER))

    response = api.dispatch("GET", "/settings/ats", None, None)

    assert response.status == 404


def test_put_refuses_non_text_entries_without_clearing(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    store.save([AtsCompany(LEVER, "swile")])

    response = _api(store).dispatch("PUT", "/settings/ats", {"companies": [None]})

    assert response.status == 400
    assert store.load() == [AtsCompany(LEVER, "swile")]

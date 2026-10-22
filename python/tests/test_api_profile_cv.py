"""Tests de la route d'import de CV PDF (POST /candidates/{id}/profile/cv, OPP-174).

Intake injecté (faux) : on vérifie le contrat HTTP — décodage base64, délégation,
sérialisation du profil, gardes propriété/reviewer, mapping des erreurs, route optionnelle.
Aucun PDF réel, aucun LLM.
"""

import base64

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, AuthProvider, User
from app.candidate_profile import ProfileValidationError, create_profile
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.llm_client import LLMError
from app.offer_store import OfferStore
from app.profile_analysis import ProfileAnalysisError
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.pdf_extract import PdfExtractionError
from hermes.run_store import RunStore

PDF_B64 = base64.b64encode(b"%PDF-1.4 fake bytes").decode("ascii")


class FakeCvIntake:
    """Faux intake CV : enregistre les appels, retourne un profil ou lève une erreur."""

    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, candidate_id, pdf_bytes, *, contract_type, **preferences):
        self.calls.append(
            {
                "candidate_id": candidate_id,
                "pdf_bytes": pdf_bytes,
                "contract_type": contract_type,
                "preferences": preferences,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


def _profile(candidate_id="cand-1"):
    return create_profile(id=candidate_id, name="Marie", skills=["React"], contract_type="CDI")


def _api(cv_intake, *, auth=None) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=auth, cv_intake=cv_intake)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _auth():
    return AuthProvider({
        "tok-rev": User("rev", REVIEWER, frozenset({"cand-1"})),
        "tok-view": User("view", "viewer", frozenset({"cand-1"})),
        "tok-other": User("other", REVIEWER, frozenset({"cand-2"})),
    })


def _post(api, body, headers=None, candidate="cand-1"):
    return api.dispatch("POST", f"/candidates/{candidate}/profile/cv", body, headers)


# --- Succès ------------------------------------------------------------------

def test_decodes_pdf_and_delegates_to_intake():
    intake = FakeCvIntake(result=_profile())
    api = _api(intake)
    resp = _post(api, {"pdf_base64": PDF_B64, "contract_type": "CDI"})
    assert resp.status == 200
    assert resp.body["id"] == "cand-1"
    assert resp.body["name"] == "Marie"
    # Le PDF est bien décodé (bytes), le candidat et le contrat transmis tels quels.
    call = intake.calls[0]
    assert call["pdf_bytes"] == b"%PDF-1.4 fake bytes"
    assert call["candidate_id"] == "cand-1"
    assert call["contract_type"] == "CDI"


def test_forwards_known_preferences_only():
    intake = FakeCvIntake(result=_profile())
    api = _api(intake)
    _post(
        api,
        {
            "pdf_base64": PDF_B64,
            "contract_type": "freelance",
            "target_daily_rate": 500,
            "mobility": "France entière",
            "inconnu": "ignoré",  # clé hors allowlist → écartée
        },
    )
    prefs = intake.calls[0]["preferences"]
    assert prefs == {"target_daily_rate": 500, "mobility": "France entière"}


# --- Décodage base64 ---------------------------------------------------------

@pytest.mark.parametrize("bad", [None, "", "   ", 123, "pas du base64 !!"])
def test_invalid_or_missing_base64_is_400_without_calling_intake(bad):
    intake = FakeCvIntake(result=_profile())
    api = _api(intake)
    resp = _post(api, {"pdf_base64": bad, "contract_type": "CDI"})
    assert resp.status == 400
    assert intake.calls == []  # on ne délègue jamais un corps invalide


def test_empty_pdf_after_decode_is_400():
    intake = FakeCvIntake(result=_profile())
    api = _api(intake)
    resp = _post(api, {"pdf_base64": base64.b64encode(b"").decode(), "contract_type": "CDI"})
    assert resp.status == 400
    assert intake.calls == []


def test_oversized_pdf_is_400_without_calling_intake():
    intake = FakeCvIntake(result=_profile())
    api = _api(intake)
    oversized = base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
    resp = _post(api, {"pdf_base64": oversized, "contract_type": "CDI"})
    assert resp.status == 400
    assert intake.calls == []  # on ne charge jamais un CV démesuré jusqu'à l'intake


# --- Auth --------------------------------------------------------------------

def test_requires_token_owner_and_reviewer():
    api = _api(FakeCvIntake(result=_profile()), auth=_auth())
    body = {"pdf_base64": PDF_B64, "contract_type": "CDI"}
    assert _post(api, body, None).status == 401  # pas de jeton
    assert _post(api, body, _hdr("tok-other")).status == 404  # owner d'un autre candidat
    assert _post(api, body, _hdr("tok-view")).status == 403  # propriétaire mais non reviewer
    assert _post(api, body, _hdr("tok-rev")).status == 200


# --- Route optionnelle / méthode ---------------------------------------------

def test_route_absent_without_cv_intake():
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator)  # pas d'intake CV → route non montée
    assert _post(api, {"pdf_base64": PDF_B64, "contract_type": "CDI"}).status == 404


def test_unsupported_method_405():
    api = _api(FakeCvIntake(result=_profile()))
    assert api.dispatch("GET", "/candidates/cand-1/profile/cv", None, None).status == 405


# --- Mapping des erreurs métier ----------------------------------------------

@pytest.mark.parametrize(
    "error,status",
    [
        (PdfExtractionError("PDF scanné"), 400),
        (ProfileValidationError("aucune compétence"), 400),
        (ValueError("CV vide"), 400),
        (ProfileAnalysisError("JSON non conforme"), 502),
        (LLMError("Ollama injoignable"), 502),
    ],
)
def test_maps_intake_errors(error, status):
    api = _api(FakeCvIntake(error=error))
    resp = _post(api, {"pdf_base64": PDF_B64, "contract_type": "CDI"})
    assert resp.status == status

"""Tests des routes d'export / import des données (OPP-232) : contrat HTTP."""

import base64
import sqlite3

from api.app import HermesApi
from app.auth import REVIEWER, LocalAuthProvider, User
from app.data_transfer_service import DataTransferBusy, ExportTooLarge
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

REVIEWER_USER = User("moi", REVIEWER, frozenset({"cand-1"}))
VIEWER_USER = User("moi", "viewer", frozenset({"cand-1"}))


class FakeExport:
    content = b"zip"
    filename = "opportune-export-2026-11-05.zip"


class FakeDataTransfer:
    def __init__(self, tmp_path, *, import_error=None, export_error=None):
        self._import_error = import_error
        self._export_error = export_error
        self.imported: list[bytes] = []

    def export(self):
        if self._export_error is not None:
            raise self._export_error
        return FakeExport()

    def import_(self, data):
        if self._import_error is not None:
            raise self._import_error
        self.imported.append(data)


def _api(data_transfer, *, user=REVIEWER_USER) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=LocalAuthProvider(user), data_transfer=data_transfer)


def test_export_returns_the_encoded_archive_and_its_name(tmp_path):
    api = _api(FakeDataTransfer(tmp_path))

    response = api.dispatch("POST", "/data/export", {})

    assert response.status == 200
    assert response.body == {
        "archive_base64": base64.b64encode(b"zip").decode(),
        "filename": "opportune-export-2026-11-05.zip",
    }


def test_import_decodes_the_archive(tmp_path):
    data_transfer = FakeDataTransfer(tmp_path)
    api = _api(data_transfer)

    response = api.dispatch(
        "POST", "/data/import", {"archive_base64": base64.b64encode(b"zip").decode()}
    )

    assert response.status == 200
    assert data_transfer.imported == [b"zip"]


def test_import_errors_map_to_400_409_500_503(tmp_path):
    body = {"archive_base64": base64.b64encode(b"zip").decode()}

    invalid = _api(FakeDataTransfer(tmp_path, import_error=ValueError("pas un export")))
    busy = _api(FakeDataTransfer(tmp_path, import_error=DataTransferBusy("collecte en cours")))
    disk = _api(FakeDataTransfer(tmp_path, import_error=PermissionError("lecture seule")))
    database = _api(FakeDataTransfer(tmp_path, import_error=sqlite3.DatabaseError("disk I/O error")))
    locked = _api(
        FakeDataTransfer(tmp_path, import_error=sqlite3.OperationalError("database is locked"))
    )
    bad_base64 = _api(FakeDataTransfer(tmp_path))

    assert invalid.dispatch("POST", "/data/import", body).status == 400
    assert busy.dispatch("POST", "/data/import", body).status == 409
    assert disk.dispatch("POST", "/data/import", body).status == 500
    assert database.dispatch("POST", "/data/import", body).status == 500
    assert locked.dispatch("POST", "/data/import", body).status == 503
    assert bad_base64.dispatch("POST", "/data/import", {"archive_base64": "%%%"}).status == 400


def test_routes_require_the_reviewer_role(tmp_path):
    api = _api(FakeDataTransfer(tmp_path), user=VIEWER_USER)

    response = api.dispatch("POST", "/data/export", {})

    assert response.status == 403


def test_routes_are_absent_without_data_transfer(tmp_path):
    api = _api(None)

    response = api.dispatch("POST", "/data/export", {})

    assert response.status == 404


def test_export_too_large_to_be_imported_back_is_413(tmp_path):
    api = _api(FakeDataTransfer(tmp_path, export_error=ExportTooLarge("trop gros")))

    response = api.dispatch("POST", "/data/export", {})

    assert response.status == 413

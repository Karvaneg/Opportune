"""Tests du service d'export / import des données (OPP-232)."""

from datetime import datetime

import pytest

from app import data_transfer_service
from app.data_transfer_service import DataTransferBusy, DataTransferService, ExportTooLarge
from app.database_schema import ensure_schema
from app.db import connect


def _service(tmp_path, conn, *, busy=False):
    return DataTransferService(
        conn=conn,
        settings_files=[tmp_path / "rss.json"],
        app_version="1.0.0",
        ensure_schema=ensure_schema,
        is_busy=lambda: busy,
        now=lambda: datetime(2026, 11, 5, 10, 0, 0),
    )


def test_export_names_the_archive_after_the_day(tmp_path):
    service = _service(tmp_path, connect(":memory:"))

    export = service.export()

    assert export.filename == "opportune-export-2026-11-05.zip"
    assert export.content.startswith(b"PK")


def test_export_then_import_round_trips_the_data(tmp_path):
    source = connect(str(tmp_path / "source.db"))
    source.execute("CREATE TABLE notes (value TEXT)")
    source.execute("INSERT INTO notes VALUES ('gardée')")
    source.commit()
    exported = _service(tmp_path, source).export()
    target = connect(str(tmp_path / "target.db"))

    _service(tmp_path, target).import_(exported.content)

    assert [row[0] for row in target.execute("SELECT value FROM notes")] == ["gardée"]


def test_import_is_refused_while_a_collection_runs(tmp_path):
    service = _service(tmp_path, connect(":memory:"), busy=True)

    with pytest.raises(DataTransferBusy):
        service.import_(b"peu importe")


def test_export_too_large_to_be_imported_back_is_refused(tmp_path, monkeypatch):
    service = _service(tmp_path, connect(":memory:"))
    monkeypatch.setattr(data_transfer_service, "MAX_ARCHIVE_BYTES", 10)

    with pytest.raises(ExportTooLarge):
        service.export()

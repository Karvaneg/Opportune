"""Câblage des clés Adzuna dans l'API assemblée : seules les clés saisies comptent (OPP-227)."""

import time

from api.server import assemble_api, build_local_auth
from app.db import connect


def _wait_for_job(api, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = api.dispatch("GET", f"/collect/{job_id}", None, None).body
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("le job de collecte ne s'est pas terminé")


def test_collect_ignores_environment_keys_when_none_are_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "env-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "env-key")
    conn = connect(str(tmp_path / "opportune.db"))
    api = assemble_api(
        conn, build_local_auth(lambda: ["cand-1"]), settings_dir=tmp_path / "settings"
    )

    started = api.dispatch(
        "POST", "/collect", {"source": "adzuna", "what": "python", "candidate_id": "cand-1"}
    )
    finished_job = _wait_for_job(api, started.body["job_id"])
    settings = api.dispatch("GET", "/settings/adzuna", None, None).body

    assert settings == {"configured": False}
    assert finished_job["status"] == "done"
    assert finished_job["report"]["stored"] == 0
    assert "Clés Adzuna non configurées" in finished_job["report"]["source_error"]

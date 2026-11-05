"""Câblage de la source « entreprises ciblées » dans l'API assemblée (OPP-226, RG-8/RG-10)."""

import time

from api.server import assemble_api, build_local_auth
from app import ats_source
from app.ats_source import AtsSource
from app.ats_company import LEVER, AtsCompany
from app.db import connect


def _wait_for_job(api, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = api.dispatch("GET", f"/collect/{job_id}", None, None).body
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("le job de collecte ne s'est pas terminé")


def test_collect_without_target_companies_reports_a_clear_source_error(tmp_path):
    conn = connect(str(tmp_path / "opportune.db"))
    api = assemble_api(conn, build_local_auth(lambda: []), settings_dir=tmp_path / "settings")

    started = api.dispatch("POST", "/collect", {"source": "ats"})
    finished_job = _wait_for_job(api, started.body["job_id"])

    assert finished_job["status"] == "done"
    assert finished_job["report"]["source_error"] == (
        "Aucune entreprise ciblée : ajoute des pages carrière dans les Réglages."
    )


def test_each_space_keeps_its_own_target_companies(tmp_path):
    mine_conn = connect(str(tmp_path / "mine.db"))
    demo_conn = connect(str(tmp_path / "demo.db"))
    mine = assemble_api(mine_conn, build_local_auth(lambda: []), settings_dir=tmp_path / "mine")
    demo = assemble_api(demo_conn, build_local_auth(lambda: []), settings_dir=tmp_path / "demo")
    mine.ats_companies.save([AtsCompany(LEVER, "swile")])

    demo_companies = demo.dispatch("GET", "/settings/ats", None, None).body

    assert demo_companies == {"companies": []}


class _EmptyAtsClient:
    def list_jobs(self, company, *, with_content=True):
        return []


def test_collect_passes_the_job_title_to_the_ats_title_filter(tmp_path, monkeypatch):
    captured = {}

    def fake_build_ats_source(companies, *, max_offers, title_query):
        captured["title_query"] = title_query
        return AtsSource(companies, client=_EmptyAtsClient(), title_query=title_query)

    monkeypatch.setattr(ats_source, "build_ats_source", fake_build_ats_source)
    conn = connect(str(tmp_path / "opportune.db"))
    api = assemble_api(conn, build_local_auth(lambda: []), settings_dir=tmp_path / "settings")
    api.ats_companies.save([AtsCompany(LEVER, "swile")])

    started = api.dispatch("POST", "/collect", {"source": "ats", "what": " data analyst "})
    finished_job = _wait_for_job(api, started.body["job_id"])

    assert finished_job["status"] == "done"
    assert captured == {"title_query": "data analyst"}

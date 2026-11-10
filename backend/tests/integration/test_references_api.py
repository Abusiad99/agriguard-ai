"""Knowledge-base references API and their use in reports. All references, diseases and
treatments here are SYNTHETIC test fixtures (example.test URLs)."""
from __future__ import annotations

import io

from PIL import Image

from app.infrastructure.db.models.user_model import UserModel
from tests.conftest import make_auth_header
from tests.integration.test_reports_api import kb  # noqa: F401 - synthetic knowledge-base fixture


def _promote(db_session, email, role):
    user = db_session.query(UserModel).filter(UserModel.email == email).one()
    user.role = role
    db_session.commit()


def _ref(**extra):
    return {"title": "Synthetic extension sheet", "organization": "Test Extension (synthetic)", "url": "https://example.test/sheet",
            "source_type": "university_extension", "publication_date": "2021", "verified_on": "2026-11-01", **extra}


class TestReferenceApi:
    def test_permissions_and_validation(self, client, db_session):
        farmer = make_auth_header(client, email="ref-farmer@example.com")
        agro = make_auth_header(client, email="ref-agro@example.com")
        _promote(db_session, "ref-agro@example.com", "agronomist")
        assert client.post("/api/v1/references", headers=farmer, json=_ref()).status_code == 403
        created = client.post("/api/v1/references", headers=agro, json=_ref())
        assert created.status_code == 201, created.text
        assert client.post("/api/v1/references", headers=agro, json=_ref()).status_code == 409           # same URL
        assert client.post("/api/v1/references", headers=agro, json=_ref(url="ftp://x.test")).status_code == 400
        assert client.post("/api/v1/references", headers=agro, json=_ref(url="https://x.test/2", source_type="blog")).status_code == 400
        assert client.post("/api/v1/references", headers=agro, json=_ref(url="https://x.test/3", verified_on="2999-01-01")).status_code == 400
        assert client.post("/api/v1/references", headers=agro, json={"url": "https://x.test/4"}).status_code == 400  # no title
        # everyone signed in can read; nobody anonymous
        listing = client.get("/api/v1/references", headers=farmer).json()
        assert listing["total"] == 1 and listing["items"][0]["title"] == "Synthetic extension sheet"
        assert client.get("/api/v1/references").status_code == 401
        catalog = client.get("/api/v1/references/catalog", headers=farmer).json()
        assert any(r["id"] == "ref-umn-prevention" for r in catalog["references"])

    def test_claims_attach_to_existing_knowledge_only(self, client, db_session, kb):  # noqa: F811
        agro = make_auth_header(client, email="ref-agro2@example.com")
        _promote(db_session, "ref-agro2@example.com", "agronomist")
        ref = client.post("/api/v1/references", headers=agro, json=_ref(url="https://example.test/eb")).json()
        ok = client.post(f"/api/v1/references/{ref['id']}/claims", headers=agro,
                         json={"subject_type": "disease", "subject_key": "tomato/early_blight", "claim": "Synthetic symptom claim."})
        assert ok.status_code == 201, ok.text
        assert ok.json()["claims"][0]["subject_key"] == "tomato/early_blight"
        bad = [{"subject_type": "disease", "subject_key": "tomato/no_such_disease", "claim": "x"},
               {"subject_type": "treatment", "subject_id": "00000000-0000-0000-0000-000000000000", "claim": "x"},
               {"subject_type": "disease", "subject_key": "tomato/early_blight", "claim": " "},
               {"subject_type": "opinion", "subject_key": "x", "claim": "x"}]
        for body in bad:
            assert client.post(f"/api/v1/references/{ref['id']}/claims", headers=agro, json=body).status_code == 400, body
        by_subject = client.get("/api/v1/references?subject_type=disease&subject_key=tomato/early_blight", headers=agro).json()
        assert [r["id"] for r in by_subject["items"]] == [ref["id"]]
        # deactivated references disappear from listings (and reports) but are kept
        assert client.delete(f"/api/v1/references/{ref['id']}", headers=agro).json()["is_active"] is False
        assert client.get("/api/v1/references", headers=agro).json()["total"] == 0
        assert client.get("/api/v1/references?include_inactive=true", headers=agro).json()["total"] == 1
        from app.infrastructure.db.models.diagnosis_model import AuditLogModel
        actions = {a.action for a in db_session.query(AuditLogModel).filter(AuditLogModel.entity_type == "knowledge_reference")}
        assert {"create_reference", "add_reference_claim", "deactivate_reference"} <= actions

    def test_reports_cite_knowledge_base_references(self, client, db_session, kb):  # noqa: F811
        from app.infrastructure.db.models.knowledge_base_model import TreatmentModel

        agro = make_auth_header(client, email="ref-agro3@example.com")
        _promote(db_session, "ref-agro3@example.com", "agronomist")
        ref = client.post("/api/v1/references", headers=agro, json=_ref(url="https://example.test/report")).json()
        client.post(f"/api/v1/references/{ref['id']}/claims", headers=agro,
                    json={"subject_type": "disease", "subject_key": "tomato/early_blight", "claim": "Synthetic description claim."})
        organic = db_session.query(TreatmentModel).filter_by(disease_id=kb.id, category="organic").one()
        client.post(f"/api/v1/references/{ref['id']}/claims", headers=agro,
                    json={"subject_type": "treatment", "subject_id": str(organic.id), "claim": "Synthetic treatment claim."})

        owner = make_auth_header(client, email="ref-owner@example.com")
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (70, 120, 50)).save(buf, format="JPEG")
        buf.seek(0)
        dx = client.post("/api/v1/scans", headers=owner, files={"image": ("leaf.jpg", buf, "image/jpeg")}).json()
        rep = client.post("/api/v1/agri-reports", headers=owner, json={"type": "diagnosis", "subject_id": dx["diagnosis_id"]})
        assert rep.status_code == 201, rep.text
        body = rep.json()
        c = body["content"]
        kb_ref = next(r for r in c["references"] if r["origin"] == "knowledge_base")
        assert kb_ref["url"] == "https://example.test/report"
        assert set(kb_ref["claims"]) == {"Synthetic description claim.", "Synthetic treatment claim."}
        knowledge = next(s for s in c["sections"] if s["id"] == "knowledge")
        assert kb_ref["id"] in next(f for f in knowledge["facts"] if f["key"] == "description")["refs"]
        organic_rec = next(r for r in c["recommendations"] if r["rule"] == "R-KB-TREATMENT" and kb_ref["id"] in r["refs"])
        assert organic_rec["basis"] == "knowledge_base"
        assert {"kind": "reference", "table": "knowledge_references", "id": ref["id"]} in body["sources"]
        # a shared copy keeps the citation (references are public sources, not personal data)
        share = client.post(f"/api/v1/agri-reports/{body['id']}/shares", headers=owner, json={"expires_in_days": 1}).json()
        shared = client.get(f"/api/v1/shared-reports/{share['token']}").json()
        assert any(r["url"] == "https://example.test/report" for r in shared["content"]["references"])

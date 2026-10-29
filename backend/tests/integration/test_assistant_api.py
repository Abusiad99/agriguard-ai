"""Assistant endpoint: honest modes, source metadata, validation, authorization."""
from __future__ import annotations

import io

from app.application.services import assistant_service as svc_module
from app.application.services.rag.text import chunk_text
from app.infrastructure.repositories.knowledge_document_repository import (
    DocumentMeta,
    SqlAlchemyKnowledgeDocumentRepository,
)
from tests.conftest import make_auth_header, make_leaf_like_image_bytes

FIXTURE_TEXT = (
    "# Symptoms\nTest-fixture document: early blight on tomato shows concentric rings on older leaves. "
    "Lesions may be surrounded by yellow tissue. This text exists only for automated tests.\n\n"
    "# Monitoring\nCheck lower leaves weekly and record new lesions."
)


def _seed(db_session):
    svc_module._INDEX_CACHE.update(signature=None, index=None)
    repo = SqlAlchemyKnowledgeDocumentRepository(db_session)
    repo.add_document(DocumentMeta(title="Fixture: tomato early blight", organization="Test fixture organization",
                                   source_type="other", source_url="https://example.org/fixture",
                                   crops=("tomato",), diseases=("early_blight",)),
                      FIXTURE_TEXT, chunk_text(FIXTURE_TEXT))


def test_empty_knowledge_base_reports_no_sources(client, db_session):
    svc_module._INDEX_CACHE.update(signature=None, index=None)
    h = make_auth_header(client, email="asst1@example.com")
    r = client.post("/api/v1/assistant/chat", headers=h, json={"message": "What does early blight look like?"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "no_sources" and body["answer"] is None
    assert "knowledge_base_empty" in body["notices"]


def test_retrieval_only_returns_cited_source_metadata(client, db_session, monkeypatch):
    monkeypatch.setattr(svc_module.settings, "gemini_api_key", "")
    _seed(db_session)
    h = make_auth_header(client, email="asst2@example.com")
    r = client.post("/api/v1/assistant/chat", headers=h, json={"message": "concentric rings on tomato leaves"})
    body = r.json()
    assert body["mode"] == "retrieval_only"
    src = body["sources"][0]
    assert src["id"] == "S1" and src["organization"] == "Test fixture organization"
    assert src["url"] == "https://example.org/fixture" and "concentric rings" in src["excerpt"]
    docs = client.get("/api/v1/assistant/sources", headers=h).json()
    assert docs["total"] == 1 and docs["items"][0]["chunk_count"] >= 1


def test_validation_and_auth(client):
    h = make_auth_header(client, email="asst3@example.com")
    assert client.post("/api/v1/assistant/chat", json={"message": "hi"}).status_code == 401
    # Request-validation failures use the API's standard 400 VALIDATION_ERROR envelope.
    assert client.post("/api/v1/assistant/chat", headers=h, json={"message": "x" * 2001}).status_code == 400
    assert client.post("/api/v1/assistant/chat", headers=h, json={"message": "hi", "language": "fr"}).status_code == 400


def test_diagnosis_context_is_owner_only(client):
    owner = make_auth_header(client, email="asst-owner@example.com")
    other = make_auth_header(client, email="asst-other@example.com")
    d = client.post("/api/v1/scans", headers=owner,
                    files={"image": ("leaf.jpg", io.BytesIO(make_leaf_like_image_bytes()), "image/jpeg")}).json()
    r = client.post("/api/v1/assistant/chat", headers=other,
                    json={"message": "what is this?", "diagnosis_id": d["diagnosis_id"]})
    assert r.status_code == 404
    ok = client.post("/api/v1/assistant/chat", headers=owner,
                     json={"message": "what is this?", "diagnosis_id": d["diagnosis_id"]})
    assert ok.status_code == 200
    assert any("candidate" in m for m in ok.json()["context_used"]["model_result"])

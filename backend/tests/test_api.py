from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.main import app


client = TestClient(app)


def _make_pdf(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buffer.getvalue()


def test_health(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_translate_text(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.post(
        "/api/translate",
        json={"text": "If $x^2$ is positive.", "direction": "en2ar"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "mock"
    assert "<MATH_0>" not in payload["translated_text"]
    assert "$x^2$" in payload["translated_text"]


def test_translate_document(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.post(
        "/api/translate/document",
        data={"direction": "en2ar"},
        files={"file": ("sample.pdf", _make_pdf("If x > 0 then f(x) = x."), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"

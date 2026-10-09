from types import SimpleNamespace

# pyrefly: ignore [missing-import]
import pytest
from fastapi import HTTPException

from backend.app.api.routes import InMemoryRateLimiter, ask, get_conversation, health
from backend.app.config import Settings
from backend.app.schemas.chat import AskRequest, AskResponse

class FakeDB:
    def create_conversation(self) -> tuple[str, str]:
        return "conversation-1", "secret-token"
    def get_conversation(self, conversation_id: str, token: str):
        return [] if (conversation_id, token) == ("conversation-1", "secret-token") else None

class FakeRAG:
    def ask(self, payload, question_limit: int) -> AskResponse:
        return AskResponse(resposta="Resposta simulada", fontes=[])

def make_request(limit: int = 20):
    settings = Settings(rate_limit_per_minute=limit)
    state = SimpleNamespace(settings=settings, db=FakeDB(), rag=FakeRAG(), rate_limiter=InMemoryRateLimiter(limit))
    app = SimpleNamespace(state=state)
    return SimpleNamespace(app=app, client=SimpleNamespace(host="127.0.0.1"))

def test_health_and_ask_preserve_widget_contract() -> None:
    request = make_request()
    assert health() == {"status": "ok"}
    response = ask(request, AskRequest(pergunta="O que é RAG?"))
    assert response.resposta == "Resposta simulada"
    assert response.fontes == []
    assert response.conversa_id == "conversation-1"
    assert response.conversa_token == "secret-token"

def test_conversation_requires_opaque_token() -> None:
    request = make_request()
    with pytest.raises(HTTPException) as missing:
        get_conversation("conversation-1", request, None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as invalid:
        get_conversation("conversation-1", request, "wrong")
    assert invalid.value.status_code == 404

def test_rate_limit_returns_429() -> None:
    request = make_request(limit=1)
    ask(request, AskRequest(pergunta="primeira"))
    with pytest.raises(HTTPException) as limited:
        ask(request, AskRequest(pergunta="segunda"))
    assert limited.value.status_code == 429

def test_question_size_is_limited() -> None:
    request = make_request()
    request.app.state.settings.max_question_chars = 100
    with pytest.raises(HTTPException) as too_large:
        ask(request, AskRequest(pergunta="x" * 101))
    assert too_large.value.status_code == 413

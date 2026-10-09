"""Public API endpoints."""
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Annotated
from fastapi import APIRouter, Header, HTTPException, Request, status
from backend.app.schemas.chat import AskRequest, AskResponse

logger = logging.getLogger(__name__)
router = APIRouter()

class InMemoryRateLimiter:
    """Per-process limiter; use a shared store before scaling to multiple workers."""
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()
    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            bucket = self.events[key]
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@router.post("/ask", response_model=AskResponse)
def ask(request: Request, payload: AskRequest) -> AskResponse:
    settings = request.app.state.settings
    ip = request.client.host if request.client else "unknown"
    if not request.app.state.rate_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="Limite de perguntas atingido. Tente novamente em instantes.")
    if len(payload.pergunta) > settings.max_question_chars:
        raise HTTPException(status_code=413, detail="A pergunta excede o tamanho permitido.")
    has_conversation_id = bool(payload.conversa_id)
    has_conversation_token = bool(payload.conversa_token)
    if has_conversation_id != has_conversation_token:
        raise HTTPException(status_code=422, detail="Envie o ID e o token da conversa juntos.")
    if has_conversation_id:
        try:
            valid = request.app.state.db.validate_conversation(payload.conversa_id, payload.conversa_token)
        except Exception as error:
            logger.exception("Falha ao validar conversa")
            raise HTTPException(status_code=503, detail="Não foi possível validar a conversa.") from error
        if not valid:
            raise HTTPException(status_code=401, detail="ID ou token da conversa inválido.")
    else:
        try:
            payload.conversa_id, payload.conversa_token = request.app.state.db.create_conversation()
        except Exception as error:
            logger.exception("Falha ao criar conversa")
            raise HTTPException(status_code=503, detail="Não foi possível iniciar uma conversa.") from error
    try:
        result = request.app.state.rag.ask(payload, settings.max_question_chars)
        result.conversa_id, result.conversa_token = payload.conversa_id, payload.conversa_token
        return result
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception("Falha interna ao processar pergunta")
        raise HTTPException(status_code=502, detail="Não foi possível consultar o assistente agora.") from error

@router.get("/conversas/{conversation_id}")
def get_conversation(conversation_id: str, request: Request, x_conversa_token: Annotated[str | None, Header()] = None) -> dict:
    if not x_conversa_token:
        raise HTTPException(status_code=401, detail="Token da conversa obrigatório.")
    try:
        messages = request.app.state.db.get_conversation(conversation_id, x_conversa_token)
    except Exception as error:
        logger.exception("Falha ao consultar conversa")
        raise HTTPException(status_code=502, detail="Não foi possível consultar a conversa.") from error
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"id": conversation_id, "mensagens": messages}

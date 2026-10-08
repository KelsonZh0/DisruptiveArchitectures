"""FastAPI application factory."""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.routes import InMemoryRateLimiter, router
from backend.app.config import Settings, get_settings
from backend.app.repositories.oracle import OracleRepository
from backend.app.repositories.vectorize import VectorizeRepository
from backend.app.services.embeddings import EmbeddingService
from backend.app.services.llm import GeminiService
from backend.app.services.rag import RAGService

def create_app(settings: Settings | None = None, rag_service: RAGService | None = None) -> FastAPI:
    config = settings or get_settings()
    logging.basicConfig(level=config.log_level.upper())
    app = FastAPI(title="Disruptive Architectures RAG API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=[str(config.allowed_origin).rstrip("/")], allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "X-Conversa-Token"])
    db = OracleRepository(config.oracle_user, config.oracle_password.get_secret_value(), config.oracle_dsn)
    app.state.settings, app.state.db = config, db
    app.state.rag = rag_service or RAGService(
        db=db,
        embeddings=EmbeddingService(config.cloudflare_account_id, config.cloudflare_api_token.get_secret_value()),
        vectors=VectorizeRepository(config.cloudflare_account_id, config.cloudflare_api_token.get_secret_value(), config.vectorize_index),
        llm=GeminiService(
            config.gemini_api_key.get_secret_value(), config.gemini_model,
            config.gemini_fallback_models, config.groq_api_key.get_secret_value(), config.groq_model,
        ),
        top_k=config.retrieval_top_k, min_score=config.minimum_vector_score, max_history_turns=config.max_history_turns,
    )
    app.state.rate_limiter = InMemoryRateLimiter(config.rate_limit_per_minute)
    app.include_router(router)
    return app

app = create_app()

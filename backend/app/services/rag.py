"""RAG orchestration: history-aware retrieval and citation validation."""
import time
from typing import Any
from backend.app.repositories.oracle import OracleRepository
from backend.app.repositories.vectorize import VectorizeRepository
from backend.app.schemas.chat import AskRequest, AskResponse, Chunk
from backend.app.services.embeddings import EmbeddingService
from backend.app.services.llm import LLMService
from backend.app.services.retrieval import reciprocal_rank_fusion

class RAGService:
    def __init__(self, db: OracleRepository, embeddings: EmbeddingService, vectors: VectorizeRepository, llm: LLMService, top_k: int, min_score: float, max_history_turns: int) -> None:
        self.db, self.embeddings, self.vectors, self.llm = db, embeddings, vectors, llm
        self.top_k, self.min_score, self.max_history_turns = top_k, min_score, max_history_turns

    def ask(self, request: AskRequest, question_limit: int) -> AskResponse:
        started = time.perf_counter()
        question = request.pergunta.strip()
        if not question or len(question) > question_limit:
            raise ValueError("A pergunta está vazia ou excede o limite permitido")
        history = [item.model_dump() for item in request.historico[-self.max_history_turns * 2:]] if self.max_history_turns else []
        retrieved: list[Chunk] = []
        answer = "Não encontrei essa informação no material da disciplina."
        sources: list[Chunk] = []
        try:
            query = self.llm.rewrite_query(question, history)
            embedding = self.embeddings.embed(query)
            vector_hits = self.vectors.search(embedding, self.top_k)
            text_hits = self.db.search_text(query, self.top_k)
            fused = reciprocal_rank_fusion([vector_hits, text_hits])[:self.top_k]
            full = self.db.get_chunks([item.id for item in fused])
            retrieved = [full[item.id].model_copy(update={"score": item.score, "ranks": item.ranks}) for item in fused if item.id in full]
            vector_scores = {item.id: item.score for item in vector_hits}
            candidates = [item for item in retrieved if item.id not in vector_scores or vector_scores[item.id] >= self.min_score]
            if candidates:
                result = self.llm.answer(question, history, candidates)
                allowed = {item.id for item in candidates}
                cited = list(dict.fromkeys(item for item in result.ids_trechos_usados if item in allowed))
                if result.encontrou_no_material and cited:
                    answer = result.resposta
                    by_id = {item.id: item for item in candidates}
                    sources = [by_id[item] for item in cited]
                elif result.encontrou_no_material:
                    answer = "Não encontrei evidência suficiente no material para responder com segurança."
                else:
                    answer = result.resposta
        except Exception:
            elapsed = int((time.perf_counter() - started) * 1000)
            try:
                self.db.save_interaction(request.conversa_id, request.conversa_token, question, answer, [], elapsed, "Falha ao processar pergunta")
            except Exception:
                pass
            raise
        elapsed = int((time.perf_counter() - started) * 1000)
        logs: list[dict[str, Any]] = [{"id": item.id, "score_rrf": item.score, "ranks": item.ranks} for item in retrieved]
        usage = getattr(self.llm, "last_usage", {})
        self.db.save_interaction(
            request.conversa_id, request.conversa_token, question, answer, logs, elapsed,
            tokens_input=usage.get("input"), tokens_output=usage.get("output"),
        )
        return AskResponse(resposta=answer, fontes=[{"titulo": item.titulo, "url": item.url} for item in sources], conversa_id=request.conversa_id)

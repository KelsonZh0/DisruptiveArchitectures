from backend.app.schemas.chat import AskRequest, Chunk, ModelAnswer
from backend.app.services.rag import RAGService

class FakeDB:
    def __init__(self) -> None:
        self.saved = []
        self.chunk = Chunk(id="valid-1", titulo="Lab 4", secao="RAG", url="https://kelsonzh0.github.io/DisruptiveArchitectures/aulas/genAI/lab4/lab4/", texto="RAG recupera evidências.")
    def search_text(self, query: str, limit: int) -> list[Chunk]:
        return [self.chunk]
    def get_chunks(self, ids: list[str]) -> dict[str, Chunk]:
        return {self.chunk.id: self.chunk} if self.chunk.id in ids else {}
    def save_interaction(self, *args, **kwargs) -> None:
        self.saved.append(args)

class FakeEmbeddings:
    def embed(self, text: str) -> list[float]:
        return [0.0] * 1024

class FakeVectorize:
    def search(self, vector: list[float], top_k: int) -> list[Chunk]:
        return [Chunk(id="valid-1", titulo="Lab 4", secao="RAG", url="https://kelsonzh0.github.io/DisruptiveArchitectures/aulas/genAI/lab4/lab4/", texto="", score=0.8)]

class FakeLLM:
    def __init__(self, result: ModelAnswer) -> None:
        self.result = result
    def rewrite_query(self, question: str, history: list[dict[str, str]]) -> str:
        return question
    def answer(self, question: str, history: list[dict[str, str]], chunks: list[Chunk]) -> ModelAnswer:
        assert chunks[0].texto == "RAG recupera evidências."
        return self.result

def run(result: ModelAnswer):
    database = FakeDB()
    service = RAGService(database, FakeEmbeddings(), FakeVectorize(), FakeLLM(result), top_k=5, min_score=0.25, max_history_turns=8)
    response = service.ask(AskRequest(pergunta="O que é RAG?"), question_limit=2000)
    return response, database

def test_rag_returns_only_sources_for_ids_in_context() -> None:
    response, _ = run(ModelAnswer(resposta="O material descreve RAG.", ids_trechos_usados=["valid-1", "inventado"], encontrou_no_material=True))
    assert response.resposta == "O material descreve RAG."
    assert len(response.fontes) == 1
    assert str(response.fontes[0].url).startswith("https://kelsonzh0.github.io/")

def test_rag_rejects_affirmative_answer_without_valid_citation() -> None:
    response, _ = run(ModelAnswer(resposta="Resposta sem fonte.", ids_trechos_usados=["inventado"], encontrou_no_material=True))
    assert response.fontes == []
    assert "evidência suficiente" in response.resposta

def test_rag_logs_retrieval_metadata() -> None:
    _, database = run(ModelAnswer(resposta="Não consta.", ids_trechos_usados=[], encontrou_no_material=False))
    assert database.saved

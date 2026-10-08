"""PostgreSQL persistence and full-text search adapter."""

import hashlib
import secrets
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.schemas.chat import Chunk


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL não está configurada")
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=5)

    def search_text(self, query: str, limit: int) -> list[Chunk]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id, titulo, secao, url, texto, score FROM buscar_chunks_texto(%s, %s)", (query, limit)).fetchall()
        return [Chunk(**row) for row in rows]

    def get_chunks(self, ids: list[str]) -> dict[str, Chunk]:
        if not ids:
            return {}
        with self._connect() as connection:
            rows = connection.execute("SELECT id, titulo, secao, url, texto FROM chunks WHERE id = ANY(%s)", (ids,)).fetchall()
        return {row["id"]: Chunk(**row) for row in rows}

    def create_conversation(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).digest()
        with self._connect() as connection:
            row = connection.execute("INSERT INTO conversas (token_hash) VALUES (%s) RETURNING id", (digest,)).fetchone()
        return str(row["id"]), token

    @staticmethod
    def _valid_conversation(connection: psycopg.Connection, conversation_id: str, token: str) -> bool:
        digest = hashlib.sha256(token.encode()).digest()
        row = connection.execute("SELECT 1 FROM conversas WHERE id = %s AND token_hash = %s", (conversation_id, digest)).fetchone()
        return row is not None

    def save_interaction(self, conversation_id: str | None, conversation_token: str | None, question: str, answer: str, retrieved: list[dict[str, Any]], latency_ms: int, error: str | None = None, tokens_input: int | None = None, tokens_output: int | None = None) -> None:
        with self._connect() as connection:
            if conversation_id and conversation_token and self._valid_conversation(connection, conversation_id, conversation_token):
                connection.execute("INSERT INTO mensagens (conversa_id, papel, conteudo) VALUES (%s, 'user', %s), (%s, 'assistant', %s)", (conversation_id, question, conversation_id, answer))
                connection.execute("UPDATE conversas SET atualizada_em = now() WHERE id = %s", (conversation_id,))
            else:
                conversation_id = None
            connection.execute("INSERT INTO interaction_logs (conversa_id, pergunta, resposta, chunks_recuperados, latencia_ms, tokens_entrada, tokens_saida, erro) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (conversation_id, question, answer, Jsonb(retrieved), latency_ms, tokens_input, tokens_output, error))

    def get_conversation(self, conversation_id: str, token: str) -> list[dict[str, Any]] | None:
        with self._connect() as connection:
            if not self._valid_conversation(connection, conversation_id, token):
                return None
            return connection.execute("SELECT papel, conteudo, criada_em FROM mensagens WHERE conversa_id = %s ORDER BY criada_em, id", (conversation_id,)).fetchall()

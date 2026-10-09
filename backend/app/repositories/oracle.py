"""Oracle persistence and lexical search adapter."""

import hashlib
import json
import secrets
from datetime import datetime
from typing import Any

import oracledb

from backend.app.schemas.chat import Chunk


class OracleRepository:
    def __init__(self, user: str, password: str, dsn: str) -> None:
        self.user = user
        self.password = password
        self.dsn = dsn

    def _connect(self) -> oracledb.Connection:
        if not self.user or not self.password or not self.dsn:
            raise RuntimeError("ORACLE_USER, ORACLE_PASSWORD e ORACLE_DSN devem estar configurados")
        return oracledb.connect(user=self.user, password=self.password, dsn=self.dsn, tcp_connect_timeout=5)

    @staticmethod
    def _rows(cursor: oracledb.Cursor) -> list[dict[str, Any]]:
        columns = [column[0].lower() for column in cursor.description]
        rows = []
        for values in cursor.fetchall():
            row = dict(zip(columns, values))
            for key, value in row.items():
                if isinstance(value, oracledb.LOB):
                    row[key] = value.read()
            rows.append(row)
        return rows

    def search_text(self, query: str, limit: int) -> list[Chunk]:
        # Oracle Text is not guaranteed to be installed/enabled on the FIAP account.
        # This portable fallback ranks chunks by exact token matches.
        tokens = list(dict.fromkeys(token for token in query.lower().split() if len(token) > 1))[:12]
        if not tokens:
            return []
        clauses = " OR ".join(
            "INSTR(LOWER(titulo || ' ' || secao || ' ' || texto), :token_{} ) > 0".format(index)
            for index in range(len(tokens))
        )
        score_terms = " + ".join(
            "CASE WHEN INSTR(LOWER(titulo || ' ' || secao || ' ' || texto), :token_{}) > 0 THEN 1 ELSE 0 END".format(index)
            for index in range(len(tokens))
        )
        binds = {f"token_{index}": token for index, token in enumerate(tokens)}
        binds["limite"] = max(1, min(limit, 100))
        sql = f"""
            SELECT id, titulo, secao, url, texto, ({score_terms}) / {len(tokens)} AS score
            FROM chunks
            WHERE {clauses}
            ORDER BY score DESC, id
            FETCH FIRST :limite ROWS ONLY
        """
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, binds)
            rows = self._rows(cursor)
        return [Chunk(**row) for row in rows]

    def get_chunks(self, ids: list[str]) -> dict[str, Chunk]:
        if not ids:
            return {}
        binds = {f"id_{index}": value for index, value in enumerate(ids)}
        placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT id, titulo, secao, url, texto FROM chunks WHERE id IN ({placeholders})",
                binds,
            )
            rows = self._rows(cursor)
        return {row["id"]: Chunk(**row) for row in rows}

    def create_conversation(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as connection:
            cursor = connection.cursor()
            conversation_id = cursor.var(str, size=36)
            cursor.execute(
                "INSERT INTO conversas (token_hash) VALUES (:token_hash) RETURNING id INTO :conversation_id",
                {"token_hash": digest, "conversation_id": conversation_id},
            )
            return str(conversation_id.getvalue()), token

    @staticmethod
    def _valid_conversation(connection: oracledb.Connection, conversation_id: str, token: str) -> bool:
        digest = hashlib.sha256(token.encode()).hexdigest()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT 1 FROM conversas WHERE id = :conversation_id AND token_hash = :token_hash",
            {"conversation_id": conversation_id, "token_hash": digest},
        )
        return cursor.fetchone() is not None

    def validate_conversation(self, conversation_id: str, token: str) -> bool:
        """Validate the opaque conversation token before spending model/API calls."""
        with self._connect() as connection:
            return self._valid_conversation(connection, conversation_id, token)

    def save_interaction(
        self,
        conversation_id: str | None,
        conversation_token: str | None,
        question: str,
        answer: str,
        retrieved: list[dict[str, Any]],
        latency_ms: int,
        error: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
    ) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            if conversation_id and conversation_token and self._valid_conversation(connection, conversation_id, conversation_token):
                cursor.executemany(
                    "INSERT INTO mensagens (conversa_id, papel, conteudo) VALUES (:conversation_id, :papel, :conteudo)",
                    [
                        {"conversation_id": conversation_id, "papel": "user", "conteudo": question},
                        {"conversation_id": conversation_id, "papel": "assistant", "conteudo": answer},
                    ],
                )
                cursor.execute(
                    "UPDATE conversas SET atualizada_em = SYSTIMESTAMP WHERE id = :conversation_id",
                    {"conversation_id": conversation_id},
                )
            else:
                conversation_id = None
            cursor.execute(
                """INSERT INTO interaction_logs
                   (conversa_id, pergunta, resposta, chunks_recuperados, latencia_ms,
                    tokens_entrada, tokens_saida, erro)
                   VALUES (:conversation_id, :pergunta, :resposta, :chunks_recuperados,
                           :latencia_ms, :tokens_entrada, :tokens_saida, :erro)""",
                {
                    "conversation_id": conversation_id,
                    "pergunta": question,
                    "resposta": answer,
                    "chunks_recuperados": json.dumps(retrieved, ensure_ascii=False),
                    "latencia_ms": latency_ms,
                    "tokens_entrada": tokens_input,
                    "tokens_saida": tokens_output,
                    "erro": error,
                },
            )

    def get_conversation(self, conversation_id: str, token: str) -> list[dict[str, Any]] | None:
        with self._connect() as connection:
            if not self._valid_conversation(connection, conversation_id, token):
                return None
            cursor = connection.cursor()
            cursor.execute(
                "SELECT papel, conteudo, criada_em FROM mensagens WHERE conversa_id = :conversation_id ORDER BY criada_em, id",
                {"conversation_id": conversation_id},
            )
            rows = self._rows(cursor)
        for row in rows:
            if isinstance(row.get("criada_em"), datetime):
                row["criada_em"] = row["criada_em"].isoformat()
        return rows

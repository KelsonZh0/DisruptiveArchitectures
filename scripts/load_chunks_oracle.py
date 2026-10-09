"""Load extracted JSONL chunks into the Oracle schema used by the RAG API."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import oracledb


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="scripts/chunks.jsonl", help="JSONL produced by ingest.py")
    parser.add_argument("--version", default=None, help="Optional ingestion version; defaults to UTC timestamp")
    args = parser.parse_args()

    user = os.environ.get("ORACLE_USER", "")
    password = os.environ.get("ORACLE_PASSWORD", "")
    host = os.environ.get("ORACLE_HOST") or "oracle.fiap.com.br"
    port = int(os.environ.get("ORACLE_PORT") or "1521")
    service_name = os.environ.get("ORACLE_SERVICE_NAME") or ""
    sid = os.environ.get("ORACLE_SID") or "orcl"
    if not user or not password:
        raise SystemExit("Defina ORACLE_USER e ORACLE_PASSWORD no PowerShell antes de carregar.")
    dsn = f"{host}:{port}/{service_name or sid}"
    version = args.version or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    source = Path(args.input)
    if not source.is_file():
        raise SystemExit(f"Arquivo não encontrado: {source}")
    rows = []
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
                rows.append({
                    # Oracle treats the empty string as NULL; the schema marks
                    # SECAO NOT NULL, so store a single blank for root sections.
                    "id": chunk["id"], "titulo": chunk["titulo"], "secao": chunk.get("secao") or " ",
                    "url": chunk["url"], "origem": chunk["origem"], "indice": chunk["indice"],
                    "texto": chunk["texto"], "versao": version,
                })
            except (json.JSONDecodeError, KeyError, TypeError) as error:
                raise SystemExit(f"Chunk inválido na linha {line_number}: {error}") from error
    if not rows:
        raise SystemExit("O arquivo não contém chunks para carregar.")

    connection = oracledb.connect(user=user, password=password, dsn=dsn, tcp_connect_timeout=5)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO reindex_runs (versao, status, total_chunks) VALUES (:versao, 'processing', :total)",
                {"versao": version, "total": len(rows)},
            )
            cursor.setinputsizes(texto=oracledb.DB_TYPE_CLOB)
            cursor.executemany(
                """MERGE INTO chunks target
                   USING (
                       SELECT :id AS id, :titulo AS titulo, :secao AS secao, :url AS url,
                              :origem AS origem, :indice AS indice, :texto AS texto,
                              :versao AS versao
                       FROM dual
                   ) src
                   ON (target.id = src.id)
                   WHEN MATCHED THEN UPDATE SET
                       target.titulo = src.titulo,
                       target.secao = src.secao,
                       target.url = src.url,
                       target.origem = src.origem,
                       target.indice = src.indice,
                       target.texto = src.texto,
                       target.versao_ingestao = src.versao
                   WHEN NOT MATCHED THEN INSERT
                       (id, titulo, secao, url, origem, indice, texto, versao_ingestao)
                       VALUES (src.id, src.titulo, src.secao, src.url, src.origem,
                               src.indice, src.texto, src.versao)""",
                rows,
                batcherrors=True,
            )
            errors = cursor.getbatcherrors()
            if errors:
                first = errors[0]
                raise RuntimeError(f"Falha ao inserir chunk na linha do arquivo {first.offset + 1}: {first.message}")
            # A nova ingestão já foi aplicada por completo dentro desta transação;
            # agora remova do Oracle páginas/chunks que desapareceram do material.
            cursor.execute("DELETE FROM chunks WHERE versao_ingestao <> :versao", {"versao": version})
            cursor.execute(
                "UPDATE reindex_runs SET status = 'active', concluido_em = SYSTIMESTAMP WHERE versao = :versao",
                {"versao": version},
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(f"Chunks carregados: {len(rows)}")
    print(f"Versão: {version}")


if __name__ == "__main__":
    main()

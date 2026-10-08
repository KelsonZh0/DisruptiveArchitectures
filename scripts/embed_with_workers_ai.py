"""
Re-gera os embeddings de chunks.json usando o Workers AI da Cloudflare
(modelo @cf/baai/bge-m3, multilíngue, grátis) em vez do sentence-transformers local.

Por quê: a pergunta do aluno vai ser "embeddada" dentro do Worker (JavaScript),
usando Workers AI. Pra busca por similaridade fazer sentido, os chunks precisam
ter sido embeddados com o MESMO modelo.

Como pegar suas credenciais:
  - Account ID: aparece no dashboard do Cloudflare (barra lateral direita) ou:
    wrangler whoami
  - API Token: dash.cloudflare.com -> My Profile -> API Tokens -> Create Token
    -> template "Workers AI" (ou permissão "Account.Workers AI: Edit")

Como rodar:
  pip install requests
  export CF_ACCOUNT_ID=""
  export CF_API_TOKEN=""
  python embed_with_workers_ai.py --input chunks.json --output chunks_embedded.json
"""

import argparse
import json
import os
import time
from pathlib import Path

import requests

MODEL = "@cf/baai/bge-m3"
BATCH_SIZE = 10  # lotes menores reduzem erros de tamanho na API


def embed_lote(textos, account_id, token):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"text": textos},
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"Workers AI HTTP {resp.status_code}: {resp.text[:2000]}")
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Erro na API Workers AI: {data}")
    return data["result"]["data"]  # lista de vetores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="chunks.jsonl", help="Arquivo JSONL de entrada")
    parser.add_argument("--output", default="chunks_embedded.jsonl", help="Arquivo JSONL de saída")
    parser.add_argument("--resume", action="store_true", help="Retoma de um arquivo de saída parcial, validando o prefixo concluído")
    args = parser.parse_args()

    account_id = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    if not account_id or not token:
        raise SystemExit("Defina as variáveis de ambiente CF_ACCOUNT_ID e CF_API_TOKEN antes de rodar.")

    input_path = Path(args.input)
    output_path = Path(args.output)
    chunks = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    existing: list[dict] = []
    if args.resume and output_path.exists():
        with output_path.open(encoding="utf-8") as saved:
            for line_number, line in enumerate(saved, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if "embedding" not in item:
                        raise ValueError("embedding ausente")
                    existing.append(item)
                except (json.JSONDecodeError, ValueError) as error:
                    raise SystemExit(f"Saída parcial inválida na linha {line_number}: {error}") from error
        if len(existing) > len(chunks):
            raise SystemExit("A saída parcial tem mais chunks que a entrada; use outro --output.")
        for index, item in enumerate(existing):
            expected = chunks[index]
            if item.get("id") != expected.get("id") or any(item.get(key) != value for key, value in expected.items()):
                raise SystemExit("O conteúdo mudou desde a saída parcial; use outro --output para não reaproveitar embeddings antigos.")
    elif output_path.exists():
        output_path.unlink()

    total = len(existing)
    dimension = 0
    mode = "a" if args.resume and existing else "w"
    with output_path.open(mode, encoding="utf-8", newline="\n") as destination:
        for start in range(len(existing), len(chunks), BATCH_SIZE):
            batch = chunks[start:start + BATCH_SIZE]
            try:
                vectors = embed_lote([item["texto"] for item in batch], account_id, token)
            except RuntimeError as error:
                # A 400 can be caused by one oversized/problematic item. Split
                # the batch to isolate it while preserving all earlier output.
                if "Workers AI HTTP 400" in str(error) and len(batch) > 1:
                    vectors = []
                    for item in batch:
                        try:
                            vectors.extend(embed_lote([item["texto"]], account_id, token))
                        except RuntimeError as single_error:
                            raise RuntimeError(f"Falha no chunk {item.get('id')}: {single_error}") from single_error
                elif "Workers AI HTTP 400" in str(error):
                    raise RuntimeError(f"Falha no chunk {batch[0].get('id')}: {error}") from error
                else:
                    raise
            if len(vectors) != len(batch):
                raise RuntimeError(f"A API retornou {len(vectors)} vetores para {len(batch)} textos")
            for item, vector in zip(batch, vectors):
                item["embedding"] = vector
                dimension = len(vector)
                destination.write(json.dumps(item, ensure_ascii=False) + "\n")
            destination.flush()
            total += len(batch)
            print(f"  embeddados {total} chunks")
            time.sleep(0.3)  # gentileza com o rate limit

    if not dimension and existing:
        dimension = len(existing[-1]["embedding"])
    print(f"Salvo {total} chunks em {output_path} (dimensão {dimension})")


if __name__ == "__main__":
    main()

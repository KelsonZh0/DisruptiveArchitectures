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

import requests

MODEL = "@cf/baai/bge-m3"
BATCH_SIZE = 20  # quantos textos manda por chamada


def embed_lote(textos, account_id, token):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"text": textos},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Erro na API Workers AI: {data}")
    return data["result"]["data"]  # lista de vetores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="chunks.jsonl", help="Arquivo JSONL de entrada")
    parser.add_argument("--output", default="chunks_embedded.jsonl", help="Arquivo JSONL de saída")
    args = parser.parse_args()

    account_id = os.environ.get("CF_ACCOUNT_ID")
    token = os.environ.get("CF_API_TOKEN")
    if not account_id or not token:
        raise SystemExit("Defina as variáveis de ambiente CF_ACCOUNT_ID e CF_API_TOKEN antes de rodar.")

    total = 0
    dimension = 0
    with open(args.input, encoding="utf-8") as source, open(args.output, "w", encoding="utf-8", newline="\n") as destination:
        while True:
            lines = []
            for _ in range(BATCH_SIZE):
                line = source.readline()
                if not line:
                    break
                if line.strip():
                    lines.append(json.loads(line))
            if not lines:
                break
            vectors = embed_lote([item["texto"] for item in lines], account_id, token)
            if len(vectors) != len(lines):
                raise RuntimeError(f"A API retornou {len(vectors)} vetores para {len(lines)} textos")
            for item, vector in zip(lines, vectors):
                item["embedding"] = vector
                dimension = len(vector)
                destination.write(json.dumps(item, ensure_ascii=False) + "\n")
            total += len(lines)
            print(f"  embeddados {total} chunks")
            time.sleep(0.3)  # gentileza com o rate limit

    print(f"Salvo {total} chunks em {args.output} (dimensão {dimension})")


if __name__ == "__main__":
    main()

"""Remove Vectorize IDs that are no longer present in the current corpus."""

from __future__ import annotations

import argparse
import json
import os

import requests

API_BASE = "https://api.cloudflare.com/client/v4"
PAGE_SIZE = 1000
DELETE_BATCH_SIZE = 100


def read_current_ids(path: str) -> set[str]:
    current: set[str] = set()
    with open(path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                vector_id = row["id"]
                if not isinstance(vector_id, str) or not vector_id:
                    raise ValueError("id vazio ou inválido")
                current.add(vector_id)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Registro inválido na linha {line_number}: {error}") from error
    if not current:
        raise ValueError("A lista atual está vazia; recusando apagar o índice inteiro.")
    return current


def list_remote_ids(account_id: str, token: str, index: str) -> set[str]:
    endpoint = f"{API_BASE}/accounts/{account_id}/vectorize/v2/indexes/{index}/list"
    headers = {"Authorization": f"Bearer {token}"}
    cursor = None
    identifiers: set[str] = set()
    while True:
        params = {"count": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        response = requests.get(endpoint, headers=headers, params=params, timeout=60)
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"Falha ao listar IDs do Vectorize: {body}")
        result = body.get("result") or {}
        identifiers.update(item["id"] for item in result.get("vectors", []))
        if not result.get("isTruncated"):
            return identifiers
        cursor = result.get("nextCursor")
        if not cursor:
            raise RuntimeError("Vectorize indicou mais páginas, mas não retornou nextCursor.")


def delete_ids(account_id: str, token: str, index: str, identifiers: list[str]) -> None:
    endpoint = f"{API_BASE}/accounts/{account_id}/vectorize/v2/indexes/{index}/delete_by_ids"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for start in range(0, len(identifiers), DELETE_BATCH_SIZE):
        batch = identifiers[start:start + DELETE_BATCH_SIZE]
        response = requests.post(endpoint, headers=headers, json={"ids": batch}, timeout=60)
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError(f"Falha ao excluir IDs obsoletos do Vectorize: {body}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="vectors.ndjson", help="NDJSON atual, com um id por linha")
    parser.add_argument("--index", default=os.getenv("VECTORIZE_INDEX", "disruptive-architectures-index"))
    args = parser.parse_args()

    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID") or os.getenv("CF_ACCOUNT_ID")
    token = os.getenv("CLOUDFLARE_API_TOKEN") or os.getenv("CF_API_TOKEN")
    if not account_id or not token:
        raise SystemExit("Defina CLOUDFLARE_ACCOUNT_ID e CLOUDFLARE_API_TOKEN.")

    current = read_current_ids(args.input)
    remote = list_remote_ids(account_id, token, args.index)
    obsolete = sorted(remote - current)
    if obsolete:
        delete_ids(account_id, token, args.index, obsolete)
    print(f"Vetores atuais: {len(current)}; removidos do índice: {len(obsolete)}")


if __name__ == "__main__":
    main()

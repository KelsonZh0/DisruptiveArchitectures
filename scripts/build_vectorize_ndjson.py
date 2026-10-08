"""
Converte chunks_embedded.json no formato NDJSON exigido pelo `wrangler vectorize insert`.

Como rodar:
  python build_vectorize_ndjson.py --input chunks_embedded.json --output vectors.ndjson
"""

import argparse
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="chunks_embedded.jsonl", help="Arquivo JSONL com embeddings")
    parser.add_argument("--output", default="vectors.ndjson")
    args = parser.parse_args()

    total = 0
    with open(args.input, encoding="utf-8") as source, open(args.output, "w", encoding="utf-8", newline="\n") as destination:
        for line in source:
            if not line.strip():
                continue
            chunk = json.loads(line)
            if "embedding" not in chunk:
                raise ValueError(f"Chunk {chunk.get('id', '<sem id>')} sem embedding")
            vector = {
                "id": chunk["id"],
                "values": chunk["embedding"],
                "metadata": {
                    "titulo": chunk["titulo"],
                    "secao": chunk.get("secao", ""),
                    "url": chunk["url"],
                    "origem": chunk["origem"],
                },
            }
            destination.write(json.dumps(vector, ensure_ascii=False) + "\n")
            total += 1

    print(f"Salvo {total} vetores em {args.output}")


if __name__ == "__main__":
    main()

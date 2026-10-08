"""Extract Markdown and notebook content into stable, source-linked chunks.

This script never executes notebook cells. Output is JSON Lines so it can be
streamed into the database and embedding pipeline without loading the corpus
as one large Python object.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


TARGET_WORDS = 360
OVERLAP_WORDS = 36
MAX_WORDS = 500
MIN_WORDS = 40


@dataclass
class Section:
    title: str
    level: int
    blocks: list[str] = field(default_factory=list)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = value.replace("º", "o").replace("ª", "a")
    value = re.sub(r"[^\w-]+", "-", value, flags=re.UNICODE)
    return re.sub(r"-+", "-", value).strip("-")


def strip_front_matter(text: str) -> str:
    return re.sub(r"\A---\s*\n.*?\n---\s*(?:\n|\Z)", "", text, count=1, flags=re.DOTALL)


def markdown_blocks(text: str) -> list[str]:
    """Split markdown into paragraphs while keeping fenced blocks intact."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence, fence_marker = True, marker[0]
            elif marker[0] == fence_marker:
                in_fence = False
        if not line.strip() and not in_fence:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def markdown_sections(text: str) -> list[Section]:
    text = strip_front_matter(text)
    sections: list[Section] = []
    title_stack: list[str] = []
    current = Section("", 0)
    sections.append(current)
    body: list[str] = []
    in_fence = False
    fence_char = ""

    def flush_body() -> None:
        nonlocal body
        if body:
            current.blocks.extend(markdown_blocks("\n".join(body)))
            body = []

    for line in text.splitlines():
        fence = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence, fence_char = True, marker[0]
            elif marker[0] == fence_char:
                in_fence = False
        heading = None if in_fence else re.match(r"^(#{2,3})\s+(.+?)\s*#*\s*$", line)
        if not heading:
            body.append(line)
            continue
        flush_body()
        level, title = len(heading.group(1)), heading.group(2).strip()
        title_stack = title_stack[: level - 2]
        title_stack.append(title)
        current = Section(" > ".join(title_stack), level)
        sections.append(current)
    flush_body()
    return [section for section in sections if section.blocks]


def notebook_sections(path: Path) -> list[Section]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = [Section("", 0)]
    for cell in data.get("cells", []):
        source = "".join(cell.get("source", [])) if isinstance(cell.get("source", []), list) else cell.get("source", "")
        source = source.strip()
        if not source:
            continue
        if cell.get("cell_type") == "markdown":
            parsed = markdown_sections(source)
            # Notebook markdown may start with a single-# title; promote it as a section.
            first = source.splitlines()[0] if source.splitlines() else ""
            match = re.match(r"^#\s+(.+?)\s*#*\s*$", first)
            if match:
                sections.append(Section(match.group(1), 1, markdown_blocks("\n".join(source.splitlines()[1:]))))
            else:
                sections.extend(parsed)
        elif cell.get("cell_type") == "code":
            # Keep code whole; it is useful evidence and should not be executed.
            sections.append(Section("Código", 4, [f"```python\n{source}\n```" ]))
    return [section for section in sections if section.blocks]


def split_large_block(block: str, max_words: int = MAX_WORDS) -> list[str]:
    words = block.split()
    if len(words) <= max_words:
        return [block]
    result = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        result.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - OVERLAP_WORDS
    return result


def chunk_section(section: Section, page_title: str) -> list[str]:
    prefix = " > ".join(part for part in (page_title, section.title) if part)
    chunks: list[str] = []
    parts: list[str] = []
    count = 0

    def emit() -> None:
        nonlocal parts, count
        if parts:
            chunks.append((f"{prefix}\n\n" if prefix else "") + "\n\n".join(parts))
            parts, count = [], 0

    for raw_block in section.blocks:
        for block in split_large_block(raw_block):
            words = len(block.split())
            if parts and count + words > TARGET_WORDS:
                previous = " ".join("\n\n".join(parts).split())
                emit()
                overlap = previous.split()[-OVERLAP_WORDS:]
                overlap_text = " ".join(overlap)
                if overlap_text:
                    parts, count = [overlap_text], len(overlap)
            parts.append(block)
            count += words
            if count >= MAX_WORDS:
                emit()
    emit()
    return chunks


def page_url(relative_path: Path, base_url: str, source_root: Path) -> str:
    parts = list(relative_path.parts)
    suffix = Path(parts[-1]).suffix.lower()
    if suffix in {".md", ".ipynb"}:
        stem = Path(parts[-1]).stem
        parts = parts[:-1] + ([] if stem == "index" else [stem])
    path = "/".join(parts)
    return base_url.rstrip("/") + (f"/{path}/" if path else "/")


def heading_anchor(section_title: str) -> str:
    # MkDocs Material uses GitHub-style heading IDs; H2/H3 titles include hierarchy in source metadata,
    # while anchors use only the final heading text as MkDocs does.
    title = section_title.split(" > ")[-1]
    return slugify(title)


def stable_id(relative_path: Path, section_title: str, index: int, text: str) -> str:
    raw = f"{relative_path.as_posix()}\0{section_title}\0{index}\0{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_file(path: Path, source_root: Path, base_url: str) -> Iterable[dict]:
    relative = path.relative_to(source_root)
    if path.suffix.lower() == ".md":
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Existing course materials include legacy Windows-1252 files.
            text = raw.decode("cp1252")
        sections = markdown_sections(text)
        title_match = re.search(r"^#\s+(.+?)\s*#*\s*$", strip_front_matter(text), re.MULTILINE)
        page_title = title_match.group(1).strip() if title_match else path.stem
    else:
        sections = notebook_sections(path)
        page_title = path.stem
    url = page_url(relative, base_url, source_root)
    section_counts: dict[str, int] = {}
    for section in sections:
        title = section.title
        for chunk in chunk_section(section, page_title):
            words = len(chunk.split())
            if words < MIN_WORDS and words < MAX_WORDS:
                # Keep short chunks when their block is an indivisible table/code example.
                if not any(token in chunk for token in ("|", "```")):
                    continue
            idx = section_counts.get(title, 0)
            section_counts[title] = idx + 1
            anchor = heading_anchor(title) if title else ""
            yield {
                "id": stable_id(relative, title, idx, chunk),
                "titulo": page_title,
                "secao": title,
                "url": url + (f"#{anchor}" if anchor else ""),
                "origem": relative.as_posix(),
                "indice": idx,
                "texto": chunk,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--material-dir", required=True, help="Diretório material/ do MkDocs")
    parser.add_argument("--base-url", required=True, help="URL base publicada, sem barra final")
    parser.add_argument("--output", default="chunks.jsonl", help="Saída JSON Lines")
    parser.add_argument("--extensions", nargs="+", default=[".md", ".ipynb"])
    args = parser.parse_args()

    source_root = Path(args.material_dir).resolve()
    extensions = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in args.extensions}
    files = sorted(path for path in source_root.rglob("*") if path.is_file() and path.suffix.lower() in extensions)
    output = Path(args.output)
    count = 0
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for path in files:
            for chunk in extract_file(path, source_root, args.base_url):
                stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                count += 1
    print(f"Arquivos processados: {len(files)}")
    print(f"Chunks gerados: {count}")
    print(f"Saída: {output.resolve()}")


if __name__ == "__main__":
    main()

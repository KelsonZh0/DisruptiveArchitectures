import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import ingest

def test_markdown_keeps_code_and_hierarchical_sections() -> None:
    fence = chr(96) * 3
    source = "## Instalacao\n\nTexto de aula.\n\n" + fence + "python\nprint('oi')\n" + fence + "\n\n### Detalhe\n\nTabela:\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    sections = ingest.markdown_sections(source)
    assert len(sections) == 2
    assert fence + "python" in "\n".join(sections[0].blocks)
    assert sections[1].title == "Instalacao > Detalhe"
    assert "| 1 | 2 |" in "\n".join(sections[1].blocks)

def test_slug_and_stable_id() -> None:
    assert ingest.slugify("Introdução ao ESP32") == "introducao-ao-esp32"
    path = Path("aula/index.md")
    assert ingest.stable_id(path, "Visão geral", 0) == ingest.stable_id(path, "Visão geral", 0)
    assert ingest.stable_id(path, "Visão geral", 0) != ingest.stable_id(path, "Visão geral", 1)

def test_markdown_slug_handles_portuguese_ordinal() -> None:
    assert ingest.slugify("1º Semestre") == "1o-semestre"

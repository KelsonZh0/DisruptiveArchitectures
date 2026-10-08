import pytest
from pydantic import ValidationError
from backend.app.schemas.chat import ModelAnswer
from backend.app.services.llm import SYSTEM_PROMPT

def test_system_prompt_contains_lab_pillars() -> None:
    for term in ("PAPEL:", "TAREFA:", "CONTEXTO:", "FORMATO:", "RESTRIÇÕES:", "português", "Não invente"):
        assert term in SYSTEM_PROMPT

def test_model_output_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ModelAnswer.model_validate({"resposta": "ok", "ids_trechos_usados": [], "encontrou_no_material": False, "url": "https://attacker.example"})

def test_model_output_requires_boolean_flag() -> None:
    with pytest.raises(ValidationError):
        ModelAnswer.model_validate({"resposta": "ok", "ids_trechos_usados": [], "encontrou_no_material": "sim"})

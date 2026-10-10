"""The new protocol is explicit and leaves current defaults compatible."""
import pytest
from app.config import Settings


def test_quality_contract_default_preserves_legacy_strategy_and_compatibility():
    settings = Settings()
    assert settings.llm_summary_strategy == "legacy"
    contract = getattr(settings, "llm_summary_quality_contract", None)
    assert contract == "compat"


def test_quality_contract_reads_explicit_compact_environment(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_QUALITY_CONTRACT", "compact")
    contract = getattr(Settings.from_env(), "llm_summary_quality_contract", None)
    assert contract == "compact"


@pytest.mark.parametrize("value", ["unknown", "COMPACT", "", True, None, 1])
def test_invalid_quality_contract_is_rejected(value):
    assert "llm_summary_quality_contract" in Settings.__dataclass_fields__, "Quality protocol configuration is missing"
    with pytest.raises(ValueError):
        Settings(llm_summary_quality_contract=value)

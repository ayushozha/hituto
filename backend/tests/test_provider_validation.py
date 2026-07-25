import pytest

from app.core.config import Settings
from app.providers.registry import validate_provider_config


def test_skip_provider_validation_loads_from_env_file(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SKIP_PROVIDER_VALIDATION=1\n", encoding="utf-8")
    monkeypatch.delenv("SKIP_PROVIDER_VALIDATION", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.skip_provider_validation is True
    validate_provider_config(settings)


def test_false_skip_value_keeps_provider_validation_enabled(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SKIP_PROVIDER_VALIDATION=0\n", encoding="utf-8")
    monkeypatch.delenv("SKIP_PROVIDER_VALIDATION", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.skip_provider_validation is False
    with pytest.raises(RuntimeError):
        validate_provider_config(settings)

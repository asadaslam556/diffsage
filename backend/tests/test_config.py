import pytest

from app.core.config import ConfigError, apply_env_overrides, build_settings

BASE = {
    "app": {"environment": "development", "cors_origins": ["http://localhost:5173"]},
    "rate_limits": {"default": {"limit": 100, "window_seconds": 60}, "fail_open": True},
    "agent": {"default_provider": "ollama", "fallback_provider": "ollama", "max_tool_rounds": 3},
    "providers": {
        "ollama": {"base_url": "http://localhost:11434", "model": "qwen2.5-coder:7b"},
        "anthropic": {"base_url": "https://api.anthropic.com", "model": "claude-sonnet-5"},
    },
}


def fresh():
    import copy
    return copy.deepcopy(BASE)


def test_env_overrides_are_typed_from_the_toml_value():
    data = apply_env_overrides(fresh(), {
        "AGENT__MAX_TOOL_ROUNDS": "5",
        "RATE_LIMITS__FAIL_OPEN": "false",
        "APP__CORS_ORIGINS": "https://a.com, https://b.com",
        "PROVIDERS__OLLAMA__MODEL": "llama3.1:8b",
    })
    assert data["agent"]["max_tool_rounds"] == 5
    assert data["rate_limits"]["fail_open"] is False
    assert data["app"]["cors_origins"] == ["https://a.com", "https://b.com"]
    assert data["providers"]["ollama"]["model"] == "llama3.1:8b"


def test_unrelated_env_vars_are_ignored():
    data = apply_env_overrides(fresh(), {"PATH__X": "1", "SOMETHING": "else"})
    assert "path" not in data


def test_api_keys_come_from_env_only():
    settings = build_settings(fresh(), {"ANTHROPIC_API_KEY": "sk-test", "JWT_SECRET": "j" * 40})
    assert settings.providers["anthropic"].api_key == "sk-test"
    assert settings.providers["ollama"].api_key is None
    assert settings.providers["anthropic"].adapter == "anthropic"


def test_production_refuses_a_placeholder_jwt_secret():
    data = fresh()
    data["app"]["environment"] = "production"
    with pytest.raises(ConfigError):
        build_settings(data, {"JWT_SECRET": "change-me", "DATABASE_URL": "postgresql+asyncpg://u:p@db/x"})


def test_production_refuses_self_serve_plan_changes():
    data = fresh()
    data["app"]["environment"] = "production"
    env = {"JWT_SECRET": "j" * 40, "DATABASE_URL": "postgresql+asyncpg://u:p@db/x"}
    data["billing"] = {"allow_self_serve_plan_change": True}
    with pytest.raises(ConfigError, match="self_serve"):
        build_settings(data, env)
    data["billing"] = {"allow_self_serve_plan_change": False}
    assert build_settings(data, env).billing_self_serve is False


def test_dev_generates_a_jwt_secret_if_missing():
    assert len(build_settings(fresh(), {}).jwt_secret) >= 32


def test_default_provider_must_exist():
    data = fresh()
    data["agent"]["default_provider"] = "mistral"
    with pytest.raises(ConfigError):
        build_settings(data, {})


def test_fallback_can_be_an_ordered_list():
    data = fresh()
    data["providers"]["deepseek"] = {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"}
    data["agent"]["fallback_provider"] = "deepseek, ollama"
    settings = build_settings(data, {})
    assert settings.fallback_chain == ("deepseek", "ollama")
    assert settings.fallback_provider == "deepseek"
    data["agent"]["fallback_provider"] = "deepseek,mistral"
    with pytest.raises(ConfigError):
        build_settings(data, {})


def test_vector_collection_name_includes_the_dimension():
    data = fresh()
    data["embeddings"] = {"backend": "hashing", "dim": 256}
    assert build_settings(data, {}).vector_collection == "guidelines_hashing_256"

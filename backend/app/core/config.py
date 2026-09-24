"""Settings.

Defaults come from config/settings.toml, env vars override them, and secrets
(API keys, JWT secret, connection strings) only ever come from the environment.
Nested overrides use double underscores: AGENT__DEFAULT_PROVIDER=anthropic.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
DEFAULT_SETTINGS_FILE = BACKEND_DIR / "config" / "settings.toml"

# Values people tend to leave in by accident. Refuse them in production.
_PLACEHOLDER_SECRETS = {"", "change-me", "changeme", "secret", "dev-secret"}

log = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    adapter: str
    base_url: str
    model: str
    api_key: str | None = None
    enabled: bool = True
    timeout_seconds: float = 60.0
    max_tokens: int = 4096
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    log_level: str
    log_format: str
    cors_origins: list[str]
    trust_proxy_headers: bool

    database_url: str
    redis_url: str
    qdrant_url: str
    qdrant_api_key: str | None

    jwt_secret: str
    jwt_algorithm: str
    access_token_minutes: int
    refresh_token_days: int
    password_hash_iterations: int

    rate_limits: dict[str, RateLimitRule]
    rate_limit_fail_open: bool

    default_provider: str
    fallback_provider: str               # first fallback, what the UI and health report show
    fallback_chain: tuple[str, ...]     # every fallback in order, e.g. ("deepseek", "ollama")
    first_token_timeout: float
    max_tool_rounds: int
    history_messages: int
    default_profile: str
    internal_gateway_url: str

    providers: dict[str, ProviderConfig]

    embedding_backend: str
    embedding_model: str
    embedding_dim: int
    collection_prefix: str

    billing_self_serve: bool
    health_provider_cache_seconds: float
    health_check_timeout: float

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def vector_collection(self) -> str:
        # dimension goes in the name so switching embedding models never
        # tries to shove 384-d vectors into a 768-d collection
        return f"{self.collection_prefix}_{self.embedding_backend}_{self.embedding_dim}"


def _coerce(raw: str, current: Any) -> Any:
    if isinstance(current, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    if isinstance(current, (list, dict)):
        raw = raw.strip()
        if raw.startswith(("[", "{")):
            return json.loads(raw)
        return [part.strip() for part in raw.split(",") if part.strip()]
    return raw


def apply_env_overrides(data: dict[str, Any], environ: dict[str, str]) -> dict[str, Any]:
    """Walk FOO__BAR style env vars into the nested toml dict.

    Only touches keys whose first segment is already a section in the toml,
    so random env vars like PATH__SOMETHING can't sneak in.
    """
    for key, raw in environ.items():
        if "__" not in key:
            continue
        parts = [p.lower() for p in key.split("__")]
        if parts[0] not in data:
            continue
        node = data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                break
        else:
            leaf = parts[-1]
            node[leaf] = _coerce(raw, node.get(leaf, ""))
    return data


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional in the slim test environment
        return
    # repo-root .env is the one docker compose uses too; backend/.env wins if present
    load_dotenv(REPO_DIR / ".env", override=False)
    load_dotenv(BACKEND_DIR / ".env", override=True)


def build_settings(data: dict[str, Any], environ: dict[str, str]) -> Settings:
    app = data.get("app", {})
    auth = data.get("auth", {})
    rl = dict(data.get("rate_limits", {}))
    agent = data.get("agent", {})
    emb = data.get("embeddings", {})
    environment = str(app.get("environment", "development"))
    is_prod = environment.lower() == "production"

    fail_open = bool(rl.pop("fail_open", True))
    rate_limits = {
        name: RateLimitRule(int(rule["limit"]), int(rule["window_seconds"]))
        for name, rule in rl.items()
    }
    if "default" not in rate_limits:
        raise ConfigError("rate_limits.default is required")

    providers: dict[str, ProviderConfig] = {}
    for name, cfg in data.get("providers", {}).items():
        cfg = dict(cfg)
        known = {"adapter", "base_url", "model", "enabled", "timeout_seconds", "max_tokens"}
        providers[name] = ProviderConfig(
            name=name,
            adapter=str(cfg.get("adapter", name)),
            base_url=str(cfg.get("base_url", "")).rstrip("/"),
            model=str(cfg.get("model", "")),
            api_key=environ.get(f"{name.upper()}_API_KEY") or None,
            enabled=bool(cfg.get("enabled", True)),
            timeout_seconds=float(cfg.get("timeout_seconds", 60)),
            max_tokens=int(cfg.get("max_tokens", 4096)),
            extra={k: v for k, v in cfg.items() if k not in known},
        )

    default_provider = str(agent.get("default_provider", "ollama"))
    # one name or an ordered list: "deepseek,ollama" tries DeepSeek, then the local model
    fallback_chain = tuple(n.strip() for n in str(agent.get("fallback_provider", "ollama")).split(",") if n.strip()) or ("ollama",)
    for label, name in (("default_provider", default_provider), *(("fallback_provider", n) for n in fallback_chain)):
        if name not in providers:
            raise ConfigError(f"agent.{label} is '{name}' but there's no [providers.{name}] section")

    jwt_secret = environ.get("JWT_SECRET", "")
    if jwt_secret in _PLACEHOLDER_SECRETS or len(jwt_secret) < 32:
        if is_prod:
            raise ConfigError("JWT_SECRET must be set to a real value (32+ chars) in production")
        # dev convenience: tokens just stop working when the process restarts
        jwt_secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET not set, using a random one for this process")

    database_url = environ.get("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/diffsage")
    if is_prod and "app:app@" in database_url:
        raise ConfigError("DATABASE_URL is still using the default dev credentials")

    billing_self_serve = bool(data.get("billing", {}).get("allow_self_serve_plan_change", False))
    if is_prod and billing_self_serve:
        # without checkout in front of it, this lets any user give themselves the Team plan
        raise ConfigError("billing.allow_self_serve_plan_change must be off in production (BILLING__ALLOW_SELF_SERVE_PLAN_CHANGE=false)")

    return Settings(
        app_name=str(app.get("name", "DiffSage")),
        environment=environment,
        log_level=str(app.get("log_level", "INFO")).upper(),
        log_format=str(app.get("log_format", "text")),
        cors_origins=list(app.get("cors_origins", [])),
        trust_proxy_headers=bool(app.get("trust_proxy_headers", False)),
        database_url=database_url,
        redis_url=environ.get("REDIS_URL", "redis://localhost:6379/0"),
        qdrant_url=environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/"),
        qdrant_api_key=environ.get("QDRANT_API_KEY") or None,
        jwt_secret=jwt_secret,
        jwt_algorithm="HS256",
        access_token_minutes=int(auth.get("access_token_minutes", 15)),
        refresh_token_days=int(auth.get("refresh_token_days", 14)),
        password_hash_iterations=int(auth.get("password_hash_iterations", 600_000)),
        rate_limits=rate_limits,
        rate_limit_fail_open=fail_open,
        default_provider=default_provider,
        fallback_provider=fallback_chain[0],
        fallback_chain=fallback_chain,
        first_token_timeout=float(agent.get("first_token_timeout_seconds", 25)),
        max_tool_rounds=int(agent.get("max_tool_rounds", 3)),
        history_messages=int(agent.get("history_messages", 20)),
        default_profile=str(agent.get("default_profile", "code_reviewer")),
        internal_gateway_url=str(agent.get("internal_gateway_url", "http://127.0.0.1:8000")).rstrip("/"),
        providers=providers,
        embedding_backend=str(emb.get("backend", "ollama")),
        embedding_model=str(emb.get("model", "nomic-embed-text")),
        embedding_dim=int(emb.get("dim", 768)),
        collection_prefix=str(data.get("vectorstore", {}).get("collection_prefix", "guidelines")),
        billing_self_serve=billing_self_serve,
        health_provider_cache_seconds=float(data.get("health", {}).get("provider_cache_seconds", 30)),
        health_check_timeout=float(data.get("health", {}).get("check_timeout_seconds", 4)),
    )


def load_settings(path: Path | None = None, environ: dict[str, str] | None = None) -> Settings:
    if environ is None:
        _load_dotenv()
        environ = dict(os.environ)
    path = path or Path(environ.get("SETTINGS_FILE", DEFAULT_SETTINGS_FILE))
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"settings file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"settings file {path} isn't valid TOML: {exc}") from exc
    return build_settings(apply_env_overrides(data, environ), environ)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()

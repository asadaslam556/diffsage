"""Adapter registry.

Adapters register themselves by name. build_providers() then reads the
[providers.*] tables from settings and instantiates the matching adapter
for each one. Modules in this package are imported automatically, so a new
adapter file is picked up without touching an import list anywhere.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Callable

from app.agent.providers.base import LLMProvider
from app.core.config import ProviderConfig

log = logging.getLogger(__name__)

_ADAPTERS: dict[str, type[LLMProvider]] = {}
_SKIP_MODULES = {"base", "registry", "router"}


def register_provider(name: str) -> Callable[[type[LLMProvider]], type[LLMProvider]]:
    def decorator(cls: type[LLMProvider]) -> type[LLMProvider]:
        existing = _ADAPTERS.get(name)
        if existing is not None and existing is not cls:
            raise RuntimeError(f"two adapters registered as '{name}': {existing.__name__} and {cls.__name__}")
        cls.adapter_name = name
        _ADAPTERS[name] = cls
        return cls

    return decorator


def discover_adapters() -> dict[str, type[LLMProvider]]:
    package = importlib.import_module("app.agent.providers")
    for module in pkgutil.iter_modules(package.__path__):
        # files starting with _ are helpers (wire formats, http bits)
        if module.name in _SKIP_MODULES or module.name.startswith("_"):
            continue
        importlib.import_module(f"app.agent.providers.{module.name}")
    return dict(_ADAPTERS)


def available_adapters() -> dict[str, type[LLMProvider]]:
    return dict(_ADAPTERS)


def build_providers(configs: dict[str, ProviderConfig], *, discover: bool = True) -> dict[str, LLMProvider]:
    if discover:
        discover_adapters()
    providers: dict[str, LLMProvider] = {}
    for name, cfg in configs.items():
        adapter = _ADAPTERS.get(cfg.adapter)
        if adapter is None:
            # config typo shouldn't take the whole app down, just this provider
            log.error("no adapter called '%s' for provider '%s', skipping it", cfg.adapter, name)
            continue
        providers[name] = adapter(cfg)
        log.info(
            "provider %s ready (adapter=%s model=%s configured=%s)",
            name, cfg.adapter, cfg.model, providers[name].is_configured(),
        )
    return providers

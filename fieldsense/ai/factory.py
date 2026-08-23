"""AIAdapterFactory - runtime selection of the active explanation backend.

Mirrors fieldsense.hardware.factory.SensorAdapterFactory. Where that factory
chooses between a simulated and a physical sensor, this one chooses between a
deterministic template backend and a local model backend, based on whether the
model assets actually exist on disk.

Absence of GGUF weights is the expected default on a development machine and is
NOT an error. The factory silently resolves to MockAIAdapter so the pipeline
runs identically with or without a model installed.
"""

from typing import Optional

from .base import LocalLLMAdapter
from .config import AIConfig
from .llama_cpp import LlamaCppAdapter
from .mock import MockAIAdapter


class AIAdapterFactory:
    """Factory for creating the active LocalLLMAdapter implementation."""

    @staticmethod
    def create_adapter(config: Optional[AIConfig] = None) -> LocalLLMAdapter:
        """Create the explanation backend selected by configuration.

        Backend resolution:
            MOCK       always the deterministic template backend
            LLAMA_CPP  always the model backend, which degrades internally
                       to templates when its assets are missing
            AUTO       the model backend when weights and binary are both
                       present, otherwise the template backend

        Args:
            config: Optional AIConfig. Defaults are AUTO with no weights, which
                resolves to MockAIAdapter.

        Returns:
            An initialized LocalLLMAdapter.
        """
        cfg = config or AIConfig()
        backend = cfg.backend.upper()

        if backend == "MOCK":
            adapter: LocalLLMAdapter = MockAIAdapter()
        elif backend == "LLAMA_CPP":
            adapter = LlamaCppAdapter(config=cfg)
        else:
            candidate = LlamaCppAdapter(config=cfg)
            adapter = candidate if candidate.is_available() else MockAIAdapter()

        adapter.initialize()
        return adapter

    @staticmethod
    def describe_active_backend(config: Optional[AIConfig] = None) -> str:
        """Report which backend would be selected, for diagnostics and the UI.

        Args:
            config: Optional AIConfig.

        Returns:
            Human-readable backend description.
        """
        cfg = config or AIConfig()
        adapter = AIAdapterFactory.create_adapter(cfg)
        name = type(adapter).__name__
        if isinstance(adapter, LlamaCppAdapter):
            return f"{name} ({cfg.model_path})"
        return f"{name} (no model weights required)"

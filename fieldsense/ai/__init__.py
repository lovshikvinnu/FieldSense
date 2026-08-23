"""AI explanation layer.

Optional, downstream, and powerless by design. This layer consumes already
computed deterministic results and renders them as natural language. It can
never alter a score, a spatial raster, a zone boundary, or a recommendation.

See docs/03_ARCHITECTURE.md section 22 (AI Boundary).

Backends implement LocalLLMAdapter. MockAIAdapter is the default and requires
no model weights; LlamaCppAdapter drives a local llama.cpp binary and is
selected only when a GGUF model and inference binary are present on disk.
AIAdapterFactory resolves between them at runtime.
"""

from .base import LocalLLMAdapter
from .config import AIConfig, GuardConfig
from .context import build_context_from_view, build_explanation_context
from .factory import AIAdapterFactory
from .guard import NarrativeGuard
from .llama_cpp import LlamaCppAdapter
from .mock import MockAIAdapter
from .models import (
    AIError,
    AIErrorCode,
    AINarrative,
    ExplanationContext,
    NarrativeStatus,
    ZoneContext,
)

__all__ = [
    # Contracts
    "LocalLLMAdapter",
    # Models
    "AINarrative",
    "ExplanationContext",
    "ZoneContext",
    "NarrativeStatus",
    "AIError",
    "AIErrorCode",
    # Configuration
    "AIConfig",
    "GuardConfig",
    # Context construction
    "build_explanation_context",
    "build_context_from_view",
    # Safety
    "NarrativeGuard",
    # Backends
    "MockAIAdapter",
    "LlamaCppAdapter",
    "AIAdapterFactory",
]

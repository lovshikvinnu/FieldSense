"""Centralized configuration for the AI explanation layer."""

import os
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class AIConfig:
    """Configuration for local SLM / LLM narrative generation.

    Deliberately model-agnostic. Any lightweight quantized GGUF model that
    llama.cpp can load is acceptable; sizing is a deployment decision, not a
    code decision. Reference targets validated for the QRB2210 memory budget:

        Qwen2.5-0.5B-Instruct  Q4_K_M   ~0.40 GB
        TinyLlama-1.1B-Chat    Q4_K_M   ~0.67 GB
        Phi-3-mini-4k-instruct Q4_K_M   ~2.30 GB   (4 GB boards only)

    HARDWARE_SPEC_REQUIRED - binary_path and thread count require confirmation
    against the physical Arduino UNO Q Debian image.
    """
    backend: str = "AUTO"                        # AUTO, MOCK, LLAMA_CPP
    model_path: str = "models/fieldsense-slm.gguf"
    binary_path: str = "llama-cli"
    context_tokens: int = 2048
    max_output_tokens: int = 256
    temperature: float = 0.0                     # 0.0 = greedy, most repeatable
    seed: int = 42
    threads: int = 4                             # QRB2210 exposes 4 Cortex-A53 cores
    timeout_seconds: float = 120.0
    fallback_to_mock: bool = True
    max_generation_attempts: int = 2             # one retry with a stricter prompt
    generate_zone_narratives: bool = True
    max_zone_generations: int = 8                # caps total wall-clock on slow hardware
    # Additional llama-cli flags. Kept in configuration because flag names vary
    # between llama.cpp releases; verify against the installed binary.
    # HARDWARE_SPEC_REQUIRED
    extra_args: Tuple[str, ...] = ("-no-cnv",)
    methodology_version: str = "0.1"

    @classmethod
    def from_env(cls, **overrides: object) -> "AIConfig":
        """Build a configuration from environment variables.

        The default `model_path` is RELATIVE, which is correct when the pipeline
        is run from a shell in the repository and wrong under systemd, where the
        service's working directory is not guaranteed and a relative path
        silently resolves to nothing. A boot unit therefore sets:

            FIELDSENSE_AI_BACKEND=AUTO
            FIELDSENSE_MODEL_PATH=/opt/fieldsense/models/fieldsense-slm.gguf
            FIELDSENSE_LLAMA_BIN=llama-cli
            FIELDSENSE_AI_THREADS=4
            FIELDSENSE_AI_TIMEOUT=120

        Explicit keyword overrides win over the environment, which wins over
        the defaults. Malformed numeric values fall back to the default rather
        than raising: a typo in a unit file must not stop the board from
        booting, it must only cost the optional narrative.
        """
        cfg = cls(
            backend=os.environ.get("FIELDSENSE_AI_BACKEND", cls.backend).upper(),
            model_path=os.path.expanduser(
                os.environ.get("FIELDSENSE_MODEL_PATH", cls.model_path)
            ),
            binary_path=os.environ.get("FIELDSENSE_LLAMA_BIN", cls.binary_path),
            threads=_env_int("FIELDSENSE_AI_THREADS", cls.threads),
            timeout_seconds=_env_float("FIELDSENSE_AI_TIMEOUT", cls.timeout_seconds),
            max_output_tokens=_env_int("FIELDSENSE_AI_MAX_TOKENS", cls.max_output_tokens),
        )
        if overrides:
            from dataclasses import replace

            cfg = replace(cfg, **overrides)  # type: ignore[arg-type]
        return cfg

    def resolved_model_path(self, base_dir: str = "") -> str:
        """Return an absolute model path, anchored to `base_dir` when relative.

        Args:
            base_dir: Directory a relative path is measured from. Defaults to
                the process working directory.

        Returns:
            An absolute filesystem path. Does not check that the file exists —
            `LlamaCppAdapter.is_available()` owns that decision.
        """
        if os.path.isabs(self.model_path):
            return self.model_path
        return os.path.abspath(os.path.join(base_dir or os.getcwd(), self.model_path))


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back on anything invalid."""
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back on anything invalid."""
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True)
class GuardConfig:
    """Safety boundary configuration for NarrativeGuard.

    Mirrors the prohibition already enforced structurally by the recommendation
    rule tables: FieldSense emits directional guidance only, never a
    quantitative chemical, fertilizer, or irrigation prescription, and never a
    soil organic carbon or carbon credit claim.
    """

    # Dose-bearing units. Deliberately excludes '%' and 'm2'/'m^2', which are
    # legitimate on this dashboard (scores as percentages, zone area in m^2)
    # and are separately constrained by the unsupported-number check.
    forbidden_unit_tokens: List[str] = field(
        default_factory=lambda: [
            "kg", "kilogram", "kilograms",
            "g/l", "gram", "grams",
            "ha", "hectare", "hectares",
            "acre", "acres",
            "lb", "lbs", "pound", "pounds",
            "ton", "tons", "tonne", "tonnes",
            "litre", "litres", "liter", "liters",
            "gallon", "gallons",
            "ml", "millilitre", "milliliter",
            "ppm", "mg/kg",
            "quintal", "bushel", "bushels",
        ]
    )

    # Named agrochemicals and soil amendments.
    forbidden_substance_tokens: List[str] = field(
        default_factory=lambda: [
            "urea", "dap", "mop", "npk",
            "ammonium", "nitrate", "phosphate fertilizer",
            "superphosphate", "muriate",
            "gypsum", "lime", "limestone",
            "manure", "compost tea",
            "pesticide", "herbicide", "fungicide", "insecticide",
        ]
    )

    # Claims outside the evidence boundary of this methodology.
    forbidden_claim_phrases: List[str] = field(
        default_factory=lambda: [
            "carbon credit", "carbon credits",
            "carbon offset", "carbon offsets",
            "sequester", "sequestration",
            "soil organic carbon is", "soc is",
            "certified", "certification",
            "guaranteed yield", "will increase yield",
        ]
    )

    reject_unsupported_numbers: bool = True
    max_field_summary_chars: int = 900
    max_zone_narrative_chars: int = 500
    number_match_tolerance: float = 0.01

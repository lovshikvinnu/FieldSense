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
    # between llama.cpp releases, which is not hypothetical: this default was
    # `-no-cnv` until the flag was verified against the binary actually built
    # for the board, which does not have it.
    #
    # VERIFIED 2026-08-25 on the UNO Q against llama.cpp 0.2.0-dev
    # (build 10615, commit f280b2698, Linux aarch64): that build offers
    # `-st, --single-turn`. The long form is used here because a config value
    # is read far more often than it is typed.
    #
    # Suppressing conversation mode is not cosmetic. Without it llama-cli waits
    # for interactive turns, so a subprocess with no tty produces nothing, the
    # adapter records GENERATION_FAILED and degrades to templates - a silent
    # fallback that looks like a working pipeline. Re-verify this flag against
    # any newly built binary: `llama-cli --help | grep -i single-turn`.
    extra_args: Tuple[str, ...] = ("--single-turn",)
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
        if os.path.isabs(self.model_path) or self.model_path.startswith("/") or self.model_path.startswith("\\"):
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
class FidelityConfig:
    """Configuration for the semantic fidelity checker.

    Separate from GuardConfig on purpose. The guard decides whether a sentence
    is SAFE - no dose, no product, no invented number. Fidelity decides whether
    it is TRUE to the deterministic result it claims to describe. A narrative
    can be perfectly safe and still say the opposite of the data.

    Deliberately conservative. A false positive routes every narrative to the
    template and silently disables the model, which is worse than a missed
    contradiction because nothing reports it.
    """

    enabled: bool = True

    # Scores at or below the first value read as deficient, at or above the
    # second as excessive. The band between is not judged.
    low_score_ceiling: float = 0.34
    high_score_floor: float = 0.66

    positive_terms: List[str] = field(default_factory=lambda: [
        "good", "healthy", "excellent", "strong", "favourable", "favorable",
        "high", "reliable", "robust",
    ])
    negative_terms: List[str] = field(default_factory=lambda: [
        "poor", "degraded", "unhealthy", "critical", "bad", "low", "weak",
        "limited", "unreliable",
    ])

    excess_moisture_terms: List[str] = field(default_factory=lambda: [
        "high moisture", "excess moisture", "excessive moisture", "high water",
        "waterlogged", "water logged", "too much water", "saturated soil",
        "overwatered", "over-watered",
    ])
    deficient_moisture_terms: List[str] = field(default_factory=lambda: [
        "low moisture", "moisture deficiency", "lack of moisture", "drought",
        "dry soil", "too dry", "insufficient moisture",
    ])

    # Reversals of a WATER recommendation. A narrative telling a farmer to
    # withhold water above a recommendation to review irrigation is the single
    # most consequential contradiction this layer exists to catch.
    water_reversal_terms: List[str] = field(default_factory=lambda: [
        "reduce irrigation", "reduce watering", "stop irrigation",
        "stop watering", "avoid irrigation", "avoid watering", "do not water",
        "withhold water", "cease irrigation", "less water",
    ])

    minimising_terms: List[str] = field(default_factory=lambda: [
        "mild", "minor", "negligible", "no concern", "not a concern",
        "no action", "healthy condition",
    ])


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

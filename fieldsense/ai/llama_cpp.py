"""LlamaCppAdapter - narrative generation via a local llama.cpp binary.

The inference engine is treated as a SYSTEM ASSET, not a Python dependency:
a compiled binary plus a quantized GGUF weights file, discovered on disk at
runtime and absent by default. It is invoked through the standard library
subprocess module, so `pyproject.toml` dependencies remains empty and no
compiler toolchain is required on the target.

    fieldsense (pure Python, stdlib only)
            |
            |  subprocess.run()
            v
    llama-cli  +  model.gguf        <- optional system assets

Failure handling is per section. Each generated paragraph is guarded
independently; a rejected paragraph is replaced by the deterministic template
for that same section while the rest of the narrative survives. Absent weights,
timeouts, and guard rejections are all normal conditions reported through
AINarrative.generation_status, never raised.
"""

import os
import re
import shutil
import subprocess
import time
from typing import List, Optional, Tuple

from .base import LocalLLMAdapter
from .config import AIConfig, GuardConfig
from .guard import NarrativeGuard
from .mock import MockAIAdapter
from .models import AINarrative, ExplanationContext, NarrativeStatus, ZoneContext
from .prompt import build_field_summary_prompt, build_retry_suffix, build_zone_prompt

_END_MARKERS = ("[end of text]", "</s>", "<|im_end|>", "<|endoftext|>", "<|eot_id|>")

# llama-cli writes its own furniture to the same stream as the generation. Left
# in, it is judged as though the model had written it. Measured on the UNO Q
# against build 10615: the timing line's token rates reached the guard as
# UNSUPPORTED_NUMBER:15.9 and :8.3 - numbers about llama.cpp, not about soil -
# and the spinner added several hundred characters toward LENGTH_EXCEEDED before
# the model had said anything.
#
# Each pattern matches llama.cpp's output specifically, never anything shaped
# like prose, so a narrative is not silently edited on its way to the guard.
# Measured on the UNO Q with Qwen2.5-0.5B: four generations at -n 256 produced
# 1354, 1420, 1296 and 1274 characters - 4.98 to 5.55 characters per token. The
# spread across two different sections with unrelated content is the giveaway:
# the model was not choosing a length, it was running into the cap every time.
#
# 5.6 is deliberately above the measured maximum. Overestimating characters per
# token asks for fewer tokens, which errs toward a shorter answer rather than a
# rejected one.
_CHARS_PER_TOKEN = 5.6

# Ask for a little less than the section allows, so a model that runs slightly
# rich still lands inside the guard's limit.
_TOKEN_BUDGET_MARGIN = 0.9

_LLAMA_NOISE = (
    re.compile(r"\[\s*Prompt:.*?t/s.*?\]", re.IGNORECASE | re.DOTALL),
    re.compile(r"^Loading model\.\.\..*$", re.MULTILINE),
    re.compile(r"^Exiting\.\.\.\s*$", re.MULTILINE),
)


class LlamaCppAdapter(LocalLLMAdapter):
    """Offline narrative backend driving a llama.cpp binary over subprocess."""

    def __init__(
        self,
        config: Optional[AIConfig] = None,
        guard: Optional[NarrativeGuard] = None,
        fallback: Optional[MockAIAdapter] = None,
    ) -> None:
        """Initialize the backend.

        Args:
            config: AIConfig holding model path, binary path, and limits.
            guard: NarrativeGuard applied to every generated section.
            fallback: Template backend supplying per-section replacements.
        """
        self.config = config or AIConfig()
        self.guard = guard or NarrativeGuard(GuardConfig())
        self.fallback = fallback or MockAIAdapter(guard=self.guard)
        self._initialized = False

    # ------------------------------------------------------------- lifecycle

    def is_available(self) -> bool:
        """Report whether both the model weights and the binary are present.

        Never raises. A machine with neither installed is the expected default.
        """
        try:
            if not os.path.isfile(self.model_path()):
                return False
            return self._resolve_binary() is not None
        except OSError:
            return False

    def model_path(self) -> str:
        """Return the absolute weights path.

        A relative `model_path` is fine from a shell in the repository and
        useless under systemd, whose working directory is not the repository
        unless the unit says so. Resolving here means both work.
        """
        return self.config.resolved_model_path()

    def initialize(self) -> None:
        """Probe for required on-disk assets."""
        self._initialized = self.is_available()

    def shutdown(self) -> None:
        """No persistent process is held between calls."""
        self._initialized = False

    # ------------------------------------------------------------- generation

    def explain(self, context: ExplanationContext) -> AINarrative:
        """Generate a guarded narrative, degrading per section on any failure.

        Args:
            context: Deterministic pipeline results to describe.

        Returns:
            AINarrative. Never raises; every failure mode is reported through
            generation_status and guard_violations.
        """
        started = time.perf_counter()

        if not self.is_available():
            narrative = self.fallback.explain(context)
            from dataclasses import replace

            return replace(
                narrative,
                generation_status=NarrativeStatus.MODEL_UNAVAILABLE,
                generated_by=self._missing_asset_label(),
            )

        violations: List[str] = []
        timed_out = False
        model_sections = 0

        summary, ok, section_violations, section_timeout = self._generate_section(
            prompt=build_field_summary_prompt(context),
            context=context,
            location="field_summary",
            max_chars=self.guard.config.max_field_summary_chars,
            fallback_text=self.fallback.compose_field_summary(context),
        )
        violations.extend(section_violations)
        timed_out = timed_out or section_timeout
        model_sections += 1 if ok else 0

        zone_narratives = {}
        zones = context.zones if self.config.generate_zone_narratives else []
        for zone in zones[: self.config.max_zone_generations]:
            text, ok, section_violations, section_timeout = self._generate_section(
                prompt=build_zone_prompt(zone),
                context=context,
                location=zone.zone_id,
                max_chars=self.guard.config.max_zone_narrative_chars,
                fallback_text=self.fallback.compose_zone_narrative(zone),
            )
            zone_narratives[zone.zone_id] = text
            violations.extend(section_violations)
            timed_out = timed_out or section_timeout
            model_sections += 1 if ok else 0

        # Zones beyond the generation cap, or with generation disabled, always
        # receive the deterministic template so no zone is silently omitted.
        for zone in context.zones:
            if zone.zone_id not in zone_narratives:
                zone_narratives[zone.zone_id] = self.fallback.compose_zone_narrative(zone)

        total_sections = 1 + len(zones[: self.config.max_zone_generations])
        if timed_out:
            status = NarrativeStatus.TIMEOUT
        elif model_sections == 0:
            status = NarrativeStatus.GUARD_REJECTED if violations else NarrativeStatus.FALLBACK_TEMPLATE
        elif model_sections < total_sections:
            status = NarrativeStatus.FALLBACK_TEMPLATE
        else:
            status = NarrativeStatus.OK

        return AINarrative(
            field_summary=summary,
            zone_narratives=zone_narratives,
            generated_by=os.path.basename(self.model_path()),
            generation_status=status,
            guard_violations=violations,
            is_ai_generated=model_sections > 0,
            decision_support_only=True,
            evidence_level=context.evidence_level,
            generation_time_ms=round((time.perf_counter() - started) * 1000.0, 1),
            methodology_version=context.methodology_version,
        )

    def _generate_section(
        self,
        prompt: str,
        context: ExplanationContext,
        location: str,
        max_chars: int,
        fallback_text: str,
    ) -> Tuple[str, bool, List[str], bool]:
        """Generate and guard one narrative section.

        Returns:
            Tuple of (text, came_from_model, violations, timed_out). On rejection
            or failure the deterministic template text is returned instead.
        """
        all_violations: List[str] = []
        attempts = max(1, self.config.max_generation_attempts)
        current_prompt = prompt
        token_budget = self._token_budget(max_chars)

        for attempt in range(attempts):
            try:
                raw = self._run_binary(current_prompt, max_tokens=token_budget)
            except subprocess.TimeoutExpired:
                return fallback_text, False, all_violations + [f"TIMEOUT[{location}]:"], True
            except (OSError, subprocess.SubprocessError) as exc:
                return (
                    fallback_text,
                    False,
                    all_violations + [f"GENERATION_FAILED[{location}]:{type(exc).__name__}"],
                    False,
                )

            text = self._trim_to_sentence(self._clean_output(raw), max_chars)
            section_violations = self.guard.inspect_text(
                text, context, location=location, max_chars=max_chars
            )
            if not section_violations:
                return text, True, all_violations, False

            all_violations.extend(section_violations)
            if attempt < attempts - 1:
                current_prompt = prompt + build_retry_suffix(section_violations)

        return fallback_text, False, all_violations, False

    # ------------------------------------------------------------- subprocess

    def _resolve_binary(self) -> Optional[str]:
        """Locate the llama.cpp CLI binary on PATH or at an explicit path."""
        candidate = self.config.binary_path
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        return shutil.which(candidate)

    def _token_budget(self, max_chars: Optional[int]) -> int:
        """Tokens to allow for a section of at most `max_chars` characters.

        Every section shared one global `max_output_tokens` before this, so a
        500 character zone note and a 900 character field summary were both
        given 256 tokens and both overran. Deriving the budget from the limit
        the guard will actually apply is what makes the section fit by
        construction rather than by asking the model nicely - which it ignored.

        Never returns more than the configured ceiling, so this can only ever
        shorten generation.
        """
        if not max_chars:
            return self.config.max_output_tokens
        derived = int(max_chars / _CHARS_PER_TOKEN * _TOKEN_BUDGET_MARGIN)
        return max(1, min(self.config.max_output_tokens, derived))

    def _build_command(self, prompt: str, max_tokens: Optional[int] = None) -> List[str]:
        """Assemble the llama-cli argument vector.

        Args:
            prompt: Fully built section prompt.
            max_tokens: Token ceiling for this section. Falls back to the
                configured maximum when a caller has no section limit.
        """
        binary = self._resolve_binary() or self.config.binary_path
        command = [
            binary,
            "-m", self.model_path(),
            "-p", prompt,
            "-n", str(max_tokens or self.config.max_output_tokens),
            "-c", str(self.config.context_tokens),
            "-t", str(self.config.threads),
            "--temp", str(self.config.temperature),
            "--seed", str(self.config.seed),
            "--no-display-prompt",
        ]
        command.extend(self.config.extra_args)
        return command

    def _run_binary(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Execute one generation and return raw stdout.

        Raises:
            subprocess.TimeoutExpired: Generation exceeded the configured limit.
            OSError / subprocess.SubprocessError: Binary could not be executed.
        """
        completed = subprocess.run(
            self._build_command(prompt, max_tokens=max_tokens),
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
            check=False,
            # Detach the controlling terminal. llama-cli opens /dev/tty directly
            # and renders its chat UI there, so with a terminal present it exits
            # 0 having written nothing to either pipe - and the guard reports
            # EMPTY_NARRATIVE on text that generated perfectly well.
            #
            # Measured on the UNO Q against llama.cpp 0.2.0-dev build 10615,
            # running the real command four ways: inherited stdin gave 0 bytes
            # on both pipes, stdin=DEVNULL also gave 0 - stdin is not what it
            # consults - and start_new_session gave 1055 bytes on stdout.
            # setsid() removes the controlling terminal, the /dev/tty open
            # fails, and generation falls back to stdout.
            start_new_session=True,
        )
        if completed.returncode != 0:
            raise subprocess.SubprocessError(
                f"llama-cli exited with code {completed.returncode}"
            )
        return completed.stdout

    @staticmethod
    def _clean_output(raw: str) -> str:
        """Normalize model stdout into a single plain paragraph.

        Removes llama.cpp's own output before anything is judged, so the guard's
        verdict is about the model rather than about the tool that ran it. See
        `_LLAMA_NOISE` for what that furniture is and why it matters.
        """
        text = raw or ""
        for pattern in _LLAMA_NOISE:
            text = pattern.sub(" ", text)

        # The spinner is drawn with backspaces, which survive the line match
        # above when they trail other output. Newline and tab are kept so the
        # whitespace collapse below still sees paragraph structure.
        text = "".join(ch for ch in text if ch >= " " or ch in "\n\t")

        text = text.strip()
        for marker in _END_MARKERS:
            text = text.replace(marker, " ")
        return " ".join(text.split())

    @staticmethod
    def _trim_to_sentence(text: str, max_chars: Optional[int]) -> str:
        """Cut to the last complete sentence that fits inside `max_chars`.

        The model is stopped by a token ceiling, not by finishing, so its last
        sentence is routinely cut mid-word. Handing that to the guard means a
        section is rejected and replaced by a template - the reader loses the
        whole narrative because of its final few characters.

        Trimming at a sentence boundary shows what the model actually completed.
        It is not a relaxation of anything: the guard still applies its own
        limit, and this only ever removes text.
        """
        if not text or not max_chars or len(text) <= max_chars:
            return text

        window = text[:max_chars]
        cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
        if cut == -1:
            for end in (".", "!", "?"):
                cut = max(cut, window.rfind(end))
        if cut != -1:
            return window[:cut + 1].strip()

        # No sentence ended in range. Fall back to a word boundary rather than
        # slicing through a word, and leave the text alone if even that fails,
        # so the guard sees the real output instead of something this invented.
        space = window.rfind(" ")
        return window[:space].strip() if space > 0 else text

    def _missing_asset_label(self) -> str:
        """Describe which asset is missing, for the audit trail."""
        if not os.path.isfile(self.model_path()):
            return f"MODEL_NOT_FOUND:{self.model_path()}"
        return f"BINARY_NOT_FOUND:{self.config.binary_path}"

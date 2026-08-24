#!/usr/bin/env python3
"""On-board validation for the FieldSense explanation model.

Answers one question the test suite cannot: **did a model actually run on this
board, or did the pipeline quietly fall back to templates?**

That distinction is easy to lose. `AIAdapterFactory` resolves `AUTO` to
`MockAIAdapter` whenever the weights or binary are missing, and `LlamaCppAdapter`
degrades to templates internally when a section fails. Both paths produce a
complete, valid narrative and a green pipeline run. Nothing errors. The only
honest markers are `generated_by`, which carries the GGUF filename on real
inference and `MOCK_TEMPLATE_v1` otherwise, and `is_ai_generated`.

So this probe never trusts a status line. It runs one real generation against a
real ExplanationContext and reports what came back, with timings.

    python3 tools/slm_probe.py                 # full check, one inference
    python3 tools/slm_probe.py --no-inference  # assets and config only, fast
    python3 tools/slm_probe.py --selftest      # check the probe's own logic

Standard library only, per `dependencies = []`.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fieldsense.ai.config import AIConfig  # noqa: E402
from fieldsense.ai.factory import AIAdapterFactory  # noqa: E402
from fieldsense.ai.mock import TEMPLATE_VERSION  # noqa: E402
from fieldsense.ai.models import ExplanationContext, ZoneContext  # noqa: E402

GGUF_MAGIC = b"GGUF"

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
INFO = "INFO"


def line(status: str, label: str, detail: str = "") -> None:
    """Print one check result."""
    print("  [{:<4}] {:<34} {}".format(status, label, detail))


def human_bytes(count: float) -> str:
    """Render a byte count at a sensible scale."""
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024.0:
            return "{:.1f} {}".format(count, unit)
        count /= 1024.0
    return "{:.1f} TB".format(count)


# --------------------------------------------------------------------- assets


def check_model(config: AIConfig) -> dict:
    """Verify the weights exist and are a real GGUF file.

    A path that resolves but is not GGUF is worth catching here: llama.cpp
    reports it as a load failure at generation time, by which point the adapter
    has already degraded to templates and the run looks merely unremarkable.
    """
    result = {"present": False, "path": None, "size": 0, "gguf": False}
    path = config.resolved_model_path()
    result["path"] = path

    if not os.path.isfile(path):
        line(FAIL, "model weights", "not found at {}".format(path))
        return result

    result["present"] = True
    result["size"] = os.path.getsize(path)
    line(PASS, "model weights", "{} ({})".format(path, human_bytes(result["size"])))

    try:
        with open(path, "rb") as handle:
            magic = handle.read(4)
    except OSError as exc:
        line(FAIL, "model readable", str(exc))
        return result

    result["gguf"] = magic == GGUF_MAGIC
    if result["gguf"]:
        line(PASS, "GGUF magic", "file begins 'GGUF'")
    else:
        line(FAIL, "GGUF magic", "begins {!r}, not a GGUF file".format(magic))
    return result


def check_binary(config: AIConfig) -> dict:
    """Verify the llama.cpp binary is present and actually executable."""
    result = {"present": False, "path": None, "runs": False}
    candidate = config.binary_path
    resolved = candidate if os.path.isfile(candidate) else shutil.which(candidate)

    if not resolved:
        line(FAIL, "llama.cpp binary", "{!r} not on PATH and not a file".format(candidate))
        return result

    result["present"] = True
    result["path"] = resolved
    line(PASS, "llama.cpp binary", resolved)

    if not os.access(resolved, os.X_OK):
        line(FAIL, "binary executable", "found but not executable (chmod +x)")
        return result

    try:
        proc = subprocess.run([resolved, "--version"], capture_output=True,
                              text=True, timeout=20)
        banner = (proc.stdout + proc.stderr).strip().splitlines()
        result["runs"] = True
        line(PASS, "binary runs", banner[0][:60] if banner else "(no version banner)")
    except (OSError, subprocess.SubprocessError) as exc:
        line(FAIL, "binary runs", "{}: {}".format(type(exc).__name__, exc))
    return result


def check_memory(model_bytes: int) -> dict:
    """Compare available RAM against the weights.

    Generation streams every weight per token, so the model has to fit in free
    memory or the board swaps and tokens-per-second collapses. Linux only; on
    any other platform this is skipped rather than guessed.
    """
    result = {"available": None, "fits": None}
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            fields = dict(
                (parts[0].rstrip(":"), int(parts[1]) * 1024)
                for parts in (l.split() for l in handle) if len(parts) >= 2
            )
    except OSError:
        line(INFO, "memory headroom", "no /proc/meminfo (not Linux) - skipped")
        return result

    available = fields.get("MemAvailable", fields.get("MemFree", 0))
    result["available"] = available
    if not model_bytes:
        line(INFO, "memory headroom", "{} available".format(human_bytes(available)))
        return result

    result["fits"] = available > model_bytes * 1.2
    detail = "{} available vs {} of weights".format(
        human_bytes(available), human_bytes(model_bytes))
    line(PASS if result["fits"] else WARN, "memory headroom", detail)
    if not result["fits"]:
        line(WARN, "", "under 1.2x the weights - expect swapping and very slow tokens")
    return result


# ------------------------------------------------------------------ inference


def sample_context() -> ExplanationContext:
    """A realistic context, shaped like the single-location V1 run."""
    return ExplanationContext(
        field_name="SLM Probe Field",
        session_id="SLM-PROBE-001",
        overall_soil_health=0.36,
        soil_health_status="POOR",
        nitrogen_score=0.21,
        moisture_score=0.05,
        carbon_readiness_score=0.30,
        total_samples=5,
        valid_samples=5,
        rejected_samples=0,
        coverage_ratio=1.0,
        zones=[ZoneContext(
            zone_id="ZONE-01",
            status="POOR",
            severity="HIGH",
            primary_issue="moisture",
            affected_parameters=["moisture", "nitrogen"],
            confidence="LOW",
            area_estimate=225.0,
            action_ids=["REC-ZONE-01-WATER"],
            actions=["Review irrigation timing and soil moisture conditions."],
            categories=["WATER"],
            priorities=["HIGH"],
        )],
        evidence_level="LIMITED",
        methodology_version="0.1",
    )


def run_inference(config: AIConfig) -> dict:
    """Generate one narrative and report which backend truly produced it."""
    print("\nInference")
    adapter = AIAdapterFactory.create_adapter(config)
    line(INFO, "adapter selected", type(adapter).__name__)

    context = sample_context()
    started = time.perf_counter()
    try:
        narrative = adapter.explain(context)
    except Exception as exc:
        line(FAIL, "generation", "{}: {}".format(type(exc).__name__, exc))
        return {"ran": False, "real": False}
    finally:
        try:
            adapter.shutdown()
        except Exception:
            pass

    wall_ms = round((time.perf_counter() - started) * 1000.0, 1)
    status = getattr(narrative.generation_status, "value", str(narrative.generation_status))
    violations = [str(v) for v in (narrative.guard_violations or [])]

    # Two separate facts, and conflating them cost a real diagnosis once.
    #
    #   executed  the GGUF actually ran. generated_by carries the model
    #             filename whenever the LlamaCpp path was taken, and an
    #             execution failure would have recorded GENERATION_FAILED or
    #             TIMEOUT instead of a guard violation.
    #   accepted  the text it produced survived the guard and reached the
    #             narrative.
    #
    # A model can execute perfectly and still be rejected downstream - wrong
    # output stream, wrong format, a guard rule it trips. Reporting that as
    # "no real inference" hides the most useful thing the run established.
    took_model_path = narrative.generated_by != TEMPLATE_VERSION
    failed_to_run = any(v.startswith(("GENERATION_FAILED", "TIMEOUT")) for v in violations)
    executed = took_model_path and not failed_to_run
    accepted = bool(narrative.is_ai_generated) and took_model_path

    line(INFO, "generated_by", narrative.generated_by)
    line(INFO, "generation_status", status)
    line(INFO, "wall clock", "{} ms".format(wall_ms))
    line(INFO, "reported generation time", "{} ms".format(narrative.generation_time_ms))
    if violations:
        line(WARN, "guard violations", ", ".join(violations))

    line(PASS if executed else FAIL, "model executed",
         "yes - {} ran".format(narrative.generated_by) if executed
         else "NO - no model process produced output")
    line(PASS if accepted else FAIL, "output accepted",
         "yes" if accepted else "NO - generated text was rejected downstream")
    real = executed and accepted

    summary = (narrative.field_summary or "").strip().replace("\n", " ")
    print("\n  first 200 characters of the summary:")
    print("    {}".format(summary[:200] or "(empty)"))

    return {"ran": True, "real": real, "executed": executed, "accepted": accepted,
            "wall_ms": wall_ms, "generated_by": narrative.generated_by,
            "status": status, "violations": violations}


def dump_streams(config: AIConfig) -> int:
    """Run the real command with pipes and no tty, and show both streams.

    This exists because a hand-run command in a terminal is not the same
    experiment. llama-cli checks for a tty and renders a chat UI when it finds
    one, so shell redirection can leave both captured files empty while text
    still reaches the screen. `subprocess.run(capture_output=True)` gives it no
    tty, which is what FieldSense actually does - so this is the only test whose
    answer applies to `_run_binary`.
    """
    from fieldsense.ai.llama_cpp import LlamaCppAdapter

    adapter = LlamaCppAdapter(config=config)
    command = adapter._build_command("Summarise in one sentence: soil health is poor.")

    print("Command FieldSense would run\n")
    print("  " + " ".join(repr(a) if " " in a else a for a in command))
    print("\nRunning with pipes and no controlling terminal...\n")

    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=config.timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        line(FAIL, "run", "timed out after {}s".format(config.timeout_seconds))
        return 1
    except (OSError, subprocess.SubprocessError) as exc:
        line(FAIL, "run", "{}: {}".format(type(exc).__name__, exc))
        return 1

    out, err = completed.stdout or "", completed.stderr or ""
    line(INFO, "exit code", str(completed.returncode))
    line(INFO, "stdout length", "{} chars".format(len(out)))
    line(INFO, "stderr length", "{} chars".format(len(err)))

    print("\n--- STDOUT (what _run_binary reads) ---")
    print(out if out.strip() else "(empty)")
    print("\n--- STDERR (currently discarded) ---")
    print(err if err.strip() else "(empty)")

    print("\n" + "=" * 72)
    if out.strip():
        print("Generation is on STDOUT. _run_binary is reading the right stream,")
        print("so an EMPTY_NARRATIVE has some other cause - check _clean_output.")
    elif err.strip():
        print("Generation is on STDERR. _run_binary reads stdout only, which is")
        print("why the guard saw an empty string. Note what else shares that")
        print("stream - load logs and the timing line - before merging it.")
    else:
        print("BOTH streams are empty with no tty attached. The text is not")
        print("being written to either pipe, so reading stderr would not help.")
        print("The flags are producing no piped output at all.")
    return 0


def tty_matrix(config: AIConfig) -> int:
    """Run the real command four ways and report which one yields piped output.

    Detaching stdin was not enough on the UNO Q: llama-cli still rendered to the
    screen with stdin on /dev/null and both pipes empty. That rules out an
    isatty(stdin) check and points at the program opening /dev/tty directly,
    which no stream redirection can defeat - only removing the controlling
    terminal, which is what start_new_session (setsid) does.

    This runs every combination so the answer is observed rather than argued.
    """
    from fieldsense.ai.llama_cpp import LlamaCppAdapter

    adapter = LlamaCppAdapter(config=config)
    command = adapter._build_command("Summarise in one sentence: soil health is poor.")

    print("Probe process context")
    line(INFO, "sys.stdin.isatty()", str(sys.stdin.isatty()))
    line(INFO, "sys.stdout.isatty()", str(sys.stdout.isatty()))
    try:
        with open("/dev/tty", "w"):
            has_tty = True
    except OSError:
        has_tty = False
    line(INFO, "/dev/tty openable", str(has_tty))
    if not sys.stdin.isatty() and not has_tty:
        line(WARN, "", "no controlling terminal here - the 'inherited' row "
                       "cannot reproduce the interactive case")

    variants = (
        ("inherited stdin (what the adapter does today)", {}),
        ("stdin=DEVNULL", {"stdin": subprocess.DEVNULL}),
        ("start_new_session=True (setsid)", {"start_new_session": True}),
        ("DEVNULL + new session", {"stdin": subprocess.DEVNULL,
                                   "start_new_session": True}),
    )

    print("\nRunning {} variants of the same command\n".format(len(variants)))
    winners = []
    for label, kwargs in variants:
        try:
            done = subprocess.run(command, capture_output=True, text=True,
                                  timeout=config.timeout_seconds, check=False,
                                  **kwargs)
        except subprocess.TimeoutExpired:
            line(FAIL, label, "timed out")
            continue
        except (OSError, subprocess.SubprocessError) as exc:
            line(FAIL, label, "{}: {}".format(type(exc).__name__, exc))
            continue

        out, err = done.stdout or "", done.stderr or ""
        got = out.strip() or err.strip()
        status = PASS if got else FAIL
        line(status, label, "rc={} stdout={} stderr={}".format(
            done.returncode, len(out), len(err)))
        if got:
            stream = "stdout" if out.strip() else "stderr"
            print("           {} -> {!r}".format(stream, got[:90]))
            winners.append((label, stream, kwargs))

    print("\n" + "=" * 72)
    if not winners:
        print("No variant produced piped output. llama-cli is writing to the")
        print("controlling terminal by a route none of these close, so the fix is")
        print("not a subprocess argument. Next candidates, in order: a different")
        print("binary in build/bin (llama-simple, llama-run) that is built for")
        print("non-interactive use, or an output flag this build does provide.")
        return 1

    print("Piped output achieved by:")
    for label, stream, kwargs in winners:
        print("  {:<46} via {}".format(label, stream))
    print("\nThe narrowest working option is the one to apply to _run_binary.")
    return 0


# ------------------------------------------------------------------- selftest


def selftest() -> int:
    """Check the probe's own discriminator with no model installed."""
    print("Self-test: forcing the MOCK backend, which must be reported as NOT real.\n")
    result = run_inference(AIConfig(backend="MOCK"))
    ok = result["ran"] and not result["real"]
    print("\n{}".format(
        "PASS - a template narrative is correctly identified as not model output."
        if ok else
        "FAIL - the probe called template output a real inference."))
    return 0 if ok else 1


# ----------------------------------------------------------------------- main


def main(argv=None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-inference", action="store_true",
                        help="check assets and configuration only")
    parser.add_argument("--selftest", action="store_true",
                        help="verify this probe's own logic, no model needed")
    parser.add_argument("--tty-matrix", action="store_true",
                        help="run the real command under four stdin/session "
                             "combinations and report which yields piped output")
    parser.add_argument("--dump-streams", action="store_true",
                        help="run the real llama-cli command with pipes and no "
                             "tty, and print stdout and stderr separately")
    parser.add_argument("--backend", default=None,
                        help="override the backend: AUTO, MOCK, LLAMA_CPP")
    parser.add_argument("--model", default=None, help="override the GGUF path")
    parser.add_argument("--binary", default=None, help="override the llama.cpp binary")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    overrides = {}
    if args.backend:
        overrides["backend"] = args.backend.upper()
    if args.model:
        overrides["model_path"] = args.model
    if args.binary:
        overrides["binary_path"] = args.binary
    config = AIConfig.from_env(**overrides)

    if args.tty_matrix:
        return tty_matrix(config)

    if args.dump_streams:
        return dump_streams(config)

    print("FieldSense SLM probe")
    print("=" * 72)
    print("\nResolved configuration")
    line(INFO, "backend", config.backend)
    line(INFO, "model_path", config.resolved_model_path())
    line(INFO, "binary_path", config.binary_path)
    line(INFO, "threads", str(config.threads))
    line(INFO, "timeout_seconds", str(config.timeout_seconds))
    line(INFO, "max_output_tokens", str(config.max_output_tokens))

    print("\nAssets")
    model = check_model(config)
    binary = check_binary(config)
    check_memory(model["size"])

    print("\nBackend resolution")
    described = AIAdapterFactory.describe_active_backend(config)
    line(INFO, "factory would use", described)

    assets_ok = model["present"] and model["gguf"] and binary["present"] and binary["runs"]
    if not assets_ok:
        print("\n" + "=" * 72)
        print("VERDICT: the on-board model is NOT installed or NOT usable.")
        print("The pipeline will still run and still produce narratives - they")
        print("will be deterministic templates, badged MOCK_TEMPLATE_v1. That is")
        print("a supported mode, but it is NOT onboard SLM validation.")
        print("\nInstall steps are in docs/AI_DEPLOYMENT.md section 2.")
        return 1

    if args.no_inference:
        print("\nAssets look good. Re-run without --no-inference to prove the model runs.")
        return 0

    result = run_inference(config)

    print("\n" + "=" * 72)
    if result.get("real"):
        print("VERDICT: real on-board inference confirmed.")
        print("  model     : {}".format(result["generated_by"]))
        print("  status    : {}".format(result["status"]))
        print("  wall clock: {} ms".format(result["wall_ms"]))
        print("\nThis is the evidence to record for SLM validation.")
        return 0

    if result.get("executed"):
        print("VERDICT: the model RAN, but its output was rejected.")
        print("  model     : {}".format(result["generated_by"]))
        print("  status    : {}".format(result["status"]))
        print("  wall clock: {} ms".format(result["wall_ms"]))
        print("\nOn-board execution IS proven - the GGUF loaded and generated.")
        print("What failed is downstream acceptance, a different problem from a")
        print("missing or broken model.\n")

        # Say what these violations mean, rather than a fixed note about one
        # failure mode. This block used to explain EMPTY_NARRATIVE unconditionally
        # and kept saying "the adapter received no text" for runs where the model
        # had plainly produced text and been rejected on its content.
        codes = {v.split("[")[0] for v in result.get("violations", [])}
        if "EMPTY_NARRATIVE" in codes:
            print("  EMPTY_NARRATIVE - the adapter received nothing. Check that")
            print("    llama-cli writes generation to a pipe: --dump-streams shows")
            print("    which stream carries it, --tty-matrix which invocation does.")
        if "LENGTH_EXCEEDED" in codes:
            print("  LENGTH_EXCEEDED - the model wrote past the section limit. A")
            print("    prompt word budget and max_output_tokens govern this.")
        if "FORBIDDEN_CLAIM" in codes or "FORBIDDEN_UNIT" in codes:
            print("  FORBIDDEN_CLAIM / FORBIDDEN_UNIT - the model raised a subject")
            print("    the guard refuses. A prompt scope problem, not a guard fault.")
        if "UNSUPPORTED_NUMBER" in codes:
            print("  UNSUPPORTED_NUMBER - a number appeared that is not in the")
            print("    context. Check it is the model's and not the tool's output.")
        if not codes:
            print("  No violations recorded, so the rejection came from elsewhere.")
        return 1

    print("VERDICT: NO real inference. The narrative came from templates.")
    print("Assets are present, so the failure is at generation, not installation.")
    print("Check generation_status above: TIMEOUT means the model is too slow for")
    print("the configured timeout; FALLBACK_TEMPLATE means the binary failed or")
    print("its output was rejected; GUARD_REJECTED means the text broke the")
    print("safety guard in fieldsense/ai/guard.py.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

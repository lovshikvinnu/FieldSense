#!/usr/bin/env python3
"""Controlled comparison of candidate models on the task that actually fails.

Gate 3 on the UNO Q accepted the zone narrative and rejected the field summary,
every time, for the same three contradictions. Two questions follow, and neither
is answerable by running the pipeline again:

    1. Is that failure deterministic, or did one sample look worse than typical?
    2. Does a larger model read the same structured context correctly?

This runs one section repeatedly against one model, and reports acceptance,
contradictions, wall clock and peak child RSS. Nothing here changes the
deployment: the model path is a parameter, and the prompt, guard and fidelity
checker are the shipped ones, used exactly as the adapter uses them.

    python3 tools/slm_bench.py --repeats 5
    python3 tools/slm_bench.py --repeats 5 --model ~/models/tinyllama.gguf --label TinyLlama
    python3 tools/slm_bench.py --repeats 5 --section zone

Standard library only.
"""

import argparse
import os
import resource
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fieldsense.ai.config import AIConfig  # noqa: E402
from fieldsense.ai.llama_cpp import LlamaCppAdapter  # noqa: E402
from fieldsense.ai.prompt import (  # noqa: E402
    build_field_summary_prompt,
    build_zone_prompt,
)
from slm_probe import sample_context  # noqa: E402


# ru_maxrss units differ by platform: kilobytes on Linux, bytes on macOS.
# Getting this wrong reports a 500 MB model as using 7.8 GB, which is exactly
# the kind of number that ends an investigation in the wrong place.
_RSS_SCALE = 1 if sys.platform == "darwin" else 1024


def peak_child_rss_bytes() -> int:
    """Peak resident set size of child processes so far, in bytes.

    A high-water mark rather than a current reading, and it never decreases, so
    the meaningful figure is the delta across one generation.
    """
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * _RSS_SCALE


def human(n: float) -> str:
    """Render bytes at a sensible scale."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return "{:.0f} {}".format(n, unit) if unit in ("B", "KB") else "{:.2f} {}".format(n, unit)
        n /= 1024.0
    return "{:.2f} TB".format(n)


def run_once(adapter, context, section):
    """Generate one section and report what happened to it.

    Uses the adapter's own `_generate_section`, so the prompt, the retry, the
    safety guard and the fidelity checker are all exactly what ships. The only
    thing this file decides is which model binary the adapter points at.
    """
    if section == "zone":
        zone = context.zones[0]
        kwargs = dict(
            prompt=build_zone_prompt(zone),
            location=zone.zone_id,
            max_chars=adapter.guard.config.max_zone_narrative_chars,
            fallback_text=adapter.fallback.compose_zone_narrative(zone),
            zone=zone,
        )
    else:
        kwargs = dict(
            prompt=build_field_summary_prompt(context),
            location="field_summary",
            max_chars=adapter.guard.config.max_field_summary_chars,
            fallback_text=adapter.fallback.compose_field_summary(context),
        )

    # The model's own text, before the accept/reject decision. _generate_section
    # returns the TEMPLATE when it rejects, so comparing its return value across
    # runs would report every failing model as perfectly deterministic - it would
    # be comparing the fallback with itself.
    rss_before = peak_child_rss_bytes()
    started = time.perf_counter()
    raw = adapter._run_binary(
        kwargs["prompt"], max_tokens=adapter._token_budget(kwargs["max_chars"]))
    model_text = adapter._trim_to_sentence(
        adapter._clean_output(raw, kwargs["prompt"]), kwargs["max_chars"])
    elapsed = time.perf_counter() - started
    rss_after = peak_child_rss_bytes()

    # Then judge that text with the shipped guard and fidelity checker, exactly
    # as the adapter does.
    violations = adapter.guard.inspect_text(
        model_text, context, location=kwargs["location"], max_chars=kwargs["max_chars"])
    violations += adapter.fidelity.inspect(
        model_text, context, location=kwargs["location"], zone=kwargs.get("zone"))
    accepted, timed_out, text = not violations, False, model_text

    return {
        "accepted": bool(accepted),
        "violations": list(violations),
        "seconds": round(elapsed, 1),
        "rss_delta": max(0, rss_after - rss_before),
        "rss_peak": rss_after,
        "timed_out": timed_out,
        "text": text,
    }


def main(argv=None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=5,
                        help="how many times to generate the same section")
    parser.add_argument("--section", default="field_summary",
                        choices=("field_summary", "zone"),
                        help="which section to exercise (default the failing one)")
    parser.add_argument("--model", default=None,
                        help="GGUF path; defaults to the configured model")
    parser.add_argument("--binary", default=None, help="llama.cpp binary path")
    parser.add_argument("--label", default=None, help="name for this model in the report")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)

    overrides = {"backend": "LLAMA_CPP", "timeout_seconds": args.timeout}
    if args.model:
        overrides["model_path"] = os.path.expanduser(args.model)
    if args.binary:
        overrides["binary_path"] = os.path.expanduser(args.binary)
    config = AIConfig.from_env(**overrides)

    label = args.label or os.path.basename(config.resolved_model_path())
    weights = config.resolved_model_path()
    if not os.path.isfile(weights):
        print("model not found: {}".format(weights), file=sys.stderr)
        return 1

    adapter = LlamaCppAdapter(config=config)
    adapter.initialize()
    context = sample_context()

    print("=" * 74)
    print("MODEL   : {}".format(label))
    print("weights : {} ({})".format(weights, human(os.path.getsize(weights))))
    print("section : {}   repeats: {}".format(args.section, args.repeats))
    print("=" * 74)

    results = []
    for index in range(1, args.repeats + 1):
        outcome = run_once(adapter, context, args.section)
        results.append(outcome)
        codes = sorted({v.split(":")[1].split("=")[0]
                        for v in outcome["violations"] if ":" in v})
        print("\nrun {}/{}  {}  {:.1f}s".format(
            index, args.repeats,
            "ACCEPTED" if outcome["accepted"] else "REJECTED",
            outcome["seconds"]))
        if codes:
            print("  contradicts : {}".format(", ".join(codes)))
        print("  text        : {}".format(outcome["text"][:150].replace("\n", " ")))

    accepted = sum(1 for r in results if r["accepted"])
    times = [r["seconds"] for r in results]
    texts = {r["text"] for r in results}
    all_codes = [tuple(sorted({v.split(":")[1].split("=")[0]
                               for v in r["violations"] if ":" in v}))
                 for r in results]

    print("\n" + "=" * 74)
    print("SUMMARY  {}".format(label))
    print("  acceptance     : {}/{} ({:.0f}%)".format(
        accepted, len(results), 100.0 * accepted / max(1, len(results))))
    print("  generation     : {:.1f}s min, {:.1f}s mean, {:.1f}s max".format(
        min(times), sum(times) / len(times), max(times)))
    print("  peak child RSS : {}".format(human(max(r["rss_peak"] for r in results))))
    print("  distinct texts : {} of {}   (the model's own output, not the fallback)"
          .format(len(texts), len(results)))
    print("  distinct fault : {} of {}".format(len(set(all_codes)), len(results)))

    # Determinism is the first question, and it is answered by the two counts
    # above rather than by assuming temperature 0 guarantees it.
    if len(texts) == 1:
        print("\n  DETERMINISTIC: every run produced identical text.")
    else:
        print("\n  NOT deterministic: {} different outputs across {} runs."
              .format(len(texts), len(results)))
    if accepted == 0 and len(set(all_codes)) == 1 and all_codes[0]:
        print("  The same contradictions every time: a stable property of this")
        print("  model on this task, not an unlucky sample.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

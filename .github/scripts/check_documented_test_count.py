#!/usr/bin/env python3
"""Fail if the test count quoted in the documentation is not the suite's.

The README badge has said 294, 529, 552 and 565 at various points, each of them
correct when written and wrong within days. A stale number on the landing page
is a small lie that a reader has no way to check, and it undermines the honest
validation table sitting a few lines below it.

Run it locally the same way CI does:

    python3 .github/scripts/check_documented_test_count.py

WHY COLLECTED AND NOT PASSED

`pytest -q` reports how many tests *passed*, which is not a portable number:
two display-bridge tests skip when no Chromium-family browser is installed, so
a laptop with Chrome says "565 passed" and a bare runner says "563 passed, 2
skipped". Collection does not depend on what is installed, so that is the
number the documentation is held to.
"""

import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Where a test count appears, and how to recognise it. Every capture in every
#: pattern must equal the collected count. A pattern that matches nothing is
#: itself a failure: it means the wording changed and this check went blind.
DOCUMENTED = {
    "README.md": [
        # ![Suite](https://img.shields.io/badge/suite-565%20tests-...)
        r"suite-(\d+)%20tests",
        # "565 tests, no hardware required." / "| 565 tests. No hardware ... |"
        r"\b(\d+) tests[.,]",
        # "| ... | 565 automated tests |"
        r"\b(\d+) automated tests\b",
    ],
    "docs/STATUS.md": [
        r"\*\*Regression baseline:\*\* (\d+) tests passing",
    ],
}


def collected_test_count() -> int:
    """Return how many tests pytest collects, or exit with a readable error."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    if not match:
        sys.stderr.write(
            "could not read a collected count from pytest.\n\n"
            "--- pytest stdout ---\n" + result.stdout[-2000:] +
            "\n--- pytest stderr ---\n" + result.stderr[-2000:] + "\n"
        )
        raise SystemExit(2)
    return int(match.group(1))


def main() -> int:
    actual = collected_test_count()
    problems = []

    for relative_path, patterns in DOCUMENTED.items():
        path = REPO_ROOT / relative_path
        if not path.is_file():
            problems.append("{}: file is missing".format(relative_path))
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            found = re.findall(pattern, text)
            if not found:
                problems.append(
                    "{}: nothing matched /{}/ - the wording changed, so this "
                    "check is no longer reading anything. Update the pattern "
                    "rather than deleting it.".format(relative_path, pattern)
                )
                continue
            for raw in found:
                if int(raw) != actual:
                    problems.append(
                        "{}: says {}, suite collects {}".format(
                            relative_path, raw, actual
                        )
                    )

    if problems:
        print("The documented test count is out of date:\n")
        for problem in problems:
            print("  - {}".format(problem))
        print(
            "\nThe suite collects {n} tests. Update the badge and every place "
            "the body repeats it:\n"
            "\n"
            "    grep -rn '[0-9]\\{{3\\}} tests\\|suite-[0-9]*%20tests' "
            "README.md docs/STATUS.md\n".format(n=actual)
        )
        return 1

    print("Documented test count matches the suite: {}".format(actual))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

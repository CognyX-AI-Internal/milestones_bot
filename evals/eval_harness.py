"""Regression eval harness for the CMSP screening bot's LLM functions.

Runs the live LLM paths (get_age_from_gpt, generate_recommendations_new)
from main.py against fixed test cases and scores them deterministically,
so model/library upgrades can be compared against a baseline.

Usage (from project root):
    python evals/eval_harness.py --label baseline
    python evals/eval_harness.py --label candidate
    python evals/eval_harness.py --compare baseline candidate
"""

import argparse
import ast
import json
import os
import re
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "evals", "results")
REPORT_ITERATIONS = 2

# ---------------------------------------------------------------- test cases

AGE_CASES = [
    {"input": "2 years", "expected": 24},
    {"input": "18 months", "expected": 18},
    {"input": "3 years, 2 months", "expected": 38},
    {"input": "2.5 years", "expected": 30},
    {"input": "six months", "expected": 6},
    {"input": "4", "expected": 48},
    {"input": "he was born on a sunny day", "expected": None},
]


def build_report_cases(checklist_options):
    """Report cases built from the real checklist options used by the bot."""

    def numbered(milestones):
        return "\n".join(f"{i + 1}. {m}" for i, m in enumerate(milestones))

    case_delay = {
        "id": "delayed_14mo",
        "age": 14,
        "message": numbered(
            checklist_options[3] + checklist_options[6] + checklist_options[9][:3]
        ),
        "observations": "Child points at objects but does not say any words yet.",
        "expect_delay": True,
    }
    case_on_track = {
        "id": "on_track_24mo",
        "age": 24,
        "message": numbered(
            checklist_options[12] + checklist_options[18] + checklist_options[24]
        ),
        "observations": "",
        "expect_delay": False,
    }
    case_partial = {
        "id": "partial_36mo",
        "age": 36,
        "message": numbered(checklist_options[18] + checklist_options[24][:2]),
        "observations": "",
        "expect_delay": True,
    }
    return [case_delay, case_on_track, case_partial]


# ---------------------------------------------------------------- scoring

REQUIRED_SECTIONS = [
    "SPEECH AND LANGUAGE THERAPY REPORT",
    "Child's Age",
    "Overview",
    "Observations",
    "Milestones Achieved",
    "Recommendations for Parents",
    "Recommendations for the Clinical Team",
]

DELAY_PCT_RE = re.compile(r"\d+(\.\d+)?\s*%")


def score_report(text, case):
    checks = {}
    if not text:
        return {"empty_output": False}, 0.0

    for section in REQUIRED_SECTIONS:
        checks[f"has:{section}"] = section.lower() in text.lower()

    has_unmet = "milestones expected but not met" in text.lower()
    has_pct = bool(DELAY_PCT_RE.search(text))
    if case["expect_delay"]:
        checks["has_unmet_section"] = has_unmet
        checks["has_delay_percentage"] = has_pct
    else:
        checks["omits_unmet_section"] = not has_unmet
        checks["says_all_milestones_met"] = "met all the milestones" in text.lower()

    if case["observations"]:
        checks["mentions_observation"] = "point" in text.lower()

    passed = sum(1 for v in checks.values() if v)
    return checks, passed / len(checks)


# ---------------------------------------------------------------- run

def run(label):
    sys.path.insert(0, PROJECT_ROOT)
    os.chdir(PROJECT_ROOT)
    import main  # noqa: E402  (imports the real bot code / prompts)

    results = {
        "label": label,
        "openai_version": __import__("openai").__version__,
        "age_extraction": [],
        "reports": [],
    }

    print(f"=== Age extraction ({len(AGE_CASES)} cases) ===")
    for case in AGE_CASES:
        t0 = time.time()
        got = main.get_age_from_gpt(case["input"])
        elapsed = round(time.time() - t0, 2)
        ok = got == case["expected"]
        results["age_extraction"].append(
            {"input": case["input"], "expected": case["expected"], "got": got,
             "pass": ok, "seconds": elapsed}
        )
        print(f"  {'PASS' if ok else 'FAIL'}  {case['input']!r} -> {got} "
              f"(expected {case['expected']}) [{elapsed}s]")

    report_cases = build_report_cases(main.checklist_options)
    print(f"=== Reports ({len(report_cases)} cases x {REPORT_ITERATIONS} runs) ===")
    for case in report_cases:
        for i in range(REPORT_ITERATIONS):
            t0 = time.time()
            text = main.generate_recommendations_new(
                case["message"], case["age"], case["observations"]
            )
            elapsed = round(time.time() - t0, 2)
            checks, score = score_report(text, case)
            results["reports"].append(
                {"case": case["id"], "iteration": i, "score": round(score, 3),
                 "checks": checks, "seconds": elapsed, "output": text}
            )
            failed = [k for k, v in checks.items() if not v]
            print(f"  {case['id']} run {i}: score={score:.2f} [{elapsed}s]"
                  + (f" failed={failed}" if failed else ""))

    age_pass = sum(r["pass"] for r in results["age_extraction"])
    report_avg = (sum(r["score"] for r in results["reports"]) / len(results["reports"]))
    results["summary"] = {
        "age_pass_rate": f"{age_pass}/{len(results['age_extraction'])}",
        "report_avg_score": round(report_avg, 3),
        "avg_report_seconds": round(
            sum(r["seconds"] for r in results["reports"]) / len(results["reports"]), 2
        ),
    }
    print(f"=== Summary: age {results['summary']['age_pass_rate']}, "
          f"report score {report_avg:.3f}, "
          f"avg report latency {results['summary']['avg_report_seconds']}s ===")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"{label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved {out_path}")


# ---------------------------------------------------------------- compare

def compare(a_label, b_label):
    def load(label):
        with open(os.path.join(RESULTS_DIR, f"{label}.json"), encoding="utf-8") as f:
            return json.load(f)

    a, b = load(a_label), load(b_label)
    print(f"{'':24} {a_label:>12} {b_label:>12}")
    print(f"{'age pass rate':24} {a['summary']['age_pass_rate']:>12} "
          f"{b['summary']['age_pass_rate']:>12}")
    print(f"{'report avg score':24} {a['summary']['report_avg_score']:>12} "
          f"{b['summary']['report_avg_score']:>12}")
    print(f"{'avg report latency (s)':24} {a['summary']['avg_report_seconds']:>12} "
          f"{b['summary']['avg_report_seconds']:>12}")

    regressions = []
    for ra, rb in zip(a["age_extraction"], b["age_extraction"]):
        if ra["pass"] and not rb["pass"]:
            regressions.append(f"age {ra['input']!r}: {ra['got']} -> {rb['got']}")

    def per_case(results):
        by_case = {}
        for r in results["reports"]:
            by_case.setdefault(r["case"], []).append(r["score"])
        return {c: sum(s) / len(s) for c, s in by_case.items()}

    pa, pb = per_case(a), per_case(b)
    for case in pa:
        if pb.get(case, 0) < pa[case]:
            regressions.append(f"report {case}: {pa[case]:.2f} -> {pb[case]:.2f}")

    if regressions:
        print("\nREGRESSIONS:")
        for r in regressions:
            print(f"  - {r}")
        sys.exit(1)
    print("\nNo regressions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", help="run evals and save under this label")
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "CANDIDATE"))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
    elif args.label:
        run(args.label)
    else:
        parser.error("pass --label or --compare")

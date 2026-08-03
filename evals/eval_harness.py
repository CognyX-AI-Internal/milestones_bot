# -*- coding: utf-8 -*-
"""Regression eval harness for the CMSP screening bot.

Scores the model's report against ground truth computed by screening_logic, so a
prompt, model, or library change can be compared against a stored baseline.

The checks are deliberately strict about numbers: the delay percentage must
appear verbatim and no other percentage may appear anywhere in the report.

Usage (from project root):
    python evals/eval_harness.py --label baseline
    python evals/eval_harness.py --label candidate
    python evals/eval_harness.py --compare baseline candidate
"""

import argparse
import inspect
import json
import os
import re
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "evals", "results")
sys.path.insert(0, PROJECT_ROOT)

import screening_logic as sl  # noqa: E402

REPORT_ITERATIONS = 2

# ---------------------------------------------------------------- normalising

_QUOTES = dict.fromkeys(map(ord, "‘’ʼ“”"), "'")
_DASHES = dict.fromkeys(map(ord, "–—−"), "-")


def norm(text):
    """Fold the quote/dash variants models rewrite, for text matching only.

    This lives in the harness on purpose: the runtime matches milestones by
    (band, index), so it never needs to normalise anything.
    """
    if not text:
        return ""
    text = text.translate(_QUOTES).translate(_DASHES)
    return re.sub(r"\s+", " ", text).strip().lower()


def key_phrase(milestone, words=6):
    """A distinctive opening slice of a milestone, for presence checks."""
    return " ".join(norm(milestone).split()[:words])


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

RED_FLAG_OBS = ("He does not speak at all and never responds to his name. "
                "He used to say 'mama' but stopped months ago.")


def build_report_cases(checklist_options):
    """Cases mirroring the parity table, exercised end to end through the model."""

    def ticks(key, mode="none", n=0):
        size = len(checklist_options[key])
        if mode == "all":
            return [True] * size
        if mode == "some":
            return [True] * n + [False] * (size - n)
        return [False] * size

    return [
        {
            "id": "partial_24mo_presumed_floor",
            "age": 24,
            "checklists": {24: ticks(24, "some", 4)},
            "observations": "",
            "expect_disclosure": True,
        },
        {
            "id": "walked_down_14mo",
            "age": 14,
            "checklists": {18: ticks(18), 12: ticks(12), 9: ticks(9),
                           6: ticks(6, "all"), 3: ticks(3, "all")},
            "observations": "Points at objects but does not use any words yet.",
            "expect_disclosure": False,
        },
        {
            "id": "all_met_24mo",
            "age": 24,
            "checklists": {24: ticks(24, "all")},
            "observations": "",
            "expect_disclosure": False,
        },
        {
            "id": "at_least_4mo",
            "age": 4,
            "checklists": {6: ticks(6), 3: ticks(3, "all")},
            "observations": "",
            "expect_disclosure": False,
        },
        {
            "id": "no_band_complete_9mo",
            "age": 9,
            "checklists": {9: ticks(9), 6: ticks(6), 3: ticks(3, "some", 2)},
            "observations": "",
            "expect_disclosure": False,
        },
        {
            "id": "all_met_24mo_red_flag",
            "age": 24,
            "checklists": {24: ticks(24, "all")},
            "observations": RED_FLAG_OBS,
            "expect_disclosure": False,
            "expect_safety_override": True,
        },
    ]


# ---------------------------------------------------------------- scoring

REQUIRED_SECTIONS = [
    "SPEECH AND LANGUAGE THERAPY REPORT",
    "Overview",
    "Observations",
    "Milestones Achieved",
    "Recommendations for Parents",
    "Recommendations for the Clinical Team",
]

PCT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
# Anchored to a markdown heading: the phrase also occurs in Observations prose,
# and matching that instead silently scored the wrong slice of the report.
NOT_MET_HEADING = re.compile(r"^#{1,4}\s*milestones expected but not met", re.I | re.M)
NEXT_HEADING = re.compile(r"\n#{1,4}\s", re.M)


def not_met_section(text):
    """The body of the 'Milestones Expected but Not Met' section, if present."""
    match = NOT_MET_HEADING.search(text)
    if not match:
        return None
    rest = text[match.end():]
    nxt = NEXT_HEADING.search(rest)
    return rest[:nxt.start()] if nxt else rest


def score_report(text, case, truth, checklist_options):
    """Returns {check_name: bool}. Every check is derived from ground truth."""
    checks = {}
    if not text:
        return {"produced_output": False}

    body = norm(text)

    for section in REQUIRED_SECTIONS:
        checks["section:" + section] = norm(section) in body

    # --- the numbers -------------------------------------------------------
    found_pcts = {p.replace(" ", "") for p in PCT_RE.findall(text)}
    if truth.delay_text:
        expected_pcts = {p.replace(" ", "") for p in PCT_RE.findall(truth.delay_text)}
        checks["delay_verbatim"] = norm(truth.delay_text) in body
        checks["no_invented_percentage"] = found_pcts <= expected_pcts
        if truth.delay_state == sl.DELAY_AT_LEAST:
            checks["no_bogus_100_percent"] = "100%" not in found_pcts
            checks["stated_as_minimum"] = "at least" in body
    else:
        checks["no_percentage_when_no_delay"] = not found_pcts
        checks["no_delay_claimed"] = "delay of approximately" not in body

    # --- the bands ---------------------------------------------------------
    checks["chrono_band_correct"] = norm(truth.chrono_band.label) in body
    if truth.dev_band:
        checks["dev_band_correct"] = norm(truth.dev_band.label) in body
        wrong_bands = [b.label for b in sl.BANDS
                       if b.key not in (truth.dev_band.key, truth.chrono_band.key)]
        checks["no_wrong_dev_band_claimed"] = not any(
            ("developmental range of " + norm(lbl)) in body
            or ("developmental level of " + norm(lbl)) in body
            for lbl in wrong_bands
        )

    # --- the milestone lists ----------------------------------------------
    section = not_met_section(text)
    if truth.all_met_for_age:
        checks["omits_not_met_section"] = section is None
    else:
        checks["has_not_met_section"] = section is not None
        if section is not None:
            sect = norm(section)
            checks["all_unmet_listed"] = all(
                key_phrase(m[2]) in sect for m in truth.unmet)
            met_phrases = [key_phrase(m[2]) for m in truth.met]
            checks["no_met_milestone_in_unmet"] = not any(
                p in sect for p in met_phrases)
            own = {key_phrase(o) for o in checklist_options[truth.chrono_band.key]}
            foreign = []
            for band_key, options in checklist_options.items():
                if band_key == truth.chrono_band.key:
                    continue
                foreign.extend(p for p in (key_phrase(o) for o in options)
                               if p not in own)
            checks["no_foreign_band_milestone_in_unmet"] = not any(
                p in sect for p in foreign)

    # --- scope disclosure --------------------------------------------------
    disclosed = ("not administered" in body or "presumed" in body)
    if case.get("expect_disclosure"):
        checks["scope_disclosure_present"] = disclosed
    else:
        checks["no_spurious_scope_disclosure"] = not disclosed

    # --- no internal plumbing in a clinical report -------------------------
    checks["no_facts_field_names_leaked"] = not any(
        f in text for f in ("ALL_MILESTONES_MET_FOR_CURRENT_RANGE", "DELAY_PERCENTAGE",
                            "DEVELOPMENTAL_AGE_RANGE", "CURRENT_CHRONOLOGICAL_AGE_RANGE",
                            "MILESTONES_NOT_MET", "MILESTONES_MET", "VERIFIED FACTS",
                            "SCREENING_SCOPE", "SAFETY OVERRIDE"))

    # --- safety override ---------------------------------------------------
    if case.get("expect_safety_override"):
        checks["red_flag_surfaced"] = any(
            w in body for w in ("audiolog", "hearing", "developmental evaluation",
                                "further evaluation"))
        checks["red_flag_in_observations"] = ("respond" in body and "name" in body)

    return checks


# ---------------------------------------------------------------- run

def run(label):
    os.chdir(PROJECT_ROOT)
    import main  # noqa: E402
    import milestone_domains as md  # noqa: E402

    accepts_facts = "facts" in inspect.signature(
        main.generate_recommendations_new).parameters

    results = {
        "label": label,
        "openai_version": __import__("openai").__version__,
        "facts_block_wired": accepts_facts,
        "age_extraction": [],
        "reports": [],
    }

    print("=== Age extraction (%d cases) ===" % len(AGE_CASES))
    for case in AGE_CASES:
        t0 = time.time()
        got = main.get_age_from_gpt(case["input"])
        elapsed = round(time.time() - t0, 2)
        ok = got == case["expected"]
        results["age_extraction"].append(
            {"input": case["input"], "expected": case["expected"], "got": got,
             "pass": ok, "seconds": elapsed})
        print("  %s  %r -> %s (expected %s) [%ss]"
              % ("PASS" if ok else "FAIL", case["input"], got, case["expected"], elapsed))

    cases = build_report_cases(main.checklist_options)
    print("=== Reports (%d cases x %d runs, facts_block=%s) ==="
          % (len(cases), REPORT_ITERATIONS, accepts_facts))

    for case in cases:
        truth = sl.analyze(case["age"], case["checklists"],
                           main.checklist_options, md.MILESTONE_DOMAINS)
        # The message the bot builds today: a numbered list of achieved milestones.
        achieved = [m[2] for m in truth.met]
        message = "\n".join("%d. %s" % (i + 1, m) for i, m in enumerate(achieved))

        for i in range(REPORT_ITERATIONS):
            t0 = time.time()
            if accepts_facts:
                text = main.generate_recommendations_new(
                    message, case["age"], case["observations"],
                    facts=sl.build_facts_block(truth))
            else:
                text = main.generate_recommendations_new(
                    message, case["age"], case["observations"])
            elapsed = round(time.time() - t0, 2)
            checks = score_report(text, case, truth, main.checklist_options)
            score = sum(1 for v in checks.values() if v) / float(len(checks))
            failed = sorted(k for k, v in checks.items() if not v)
            results["reports"].append(
                {"case": case["id"], "iteration": i, "score": round(score, 3),
                 "checks": checks, "failed": failed, "seconds": elapsed,
                 "expected_delay": truth.delay_text, "output": text})
            print("  %s run %d: score=%.2f [%ss]%s"
                  % (case["id"], i, score, elapsed,
                     ("\n      failed: " + ", ".join(failed)) if failed else ""))

    age_pass = sum(r["pass"] for r in results["age_extraction"])
    reports = results["reports"]
    all_checks = sum(len(r["checks"]) for r in reports)
    passed_checks = sum(sum(1 for v in r["checks"].values() if v) for r in reports)
    perfect = sum(1 for r in reports if not r["failed"])

    results["summary"] = {
        "age_pass_rate": "%d/%d" % (age_pass, len(results["age_extraction"])),
        "report_avg_score": round(sum(r["score"] for r in reports) / len(reports), 3),
        "checks_passed": "%d/%d" % (passed_checks, all_checks),
        "clean_reports": "%d/%d" % (perfect, len(reports)),
        "avg_report_seconds": round(
            sum(r["seconds"] for r in reports) / len(reports), 2),
    }
    s = results["summary"]
    print("=== Summary: age %s | report score %.3f | checks %s | clean %s | %ss avg ==="
          % (s["age_pass_rate"], s["report_avg_score"], s["checks_passed"],
             s["clean_reports"], s["avg_report_seconds"]))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "%s.json" % label)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("Saved %s" % out_path)


# ---------------------------------------------------------------- compare

def compare(a_label, b_label):
    def load(label):
        with open(os.path.join(RESULTS_DIR, "%s.json" % label), encoding="utf-8") as f:
            return json.load(f)

    a, b = load(a_label), load(b_label)
    rows = ["age_pass_rate", "report_avg_score", "checks_passed", "clean_reports",
            "avg_report_seconds"]
    print("%-28s %14s %14s" % ("", a_label, b_label))
    for row in rows:
        print("%-28s %14s %14s" % (row, a["summary"][row], b["summary"][row]))

    def failures_by_case(results):
        out = {}
        for r in results["reports"]:
            out.setdefault(r["case"], set()).update(r["failed"])
        return out

    fa, fb = failures_by_case(a), failures_by_case(b)
    fixed, regressed = [], []
    for case in sorted(set(fa) | set(fb)):
        was, now = fa.get(case, set()), fb.get(case, set())
        fixed.extend("%s / %s" % (case, c) for c in sorted(was - now))
        regressed.extend("%s / %s" % (case, c) for c in sorted(now - was))

    if fixed:
        print("\nFIXED (%d):" % len(fixed))
        for f in fixed:
            print("  + %s" % f)
    if regressed:
        print("\nREGRESSED (%d):" % len(regressed))
        for f in regressed:
            print("  - %s" % f)
        sys.exit(1)
    print("\nNo regressions.")


def rescore(label):
    """Re-apply the current checks to a stored run's saved outputs.

    Every report is saved verbatim, so a fix to a check can be applied to an old
    run without paying for the API calls again - and both sides of a comparison
    stay judged by identical criteria.
    """
    os.chdir(PROJECT_ROOT)
    import ast
    import milestone_domains as md

    with open(os.path.join(PROJECT_ROOT, "checklist_options.json"), encoding="utf-8") as f:
        checklist_options = {int(k): v for k, v in ast.literal_eval(f.read()).items()}

    path = os.path.join(RESULTS_DIR, "%s.json" % label)
    with open(path, encoding="utf-8") as f:
        results = json.load(f)

    cases = {c["id"]: c for c in build_report_cases(checklist_options)}
    for r in results["reports"]:
        case = cases[r["case"]]
        truth = sl.analyze(case["age"], case["checklists"], checklist_options,
                           md.MILESTONE_DOMAINS)
        checks = score_report(r["output"], case, truth, checklist_options)
        r["checks"] = checks
        r["failed"] = sorted(k for k, v in checks.items() if not v)
        r["score"] = round(sum(1 for v in checks.values() if v) / float(len(checks)), 3)

    reports = results["reports"]
    all_checks = sum(len(r["checks"]) for r in reports)
    passed = sum(sum(1 for v in r["checks"].values() if v) for r in reports)
    results["summary"]["report_avg_score"] = round(
        sum(r["score"] for r in reports) / len(reports), 3)
    results["summary"]["checks_passed"] = "%d/%d" % (passed, all_checks)
    results["summary"]["clean_reports"] = "%d/%d" % (
        sum(1 for r in reports if not r["failed"]), len(reports))

    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    s = results["summary"]
    print("rescored %s: score %.3f | checks %s | clean %s"
          % (label, s["report_avg_score"], s["checks_passed"], s["clean_reports"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "CANDIDATE"))
    parser.add_argument("--rescore", nargs="+", metavar="LABEL")
    args = parser.parse_args()
    if args.rescore:
        for label in args.rescore:
            rescore(label)
    elif args.compare:
        compare(*args.compare)
    elif args.label:
        run(args.label)
    else:
        parser.error("pass --label, --rescore or --compare")

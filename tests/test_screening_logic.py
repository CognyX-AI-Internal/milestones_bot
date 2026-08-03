# -*- coding: utf-8 -*-
"""Parity tests for the deterministic screening arithmetic.

Pure functions, no API calls - run these on every change:
    python tests/test_screening_logic.py
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import screening_logic as sl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(HERE, "checklist_options.json"), encoding="utf-8") as f:
    CHECKLIST = {int(k): v for k, v in ast.literal_eval(f.read()).items()}

NO_DOMAINS = {}

_failures = []
_passes = []


def check(name, got, expected):
    if got == expected:
        _passes.append(name)
    else:
        _failures.append("%s\n      expected: %r\n      got:      %r" % (name, expected, got))


def band(key, mode="none", n=0):
    """Build a tick list for a band: all ticked, none ticked, or first n ticked."""
    size = len(CHECKLIST[key])
    if mode == "all":
        return [True] * size
    if mode == "some":
        return [True] * n + [False] * (size - n)
    return [False] * size


def run(age, checklists):
    return sl.analyze(age, checklists, CHECKLIST, NO_DOMAINS)


def summary(res):
    return (res.dev_band_label, res.delay_text, res.disclosure_needed, len(res.unmet))


# ---------------------------------------------------------------- parity table

def test_01_all_own_band_no_walkdown():
    """24mo, all 6 of own band -> no delay, dev = own band."""
    res = run(24, {24: band(24, "all")})
    check("01 dev band", res.dev_band_label, "19 to 24 months")
    check("01 no delay", res.delay_text, None)
    check("01 all met", res.all_met_for_age, True)
    check("01 no disclosure", res.disclosure_needed, False)


def test_01b_all_own_band_then_walked_up():
    """Same child after the bot auto-advances to the next band (real bot state):
    the walk-up band is administered and empty, which must not create a delay."""
    res = run(24, {24: band(24, "all"), 36: band(36, "none")})
    check("01b dev band", res.dev_band_label, "19 to 24 months")
    check("01b no delay", res.delay_text, None)
    check("01b all met", res.all_met_for_age, True)


def test_02_partial_own_band_no_walkdown():
    """24mo, 4 of 6, nothing below administered -> presumed floor, disclosure on."""
    res = run(24, {24: band(24, "some", 4)})
    check("02 summary", summary(res), ("13 to 18 months", "25.00% to 45.83%", True, 2))


def test_03_walked_down_to_demonstrated_floor():
    """24mo, all of 13-18 demonstrated + 3 of 19-24 -> same numbers, no disclosure."""
    res = run(24, {24: band(24, "some", 3), 18: band(18, "all")})
    check("03 summary", summary(res), ("13 to 18 months", "25.00% to 45.83%", False, 3))


def test_04_walkdown_empty_bands_are_failures_not_presumptions():
    """14mo, all of Birth-3 and 4-6, bands 7-9/10-12/13-18 shown and empty.

    This is the case that breaks tick-inference: the empty bands sit BELOW the
    lowest ticked band's neighbours and would be presumed met, yielding
    14.29%-28.57%. They were administered, so they are failures."""
    res = run(14, {18: band(18), 12: band(12), 9: band(9),
                   6: band(6, "all"), 3: band(3, "all")})
    check("04 dev band", res.dev_band_label, "4 to 6 months")
    check("04 delay", res.delay_text, "57.14% to 71.43%")
    check("04 no disclosure", res.disclosure_needed, False)


def test_05_36mo_met_through_2to3():
    """36mo at the top of its own band -> no delay."""
    res = run(36, {36: band(36, "all")})
    check("05 dev band", res.dev_band_label, "2 to 3 years")
    check("05 no delay", res.delay_text, None)
    check("05 all met", res.all_met_for_age, True)


def test_06_37mo_one_month_over_the_boundary():
    """37mo crosses into 3-4 years: a one-month age change must flip the band."""
    res = run(37, {48: band(48), 36: band(36, "all")})
    check("06 chrono band", res.chrono_band.label, "3 to 4 years")
    check("06 dev band", res.dev_band_label, "2 to 3 years")
    check("06 delay", res.delay_text, "2.70% to 32.43%")


def test_07_no_band_complete():
    """9mo, 2 of 7 in Birth-to-3 -> below the earliest band, minimum only."""
    res = run(9, {9: band(9), 6: band(6), 3: band(3, "some", 2)})
    check("07 dev band", res.dev_band_label, "Below Birth to 3 months")
    check("07 delay", res.delay_text, "at least 66.67%")


def test_08_floor_band_starts_at_month_zero():
    """4mo, all of Birth-to-3 -> upper bound would be a meaningless 100%."""
    res = run(4, {6: band(6), 3: band(3, "all")})
    check("08 delay", res.delay_text, "at least 25.00%")
    check("08 not a range", res.delay_state, sl.DELAY_AT_LEAST)


def test_09_negative_delay_is_suppressed():
    """1mo and 2mo partials compute to negative delay -> emit nothing."""
    for age in (1, 2, 3):
        res = run(age, {3: band(3, "some", 2)})
        check("09 age %dmo no delay" % age, res.delay_text, None)
        check("09 age %dmo state" % age, res.delay_state, sl.DELAY_NONE)


# ---------------------------------------------------------------- edge cases

def test_10_nothing_ticked_anywhere():
    """The failure mode tick-inference produces: a child who ticked NOTHING,
    walked all the way down, must not come out mildly delayed."""
    res = run(24, {24: band(24), 18: band(18), 12: band(12),
                   9: band(9), 6: band(6), 3: band(3)})
    check("10 dev band", res.dev_band_label, "Below Birth to 3 months")
    check("10 delay", res.delay_text, "at least 87.50%")


def test_11_delay_ignores_how_many_were_missed():
    """Accepted property: 1-of-6 and 4-of-6 give the same range."""
    a = run(24, {24: band(24, "some", 1)})
    b = run(24, {24: band(24, "some", 4)})
    check("11 same delay", a.delay_text, b.delay_text)
    check("11 value", a.delay_text, "25.00% to 45.83%")
    check("11 unmet counts differ", (len(a.unmet), len(b.unmet)), (5, 2))


def test_12_unmet_is_chronological_band_only():
    """Unmet must never include a milestone from another band."""
    res = run(24, {24: band(24, "some", 4), 18: band(18, "some", 2)})
    check("12 unmet all from chrono", {e[0] for e in res.unmet}, {24})


def test_13_out_of_scope_ages():
    for age in (61, 70, 200):
        try:
            run(age, {60: band(60, "all")})
            check("13 age %d raises" % age, "no exception", "OutOfScope")
        except sl.OutOfScope:
            check("13 age %d raises" % age, "OutOfScope", "OutOfScope")
    try:
        run(-1, {})
        check("13 negative raises", "no exception", "OutOfScope")
    except sl.OutOfScope:
        check("13 negative raises", "OutOfScope", "OutOfScope")


def test_14_boundary_ages_resolve_once():
    """Every band boundary resolves to exactly one band."""
    expected = [
        (0, "Birth to 3 months"), (3, "Birth to 3 months"), (4, "4 to 6 months"),
        (6, "4 to 6 months"), (7, "7 to 9 months"), (9, "7 to 9 months"),
        (10, "10 to 12 months"), (12, "10 to 12 months"), (13, "13 to 18 months"),
        (18, "13 to 18 months"), (19, "19 to 24 months"), (24, "19 to 24 months"),
        (25, "2 to 3 years"), (36, "2 to 3 years"), (37, "3 to 4 years"),
        (48, "3 to 4 years"), (49, "4 to 5 years"), (60, "4 to 5 years"),
    ]
    for age, label in expected:
        check("14 age %d" % age, sl.band_for_age(age).label, label)


def test_15_inconsistent_lower_band_is_flagged():
    """Own band complete but an administered lower band is not: flag it."""
    res = run(24, {24: band(24, "all"), 18: band(18, "some", 2)})
    check("15 no delay", res.delay_text, None)
    check("15 flagged", res.inconsistent, True)


def test_16_facts_block_contents():
    """The FACTS block must carry the computed values and the right variant."""
    import milestone_domains as md

    res = sl.analyze(24, {24: band(24, "some", 4)}, CHECKLIST, md.MILESTONE_DOMAINS)
    facts = sl.build_facts_block(res)
    check("16 chrono", "CURRENT_CHRONOLOGICAL_AGE_RANGE: 19 to 24 months" in facts, True)
    check("16 dev", "DEVELOPMENTAL_AGE_RANGE: 13 to 18 months" in facts, True)
    check("16 all met NO", "ALL_MILESTONES_MET_FOR_CURRENT_RANGE: NO" in facts, True)
    check("16 delay verbatim", "25.00% to 45.83%" in facts, True)
    check("16 scope disclosure", "SCREENING_SCOPE:" in facts, True)
    check("16 safety override", "SAFETY OVERRIDE:" in facts, True)
    check("16 exactly 2 unmet", "exactly these 2, and ONLY these" in facts, True)

    res2 = sl.analyze(24, {24: band(24, "all")}, CHECKLIST, md.MILESTONE_DOMAINS)
    facts2 = sl.build_facts_block(res2)
    check("16 all-met no percentage", "DELAY_PERCENTAGE: NONE" in facts2, True)
    check("16 all-met omit section", "MILESTONES_NOT_MET: NONE" in facts2, True)
    check("16 all-met both rec sections",
          "still produce both sections in full" in facts2, True)
    check("16 all-met no scope block", "SCREENING_SCOPE:" in facts2, False)

    res3 = sl.analyze(4, {6: band(6), 3: band(3, "all")}, CHECKLIST, md.MILESTONE_DOMAINS)
    facts3 = sl.build_facts_block(res3)
    check("16 at-least variant", "at least 25.00%" in facts3, True)
    check("16 at-least no 100", "100%" not in facts3.split("never print")[0], True)


def test_17_every_milestone_has_a_domain():
    """The domain map must cover every milestone in the checklist."""
    import milestone_domains as md

    expected = {(k, i) for k, opts in CHECKLIST.items() for i in range(len(opts))}
    check("17 full coverage", set(md.MILESTONE_DOMAINS.keys()), expected)
    check("17 valid values",
          set(md.MILESTONE_DOMAINS.values()) <= set(sl.DOMAIN_ORDER), True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            _failures.append("%s raised %s: %s" % (t.__name__, type(exc).__name__, exc))
    print("passed: %d" % len(_passes))
    if _failures:
        print("FAILED: %d" % len(_failures))
        for f in _failures:
            print("  - %s" % f)
        sys.exit(1)
    print("all parity cases pass")

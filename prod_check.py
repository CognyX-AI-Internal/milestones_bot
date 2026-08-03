# -*- coding: utf-8 -*-
"""Post-deploy smoke test. Run on the dyno:

    heroku run -a cmsp-speech-lang-screening-bot python prod_check.py

Verifies the things a green build does not: that Redis actually answers (the
client is constructed lazily, so a clean boot proves nothing), that the deployed
library versions are the intended ones, and that the screening arithmetic
produces known-correct values in the production environment.
"""

import sys

import openai

import main
import milestone_domains as md
import screening_logic as sl

FAILURES = []


def check(label, got, expected=None):
    ok = (got == expected) if expected is not None else bool(got)
    print("  %-22s %s%s" % (label, got, "" if ok else "   <-- EXPECTED %r" % (expected,)))
    if not ok:
        FAILURES.append(label)


print("versions")
check("openai", openai.__version__, "2.51.0")
check("redis", __import__("redis").__version__, "8.1.0")
check("model", main.OPENAI_MODEL, "gpt-5.6-terra")

print("redis round trip")
check("ping", main.r.ping(), True)
main.r.set("prod_check", "ok", ex=60)
check("set/get", main.r.get("prod_check").decode(), "ok")
main.r.delete("prod_check")

print("screening arithmetic")
opts = main.checklist_options
check("domains mapped", len(md.MILESTONE_DOMAINS), 77)

res = sl.analyze(14, {18: [False] * 8, 12: [False] * 7, 9: [False] * 7,
                      6: [True] * 7, 3: [True] * 7}, opts, md.MILESTONE_DOMAINS)
check("14mo dev band", res.dev_band_label, "4 to 6 months")
check("14mo delay", res.delay_text, "57.14% to 71.43%")

res = sl.analyze(4, {6: [False] * 7, 3: [True] * 7}, opts, md.MILESTONE_DOMAINS)
check("4mo delay", res.delay_text, "at least 25.00%")

res = sl.analyze(24, {24: [True] * 6}, opts, md.MILESTONE_DOMAINS)
check("24mo all met", res.delay_text is None, True)

try:
    sl.band_for_age(72)
    check("72mo rejected", "no exception", "OutOfScope")
except sl.OutOfScope:
    check("72mo rejected", "OutOfScope", "OutOfScope")

if FAILURES:
    print("\nFAILED: %s" % ", ".join(FAILURES))
    sys.exit(1)
print("\nall production checks passed")

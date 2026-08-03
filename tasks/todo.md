# Deterministic screening logic (2026-08-03)

Goal: the model must never compute a number or pick an age band. Code computes
bands, dev age, delay % and the unmet list; the model writes prose against an
authoritative VERIFIED FACTS block.

## Spec corrections applied before implementing

- [x] **Presumption rule was self-contradictory and unsafe.** The `lowestTicked` formula
      presumed every empty band below the lowest ticked band as MET, which is the opposite
      of the prose ("an empty band below a ticked one means shown-and-failed"). It also
      broke on two reachable inputs: a child who ticked NOTHING came out mildly delayed,
      and a partial band followed by more walk-down presumed failed bands as met.
      Replaced inference with ground truth: `administered = keys present in
      user_data['checklists']` (the bot creates a key only when a band is rendered).
- [x] **Disclosure rule contradicted the parity table.** "Disclose whenever presumed bands
      exist" would fire on case 3, which expects no disclosure. Rule is now: disclose iff
      the devBand ITSELF was presumed rather than demonstrated (basal convention).
- [x] **Chronological band comes from `age`, never `age_group`** — the bot mutates
      `age_group` during walk-down, so that field is not the chronological band.
- [x] **Match by (band, index), not normalised text.** Normalisation now exists only in the
      eval matcher, where model paraphrasing has to be tolerated.
- [x] **Old arithmetic deleted from the prompt**, not kept "as background".
- [x] **SAFETY OVERRIDE made unconditional** — red flags matter on delayed reports too.
- [x] **>60 months hard-stops** instead of clamping into the 4-to-5 band.

## Work

- [x] `screening_logic.py` — bands with inclusive bounds, administered-vs-presumed,
      devBand, delay with all guards, FACTS block builder (3 delay variants)
- [x] `milestone_domains.py` — all 77 milestones mapped to Expressive/Receptive/Social,
      keyed by (band, idx), with 25 ambiguous calls documented. NEEDS CLINICIAN SIGN-OFF.
- [x] `tests/test_screening_logic.py` — 73 assertions, all 10 parity cases + edge cases,
      pure functions, zero API cost
- [x] `evals/eval_harness.py` — rewritten to score model output against screening_logic
      ground truth (delay verbatim, no invented percentage, correct bands, no foreign-band
      milestone in the not-met list, disclosure presence, safety override)
- [x] main.py wired: facts block, prompt sections 3/4/5 rewritten, caller computes facts
      and refuses to emit a report if the computation fails
- [x] Baseline + candidate eval, compared

## Review

Measured on gpt-5.1 / gpt-5-mini (both sides), so this isolates the logic change
from the model change:

|                    | baseline (model does the maths) | candidate (code does the maths) |
|--------------------|---------------------------------|----------------------------------|
| age extraction     | 7/7                             | 7/7                              |
| report score       | 0.834                           | **1.000**                        |
| checks passed      | 165/200                         | **200/200**                      |
| clean reports      | 3/12                            | **12/12**                        |

20 checks fixed, 0 regressed. Unit tests: 73/73.

### Real clinical errors the baseline was producing (all now fixed)

1. **A 4-month-old was reported as "4 years old"** with a 93.75%-100% delay and 4-to-5-year
   milestones listed as unmet. The prompt passed a bare number and never said "months".
2. **"66.67% to 100.00%"** - the meaningless 100% upper bound, exactly as predicted.
3. **"71.42%"** - the rounding error copied verbatim from the old prompt's worked example.
4. Unmet milestones were paraphrased rather than reproduced, so reports were not traceable
   to the ASHA descriptors.
5. The scope disclosure was never produced, because nothing told the model bands had been
   presumed rather than screened.

### Defects introduced by the facts block, found and fixed during the run

- Model leaked internal field names into a parent-facing report ("Omitted
  (ALL_MILESTONES_MET_FOR_CURRENT_RANGE: YES)", "None reported in the MILESTONES_MET list").
  Root cause: band 24 has zero Social Communication milestones, and the template's fixed
  three-domain structure forced the model to say something. Fixed by allowing empty domains
  to be omitted, plus an explicit "never print field names" rule.
- "a delay of approximately at least 25.00%" - fixed the wording for the at-least variant.

### Harness bug found and fixed

`all_unmet_listed` was scoring the wrong slice of the report: the section matcher hit the
first occurrence of "Milestones Expected but Not Met", which also appears in Observations
prose. Anchored to a markdown heading. Added `--rescore` so a check fix can be re-applied to
stored outputs without re-paying for the API calls, keeping both sides judged identically.

### Deliberate report change

Reports now state the chronological ASHA age range in Observations ("...which falls within
the 4 to 6 months ASHA age range"). Previously no report stated it, so nothing tied the
narrative to the band the delay was computed from.

### Follow-ups

- `milestone_domains.py` needs clinician sign-off. 25 entries are flagged AMBIGUOUS with
  rationale; `(60,9)` (blending + rhyme) is the weakest call.
- Indexes in that file are positional: editing or reordering `checklist_options.json`
  invalidates the map. The test suite catches coverage gaps but not a reorder.
- Not verified: prod Redis (unreachable from this machine) and a live Telegram round trip.

---

# GPT-5.6 Upgrade + Library Update (2026-07-31)

Earlier work on this branch, kept for the record.

- [x] Verified gpt-5.6 family: gpt-5.6-sol / gpt-5.6-terra / gpt-5.6-luna, all support
      reasoning effort "none", Responses API compatible. Terra = $2/$12 per MTok
- [x] `OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-terra")` across all 5 call
      sites (report generator upgraded from gpt-5-mini to terra)
- [x] Pipfile libs updated (openai 2.51.0, flask 3.1.3, pyTelegramBotAPI 4.36.0, redis 8.1.0,
      markdownmail 0.11.1, python-dotenv 1.2.2, gunicorn 26.0.0), lock regenerated, py 3.10 kept
- [x] Fixed production bug: debug `print(report)` crashed on non-ASCII output under cp1252
      and the broad except swallowed the entire report
- [x] Measured with the then-current harness: no regression, reports ~4x faster

Rollback for the model change: set Heroku config var `OPENAI_MODEL=gpt-5.1`.
Note the eval results in `evals/results/` are from the deterministic-logic measurement above
and were produced by the current harness; the older gpt-5.6 numbers are superseded.

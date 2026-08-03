# GPT-5.6 Upgrade + Library Update (2026-07-31)

Goal: move bot to gpt-5.6 (terra-level intelligence), update libraries,
with a baseline-first workflow so there is no regression, only improvement.

## Plan

- [x] Map LLM call sites: `get_age_from_gpt` (gpt-5.1), `generate_recommendations_new` (gpt-5-mini) are live;
      `get_dev_age_from_gpt`, `generate_recommendations`, `get_word_age` are dead code (never called)
- [x] Restore `checklist_options.json` / `suggestions.json` (were deleted from working tree; required at startup)
- [x] Verify gpt-5.6 family: gpt-5.6-sol / gpt-5.6-terra / gpt-5.6-luna, all support reasoning effort "none",
      Responses API compatible. Terra = $2/$12 per MTok
- [x] Build eval harness `evals/eval_harness.py` (age-extraction exact-match + report structural checks)
- [x] Run baseline on current stack (openai 2.9.0, gpt-5.1 / gpt-5-mini) → `evals/results/baseline.json`
      Result: age 7/7, report score 1.000 (6/6 runs), avg report latency 57.4s
- [x] Fixed production bug found by baseline: debug `print(report)` in generate_recommendations_new
      crashed on non-ASCII chars (cp1252) and the broad except swallowed the whole report → removed
- [x] Update Pipfile libs (openai 2.51.0, flask 3.1.3, pyTelegramBotAPI 4.36.0, redis 8.1.0,
      markdownmail 0.11.1, python-dotenv 1.2.2, gunicorn 26.0.0) + regenerate Pipfile.lock (py 3.10 kept)
- [x] Smoke-test updated libs: main.py imports OK, gpt-5.1 call OK on openai 2.51.0,
      redis 8 accepts main.py's exact constructor (ssl_cert_reqs=None → CERT_NONE);
      prod Redis PING blocked by network from this machine (raw TCP also times out — not a lib issue)
- [x] Switch models → `OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-terra")`,
      all 5 call sites (incl. report generator, upgraded from gpt-5-mini → terra)
- [x] Run candidate eval → `evals/results/candidate.json`, compare vs baseline
- [x] Fix regression found on first candidate run: terra omitted both Recommendations sections when
      all milestones were met (it followed "recommendations solely based on unmet milestones" literally).
      Added explicit prompt instruction to always include both sections → re-ran, clean.

## Review

Final comparison (evals/eval_harness.py --compare baseline candidate):

|                        | baseline (gpt-5.1 / gpt-5-mini, openai 2.9.0) | candidate (gpt-5.6-terra, openai 2.51.0) |
|------------------------|------------------------------------------------|-------------------------------------------|
| age pass rate          | 7/7                                            | 7/7                                       |
| report avg score       | 1.000                                          | 1.000                                     |
| avg report latency     | 57.4s                                          | 13.9s (~4x faster)                        |

Changes:
- main.py: OPENAI_MODEL constant (env-overridable, default gpt-5.6-terra) across all 5 call sites;
  removed report-swallowing debug print; prompt instruction to always include Recommendations sections
- Pipfile / Pipfile.lock: all 7 deps to latest, python 3.10 runtime unchanged
- evals/: reusable regression harness + baseline/candidate results (rerun before future model changes)
- Restored checklist_options.json / suggestions.json (were deleted from working tree, app can't start without them)

Not verified locally: prod Redis connectivity (host unreachable from this machine at TCP level —
redis 8 client API verified compatible instead). Rollback: set Heroku config var OPENAI_MODEL=gpt-5.1.


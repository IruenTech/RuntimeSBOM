# RuntimeSBOM Phase28 — Spring Boot 2 review diagnostic and stable measurement patch

This is a **diagnostic plus test-stability patch**, not a bypass of approval or security gates.

## What happened?

The Phase28 manual workflow does not call `phase24-staging-manifest.py` or `phase25-review.py`.
Those commands are in the Phase26 workflow, which also triggers on pushes to `main`.
The Phase26 review's message combines missing evidence, invalid identity and SLO failure.
A prior, separately uploaded Phase26 review report passed for run `45763042301`.
A later push can trigger a fresh, statistically variable run.

## What this patch changes

* Preserves original fail-closed Phase24/25 manifest and approval thresholds.
* Prints explicit per-WAS checks and actual SLO metrics (`phase28-was-review-diagnostics.py`).
* Saves `results/phase28/was-review-diagnostics.json` in the Phase26 review artifact.
* Saves an additional per-WAS `phase28-diagnostic.json` in the Phase26 WAS artifact.
* Performs a 5-second warmup on each newly launched JVM and a 30-second measured
  run to reduce cold-start / short-window noise. Warmup data is retained in
  `warmup.json` and never counted as the measured interval.
* Does NOT mark anything successful if a measured SLO still fails.
* Does NOT change the official Java Agent binary, its SHA-256, or release approval.

## Test

```bash
python3 -m unittest discover -s tests -p 'test_phase28_was_review_diagnostics.py' -v
```

Run the Phase26 workflow again, inspect `review` and the `phase26-exact-binary-review-report` artifact.
If `spring-boot2` fails, inspect its metrics and send the
`phase26-was-spring-boot2` artifact or `phase21-summary.json` for root-cause analysis.

## Application to an existing Git repo

Extract this zip to your repo root **without deleting existing files**.
Inspect `git diff --stat` and `git diff` first, then commit and push.
The Phase26 CI is push-triggered and may launch on its own.
Production approval remains HOLD pending separate authorization.

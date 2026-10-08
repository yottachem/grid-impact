---
name: rewrite-claims
description: Rewrite findings statements that the latest analysis flagged as no longer fitting the data (GitHub issues labeled findings-review or data-check). Drafts new wording and matching conditions in analysis/claims.yaml for the owner's review. Run only when the owner asks (/rewrite-claims).
---

# Rewrite flagged findings statements

Every interpretive sentence on the Findings and Methods pages lives in `analysis/claims.yaml` with the
condition it rests on (`holds`). Each analysis run checks them (`analysis/narrative.py`); a statement
whose condition fails is shown as neutral figures marked "under review" and gets a GitHub issue. This
skill drafts the replacement. Nothing is published until the owner approves and the change is merged.

## Steps

1. **Get the data the site used.** Download the results from the latest successful ingest run so the
   rewrite is based on what is live, not on stale local files:
   ```
   gh run list --workflow ingest.yml --status success --limit 1 --json databaseId -q '.[0].databaseId'
   gh run download <id> -n marts-<id> -D /tmp/grid-impact-run
   ```
   Copy `analysis/results/*` and `data/marts/*` from it into the repo's `analysis/results/` and
   `data/marts/`, then run `uv run python -m analysis.exports && uv run python -m analysis.narrative`.
   If no artifact exists (older than 30 days), say so and use the local results, naming their run date.

2. **List what is flagged.** `uv run python -m analysis.narrative` prints each flagged claim and why.
   Read the open issues too: `gh issue list --label findings-review --label data-check`.

3. **Sort each flag.**
   - `data_check` (a plausibility range failed): do **not** rewrite yet. Trace the number to its source
     (raw snapshot, transform, EIA release) and report whether it looks real or like a feed error. Only
     if the owner confirms it is real, widen that range under `checks:` and continue to step 4.
   - `review` (the condition no longer holds): continue to step 4.

4. **Draft the rewrite.** For each statement:
   - Say in one line what the data now shows, using `uv run python -m analysis.narrative --values`.
   - Write new `text` that states only what the numbers support, and a new `holds` that encodes exactly
     that assertion (sign, significance from the confidence interval, ranking, year). The condition must
     be specific enough to fail again if the data moves back.
   - Prefer adding a new entry under `variants` over replacing reviewed wording when both outcomes are
     plausible in future runs.
   - Never loosen a condition just to clear a flag, never type a number into `text` (use a `{value}`
     placeholder), and keep the site's plain style: short sentences, no hedging filler, no em dashes.
   - If a needed value does not exist, add it in `values()` in `analysis/narrative.py`.
   - Check neighboring statements for consistency: a changed conclusion can make the headline, lede,
     chart readings, caveats, and Methods page disagree with each other.

5. **Verify.** `uv run python -m analysis.narrative` must report 0 flagged; `uv run pytest -q` must pass;
   `uv run python site/build.py` must build. Show the owner, for each statement: old wording, new
   wording, and the condition, plus the `git diff` of `analysis/claims.yaml`.

6. **Wait for approval.** Do not commit, push, or open a pull request until the owner says to. Then put
   the change on a branch (`claims/<yyyy-mm-dd>`), commit with the issue numbers in the message
   (`Fixes #N`), and open a pull request. After the owner merges it, offer to start a site rebuild:
   `gh workflow run ingest.yml -f cadence=daily`. The next run closes the issues automatically.

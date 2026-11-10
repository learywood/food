# AGENTS.md — food repo

Personal recipe tracker. Markdown files replace Google Keep notes/articles.
One file per dish in `recipes/`. The file body is always the **current best version** (what to cook next). Experiments are tracked inside the same file.

## Layout

- `recipes/<kebab-case-dish>.md` — one dish per file, e.g. `recipes/leek-potato-pie.md`
- `recipes/leek-potato-pie.md` is the canonical example. New recipes follow its structure.
- `TEMPLATE.md` (repo root) — blank copy of that structure. Copy it to start a new recipe.
- No index file. No subfolders per recipe. Keep it flat.
- `README.md` — human overview. This file (`AGENTS.md`) is the format spec.

## Recipe file format

Structure follows `TEMPLATE.md` (blank) and `recipes/leek-potato-pie.md` (filled example):

```md
# Dish Name

**Serves:** N · **Oven:** 400°F (200°C) · **Bake:** 25 minutes (+ status, see below)

## Phase 0 — Advance prep (optional, delete if not needed)

## Phase 1 — Prepare ingredients

- <qty><unit> <ingredient> — <prep>
- ...

## Phase 2 — Cook & assemble

1. **Bold lead-in.** Detail.
2. ...

## Notes

- Timeless rules/learnings.

## Trial log

### YYYY-MM-DD — short change description
- Change: what was different vs. previous best
- Result: pass / fail + observation
- Decision: keep / drop / retest (+ follow-up where relevant)

### To try

- Ideas not yet cooked (also marked `(trial)` in body when staged).

## Source

[Original recipe](<url>) — keep if the dish started from one. Never delete.
```

- Dated trial entries go newest at bottom, `### To try` stays last.

### Section rules

1. **Title:** `# Dish Name`, one per file.
2. **Meta line:** second line, bold keys. Include `Serves` always. Include `Oven`/`Bake`/`Time` where relevant. Append `(trial)` to the whole line or a single value while that value is untested, e.g. `**Bake:** 25 minutes (trial)`.
3. **Phases:** default to `Phase 0 / Phase 1 / Phase 2` per the template. `Phase 0` is optional — delete it when there's no advance prep (defrost-ahead, soaking, marinating). For simple dishes `Phase 1` may be renamed `## Ingredients` and `Phase 2` `## Method`; keep the phase names when prep has timing dependencies (defrost-ahead, parallel tasks).
4. **Ingredient lines:** `quantity ingredient — prep`, e.g. `500g potatoes — peel, thinly slice`. No quantity = no leading dash-segment, just the name.
5. **Untested changes in body:** mark inline with `(trial)` or `**(trial)**`, e.g. `**300g Boar's Head Irish cheddar — grate (trial)**`. Remove the marker once a trial passes and is kept; revert the line if it's dropped.
6. **Notes vs. Trial log:** Notes = distilled, timeless ("reduce sauce more than you think"). Trial log = dated, one entry per cook ("2026-11-09 — 400°F/20min, underside soft → retest 25min"). Don't mix them. Promote repeated trial findings into Notes.
7. **Units/temps:** keep the author's original units; give oven temps as `°F (°C)`.

## Experiment flow

User iterates on recipes (modify → cook → keep/drop). Follow this:

1. **Propose (before cooking):**
   - Put the change into the body marked `(trial)`.
   - Append/update a `### To try` or dated `Proposed` entry in Trial log describing the change.
   - Don't touch Notes or past log entries.
2. **Record (after cooking):**
   - Add/update the dated entry: `Change / Result / Decision`.
   - If `keep`: bake the change into Ingredients/Method, drop the `(trial)` marker, update meta line if needed, add/update a Notes bullet if there's a durable learning.
   - If `drop`: revert the body line to the previous version, note the fail in the log.
   - If `retest`: keep the `(trial)` marker, note what's next in the entry.
3. **Never rewrite history.** Append to the log; don't edit past entries' Result/Decision. Never delete the Source link.

## Adding a new recipe

- Copy `TEMPLATE.md` to `recipes/<kebab-case>.md` and fill it in. See `recipes/leek-potato-pie.md` for a filled example.
- Fill body with the version to cook next; mark anything untested `(trial)`.
- If imported from Keep/an article, add the Source link and a first Trial log entry noting what's untested.
- Filenames: lowercase, words with `-`, no dates in filename (dates live in the log).

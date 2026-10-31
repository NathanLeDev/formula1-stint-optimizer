# formula1-stint-optimizer — rules for Claude Code

Owner: Nathan (MSc student, works in French). Discussion in **French**, code, comments, notebook text in **English**.
Goal: predict lap time from tyre age, fuel and conditions, then simulate pit stops to find the lowest predicted race time.
Nathan wants to understand every step. He is not asking for code dumps.

## Read first (every session)
1. `docs/01-state-and-roadmap.md` — where we are, reference numbers.
2. `docs/02-decisions-log.md` — what was decided and why. Do not reopen a decision without saying so.
3. `docs/04-limits-and-open-questions.md` — what is NOT established.
`docs/03-concepts-and-maths.md` is read when a formula or a unit is involved.
If a doc and the code disagree, say so and ask. Do not pick one silently.

## Ask, do not assume
- If a definition, column, unit, threshold, source or intent is not in the docs or the code, **stop and ask**. One question at a time, with the options you see.
- Never invent a number, a constant, a source or a result. A value without a source is written as an assumption, with the word "assumed".
- Never fill a gap with a plausible guess to keep going. Saying "I don't know" or "I cannot check this" is the right output.
- If the request can be read two ways, ask which one.

## Before writing code
- Say in 3-5 lines what you will change and why, and wait for the answer, unless it is a small fix inside one cell.
- Change **one thing at a time**. No refactor, rename or restructure of `app/f1data.py` or of a notebook that was not asked for.
- The target `gap` is computed **once**, on the full table, by `f1data.add_target()`. Never recompute a reference on a subset.
- All cleaning lives in `f1data.py`. Notebooks import it; they do not rebuild their own table.

## After every new cell or feature (mandatory, in this order)
1. **Run it** and read the output. Check the numbers against what you expected before looking at the plot. Note anything surprising.
2. **Reread the whole notebook from the top.** Does the new cell fit the story the notebook tells? Do the text cells and the Findings still match the numbers (units, "per lap" vs cumulative, years, counts)? Does it contradict an earlier claim? Report any contradiction, do not smooth it over.
3. **Check what else it touches.** Grep for every use of any function or column you changed (`f1data.py`, `data-viz.ipynb`, `02-baseline.ipynb`, any other notebook). Re-run those notebooks from a fresh kernel, top to bottom, and compare with the reference numbers in `docs/01-state-and-roadmap.md`. If a reference number moves, stop and report it before going on.
4. **Run the tests** (`pytest tests/`). A new function in `f1data.py` comes with a test on a small synthetic frame. If tests do not exist yet for what you touched, say so and propose them.
5. **Report**, in French: what changed, what you checked, what you could not check, and what is assumed. Do not claim a check you did not run.

## Writing claims in notebooks and docs
- A claim must be no stronger than its evidence. Prefer "no better than", "shows no measurable gain" to "worse", "settles it", "proves", "the explanation".
- Stint cost is cumulative: `slope x n(n-1)/2`. `slope x n` is only the last-lap slowdown. Never use it as a stint cost.
- State units and the period (years, number of races) next to every number.
- A count of wins (e.g. 34/76) is weak evidence. Prefer an average difference with an interval.
- Hypotheses that have not been tested (the compound/race-phase confound) stay labelled as hypotheses.

## Do not
- Commit, push or rename files unless asked. A rename is its own commit.
- Commit tokens, `.env`, `app/data/`, `app/cache/` or raw data.
- Edit the docs silently. At the end of a step, propose the edit to `01` and `02` with the date and wait for approval.
- Install a new dependency without saying so.

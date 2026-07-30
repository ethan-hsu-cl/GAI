---
name: commit-message
description: Write a commit message for the current changes, in this repo's house style. Use when the user asks to "create/write the commit message", "draft a commit", or asks what to put in a commit for work that was just done. Produces the message text only — does not commit unless asked.
---

# Commit Message Writer

Draft a commit message for the pending changes, matching the conventions in
this repo's history. **Short by default.** Produce the message; do not run
`git commit` unless the user asks for it.

## Workflow

1. **Read the actual change** — never write from memory of the conversation:
   ```bash
   git status --short
   git diff --stat
   git diff                 # staged + unstaged; read it
   ```
   Untracked files (`??`) don't appear in `git diff` — open them and note that
   they'll need `git add`.

2. **Work out the *why*.** The diff shows what changed; the message exists to
   explain why, and what breaks if someone undoes it. If a change is
   non-obvious (a workaround, an ordering constraint, a rejected alternative),
   that's the part worth writing down.

3. **Write it** to the budget below.

4. **Save it** to the scratchpad so it can be used directly:
   ```bash
   git commit -F <scratchpad>/commit_msg.txt
   ```
   Print the message in the reply too.

5. **Report** anything the user must handle before committing: untracked files
   needing `git add`, and whether the current branch is the default one (see
   *Committing* below).

## Length budget

Measured across this repo's history: most commits have **no body at all**; the
well-written recent ones run ~20 body lines. Match that.

| Change | Body |
|---|---|
| Rename, tidy, dependency bump, doc typo | **Subject only** |
| Ordinary fix or small feature | **1–6 lines**, or a few bullets |
| Substantial change, several files, real reasoning | **~20 lines max** |
| Large multi-feature change (e.g. a whole build adaptation) | Sectioned body, still trim hard |

If the draft runs past ~25 lines, cut rather than reorganize. The usual
offenders, all of which should go:

- Restating what the diff already shows, file by file.
- Explaining *how* the code works — that belongs in the code or its docstring.
- Verification logs ("verified X, verified Y, all 2246 matched"). One line if
  the result is genuinely load-bearing; otherwise drop it.
- Usage examples and CLI flag lists — those belong in the README.
- Rationale for options you considered but didn't take.

## Style

- **Subject**: imperative mood, ≤72 chars, no trailing period. Say the effect,
  not the activity — "Fix SFT iOS post-generation flakiness", not "Update
  tests". Avoid the vague default ("Refactor code structure for improved
  readability"); if that's genuinely all it is, name what was refactored.
- **No `feat:`/`fix:`/`refactor:` prefix.** Most of the existing history has
  one, but that came from GitHub's autofilled suggestions, not a convention the
  repo chose — don't copy it. Say the effect in plain imperative English
  instead. Only add a prefix if the user asks for one.
- Blank line after the subject. Wrap the body at ~72 chars.
- Bullets with `-`. For a multi-part change, group under short plain-text
  section headers (no `##`), as in the 16.7.0 adaptation commit.
- **No `Co-Authored-By` trailer** — this repo doesn't use one. Only add it if
  the user asks.

## Committing

Only run `git commit` when the user explicitly asks. When they do:

- If on the default branch (`main`), create a branch first and say so, unless
  the user has said to commit to `main` directly.
- `git add` any untracked files that belong in the change — list them first.
- Never `git push` unless asked separately.

## Example

The same change, over-written and right-sized.

**Too long** (~75 lines) — narrates every file, lists CLI flags, logs all
verification:

```
Track when each iOS BFT/SFT case was added; report results by case age

Adds per-case creation-date tracking so run results can be sliced by how
old the test case is...

tools/case_registry.py (new)
Dates are derived from git history rather than annotated by hand — at
~2,900 test methods across 58 classes, per-method markers were never
viable. The tool walks every commit that touched...
- --sync   append-only manifest update. Incremental by default...
- --report joins the manifest against allure/results/*-result.json...
[...60 more lines: seeding stats, where the date surfaces, skills, verified...]
```

**Right** (~18 lines) — keeps the why, the non-obvious constraints, and the
one thing a future reader must not break:

```
Track when each iOS BFT/SFT case was added

Lets run results be sliced by case age ("did the newer scripts catch
newer bugs?"). Dates come from git history — at ~2,900 test methods,
per-method annotation was never viable — so no test file is touched.

- tools/case_registry.py: --sync (append-only), --report, --check.
- tests/case_registry.json: 3450 entries seeded from 35 commits. Commit
  this; regenerating from history alone re-dates anything later renamed.
- conftest.py: auto-sync at session start, Allure tag added:MM/YYYY per
  test, cohort summary in reports/case_age_summary.md.

The tag is a label, not an Allure parameter — parameters feed historyId
and would reset every test's trend history.

Dates on or before 2026-04-01 are approximate (bulk refactor commits).
```

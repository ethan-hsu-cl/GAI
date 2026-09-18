---
name: wan-i2v-from-deck
description: Convert a Wan 3.0 (Wan V3) image-to-video style deck — a Google Slides export or pasted text — into the tasks list of Scripts/config/batch_wan_v3_i2v_config.yaml, then populate each style's Source folder by copying a shared sample source set (Source 50 Sample by default). Use when the user provides a Wan 3.0 / Wan V3 I2V styles deck — as a Slides URL alone (fetched via the no-auth export/txt endpoint), a .txt export, or pasted text — and wants it turned into a Wan V3 I2V batch. For the same flow on the I2I2V group-shot deck use i2i2v-from-deck; for the generic per-field paste flow across other APIs use update-batch-prompts.
---

# wan-i2v-from-deck

Rebuild the `tasks:` list of `Scripts/config/batch_wan_v3_i2v_config.yaml` from a
Wan 3.0 style deck — one task per style — and then fill each style's `Source/`
folder from a shared sample source set so the batch is runnable immediately.

Two halves, both required:

1. **Config** — parse the deck, write the tasks, update the deck link.
2. **Sources** — copy the sample images into every new style folder.

A config written without step 2 is not done: `validate_structure` skips any task
whose `Source/` folder is empty ([wan_v3_i2v_handler.py:54-57](../../../Scripts/handlers/wan_v3_i2v_handler.py#L54-L57)),
so the batch would silently generate nothing.

**Always fully replace** the `tasks:` list with what the deck contains, unless
the user explicitly says to append. A deck carrying only a few styles means the
result is a full replace down to just those styles — do not merge the deck's
styles into the existing list.

## The platform constraint that shapes everything: no negative prompt

`/wan_v3` **does not accept a negative prompt.** `_predict_wan_v3` sends only
`prompt`, the frame/gallery inputs, and the six generation settings
([wan_v3_base.py:83-113](../../../Scripts/handlers/wan_v3_base.py#L83-L113)).
`negative_prompt` appears nowhere in the Wan handlers, in `wan_v3_i2v`'s
`task_fields` / `api_params` in `Scripts/core/api_definitions.json`, or in the
report's metadata fields.

Style decks are usually written for several platforms at once, so a slide often
carries a negative prompt meant for **Kling** (which does take one). For Wan:

- **Do not emit a `negative_prompt` field.** Not as a task field, not in
  `comments:`, not as a placeholder.
- **Do not splice it into the `prompt` text** — no trailing `Negative prompt:`
  line, no `--no` suffix. What the model receives must be exactly the deck's
  positive prompt.
- **Do flag it as a deck defect, not a footnote.** A negative prompt on a slide
  labeled for Wan 3.0 is content that **shouldn't be in a Wan deck at all** — it
  is almost always left over from a Kling version of the same style. Surface it
  at the **top** of the Step 8 report as a warning, not buried in the summary:
  say plainly that the deck carries negative prompts that don't belong, name
  every style that has one, and quote the dropped text so the user can decide
  whether the slide needs correcting upstream or whether that style was actually
  meant for a Kling run (via `update-batch-prompts`). Never let a run finish with
  the drop mentioned only in passing.

## Step 1 — Collect inputs

You need:

1. **The deck text** — fetched from the deck URL (see below), or a `.txt`
   export, an attached document, or pasted text.
2. **The deck link** — the Google Slides URL, for `design_link`. Reuse one the
   user pasted in an earlier turn; don't re-ask.
3. **The source set** — defaults to `Media Files/Sources/Source 50 Sample`
   (50 images). Only ask if the user named a different one or the default is
   missing. Other sets live alongside it under `Media Files/Sources/`
   (`Source 20 Sample`, `Source 25 Pet`, `Source 50`, …).

**Try the URL first — a link-shared deck exports without any credentials.**
Google Slides serves a plain-text export that needs no auth and no Drive
connector when the deck is shared by link (the normal case for these decks):

```bash
curl -sSL "https://docs.google.com/presentation/d/<DECK_ID>/export/txt" -o deck.txt
```

The `<DECK_ID>` is the path segment after `/presentation/d/`. A private deck
redirects to a login page instead — check that the response is
`text/plain` and that the body isn't HTML before trusting it. Only if that
fails do you need a `.txt` export or pasted text from the user; don't
give up on the URL untested, and don't guess at style content.

The export is **clean UTF-8**. Read it as UTF-8 (`open(p, encoding="utf-8")`);
do not inspect it with `cat -v`, which renders CJK as false mojibake and will
send you chasing an encoding problem that isn't there.

**Check the link against the other configs.** Several batch configs carry a
`*_design_link`. If the deck URL matches one already used by a different
platform's config (e.g. `batch_i2i2v_config.yaml`), say so in Step 8 — it
usually means one deck drives several platforms, but occasionally it means the
wrong link was pasted.

## Step 2 — Understand the deck anatomy

The `.txt` is a linear dump of the slides; text order within a slide is not
guaranteed, so parse by landmarks, not by absolute position. Each **style**
contributes some subset of:

- A **title** — English or Chinese, sometimes with a version suffix.
- A **per-task settings block**, usually right after the title and before
  `Prompt:`. Current decks write it as one setting per line, **with no space
  after the colon**:

  ```
  MODEL: Wan 3.0 — Image-to-Video (I2V)
  DURATION: 8 seconds
  Reolution:720p
  Ratio:1:1
  Audio:Yes
  ```

  Parse these tolerantly — key case varies, the space after `:` is optional, and
  **`Reolution` is misspelled in the live decks** (missing the `s`). Match both
  spellings with `Res?olution` — note that is `Res?`, not `Re?s`, which would
  match `Rsolution` and silently miss every real line. Don't assume the typo has
  been fixed, and don't "correct" the deck by ignoring the misspelled line.

  ```python
  PATTERNS = {
      'duration':   r"\s*DURATION\s*:\s*(\d+)",
      'resolution': r"\s*Res?olution\s*:\s*(\d+)\s*[Pp]",   # -> f"{n}P"
      'ratio':      r"\s*(?:Aspect\s*)?Ratio\s*:\s*(\S+)",
      'audio_out':  r"\s*Audio\s*:\s*(\w+)",                # Yes/No -> bool
  }
  ```

  **Assert every expected setting was found** before writing the config. A
  regex that silently matches nothing produces a task that quietly inherits
  `default_settings` instead of the deck's values — which looks like success.
- The **image/video prompt** — the English paragraph describing the motion,
  usually under a `Prompt:` label. Note the label sometimes sits *after* the
  prompt body in the linear text dump, so bound the prompt by the next title or
  settings block, not by the `Prompt:` marker alone.
- Optionally a **`Negative prompt:`** block — parse it so you can flag it, then
  discard it (see the constraint section above).
- Trailing junk to ignore: `User input` / `User Input：…` placeholder lines,
  `Key Point:…` notes, `Ref`, and the leading `GAI Template` slide.

A leading template/example slide showing one style's prompt as a format sample
is not a separate style; fold it into the style it illustrates.

## Step 3 — Field mapping (deck → wan_v3_i2v task)

Clone the **last existing task** in the file for exact quoting and indentation.
Values come from the deck as follows:

| Config field | Source in deck | Notes |
|---|---|---|
| `style_name` | title | `Underscore_Title_Case`, see Step 4 |
| `folder` | derived | `Media Files/Wan V3 I2V/<MMDD> <N> Styles/<style_name>` (Step 5) |
| `prompt` | the `Prompt:` paragraph | block scalar `\|` |
| `resolution` | `Reolution:` / `Resolution:` | upper-case the suffix: `720p` → `720P`. One of `480P`, `720P`, `1080P` |
| `ratio` | `Ratio:` / `Aspect Ratio:` | **must be quoted** — see Step 4. One of `16:9`, `9:16`, `1:1`, `4:3`, `3:4`, `adaptive` |
| `duration` | `DURATION: N seconds` | integer `N` |
| `audio_out` | `Audio:` | `Yes` → `true`, `No` → `false` |
| `duration_auto`, `thinking` | rarely in the deck | omit unless stated |

**Emit only the settings the deck actually states**; anything absent falls
through to `default_settings`, which the handler resolves as
per-task → `default_settings` → `api_params` → endpoint default
([wan_v3_base.py:42-67](../../../Scripts/handlers/wan_v3_base.py#L42-L67)).
Don't write a key just to restate the global default, and don't drop a deck
value because it happens to match one.

Field order per task, from the live template:
`style_name, folder, prompt, resolution, ratio, duration, audio_out` — settings
after the prompt, in that order, omitting any the deck didn't state. Tasks are
separated by a blank line.

Per `Scripts/config/CLAUDE.md`: **no inline `#` comments** inside tasks. Field
docs live only in the trailing `comments:` block, which you preserve untouched.

## Step 4 — Resolve the deck's ambiguities

- **Style names.** The live config's convention is short English
  `Underscore_Title_Case` (`Dog_Run_To_Owner`, `Capybara_Onsen_Closeup`), and
  `style_name` doubles as the folder leaf. If the deck's title is Chinese or a
  long English phrase, derive a concise English descriptor from the prompt's
  subject + action. **List every title → style_name mapping in Step 8** so the
  user can correct any of them.
- **Quote every numeric ratio — this is a silent data-corruption bug.** YAML 1.1
  reads an unquoted `1:1` as a *sexagesimal integer*: `yaml.safe_load("ratio: 1:1")`
  returns `61`, `16:9` returns `969`, `9:16` returns `556`. Write
  `ratio: "1:1"`, matching the repo's existing configs. Only `adaptive` is
  written bare. **Always round-trip the finished file through `yaml.safe_load`
  and assert each `ratio` is still a string** before reporting success.
- **`ratio` when the deck is silent** is `adaptive` — the sample source sets mix
  aspect ratios (filenames like `1_1-12-…`, `9_16-2-…`), so `adaptive` follows
  each source image. When the deck *does* pin a fixed ratio, honor it, but say
  so in Step 8: a fixed ratio crops or pads the mixed-ratio sample set, which is
  usually intended but worth confirming.
- **Durations are unconstrained in the repo.** `wan_v3_i2v` has
  `resolution_options` and `ratio_options` in `Scripts/core/api_definitions.json`
  but **no `duration_options`**, so a deck value like 7, 8 or 10 seconds can't be
  validated locally. Pass it through and flag in Step 8 that a single test
  generation should confirm the endpoint accepts a non-default duration.
- **Multiple prompt variants for one style.** Prefer the variant matching the
  deck's rendered sample. When two remain equally plausible, surface both
  briefly and ask which to use.
- **Mojibake (garbled CJK).** The `export/txt` endpoint returns clean UTF-8, so
  this only affects a `.txt` the user downloaded and re-saved, where Chinese can
  arrive mangled (UTF-8 misread as Latin-1: `ç¶å¸…`) while English survives.
  Wan prompts are normally English, so it usually only hits titles — recover the
  title before deriving the style name, and ask if a string can't be recovered
  confidently. Never ship mojibake into a prompt. Before assuming mojibake,
  confirm you didn't just view clean UTF-8 through `cat -v`.
- **Style count vs. expectation.** Count the distinct styles you actually
  found. If it differs from what the user expected, say so plainly and list
  what you extracted rather than inventing missing styles — the `.txt` export
  may have dropped slides.

## Step 5 — Build and write the tasks block

- **N** = final task count. **`<MMDD>`** = today's date (`currentDate`),
  zero-padded, unless the user specifies otherwise — writing the config starts a
  new batch. Every task's `folder` embeds the same group segment:
  `Media Files/Wan V3 I2V/<MMDD> <N> Styles/<style_name>`.
  Use `Styles` (plural) for N ≥ 2, `Style` for N = 1. Never `1 Styles`.

  That dated parent segment is not cosmetic — the report generator reads the
  **parent** folder name for `wan_v3_i2v` titles and grouping
  ([unified_report_generator.py:3237-3241](../../../Scripts/core/unified_report_generator.py#L3237-L3241)),
  so every task must share an identical group segment.

- Write the block **programmatically** to guarantee exact indentation — do not
  hand-assemble a giant `Edit`. Read the file, keep everything before the
  top-level `tasks:` line and everything from the top-level `comments:` line
  onward, and splice the generated tasks between them. Field lines are indented
  4 spaces; block-scalar bodies 6 spaces.

  ```python
  def emit(t):
      lines = [f"  - style_name: {t['style_name']}",
               f"    folder: {t['folder']}",
               "    prompt: |"]
      lines += [f"      {ln.rstrip()}" if ln.strip() else ""
                for ln in t['prompt'].strip().split("\n")]
      # only the settings the deck stated; quote ratio unless it is 'adaptive'
      if t.get('resolution'): lines.append(f"    resolution: {t['resolution']}")
      if t.get('ratio'):
          r = t['ratio']
          lines.append(f"    ratio: {r}" if r == "adaptive" else f'    ratio: "{r}"')
      if t.get('duration'):  lines.append(f"    duration: {t['duration']}")
      if t.get('audio_out') is not None:
          lines.append(f"    audio_out: {str(t['audio_out']).lower()}")
      return "\n".join(lines)
  # header = lines before 'tasks:'  |  footer = lines from 'comments:' onward
  # new = "tasks:\n" + "\n\n".join(emit(t) for t in tasks) + "\n\n"
  ```

## Step 6 — Update the top-level links

In `batch_wan_v3_i2v_config.yaml` these keys are **not** `root_`-prefixed:

- **`design_link`** ← the deck's Google Slides URL. The file's existing form is
  `design_link: ""`, so write it bare and unquoted: `design_link: <url>`.
- **`source_video_link`** ← leave empty (`source_video_link:`). The previous
  batch's link is stale once the tasks change; a new one is produced after the
  script runs.

Do not touch any other top-level key (`template_path`, `output`,
`generation_count`, `root_folder`, `testbed`, `schedule`, `default_settings`,
`comments`).

## Step 7 — Populate the Source folders

For each task, create `<folder>/Source/` and copy the image files from the
source set into it.

- **Copy, don't symlink** — the handler resolves and uploads real files, and
  `Media Files/` is gitignored so the copies create no git noise.
- **Copy image files only**, filtered to the api definition's `file_types`
  (`.jpg .jpeg .png .bmp .webp`); skip `.DS_Store` and any nested directories.
- **Idempotent** — skip a file that already exists at the destination, so
  re-running the skill on an existing batch is safe.
- Do **not** pre-create `Generated_Video/` or `Metadata/`; the handler makes
  them ([wan_v3_i2v_handler.py:73-76](../../../Scripts/handlers/wan_v3_i2v_handler.py#L73-L76)).

```python
import shutil
from pathlib import Path
EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
src = Path("Media Files/Sources/Source 50 Sample")
for t in tasks:
    dest = Path(t['folder']) / "Source"
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        if f.is_file() and f.suffix.lower() in EXT and not (dest / f.name).exists():
            shutil.copy2(f, dest / f.name)
```

Then **verify**: every task folder must hold the expected image count. Report
the per-folder count in Step 8, and call out any folder that came up short.

## Step 7.5 — Moderation pre-flight (before any large run)

The `/wan_v3` backend runs Alibaba's "green net" moderation on the **prompt text**
before generating. A rejected prompt fails every single source image identically:

```
Backend error: task failed: DataInspectionFailed -
Green net check failed for text (input): Input data may contain inappropriate content.
```

Nothing config-side fixes this — not resolution, ratio, duration, or a different
source set. Horror, gore and body-horror styles are the usual casualties.

**Probe each prompt once before launching**, using one source image at `480P` /
`duration 5` (moderation is text-only, so the cheap settings are representative).
A rejection fails fast (~12s, before generation); a pass costs a full generation
(~100s). Four prompts cost ~7 minutes and save a multi-hour run that produces
nothing.

```python
try:
    client.predict(prompt=t["prompt"], images=[], videos=[], audios=[],
        first_frame=handle_file(str(img)), last_frame=None, document=None, link="",
        resolution="480P", ratio=t["ratio"], duration=5, duration_auto=False,
        audio_out=t["audio_out"], thinking=False, api_name=api["api_name"])
    verdict = "PASS"
except Exception as e:
    verdict = "BLOCKED" if "DataInspection" in str(e) or "Green net" in str(e) else "ERROR"
```

Build the client the way the processor does — cookie from
`core.config_loader.get_testbed_cookie()` into `Client(endpoint, headers={"Cookie": ...})`
([unified_api_processor.py:469-484](../../../Scripts/core/unified_api_processor.py#L469-L484)).

**Report blocked prompts; never rewrite them to get past the filter.** These are
authored benchmark styles — softening one changes what the deck tests. Name the
blocked styles, quote the likely trigger clauses, and let the user or the deck
author revise the slide.

**Don't predict the verdict from the wording — measure it.** Observed Sept 2026:
a gore-heavy zombie prompt was blocked 3/3, and the deck's revision passed 3/3
while keeping *every* gore phrase verbatim (discoloration, veining, saliva
strands, scraped skin). The only edit was prepending `"An 8-second "`. Framing
the text as a shot description appears to matter more than individual terms, and
the filter was deterministic across repeats. So re-probe after any prompt edit,
however small, and never tell the user an edit won't work without testing it.

**Failure records don't block a retry.** `save_failure_metadata` writes
`<stem>_metadata.json` while the resume check looks for `<stem>_<gen>_metadata.json`
([wan_v3_i2v_handler.py:183-186](../../../Scripts/handlers/wan_v3_i2v_handler.py#L183-L186)),
so exhausted failures are always retried and `Metadata/` needs no clearing after
a blocked run.

## Step 8 — Confirm

Report:

- A clickable `file:line` link to the new tasks region, e.g.
  `[batch_wan_v3_i2v_config.yaml:28-90](Scripts/config/batch_wan_v3_i2v_config.yaml#L28-L90)`,
  and the task count.
- The **title → style_name mapping** for every style.
- **A warning, first and prominently, if any slide carried a negative prompt** —
  stating that the deck contains negative prompts that shouldn't be in a Wan
  deck, naming each affected style, quoting the dropped text, and noting that
  `/wan_v3` accepts none so it was discarded. If no slide carried one, say so
  explicitly ("no negative prompts in the deck") rather than staying silent, so
  the user knows the check ran.
- The **per-task settings taken from the deck** (resolution / ratio / duration /
  audio) and which were left to `default_settings`.
- The **source copy result**: which set, how many images, into how many folders.
- Every other ambiguity you resolved (prompt variants chosen, ratios inferred,
  CJK recovered, deck-link collisions with another config), so the user can
  correct anything you guessed.
- The run command: `python runall.py wan_v3_i2v auto`.

## What NOT to change

- Don't touch `comments`, `template_path`, `output`, `testbed`, `schedule`,
  `generation_count`, `root_folder`, `default_settings`, or any top-level key
  outside `tasks:`, `design_link`, and `source_video_link`.
- Don't reorder or rename task fields; clone the existing shape exactly.
- Don't add a `negative_prompt` field, and don't fold negative-prompt text into
  the prompt.
- Don't change the `Media Files/Wan V3 I2V` path prefix — only the
  `<MMDD> <N> Style(s)` segment and the per-style leaf.

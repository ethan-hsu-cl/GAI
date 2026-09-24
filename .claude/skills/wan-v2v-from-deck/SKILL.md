---
name: wan-v2v-from-deck
description: Convert the V2V slides of a Wan 3.0 (Wan V3) style deck — a Google Slides export or pasted text — into the tasks list of Scripts/config/batch_wan_v3_v2v_config.yaml, then check that each style's Source folder holds source videos. Use when the user provides a Wan 3.0 / Wan V3 deck containing "Video-to-Video (V2V)" slides — as a Slides URL alone (fetched via the no-auth export/txt endpoint), a .txt export, or pasted text — and wants it turned into a Wan V3 V2V batch. For the I2V slides of the same deck use wan-i2v-from-deck; for the I2I→I2V slides use i2i2v-from-deck; for the generic per-field paste flow across other APIs use update-batch-prompts.
---

# wan-v2v-from-deck

Rebuild the `tasks:` list of `Scripts/config/batch_wan_v3_v2v_config.yaml` from
the **V2V slides** of a Wan 3.0 deck — one task per style — and confirm each
style's `Source/` folder holds the videos the batch will run on.

Two halves, both required:

1. **Config** — parse the deck's V2V slides, write the tasks, update the deck link.
2. **Sources** — make sure every new style folder has source videos in it.

A config written without step 2 is not done: `validate_structure` skips any task
whose `Source/` folder holds no video
([wan_v3_v2v_handler.py:55-58](../../../Scripts/handlers/wan_v3_v2v_handler.py#L55-L58)),
and with every task skipped the run raises `No valid Wan V3 V2V tasks found`
rather than generating anything.

**Always fully replace** the `tasks:` list with the deck's V2V styles, unless the
user explicitly says to append. A deck carrying two V2V slides means the result
is a full replace down to those two — do not merge them into the existing list.

## This skill owns only the V2V slides

One deck routinely carries slides for several Wan modes at once, each labeled by
its `MODEL:` line. Take only the V2V ones and leave the rest to their own skill:

| Slide's `MODEL:` line | Config | Skill |
|---|---|---|
| `Wan3.0 — Video-to-Video (V2V)` | `batch_wan_v3_v2v_config.yaml` | **this one** |
| `Wan 3.0 — Image-to-Video (I2V)` | `batch_wan_v3_i2v_config.yaml` | [wan-i2v-from-deck](../wan-i2v-from-deck/SKILL.md) |
| an `I2I` slide paired with an `I2V` slide under one `I2I→I2V` title | `batch_i2i2v_config.yaml` | [i2i2v-from-deck](../i2i2v-from-deck/SKILL.md) |

Route by the `MODEL:` line, not by the title. A title starting `I2I→I2V` marks a
**pair** of slides that belong to the i2i2v pipeline — its I2V half is the second
step of that pipeline, not a standalone style, so do not pull it in here.

**Say what you skipped.** In Step 8, list the non-V2V slides you left alone and
name the skill that handles each, so the user knows the rest of the deck still
needs a run and doesn't assume this one covered the whole file.

## The platform constraint that shapes everything: no negative prompt

`/wan_v3` **does not accept a negative prompt.** `_predict_wan_v3` sends only
`prompt`, the frame/gallery inputs, and the six generation settings
([wan_v3_base.py:102-133](../../../Scripts/handlers/wan_v3_base.py#L102-L133)).
`negative_prompt` appears nowhere in the Wan handlers, in `wan_v3_v2v`'s
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
  meant for a Kling run. Never let a run finish with the drop mentioned only in
  passing.

## Step 1 — Collect inputs

You need:

1. **The deck text** — fetched from the deck URL (see below), or a `.txt`
   export, an attached document, or pasted text.
2. **The deck link** — the Google Slides URL, for `root_design_link`. Reuse one the
   user pasted in an earlier turn; don't re-ask.
3. **The source videos** — see Step 7. Unlike the image flows there is **no
   shared sample video set in the repo**, so this is something the user supplies.

**Try the URL first — a link-shared deck exports without any credentials.**
Google Slides serves a plain-text export that needs no auth and no Drive
connector when the deck is shared by link (the normal case for these decks):

```bash
curl -sSL "https://docs.google.com/presentation/d/<DECK_ID>/export/txt" -o deck.txt
```

The `<DECK_ID>` is the path segment after `/presentation/d/`. A private deck
redirects to a login page instead — check that the response is `text/plain` and
that the body isn't HTML before trusting it. Only if that fails do you need a
`.txt` export or pasted text from the user; don't give up on the URL untested,
and don't guess at style content.

The export is **clean UTF-8**. Read it as UTF-8 (`open(p, encoding="utf-8")`);
do not inspect it with `cat -v`, which renders CJK as false mojibake and will
send you chasing an encoding problem that isn't there.

**Check the link against the other configs.** Several batch configs carry a
`*_design_link`. If the deck URL matches one already used by a different
platform's config, that is normal for a multi-mode deck like this one — say so
in Step 8 rather than treating it as an error.

## Step 2 — Understand the deck anatomy

The `.txt` is a linear dump of the slides; text order within a slide is not
guaranteed, so parse by landmarks, not by absolute position.

**The export repeats slides.** Each slide commonly appears 2–4 times in a row
(revision copies that render identically). Deduplicate on
`(title, first ~200 chars of prompt)` before counting styles, or you will emit
four copies of one task. Report the deduplicated count.

Each **style** contributes some subset of:

- A **title** — English or Chinese, prefixed with its mode, sometimes with a
  version suffix (`V2V 靈騷 V3`, `V2V 變身南瓜頭`).
- A **per-task settings block**, usually right after the title and before
  `Prompt:`. Current decks write it as one setting per line, **with no space
  after the colon**:

  ```
  MODEL: Wan3.0 — Video-to-Video (V2V)
  DURATION: 10 seconds
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
      'model':      r"^\s*MODEL\s*:\s*(.+)$",                # route V2V vs I2V
      'duration':   r"^\s*DURATION\s*:\s*(\d+)",
      'resolution': r"^\s*Res?olution\s*:\s*(\d+)\s*[Pp]",   # -> f"{n}P"
      'ratio':      r"^\s*(?:Aspect\s*)?Ratio\s*:\s*(\S+)",
      'audio_out':  r"^\s*Audio\s*:\s*(\w+)",                # Yes/No -> bool
  }
  ```

  **Assert every expected setting was found** before writing the config. A
  regex that silently matches nothing produces a task that quietly inherits
  `default_settings` instead of the deck's values — which looks like success.
- The **video prompt** — the English body describing what changes relative to
  the source video, usually under a `Prompt:` label. The label sometimes sits
  *after* the prompt body in the linear dump, so bound the prompt by the next
  title or settings block, not by the `Prompt:` marker alone.
- Optionally a **`Negative prompt:`** block — parse it so you can flag it, then
  discard it (see the constraint section above).
- Trailing junk to ignore: `User input` / `User Input：…` placeholder lines,
  `Key Point:…` notes, `Ref`, and the leading `GAI Template` slide.

A leading template/example slide showing one style's prompt as a format sample
is not a separate style; fold it into the style it illustrates.

## Step 3 — Field mapping (deck → wan_v3_v2v task)

Clone the **last existing task** in the file for exact quoting and indentation.
Values come from the deck as follows:

| Config field | Source in deck | Notes |
|---|---|---|
| `style_name` | title | `Underscore_Title_Case`, see Step 4 |
| `folder` | derived | `Media Files/Wan V3 V2V/<MMDD> <N> Styles/<style_name>` (Step 5) |
| `prompt` | the `Prompt:` body | block scalar `\|` |
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

- **Style names.** The convention is short English `Underscore_Title_Case`
  (`Poltergeist_Haunting`, `Pumpkin_Head_Transform`), and `style_name` doubles as
  the folder leaf. Deck titles here are usually Chinese — derive a concise
  English descriptor from the prompt's subject + action. **List every
  title → style_name mapping in Step 8** so the user can correct any of them.
- **Quote every numeric ratio — this is a silent data-corruption bug.** YAML 1.1
  reads an unquoted `1:1` as a *sexagesimal integer*: `yaml.safe_load("ratio: 1:1")`
  returns `61`, `16:9` returns `969`, `9:16` returns `556`. Write
  `ratio: "1:1"`, matching the repo's existing configs. Only `adaptive` is
  written bare. **Always round-trip the finished file through `yaml.safe_load`
  and assert each `ratio` is still a string** before reporting success.
- **`ratio` when the deck is silent** is `adaptive`, which follows the source
  video. When the deck *does* pin a fixed ratio, honor it, but say so in Step 8:
  a fixed ratio crops or pads source videos shot at other aspect ratios, which is
  usually intended but worth confirming against the footage the user supplied.
- **Durations are unconstrained in the repo.** `wan_v3_v2v` has
  `resolution_options` and `ratio_options` in `Scripts/core/api_definitions.json`
  but **no `duration_options`**, so a deck value like 5 or 10 seconds can't be
  validated locally. Pass it through and flag in Step 8 that a single test
  generation should confirm the endpoint accepts it. Note the deck's `DURATION`
  is the **output** length and is independent of how long the source video
  is — a 5 s target against 30 s of footage is not an error, but is worth naming.
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
- **Style count vs. expectation.** Count the distinct V2V styles you actually
  found, after deduplicating the repeated export blocks. If it differs from what
  the user expected, say so plainly and list what you extracted rather than
  inventing missing styles — the `.txt` export may have dropped slides.

## Step 5 — Build and write the tasks block

- **N** = final task count. **`<MMDD>`** = today's date (`currentDate`),
  zero-padded, unless the user specifies otherwise — writing the config starts a
  new batch. Every task's `folder` embeds the same group segment:
  `Media Files/Wan V3 V2V/<MMDD> <N> Styles/<style_name>`.
  Use `Styles` (plural) for N ≥ 2, `Style` for N = 1. Never `1 Styles`.

  That dated parent segment is not cosmetic — the report generator reads the
  **parent** folder name for `wan_v3_v2v` titles and grouping
  ([unified_report_generator.py:3267-3269](../../../Scripts/core/unified_report_generator.py#L3267-L3269)),
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

These keys **are** `root_`-prefixed — the report generator only reads the
`root_` form for folder-based APIs like this one, so a bare `design_link:` or
`source_video_link:` is silently ignored and the title slide loses the link:

- **`root_design_link`** ← the deck's Google Slides URL, written bare and
  unquoted: `root_design_link: <url>`.
- **`root_source_video_link`** ← clear it, leaving a **single space after the
  colon** (`root_source_video_link: `), not `''` and not a bare colon with no
  space. Most editors and the `Edit` tool strip trailing whitespace, so write it
  from a small script. The previous batch's link is stale once the tasks change; a new one is produced
  after the script runs.

Do not touch any other top-level key (`template_path`, `output`,
`generation_count`, `root_folder`, `testbed`, `schedule`, `default_settings`,
`comments`).

## Step 7 — Populate the Source folders with videos

Create `<folder>/Source/` for each task, then get source videos into it.

**There is no shared sample video set in this repo.** The image flows copy from
`Media Files/Sources/Source NN Sample`, but those folders hold only stills and
nothing under `Media Files/` holds a reusable pool of input videos. So:

- **Create the empty `Source/` folders** and check each one.
- **If a folder has no video, say so and ask the user for the footage** — name
  the exact paths to drop files into. Do not invent a source set, do not reuse
  generated output from another platform's `Generated_Video/` as input without
  the user saying to, and do not report the batch as ready to run.
- If the user names a folder of videos, copy them in (**copy, don't symlink** —
  the handler resolves and uploads real files, and `Media Files/` is gitignored
  so the copies create no git noise). Skip a file that already exists at the
  destination, so re-running the skill on an existing batch is safe.
- Do **not** pre-create `Generated_Video/` or `Metadata/`; the handler makes
  them ([wan_v3_v2v_handler.py:74-77](../../../Scripts/handlers/wan_v3_v2v_handler.py#L74-L77)).

Source videos must clear `wan_v3_v2v`'s validation in
`Scripts/core/api_definitions.json` or the handler drops them from the run:

| Rule | Value |
|---|---|
| Container | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| Duration | **1–15 s** |
| Shorter side | ≥ 320 px |
| File size | ≤ 500 MB |

### The 15-second input cap is the constraint that bites

The backend rejects a longer source with
`InvalidParameter - <url> duration should be at most 15s, got 32.93s` — and only
**after the whole file has uploaded**, so an over-long video costs a full upload
to learn nothing. The handler therefore checks duration locally and skips
over-long sources before calling
([wan_v3_v2v_handler.py:261-278](../../../Scripts/handlers/wan_v3_v2v_handler.py#L261-L278)).

- **The cap is inclusive, and exactly 15.000 s works.** Verified against the
  live endpoint (Sept 2026): a source re-encoded to exactly `15.000000` s was
  accepted and generated normally. There is no need to leave safety headroom, so
  trim to 15 s rather than 14.5 s and keep the extra footage.
- **This cap is on the input.** The deck's `DURATION` is the *output* length and
  is independent of it: a 10 s target from a 12 s source is fine; a 10 s target
  from a 33 s source fails.
- **Raw phone/stock footage routinely blows it.** Check every source folder
  before reporting the batch ready, and list each file's duration:

  ```bash
  for f in "<folder>/Source"/*.mp4; do
    printf "%-22s %ss\n" "$(basename "$f")" \
      "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")"
  done
  ```

- **Don't trim on your own initiative.** Which 15 s window to keep is a content
  decision — the interesting action may not be at the head, and these prompts
  describe timed beats. Report which files are over the cap and by how much,
  then ask.
- **When the user does say to trim, re-encode — don't stream-copy.**
  `-c copy` cuts at the nearest keyframe and routinely overshoots 15 s, which
  puts you straight back into the backend rejection. Re-encode for an exact cut:

  ```bash
  ffmpeg -v error -y -i orig.mp4 -t 15 \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
    -c:a aac -b:a 128k -movflags +faststart trimmed.mp4
  ```

  CRF 18 is visually near-lossless, fine for benchmark sources. A 29.97 fps clip
  lands at 14.91 s rather than 15.00 s because the last whole frame falls just
  short — that is correct, not an error.

  **Move the originals aside rather than overwriting them** — `<style>/Source_Original/`
  is a good home: the handler and the report generator only read `Source/`,
  `Generated_Video/` and `Metadata/`, so an extra sibling directory is inert.
  Always re-probe after trimming and report the before → after durations.

One call is made **per source video**, so a style with 20 valid videos and
`generation_count: 1` is 20 generations. Report the per-folder count in Step 8
as **valid / total**, naming the files that will be skipped.

## Step 7.5 — Moderation pre-flight (before any large run)

The `/wan_v3` backend runs Alibaba's "green net" moderation on the **prompt text**
before generating. A rejected prompt fails every single source video identically:

```
Backend error: task failed: DataInspectionFailed -
Green net check failed for text (input): Input data may contain inappropriate content.
```

Nothing config-side fixes this — not resolution, ratio, duration, or different
footage. Horror, gore and body-horror styles are the usual casualties, and V2V
decks skew that way.

**Probe each prompt once before launching**, using one source video at `480P` /
`duration 5` (moderation is text-only, so the cheap settings are representative).
A rejection fails fast (~12s, before generation); a pass costs a full generation.

```python
from gradio_client import handle_file
try:
    client.predict(prompt=t["prompt"], images=[],
        videos=[{"video": handle_file(str(vid)), "caption": None}],
        audios=[], first_frame=None, last_frame=None, document=None, link="",
        resolution="480P", ratio=t["ratio"], duration=5, duration_auto=False,
        audio_out=t["audio_out"], thinking=False, api_name=api["api_name"])
    verdict = "PASS"
except Exception as e:
    verdict = "BLOCKED" if "DataInspection" in str(e) or "Green net" in str(e) else "ERROR"
```

Build the client the way the processor does — cookie from
`core.config_loader.get_testbed_cookie()` into `Client(endpoint, headers={"Cookie": ...})`
([unified_api_processor.py:469-486](../../../Scripts/core/unified_api_processor.py#L469-L486)).

**Report blocked prompts; never rewrite them to get past the filter.** These are
authored benchmark styles — softening one changes what the deck tests. Name the
blocked styles, quote the likely trigger clauses, and let the user or the deck
author revise the slide.

**Don't predict the verdict from the wording — measure it.** Observed on the I2V
side (Sept 2026): a gore-heavy prompt was blocked 3/3, and the deck's revision
passed 3/3 while keeping *every* gore phrase verbatim; the only edit was
prepending `"An 8-second "`. Framing the text as a shot description appears to
matter more than individual terms, and the filter was deterministic across
repeats. So re-probe after any prompt edit, however small, and never tell the
user an edit won't work without testing it.

**Failure records DO block a retry — clear them before re-running.** A failed
generation writes `<stem>_<gen>_metadata.json` (`save_failure_metadata` names it
via the handler's `failure_base_name()`, which this handler overrides to append
the generation number — [unified_api_processor.py:648-657](../../../Scripts/core/unified_api_processor.py#L648-L657)),
which is exactly what the resume check reads back. With `max_retries: 1` a
single failure is immediately `attempts >= max_retries`, so the source is
reported as `failed - max retries reached` and **skipped on every later run**.
After fixing whatever caused a batch to fail — a blocked prompt, an over-long
source, a bad cookie — delete the affected `Metadata/*_metadata.json` records,
or the re-run will quietly skip the very files you fixed.

## Step 8 — Confirm

Report:

- A clickable `file:line` link to the new tasks region, e.g.
  `[batch_wan_v3_v2v_config.yaml:32-80](Scripts/config/batch_wan_v3_v2v_config.yaml#L32-L80)`,
  and the task count.
- The **title → style_name mapping** for every style.
- **A warning, first and prominently, if any slide carried a negative prompt** —
  stating that the deck contains negative prompts that shouldn't be in a Wan
  deck, naming each affected style, quoting the dropped text, and noting that
  `/wan_v3` accepts none so it was discarded. If no slide carried one, say so
  explicitly ("no negative prompts in the deck") rather than staying silent, so
  the user knows the check ran.
- **The non-V2V slides you skipped**, and which skill handles each.
- The **per-task settings taken from the deck** (resolution / ratio / duration /
  audio) and which were left to `default_settings`.
- The **source video status per folder** as **valid / total**, naming every
  file over the 15 s cap with its duration, or plainly that a folder is empty
  and the batch will skip it until footage is added. Never report a batch as
  ready to run on a count that includes sources the handler will skip.
- Every other ambiguity you resolved (prompt variants chosen, ratios inferred,
  CJK recovered, how many duplicate export blocks you collapsed), so the user
  can correct anything you guessed.
- The run command: `python runall.py wan_v3_v2v auto`.

## What NOT to change

- Don't touch `comments`, `template_path`, `output`, `testbed`, `schedule`,
  `generation_count`, `root_folder`, `default_settings`, or any top-level key
  outside `tasks:`, `root_design_link`, and `root_source_video_link`.
- Don't reorder or rename task fields; clone the existing shape exactly.
- Don't add a `negative_prompt` field, and don't fold negative-prompt text into
  the prompt.
- Don't pull in I2V or I2I→I2V slides; they belong to the sibling skills.
- Don't change the `Media Files/Wan V3 V2V` path prefix — only the
  `<MMDD> <N> Style(s)` segment and the per-style leaf.

---
name: i2i2v-from-deck
description: Convert the image-to-image-to-video slides of a "GAI Template" Google Slides deck into the tasks list of Scripts/config/batch_i2i2v_config.yaml — both the group-shot style (one slide per style, Gemini + Kling) and the paired style (an I2I slide plus an I2V slide under one "I2I→I2V" title, OpenAI/ChatGPT image + Wan 3.0). Use when the user provides such a deck as a URL (fetched via the no-auth export/txt endpoint), a .txt export, or pasted text — with image prompts, video prompts, optional negative prompts, and model/resolution/aspect metadata — and wants it turned into i2i2v batch tasks. Also updates root_design_link to the deck URL and clears root_source_video_link. For the standalone I2V slides of the same deck use wan-i2v-from-deck; for its V2V slides use wan-v2v-from-deck; for the generic per-field paste flow across other APIs use update-batch-prompts.
---

# i2i2v-from-deck

Parse a whole **GAI Template** deck export (the `.txt` you get from a group-shot
Google Slides deck) and rebuild the `tasks:` list of
`Scripts/config/batch_i2i2v_config.yaml` from it — one task per style. Unlike
[update-batch-prompts](../update-batch-prompts/SKILL.md), which asks the user to
paste one field at a time, this skill ingests the entire deck text at once,
splits it into styles, and maps each style's blocks onto the i2i2v task shape.

## This skill owns only the I2I2V slides

A deck routinely carries slides for several pipelines at once. Take only the
image→image→video ones and leave the rest to their own skill:

| Slides | Config | Skill |
|---|---|---|
| one style slide carrying both an image prompt and a video prompt, **or** an `I2I` slide paired with an `I2V` slide under one `I2I→I2V` title | `batch_i2i2v_config.yaml` | **this one** |
| a standalone `Wan 3.0 — Image-to-Video (I2V)` slide | `batch_wan_v3_i2v_config.yaml` | [wan-i2v-from-deck](../wan-i2v-from-deck/SKILL.md) |
| `Wan3.0 — Video-to-Video (V2V)` | `batch_wan_v3_v2v_config.yaml` | [wan-v2v-from-deck](../wan-v2v-from-deck/SKILL.md) |

The distinction that matters: an I2V slide titled `I2I→I2V …` is the **second
step of this pipeline**, and its prompt becomes this task's `video_prompt` — it
is not a standalone I2V style. A plain `I2V …` slide with no I2I partner is.
List the slides you skipped in Step 7, and name the skill that handles each.

**Always fully replace** the `tasks:` list with what the deck contains, unless the
user explicitly says otherwise. This holds even when the deck carries only a few
styles that match existing tasks (e.g. `Fix` iterations of styles already in the
file): the result is a full replace down to just those styles — do **not** silently
merge the deck's styles into the existing list or keep the untouched ones. Update
in place / append only on explicit instruction.

## Step 1 — Collect inputs

You need two things:

1. **The deck link** — the Google Slides URL. Goes into `root_design_link`. If the
   user pasted it in an earlier turn (e.g. when they first asked to update the
   config), reuse that; don't re-ask.
2. **The deck text** — normally fetched from that link (below). Falls back to a
   `.txt` file path, an attached document, or pasted text. The `.pptx` itself is
   usually too large to attach.

**Fetch from the URL first — a link-shared deck exports without any credentials.**
Google Slides serves a plain-text export that needs no auth and no Drive
connector when the deck is shared by link (the normal case for these decks):

```bash
curl -sSL "https://docs.google.com/presentation/d/<DECK_ID>/export/txt" -o deck.txt
```

`<DECK_ID>` is the path segment after `/presentation/d/`. A private deck redirects
to a login page instead — check the response is `text/plain` and the body isn't
HTML before trusting it. Only if that fails do you need a `.txt` export or pasted
text from the user. **Do not tell the user the deck is unreachable without
testing that URL** — the Drive connector being unauthorized says nothing about
whether the deck is link-shared.

The export is **clean UTF-8**. Read it as UTF-8 (`open(p, encoding="utf-8")`); do
not inspect it with `cat -v`, which renders CJK as false mojibake and will send
you chasing an encoding problem that isn't there.

## Step 2 — Understand the deck anatomy

The `.txt` is a linear dump of the slides; text order within a slide is not
guaranteed, so parse by landmarks, not by absolute position. Each **style** contributes
this cluster of fragments (in roughly, but not reliably, this order):

- A **Chinese descriptive title** → becomes `style_name` (often carries a ` V3` suffix,
  e.g. `羅馬建築前 V3`, `棒球風網美照 V3`).
- A **QA/PM metadata block**: `Gemini 3` or `Gemini 3.1`, `Input N photo`,
  `Resolution: 1K|2K`, `Aspect Ratio: 3:4|4:3`.
- A **`Style_NNNN_Name_Gemini`** internal identifier (e.g. `Style_5003_Group-Lalaland_Gemini`).
- One or more **image-prompt** paragraphs (English).
- A **video section**: thumbnail markers like `01 02 03`, then `Prompt:` + the video
  prompt, then `Image to Video / Kling v3.0 / Duration: 5s`.
- Optionally a **`Negative prompt:`** / `negative prompt:` block.

A leading `GAI Template` slide may show one style's prompt as the format example —
it is not a separate style; fold it into the style it illustrates.

### The paired-slide shape

Newer decks split one style across **two consecutive slides** sharing a title
stem, each with its own `MODEL:` settings block:

```
I2I→I2V  爬出電視 I2I V2          I2I→I2V  爬出電視 I2V  V2
<the image prompt>                <the video prompt>
Prompt:                           Prompt:
MODEL: ChatGPT image2.5 …(I2I)    MODEL: Wan 3.0 — Image-to-Video (I2V)
DURATION: -                       DURATION: 10 seconds
Reolution:1k                      Reolution:720p
Ratio:1:1                         Ratio:1:1
Audio:-                           Audio:Yes
```

Pair them into **one task**: the I2I slide supplies `image_prompt` and the image
settings, the I2V slide supplies `video_prompt` and the video settings. Match on
the title stem with the trailing ` I2I`/` I2V` marker removed, and note the
markers can carry stray double spaces (`爬出電視 I2V  V2`) — normalize
whitespace before comparing, or the halves won't match.

**Both halves are required.** If a title stem has only one half, stop and say
which half is missing rather than emitting a task with an empty prompt.

**The export repeats slides.** Each slide commonly appears 2–4 times in a row
(revision copies that render identically). Deduplicate on
`(title, first ~200 chars of prompt)` before pairing, or one style becomes four
tasks. Report the deduplicated count.

These decks use the same misspelled `Reolution` key as the Wan decks; match both
spellings with `Res?olution` — that is `Res?`, not `Re?s`, which would match
`Rsolution` and silently miss every real line.

## Step 3 — Field mapping (deck → i2i2v task)

Clone the **last existing task** in the file for exact quoting/indentation, but the
field values come from the deck as follows:

| Config field | Source in deck | Notes |
|---|---|---|
| `style_name` | Chinese title | single-quote it; keep the ` V3` suffix; clean mojibake (Step 4) |
| `folder` | derived | `'Media Files/I2I2V/<MMDD> <N> Styles/<MMDD> <style_name>'` (Step 5) |
**Shared by both deck shapes:**

| Config field | Source in deck | Notes |
|---|---|---|
| `style_name` | title | group-shot: the Chinese title, single-quoted, keep the ` V3` suffix. Paired: the title stem minus the ` I2I`/` I2V` marker — derive a short English `Underscore_Title_Case` name when the stem is Chinese, and list the mapping in Step 7 |
| `folder` | derived | `'Media Files/I2I2V/<MMDD> <N> Styles/<MMDD> <style_name>'` (Step 5) |
| `image_resolution` | `Resolution:` / `Reolution:` | `'1K'` or `'2K'`; a deck's lowercase `1k` becomes `'1K'` |
| `image_aspect_ratio` | `Aspect Ratio:` / `Ratio:` | the metadata value wins over any aspect mentioned inside the prompt text |
| `image_prompt` | the finalized image prompt | block scalar `|` (Step 4 picks the variant) |
| `video_prompt` | the video slide's / video section's prompt | block scalar `|` |
| `video_duration` | `DURATION: N seconds` or `Duration: 5s` | integer `N` |
| `concurrent_requests` | — | default `3` |

**Image step — pick the service from the slide's `MODEL:` line:**

| Deck says | `image_service` | `image_model` |
|---|---|---|
| `Gemini 3` | `nano_banana` | `gemini-3-pro-image` (note: **no** `-preview` suffix) |
| `Gemini 3.1` | `nano_banana` | `gemini-3.1-flash-image` |
| `ChatGPT image …` / `gpt-image …` | `openai_image` | the matching `gpt-image-*` id — see below |

`openai_image` currently offers `gpt-image-1`, `gpt-image-1-mini`,
`gpt-image-1.5`, `gpt-image-2`, `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst`.
Decks write these loosely (`ChatGPT image2.5`), and **`2.5` is ambiguous — it
maps to two real models, `-flare` and `-sunburst`.** Ask which one rather than
guessing; the choice changes what is being benchmarked. `image_quality` is
`openai_image`-only (`auto` | `low` | `medium` | `high`) and is ignored for
`nano_banana`.

Group-shot decks also set `use_multi_image: true` with
`multi_image_config: { mode: sequential }`; paired decks normally don't — omit
both unless the deck asks for multi-image pairing.

**Video step — pick the service from the video slide's `MODEL:` line.** The two
take different fields and a field belonging to the other service is silently
ignored, so this choice drives the rest of the task:

| Deck says | `video_service` | Service-specific fields |
|---|---|---|
| `Kling v3.0` (or any Kling version) | `kling` (the default — may be omitted) | `video_model` (`v3`), `video_mode` (`pro`), `video_sound_enabled` (default `true`), `video_negative_prompt` |
| `Wan 3.0 — Image-to-Video (I2V)` | `wan_v3` | `video_resolution` (`720p` → `'720P'`), `video_ratio` (quote it), `video_audio_out` (`Audio:Yes` → `true`), optionally `video_duration_auto` / `video_thinking` |

**`wan_v3` accepts no negative prompt.** Do not emit `video_negative_prompt` on
a `wan_v3` task and do not fold the text into `video_prompt`. If the slide
carries one, flag it prominently in Step 7 the way
[wan-i2v-from-deck](../wan-i2v-from-deck/SKILL.md) does — name the style and
quote the dropped text — rather than mentioning it in passing. The handler logs
a warning and drops it at run time
([i2i2v_handler.py:944-950](../../../Scripts/handlers/i2i2v_handler.py#L944-L950)),
but the config shouldn't carry it in the first place.

**Quote every numeric ratio.** YAML 1.1 reads an unquoted `1:1` as a
*sexagesimal integer* — `yaml.safe_load("video_ratio: 1:1")` returns `61`,
`16:9` returns `969`. Write `video_ratio: '1:1'`, and round-trip the finished
file through `yaml.safe_load` asserting each ratio is still a string before
reporting success.

Field order per task, from the live template — image fields, blank line, video
fields, blank line, `concurrent_requests`:

```
style_name, folder, image_service, image_model, image_quality, image_resolution,
image_aspect_ratio, [use_multi_image, multi_image_config,] image_prompt,
(blank), video_service, [kling: video_model, video_mode, video_duration,
video_ratio, video_sound_enabled | wan_v3: video_resolution, video_ratio,
video_duration, video_audio_out], video_prompt, [kling only:
video_negative_prompt], (blank), concurrent_requests
```

## Step 4 — Resolve the deck's ambiguities

These recur in every deck; handle each, and **ask the user only when a choice
materially changes output and you can't infer it**:

- **Multiple image-prompt variants for one style.** Decks often keep a draft plus a
  finalized prompt (they differ in details like on-image title text). Prefer the
  variant tied to the `Style_NNNN` identifier / matching the deck's rendered sample.
  When two remain equally plausible, surface both briefly and ask which to use.
- **Human/Pet (or other paired) video variants.** When a style provides two video
  prompts labeled `(Human)` and `(Pet)`, emit **two tasks** sharing the same image
  prompt, with `style_name` suffixed ` (Human)` / ` (Pet)`. This raises the task
  count `N`.
- **Mojibake (garbled CJK).** The `export/txt` endpoint returns clean UTF-8, so this
  only affects a `.txt` the user downloaded and re-saved, where Chinese / Japanese
  can arrive mangled (UTF-8 misread as Latin-1: `ç¶å¸…`, `ãã£ã¡`) while English
  survives. Reconstruct the `style_name` and any **on-image text the prompt tells the
  model to render** (e.g. purikura sticker phrases) into clean CJK. Never ship
  mojibake into a prompt. If a string can't be recovered confidently, ask the user
  to confirm that specific text. Before assuming mojibake, confirm you didn't just
  view clean UTF-8 through `cat -v`.
- **An ambiguous model name.** `ChatGPT image2.5` names no single model — the
  endpoint offers `gpt-image-2.5-flare` and `gpt-image-2.5-sunburst`. Ask which
  one; don't pick for the user, and don't quietly fall back to `gpt-image-2`.
  The same goes for any deck shorthand that maps to more than one real id.
- **A video slide naming a model the pipeline can reach two ways.** A
  `Wan 3.0 — Image-to-Video (I2V)` slide under an `I2I→I2V` title is the video
  step of *this* pipeline (`video_service: wan_v3`). The same text on a
  standalone slide is a `wan_v3_i2v` task. Route by whether the slide has an I2I
  partner, and say in Step 7 which reading you used.
- **Task count vs. expectation.** Count the distinct styles you actually found (after
  Human/Pet splits and after collapsing repeated export blocks). If it differs from what the user expected, say so plainly and
  list what you extracted rather than inventing missing styles — the `.txt` export may
  have dropped slides.

## Step 5 — Build and write the tasks block

- **N** = final task count (after Human/Pet splits). **`<MMDD>`** = today's date
  (`currentDate`), zero-padded, unless the user specifies otherwise — writing the config
  starts a new batch. Every task's `folder` embeds the same group segment:
  `Media Files/I2I2V/<MMDD> <N> Styles/<MMDD> <style_name>`. Use `Styles` (plural) for
  N ≥ 2, `Style` for N = 1.
- The new `tasks:` block is large (thousands of lines). Write it **programmatically** to
  guarantee exact indentation — do not hand-assemble a giant `Edit`. Read the file,
  keep everything before the top-level `tasks:` line and everything from the top-level
  `comments:` line onward, and splice the generated tasks between them. Field lines are
  indented 4 spaces; block-scalar bodies 6 spaces; blank prompt lines stay truly empty.

  ```python
  # emit one task; `t` holds the mapped field values
  def block(field, text, indent=4):
      body = " " * (indent + 2)
      out = [f'{" "*indent}{field}: |']
      out += [f"{body}{ln.rstrip()}" if ln.strip() else "" for ln in text.split("\n")]
      return "\n".join(out)
  # header = lines before 'tasks:'  |  footer = lines from 'comments:' onward
  # new = "tasks:\n\n" + "\n\n".join(emit(t) for t in tasks) + "\n\n\n"
  ```

- Follow `Scripts/config/CLAUDE.md`: **no inline `#` comments** inside tasks; all
  field docs live only in the trailing `comments:` block (which you preserve untouched).

## Step 6 — Update the top-level links

- **`root_design_link`** ← the deck's Google Slides URL from Step 1 (bare, unquoted,
  matching the file's existing form).
- **`root_source_video_link`** ← clear it, leaving it blank with a **single space
  after the colon** (`root_source_video_link: `), not `''` and not a bare colon with
  no space. The previous batch's link is stale once the tasks change; a new one is
  produced after the script runs.

Do not touch any other top-level key (`template_path`, `output`, `testbed`, `schedule`,
`reuse_original_*`, the global image-source defaults, `comments`).

## Step 7 — Confirm

Report:

- A clickable `file:line` link to the new tasks region and the task count.
- The **title → style_name mapping** for every style.
- For each task, the **image service + model** and the **video service**, so a
  mixed batch is legible at a glance.
- **A warning, first and prominently, if a `wan_v3` task's slide carried a
  negative prompt** — naming the style, quoting the dropped text, and noting
  that `/wan_v3` accepts none. If none did, say so explicitly so the user knows
  the check ran.
- **The slides you skipped** and which skill handles each.
- Every other ambiguity you resolved: image-prompt variants chosen, Human/Pet
  splits, CJK reconstructed, resolution/aspect inferred, how many duplicate
  export blocks you collapsed, and how you paired the I2I/I2V halves.
- The run command: `python runall.py i2i2v auto`.

---
name: i2i2v-from-deck
description: Convert a "GAI Template" text export of a Google Slides group-shot deck into the full tasks list of Scripts/config/batch_i2i2v_config.yaml. Use when the user provides a .txt (or pasted text) exported from a GAI/group-shot Slides deck — with per-style image prompts, video prompts, negative prompts, and Gemini/resolution/aspect metadata — and wants it turned into i2i2v batch tasks. Also updates root_design_link to the deck URL and clears root_source_video_link. For the generic per-field paste flow across other APIs, use update-batch-prompts instead.
---

# i2i2v-from-deck

Parse a whole **GAI Template** deck export (the `.txt` you get from a group-shot
Google Slides deck) and rebuild the `tasks:` list of
`Scripts/config/batch_i2i2v_config.yaml` from it — one task per style. Unlike
[update-batch-prompts](../update-batch-prompts/SKILL.md), which asks the user to
paste one field at a time, this skill ingests the entire deck text at once,
splits it into styles, and maps each style's blocks onto the i2i2v task shape.

**Always fully replace** the `tasks:` list with what the deck contains, unless the
user explicitly says otherwise. This holds even when the deck carries only a few
styles that match existing tasks (e.g. `Fix` iterations of styles already in the
file): the result is a full replace down to just those styles — do **not** silently
merge the deck's styles into the existing list or keep the untouched ones. Update
in place / append only on explicit instruction.

## Step 1 — Collect inputs

You need two things:

1. **The deck text** — a `.txt` file path, an attached document, or pasted text.
   The `.pptx` itself is usually too large to attach; a `.txt` export is normal.
2. **The deck link** — the Google Slides URL. Goes into `root_design_link`. If the
   user pasted it in an earlier turn (e.g. when they first asked to update the
   config), reuse that; don't re-ask.

The Google Drive connector generally can't be read in a non-interactive session,
and Slides isn't WebFetch-able, so **work from the supplied text** — do not try to
fetch the deck.

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

## Step 3 — Field mapping (deck → i2i2v task)

Clone the **last existing task** in the file for exact quoting/indentation, but the
field values come from the deck as follows:

| Config field | Source in deck | Notes |
|---|---|---|
| `style_name` | Chinese title | single-quote it; keep the ` V3` suffix; clean mojibake (Step 4) |
| `folder` | derived | `'Media Files/I2I2V/<MMDD> <N> Styles/<MMDD> <style_name>'` (Step 5) |
| `image_service` | — | always `nano_banana` (deck is all Gemini) |
| `image_model` | `Gemini 3` → `gemini-3-pro-image`; `Gemini 3.1` → `gemini-3.1-flash-image` | note: **no** `-preview` suffix |
| `image_resolution` | `Resolution:` | `'1K'` or `'2K'` |
| `image_aspect_ratio` | `Aspect Ratio:` | `'3:4'` or `'4:3'` — the metadata value wins over any aspect mentioned inside the prompt text |
| `use_multi_image` | — | always `true` |
| `multi_image_config` | — | always `{ mode: sequential }` (rendered as a nested `mode: sequential`) |
| `image_prompt` | the finalized image prompt | block scalar `|` (Step 4 picks the variant) |
| `video_model` / `video_mode` | `Kling v3.0` | `v3` / `pro` |
| `video_duration` | `Duration: 5s` | `5` |
| `video_ratio` | — | matches `image_aspect_ratio` |
| `video_sound_enabled` | — | default `true` |
| `video_prompt` | the `Prompt:` under the video section | block scalar `|` |
| `video_negative_prompt` | `Negative prompt:` block, else empty | block scalar `|`, or `''` when absent |
| `concurrent_requests` | — | default `3` |

The resulting field order per task (from the live template):
`style_name, folder, image_service, image_model, image_resolution, image_aspect_ratio,
use_multi_image, multi_image_config, image_prompt, (blank), video_model, video_mode,
video_duration, video_ratio, video_sound_enabled, video_prompt, video_negative_prompt,
(blank), concurrent_requests`.

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
- **Mojibake (garbled CJK).** A downloaded `.txt` frequently arrives with Chinese /
  Japanese mangled (UTF-8 misread as Latin-1: `ç¶å¸…`, `ãã£ã¡`), while English
  survives. Reconstruct the `style_name` and any **on-image text the prompt tells the
  model to render** (e.g. purikura sticker phrases) into clean CJK. Never ship
  mojibake into a prompt. If a string can't be recovered confidently, ask the user
  to confirm that specific text.
- **Task count vs. expectation.** Count the distinct styles you actually found (after
  Human/Pet splits). If it differs from what the user expected, say so plainly and
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

Report a one-line summary with a clickable `file:line` link to the new tasks region and
the task count, and call out every ambiguity you resolved (which image-prompt variants
you chose, any Human/Pet splits, any CJK you reconstructed, and any resolution/aspect
you inferred), so the user can correct anything you guessed.

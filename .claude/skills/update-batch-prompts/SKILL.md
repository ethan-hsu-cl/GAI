---
name: update-batch-prompts
description: Add or replace prompt-driven tasks in a custom-prompt image/video-to-video batch config YAML (Kling I2V, Kling Omni, I2I2V, Veo ITV, Seedance I2V, Kling Endframe, Vidu I2V, Wan V3 I2V, Wan V3 V2V, Wan V3 Endframe, Wan V3 Reference). Use when the user wants to add the per-task parameters for one of these APIs — typically pasting prompt / negative-prompt text blocks copied from a Google Slides deck, or giving the deck URL itself. Asks which API, how many tasks, and whether to replace or append, then collects the content for each task's arguments.
---

# update-batch-prompts

Build new `tasks:` entries for one of the **custom-prompt image-to-video** configs and either replace the existing list or append to it. These APIs each have a different per-task field shape, but inside any one file every task clones the same shape — so the structure, defaults, quoting, and folder convention are learned from the existing tasks in the target file, and only the per-task *content* (prompt text, style name) is asked from the user.

This skill is for configs whose tasks carry a free-text `prompt` / `*_prompt`. For name-only effect lists with no prompt (Kling Effects, Vidu Effects, Pixverse Effects, Pixverse I2V), use **update-batch-effects** instead. For a whole Wan V3 deck, prefer the dedicated deck skills (**wan-i2v-from-deck**, **wan-v2v-from-deck**, **i2i2v-from-deck**) — they also copy sample sources; the Wan V3 rows below are for pasting a few prompts by hand.

**Not covered:** Kling v3 A/B (`batch_kling_v3ab_config.yaml` + `batch_kling_v3ab_baseline_config.yaml`) is a benchmark whose two files must keep identical prompts in the same order — edit both by hand together. Text-to-video configs (Kling/Pixverse/Seedance/Wan V3/Gemini Omni TTV) have no source images and are out of scope.

## Supported APIs

| API | Config file | Per-task content fields (ask the user) | Carry-over default fields (clone from existing task) | Per-style folder shape |
|---|---|---|---|---|
| Kling I2V | `Scripts/config/batch_kling_config.yaml` | `prompt`, `negative_prompt`, `mode` | `design_link`, `source_video_link`, `reference_folder`, `use_comparison_template` | flat: `Media Files/Kling 3.0/<MMDD> <name>` |
| I2I2V | `Scripts/config/batch_i2i2v_config.yaml` | `style_name`, `image_service`, `image_model`, `image_prompt`, `video_prompt`, `video_negative_prompt` | `image_quality`, `image_resolution`, `image_aspect_ratio`, `video_model`, `video_mode`, `video_duration`, `video_ratio` | grouped + dated: `Media Files/I2I2V/<MMDD> <N> Styles/<MMDD> <style_name>` |
| Veo ITV | `Scripts/config/batch_veo_itv_config.yaml` | `style_name`, `prompt`, `negative_prompt` | `model_id`, `duration_seconds`, `aspect_ratio`, `resolution`, `compression_quality`, `seed`, `enhance_prompt`, `generate_audio`, `person_generation` | grouped: `Media Files/Veo_ITV/<MMDD> <N> Styles/<style_name>` |
| Seedance I2V | `Scripts/config/batch_seedance_i2v_config.yaml` | `style_name`, `prompt` | `aspect_ratio` | grouped: `Media Files/Seedance I2V/<MMDD> <N> Styles/<style_name>` |
| Kling Endframe | `Scripts/config/batch_kling_endframe_config.yaml` | `prompt`, `negative_prompt`, `mode` | `duration`, `cfg`, `design_link`, `source_video_link`, `reference_folder`, `use_comparison_template` | grouped: `Media Files/Kling Endframe/<MMDD> <N> Style(s)/<name>` |
| Vidu I2V | `Scripts/config/batch_vidu_i2v_config.yaml` | `custom_effect_name`, `prompt`, `duration` | — | no folder field |
| Kling Omni | `Scripts/config/batch_kling_omni_config.yaml` | `style_name`, `prompt`; per-task overrides of `default_settings` only where the deck differs: `duration`, `aspect_ratio`, `image_type`, `mode`, `sound_enabled`, `multishot_type` (+ `multishot_df`) | — (settings live in `default_settings`) | grouped: `Media Files/Kling Omni/<MMDD> <N> Style(s)/<name>` |
| Wan V3 I2V | `Scripts/config/batch_wan_v3_i2v_config.yaml` | `style_name`, `prompt`; overrides `resolution`, `ratio`, `duration`, `audio_out` where the deck differs | — (`default_settings`) | grouped: `Media Files/Wan V3 I2V/<MMDD> <N> Styles/<style_name>` |
| Wan V3 V2V | `Scripts/config/batch_wan_v3_v2v_config.yaml` | `style_name`, `prompt`; overrides `resolution`, `ratio`, `duration`, `audio_out` | — (`default_settings`) | grouped: `Media Files/Wan V3 V2V/<MMDD> <N> Styles/<style_name>` (Source holds **videos**) |
| Wan V3 Endframe | `Scripts/config/batch_wan_v3_endframe_config.yaml` | `prompt`, `ratio` | `pairing_mode`, `design_link`, `source_video_link`, `reference_folder`, `use_comparison_template` | grouped: `Media Files/Wan V3 Endframe/<MMDD> <N> Style(s)/<name>` |
| Wan V3 Reference | `Scripts/config/batch_wan_v3_reference_config.yaml` | `effect`, `prompt`, `ratio` | — | no folder field; top-level `base_folder: Media Files/Wan V3 Reference/<MMDD> <N> Style(s)`, one subfolder per `effect` (with `Source` + `Reference`) |

The table is a guide. **Always treat the last existing task in the target file as the source of truth** for exact field order, quoting style, block-scalar (`|`) usage, indentation, and default values. If the file's shape disagrees with the table, follow the file — **with one exception: the folder naming convention always follows the `Per-style folder shape` column in the table above, never a stale folder in the live file.** If the file's existing tasks use a flat, un-grouped folder (e.g. `Media Files/I2I2V/0603 <name>`) but the table specifies a grouped shape (`Media Files/I2I2V/<MMDD> <N> Styles/<MMDD> <name>`), write the grouped shape. A flat folder already in the file is treated as stale, not as the convention.

## Step 1 — Identify the target config (API)

Resolve in this order, then call `AskUserQuestion` only if still ambiguous:
1. **IDE selection / open file** — if the user has a selection in, or just opened, one of the supported config files, that is the target.
2. **Keyword in the user message** — "i2i2v", "kling endframe", "kling omni"/"omni-v3"/"O3"/"O1", "kling", "veo"/"veo itv", "seedance", "vidu", "wan v3 i2v", "wan v3 v2v"/"v2v", "wan endframe", "wan reference" → the matching file. A deck's `Model:` line counts as a keyword: `Kling omni-v3` / `Kling O3` → Kling Omni; `Kling 3.0` / `kling-v3` → Kling I2V. ("Gemini Omni" is a text-to-video config — not Kling Omni.)
3. **Prior turn context** — if the user was just editing one of these files, assume the same one.
4. Otherwise ask via `AskUserQuestion` (header `API`) listing the supported APIs above. Disambiguate "kling" between Kling I2V, Kling Omni and Kling Endframe, and "wan" between the four Wan V3 rows, if unclear.

### Deck URL instead of pasted text

If the user gives a Google Slides link, fetch it — a link-shared deck needs no auth or Drive connector:

```bash
curl -sSL "https://docs.google.com/presentation/d/<DECK_ID>/export/txt" -o deck.txt
```

Check the body is text, not an HTML login page, before trusting it. Read it as UTF-8, then **normalize soft line breaks first**: Slides writes Shift+Enter breaks as `\x0b` (vertical tab), so `Prompt:` is often followed by `\x0b` and the prompt itself, and paragraphs inside a prompt are `\x0b`-separated. Run `text = text.replace("\x0b", "\n")` before any parsing — otherwise line-start matches like `startswith("Prompt:…")` miss, and any `\x0b` left in a prompt is a control character that breaks the YAML.

The export repeats slides and interleaves result/review slides (titles alone, QA notes in Chinese). When the user names pages (e.g. "P2-P6"), the first page usually carries the prompt and the rest are its result slides — confirm the style count rather than emitting one task per page. A `QA Debug NN` label marks a revision: use the highest-numbered one, and ignore older ones under a `過程文件` (process docs) / `Old file` heading.

## Step 2 — Ask the premises (always, up front)

Ask these before collecting any content. Combine into a single `AskUserQuestion` call with multiple questions when the API is already known:

1. **Count** — header `Count`, question "How many tasks/effects to add?" Offer a few common counts (e.g. 1, 2, 3, 6) plus the user can type their own.
2. **Mode** — header `Mode`, question "Replace the existing tasks, or append to them?" Options: `Replace` (clears the current `tasks:` list and writes only the new ones) and `Append` (keeps existing tasks and adds the new ones after them).

If the user already stated count and/or mode in their message, skip those questions.

## Step 3 — Learn the per-task template from the file

`Read` the target config. From the **last existing task** capture:
- The exact field set and their order.
- Per-field formatting: which values are quoted (single vs double), which use block scalars (`| ` literal blocks), indentation width, and whether entries are separated by a blank line.
- The carry-over default values (everything in the "default fields" column).
- The `Media Files/...` **path prefix** only (the part before the dated group segment). The rest of the **folder convention** — whether there is a `<MMDD> <N> Styles` group segment and whether the per-style leaf is date-prefixed — comes from the table's `Per-style folder shape` column, **not** from the live file: I2I2V is grouped with a date-prefixed leaf (`<MMDD> <N> Styles/<MMDD> <name>`), Veo/Seedance are grouped with a plain leaf (`<MMDD> <N> Styles/<name>`). If the file's existing tasks use a flat folder, do not copy that flat shape — apply the grouped shape from the table.
- Windows-safe leaf: in the `<name>` folder leaf (not in `style_name`) replace each of `< > : " / \ | ? *` with `_` and drop trailing dots/spaces — the suite also runs on Windows. Same rule as `Scripts/core/path_utils.py`.

If the file has zero existing tasks, fall back to the table above and to the commented example block in the file.

## Step 4 — Collect the content for each new task

For the content fields (the ones the user pastes from the Slides text blocks), ask in **plain text** — not `AskUserQuestion` — because prompt text is long. In one message, lay out exactly what you need per task, numbered, so the user can paste blocks in order. For example, for I2I2V:

```
Paste the following for each of the N tasks (I'll use the existing defaults for models/ratios/duration unless you say otherwise):

Task 1
  • style_name:
  • image_service (nano_banana | openai_image):
  • image_prompt:
  • video_prompt:
  • video_negative_prompt:
```

Guidance:
- Only ask for the **content fields** for that API (see the table). Reuse the carry-over defaults silently from Step 3; mention you're doing so, and let the user override any default if they want.
- If the user already pasted the blocks in their message, parse them directly instead of re-asking.
- For I2I2V, `image_model` follows `image_service`: default `gemini-3.1-flash-image-preview` for `nano_banana`, `gpt-image-2` for `openai_image`, unless the existing default task or the user says otherwise.
- A field the user leaves blank → use the file's default empty form (e.g. `negative_prompt: ''`).
- **Several aspect ratios on one slide** (e.g. `Aspect ratio: 16:9 / 9:16 / 1:1`) — the handlers take one ratio per task. Ask whether to run all of them (one task per ratio, `style_name` suffixed with the ratio, e.g. `360 Spin 16:9`, folder leaf `360 Spin 16_9`) or only one.
- **Settings-driven configs (Kling Omni, Wan V3 I2V/V2V)** — write a per-task override only for a setting the deck states and that differs from `default_settings`; leave the rest to the defaults.

### Kling Omni specifics

Map the deck's slide fields as follows:

| Deck | Task field |
|---|---|
| `Model: Kling omni-v3` / `O3` | `model: omni-v3` (the default — omit) · `O1` / `omni` → `model: omni` |
| `Duration: 10 Sec` | `duration: 10` (default 5; range 3–15) |
| `Aspect ratio:` | `aspect_ratio: '16:9'` etc. (see the multi-ratio rule above) |
| `Sound: off` / `on` | `sound_enabled: false` / `true` (default false) |
| `Multishot Type: no` / `intelligence` / `customize` | `multishot_type: none` / `intelligence` / `customize` (default none; `customize` also needs `multishot_df: {headers: [prompt, duration], data: [[shot prompt, seconds], …]}`) |

**`image_type` — decide from the prompt, every time.** The handler sends each source image as `img1` with `image_type`, default `start` (the photo becomes frame 1). If the prompt treats `@Image1` as a reference — "reference for the product only", "do not use its background", a new backdrop/set, the subject floating or re-posed from the first frame — write `image_type: reference`. Leaving `start` makes every video open on the source photo, background and stand included, which defeats the prompt. Use `start` only when the prompt says the video begins on the input image ("starts exactly on @Image1", "continue the scene"). Tell the user which you chose and why.

Keep `@Image1` tokens verbatim — they are passed through to the testbed as written.

### Wan V3 Reference specifics

The prompt addresses the gallery as `image1` (source), `image2`, … (files from the effect's `Reference` folder). Keep those tokens verbatim.

## Step 5 — Derive folder paths

For APIs with a `folder` field, build each task's folder from the convention learned in Step 3:
- **Date `<MMDD>`** — always use today's date (the `currentDate` from context) in zero-padded month + day (e.g. `0616` for June 16), **not** a date carried over from the existing folder prefix. Writing the config starts a new batch, so the folder date should reflect when it is written.
- **Group count `<N>`** — the total number of tasks in the final list (existing + new, for Append; just the new ones, for Replace). Apply the same `<MMDD> <N> Style(s)` group segment to **every** task in the written block, since that segment is embedded in each folder path.
  - **Grammar:** `1 Style` (singular) when N = 1; `2 Styles` (plural) when N ≥ 2. Match the file's existing noun (`Styles` for I2I2V/Veo/Seedance/Wan V3 I2V/V2V, `Style(s)` for Kling Endframe/Kling Omni/Wan V3 Endframe/Wan V3 Reference). Never write `1 Styles`.
- **Per-style leaf** — match the file's leaf convention (date-prefixed for I2I2V, plain `style_name` for Veo/Seedance/Kling Omni/Wan V3, the `name` for Kling/Endframe), made Windows-safe (Step 3).
- **Wan V3 Reference** has no per-task folder: rewrite `base_folder` instead (Step 6.3); each `effect` name must match a subfolder under it.

## Step 6 — Build and apply the edit

1. Format each new task entry by cloning the template's exact shape (field order, quoting, block scalars, blank-line separators).
2. Use `Edit`:
   - **Replace** — `old_string` = the whole existing `tasks:` block (from `tasks:` through the last task entry, not including trailing blank lines before the next top-level key or comment); `new_string` = `tasks:` + the newly formatted entries.
   - **Append** — `old_string` = the last existing task entry; `new_string` = that same entry + the new entries after it (with the file's separator style).
   - For grouped-folder APIs on Append where `<N>` changed, the group segment in the **existing** task folders also changes — rewrite the full `tasks:` block (treat it like Replace but keep the existing tasks' content) so every folder reflects the new count.
3. If the API has a separate `base_folder`/group key outside the tasks (currently only Wan V3 Reference), rewrite its last segment to `<MMDD> <N> Style(s)` with today's date and the final task count.
4. **Clear the source-video-link field** — in a separate `Edit`, blank the top-level link field, leaving a **single space after the colon** (`<field>: `), not `''` and not a bare colon with no space. The field name varies by file: `root_source_video_link` (I2I2V, Veo ITV, Kling Omni, Wan V3 I2V/V2V) or `source_video_link` (Seedance, Vidu I2V, Wan V3 Endframe/Reference, and the `root_*` block in Kling I2V / Kling Endframe). (Note: most editors and the `Edit` tool strip trailing whitespace, so add the space via a small script write rather than an `Edit`.) The previous link is stale once the tasks change; a new one is produced after the script runs. On a **Replace**, also empty any per-task `source_video_link` values (Kling I2V / Kling Endframe) rather than cloning the old batch's links into the new tasks.
5. **Check the inputs exist.** For every task folder (or `base_folder/<effect>`), check that `Source/` holds inputs — images, or videos for Wan V3 V2V; Wan V3 Reference also needs `Reference/`. The handlers silently skip a task with an empty `Source/`, so list any missing ones in the summary and offer to copy a set from `Media Files/Sources/` (e.g. `Source 20 Product` for product prompts, `Source 50 Sample` for people).
6. Validate with `python3 -c "import yaml; yaml.safe_load(open('<config>'))"` and print each task's key fields.
7. Confirm with a one-line summary including a clickable `file:line` link to the new tasks region, e.g. `[batch_i2i2v_config.yaml:28-60](Scripts/config/batch_i2i2v_config.yaml#L28-L60)`.

## What NOT to change

- Don't touch `comments`, `template_path`, `output`, `testbed`, `schedule`, `default_settings`, `root_design_link`, `root_folder`, `model_version`, or any top-level key outside the `tasks:` list, the source-video-link field (which is cleared, see Step 6.4), `base_folder` (Wan V3 Reference, Step 6.3), and the group-count segment inside folder paths. Per-task overrides go on the task, never into `default_settings`.
- Don't reorder or rename fields; clone the existing shape exactly.
- Don't add YAML commentary or leave the commented example block altered.
- Don't change the `Media Files/...` path prefix — only the `<MMDD> <N> Style(s)` segment and the per-style leaf.

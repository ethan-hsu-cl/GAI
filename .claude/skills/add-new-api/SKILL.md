---
name: add-new-api
description: Add a new API platform to the GAI automation suite — creates a handler, config YAML, api_definitions entry, runall registration, unified report generator support, README section, and runs validation. Use when the user wants to integrate a new Gradio-based generation API (image_to_video, text_to_video, effects, endframe, motion, or reference) and provides API documentation, an API type, and default parameter values.
---

# add-new-api

Integrate a new API platform into the GAI automation suite. Follow every step sequentially. Do not skip steps.

The integration is not done until it has produced a real result from the live endpoint through the real pipeline (Step 9). Static checks passing is not "done"; do not hand back with "try running it and tell me what breaks".

## Required Input

The user must provide:
1. **API documentation** — The Gradio `client.predict()` call signature, parameter definitions, and return tuple structure.
2. **API type** — One of: `image_to_video`, `text_to_video`, `effects`, `endframe`, `motion`, or `reference`.
3. **Default parameter values** — The defaults for all API parameters (aspect ratio, duration, resolution, model, seed, etc.).

If any of the three are missing, stop and ask the user via `AskUserQuestion` before proceeding.

## Step 1: Determine the API identifier

Derive a snake_case API name from the platform name (e.g., `seedance_ttv`, `kling_effects`). This identifier is used everywhere: handler filename, config filename, `api_definitions` key, runall mappings, and report generator references.

## Step 1b: Probe the live API before writing code

Pasted docs drift from the server, and a call that only fails when the user runs the batch costs them a round trip. Find the problems here instead. The testbeds sit behind an OAuth proxy, so a bare `Client(url)` fails with `Could not fetch config` — pass the cookie from `get_testbed_cookie()`, which pulls the live session from Chrome by default (`TESTBED_BROWSER` in `.env` overrides the browser) and only falls back to the `.env` copy. Keep the default `auto_fetch=True`. Run from `Scripts/core` with conda `myenv`, writing probe scripts to the scratchpad:

```python
from config_loader import get_testbed_cookie
from gradio_client import Client, handle_file
c = Client(ENDPOINT, headers={'Cookie': get_testbed_cookie()}, verbose=False)
ep = c.view_api(return_format='dict', print_info=False)['named_endpoints'][API_ROUTE]
```

1. **Schema check** — Print each parameter's name, default and component from `ep['parameters']` and compare against the pasted docs. Also read slider ranges and radio choices from `c.config['components']` (`props.minimum/maximum/step/choices`) — the docs omit them, and they belong in the config's `comments:`.
2. **One real generation** — Call `predict()` exactly as the handler will: a real file from `Media Files/Sources/Source 50 Sample/` (or a short clip for video inputs), the chosen defaults, and `None` / `""` for every input the API type leaves unused. Doc "Required" often only means "no default"; this proves which empty values the server accepts. Print `repr(result)` to learn the real tuple shape (string vs dict, error slot contents on success) before writing `_handle_result`. If the call errors, change the request (empty value → `None` vs `""`, a different input type, a file the validator accepts) and call again until it returns a video — don't write the handler around a call you haven't seen succeed.
3. **One failure** — Send a cheap invalid request (e.g. empty prompt) and note whether the error comes back in the result tuple or raises (`AppError`). Make sure its text doesn't match `CONNECTION_ERROR_PATTERNS` in `base_handler.py`, or it would be retried as an outage instead of recorded.

Record each finding (accepted empties, tuple shape, ranges, error style) and design the handler around them. If the endpoint is unreachable even with the cookie, tell the user and ask them to log in to the testbed in Chrome again (then fully quit Chrome so the new session is flushed to disk) rather than writing the handler blind.

## Step 2: Create the Handler

Create `Scripts/handlers/{api_name}_handler.py`.

**Rules:**
- Import `BaseAPIHandler` from `.base_handler`.
- Class name: Convert snake_case to CamelCase + `Handler` (e.g., `SeedanceTTVHandler`). The `HandlerRegistry` auto-discovers handlers by scanning `*_handler.py` files — no manual registration needed.
- **For text-to-video APIs:** Use `_validate_text_to_video_structure()` in `validate_structure()`.
- **For image/video input APIs:** Use `_validate_task_folder_structure()` or `_validate_base_folder_structure()` in `validate_structure()`.

**Required methods to implement:**

1. `validate_structure(self, tasks, config)` — Call the appropriate base validation method.

2. `_make_api_call(self, file_path, task_config, attempt)` — Map config fields to the Gradio `client.predict()` call. Use `self.config.get("default_settings", {})` for global defaults and `task_config.get()` for per-task overrides. Always include `api_name=self.api_defs["api_name"]` as the last parameter.

3. `_handle_result(self, result, file_path, task_config, output_folder, metadata_folder, base_name, file_name, start_time, attempt)` — Parse the API response tuple, save video files (try URL download first via `self.processor.download_file()`, then local copy via `shutil.copy2()`), and save metadata via `self.processor.save_metadata()`.

4. `process_task(self, task, task_num, total_tasks)` — Orchestrate task execution with generation_count support, skip-if-already-processed logic, and rate limiting.

5. `process(self, file_path, task_config, output_folder, metadata_folder, attempt, max_retries)` — Process a single generation by calling `_make_api_call` then `_handle_result`.

**Reference handlers by API type:**
- Text-to-video: `pixverse_ttv_handler.py`, `kling_ttv_handler.py`
- Image-to-video: `kling_handler.py`, `veo_itv_handler.py`
- Effects: `kling_effects_handler.py`, `pixverse_handler.py`

## Step 3: Create the Config File

Create `Scripts/config/batch_{api_name}_config.yaml`.

**Structure:**
```yaml
# {Platform} Configuration
template_path: templates/I2V standard 5col.pptx
output_directory: /Users/ethanhsu/Desktop/ethan-hsu-cl/GAI/Report
testbed: {endpoint_url}
design_link: ""
source_video_link: ""
generation_count: 1

output_folder: Media Files/{Platform Name}/{MMDD} {N} Styles

default_settings:
  # All API default parameters here

tasks:
  - style_name: Task_Name
    prompt: |
      Prompt text here
    # Per-task overrides here
```

**Task content:** Copy the 21 standard benchmark tasks from `batch_pixverse_ttv_config.yaml` or `batch_veo_config.yaml`, adapting fields to match the new API's parameter names. Preserve the same `style_name` values and `prompt` text. Keep aspect ratios consistent with veo and pixverse_ttv configs.

## Step 4: Add API Definitions

Add an entry to `Scripts/core/api_definitions.json` under the API name key.

**Required fields:**
```json
{
    "endpoint": "{testbed_url}",
    "api_name": "/{gradio_api_route}",
    "file_types": [],
    "validation": {},
    "folders": {
        "output": "Generated_Video",
        "metadata": "Metadata"
    },
    "rate_limit": 3,
    "task_delay": 10,
    "max_retries": 3,
    "special_handling": "text_to_video",
    "config_structure": "task_list",
    "report": {
        "enabled": true,
        "template_path": "templates/I2V standard 5col.pptx",
        "output_directory": "/Users/ethanhsu/Desktop/ethan-hsu-cl/GAI/Report",
        "use_comparison": false
    },
    "task_fields": ["prompt", ...],
    "api_params": { ... },
    "model_options": [...],
    "aspect_ratio_options": [...]
}
```

- For image/video input APIs, populate `file_types` (e.g., `[".jpg", ".jpeg", ".png"]`) and `validation` (max_size_mb, min_dimension, aspect_ratio range).
- For text-to-video APIs, set `"special_handling": "text_to_video"` and `"config_structure": "task_list"`.
- For effects/base-folder APIs, set `"config_structure": "base_folder"`.
- Validate the JSON after editing: `python3 -c "import json; json.load(open('Scripts/core/api_definitions.json')); print('JSON valid')"`.

## Step 5: Register in runall.py

Edit `Scripts/core/runall.py` — add entries in **all four** locations:

1. **`API_MAPPING`** dict — Add both the canonical name and a shorthand alias:
   ```python
   '{api_name}': '{api_name}',
   '{shorthand}': '{api_name}',
   ```

2. **`CONFIG_MAPPING`** dict:
   ```python
   '{api_name}': 'config/batch_{api_name}_config.yaml',
   ```

3. **Help text** — Add a `print()` line in the PLATFORMS section.

4. **Examples** — Add a `print()` line in the EXAMPLES section.

## Step 6: Add Report Support

Edit `Scripts/core/unified_report_generator.py` — add the API name to **all** of the following locations:

1. **Display name** — In the `DISPLAY_NAMES`-style dict in `__init__()`, add: `'{api_name}': '{Display Name}'`

2. **Slide config** — In `get_slide_config()`, add a config block. Use the same format as the closest matching API type:
   - Text-to-video: `media_types: ['prompt', 'generated']` with 2-media layout
   - Image-to-video: `media_types: ['source', 'generated']` with 2-media layout
   - Effects: `media_types: ['source', 'generated']` with 2-media layout

   Set `metadata_fields` to match the fields saved in `_handle_result`.

3. **Video detection** — Add to the `is_video` check list (search for `'pixverse_ttv'` in the `is_video` line).

4. **`process_batch()`** — Add to the appropriate routing condition:
   - Text-to-video: the `["veo", "kling_ttv", "pixverse_ttv", ...]` list
   - Base folder: the `["vidu_effects", "vidu_reference", ...]` list
   - Otherwise falls through to task folder structure

5. **`process_text_to_video_batch()`** (text-to-video only) — Add to the folder resolution condition:
   - If config uses `output_folder` at root level: add to `['kling_ttv', 'pixverse_ttv', ...]`
   - If config uses per-task `output_folder`: it falls through to the `else` (veo-style)

6. **`run()` method** — Add to the appropriate routing condition (same list as `process_batch`).

7. **Filename generation** — Search for all lists containing `'pixverse_ttv'` in `_get_filename_parts()` and `_get_grouped_filename()`. Add the new API name to each list where style count display is appropriate.

8. **`create_report_generator()`** — Add to the `supported_apis` list.

9. **`main()` argparse** — Add to the `choices` list.

## Step 7: Update README

Add a configuration section to `readme.md` following the pattern of existing TTV/effects sections. Include:
- The config filename
- A YAML example showing `default_settings` and one sample task
- A one-line summary of defaults

## Step 7b: Register in the batch-editing skills

So the new config can be filled from a deck later, add it to the skill that edits its `tasks:` list:
- Tasks carry a free-text prompt over source images/videos → add a row to the `Supported APIs` table in `.claude/skills/update-batch-prompts/SKILL.md` (content fields, carry-over fields, folder shape), its Step 1 keywords, the Step 5 `Style`/`Styles` noun list, and the Step 6.4 link-field list. Add a `### <API> specifics` section if the deck's fields need mapping (model names, `Sound: off`, image roles such as `image_type`).
- Tasks are a list of effect names/IDs → add it to the `Supported configs` table and per-task format in `.claude/skills/update-batch-effects/SKILL.md`.
- Text-to-video or benchmark configs → add them to the **Not covered** note in `update-batch-prompts` instead.
Also list the new API in that skill's frontmatter `description`, which decides when it triggers.

## Step 8: Validate

Run these checks:
1. `python3 -c "import json; json.load(open('Scripts/core/api_definitions.json')); print('JSON valid')"`
2. From `Scripts/` directory with conda myenv (`core/` must be on the path — its modules import each other bare, so `from core.…` fails with `No module named 'config_loader'`): `python -c "import sys; sys.path.insert(0, 'core'); from unified_report_generator import create_report_generator; g = create_report_generator('{api_name}'); sc = g.get_slide_config(); print('Media types:', sc.get('media_types')); print('OK')"`
3. **Coverage check** — `grep -rn "{closest_existing_api}" Scripts/core Scripts/handlers readme.md` for the existing API the new one was modeled on, and confirm the new name appears beside it in every list. The steps above name the usual spots, but routing lists get added over time; a missed one silently routes the report to the wrong folder structure.

## Step 9: End-to-end smoke run

Static checks don't exercise the handler, the folder layout or the report. Before handing over, run the real pipeline once on the smallest possible batch:

1. Write a temporary config in the scratchpad (copy the real one) with one task, `generation_count: 1`, and a scratch `folder`/`output_folder` holding one source file from `Media Files/Sources/Source 50 Sample/` (none for TTV). Point the report `output_directory` at the scratchpad too, so nothing lands in `Report/`.
2. From `Scripts/core`: `python runall.py {api_name} auto --config <temp config>`.
3. Confirm: the video saved under the expected name, the metadata JSON has `success: true` and the fields the slide config lists, and the report `.pptx` was built with one non-failed slide (open it with `python-pptx` and count slides/pictures).
4. Re-run the same command and confirm the generation is skipped as already processed (proves the resume naming matches).

**Loop until it produces a result.** If any check fails — an exception, `success: false`, a missing video, an empty or failed slide, a generation that isn't skipped on re-run — read the error (console output and the metadata `error` field), fix the handler/config/definitions/report wiring, delete that generation's metadata and output so it isn't skipped, and run again. Repeat until every check passes. Don't stop after one fix to ask the user to try it.

Acceptable end states:
- **A generated video** with every check above passing. This is the goal.
- **A content-moderation rejection** (NSFW / sensitive-content / policy / "risk" style error from the model). The request reached the model, so the wiring is proven up to generation. First retry with a different, plainly benign source image and prompt (a clothed adult half-body portrait, "the person smiles and waves"); a rejection on the first image is often the image. If benign inputs are still rejected, stop and accept it — but confirm the failure was recorded properly: metadata has `success: false` with the API's error text, the report shows the slide as failed rather than crashing, and the re-run behaves per `max_retries`. Tell the user the result was a moderation block, not a video.

Not acceptable end states: a crash, a validation/schema error, a connection error you didn't resolve, or "couldn't reach the endpoint so I skipped it". If the endpoint is genuinely unreachable (testbed down, Chrome session expired after a re-login + quit), say plainly that the integration is **unverified** and why, rather than reporting done.

In the final message, say what the run produced (video vs moderation block), how many fix iterations it took and what each fixed, and which options it did not exercise (other models/modes, sound, etc.). Delete the scratch media afterwards.

Report a one-line summary of which files were created/edited at the end, with clickable links.

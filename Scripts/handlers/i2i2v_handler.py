"""Image-to-Image-to-Video orchestrator handler.

Two-step pipeline per source image:
  1. Image generation via either /nano_banana or /openai_image
     (chosen per-task with `image_service`)
  2. Video generation via Kling /Image2Video using the generated image

Both steps run against separate Gradio testbeds, so this handler manages
two clients (one for image_generation, one for kling) instead of relying
on the single `processor.client` that other handlers share.

The intermediate image is saved to Generated_Frames/ and reused on resume
if present — only the failed step (video) is retried.

Per-task folder layout:
    {task_folder}/
    ├── Source/             # input reference images
    ├── Generated_Frames/   # intermediate images
    ├── Generated_Video/    # final videos
    └── Metadata/
"""
import base64
import json
import queue
import random
import re
import shutil
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from gradio_client import Client, handle_file
from PIL import Image

from .base_handler import BaseAPIHandler, ValidationError
from .image_generation_base import build_selection_plan
from .kling_handler import predict_image_to_video


# Original-frame staging is specific to the I2I2V pipeline. It lives here so
# the orchestrator remains self-contained rather than depending on a separate
# one-purpose handler module.
STAGE_DEFAULT_SEED = 42
STAGE_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
STAGE_PIPELINE_DIRS = {
    'Source', 'Additional', 'Original_Source', 'Generated_Frames',
    'Generated_Video', 'Metadata',
}
STAGE_RESET_DIRS = ('Source', 'Additional', 'Generated_Frames', 'Original_Source')
STAGE_OUTPUT_INDEX_RE = re.compile(r'^(?P<base>.+?)_image(?:_\d+)?$')


def _stage_images_in(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir()
         if p.is_file() and p.suffix.lower() in STAGE_IMAGE_EXTS),
        key=lambda p: p.name.lower(),
    )


def _stage_copy_missing(src, dest):
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def _stage_frame_base(output_path):
    match = STAGE_OUTPUT_INDEX_RE.match(output_path.stem)
    return match.group('base') if match else output_path.stem


def _find_original_runs(task_folder):
    if not task_folder.is_dir():
        return []
    return [
        folder for folder in task_folder.iterdir()
        if folder.is_dir()
        and folder.name not in STAGE_PIPELINE_DIRS
        and (folder / 'Generated_Output').is_dir()
    ]


def _report_original_mode(original):
    meta_dir = original / 'Metadata'
    if not meta_dir.is_dir():
        return 'no metadata'
    additional_counts = Counter()
    random_selection_count = 0
    total = 0
    for metadata_file in meta_dir.glob('*_metadata.json'):
        try:
            metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        total += 1
        if metadata.get('selected_source_images') or metadata.get('random_source_selection'):
            random_selection_count += 1
        additional_counts[len(metadata.get('additional_images_used') or [])] += 1
    if not total:
        return 'no readable metadata'
    parts = [f'{total} calls']
    if random_selection_count:
        parts.append(f'random source selection: {random_selection_count}')
    paired = sum(count for size, count in additional_counts.items() if size > 0)
    if paired:
        distribution = ', '.join(
            f'{size} additional × {count}'
            for size, count in sorted(additional_counts.items()) if size > 0
        )
        parts.append(f'multi-image pairing: {paired} ({distribution})')
    if additional_counts.get(0) and not random_selection_count:
        parts.append(f'single-image: {additional_counts[0]}')
    return '; '.join(parts)


def _read_additional_index(original):
    index = {}
    meta_dir = original / 'Metadata'
    if not meta_dir.is_dir():
        return index
    suffix = '_metadata.json'
    for metadata_file in meta_dir.glob(f'*{suffix}'):
        base = metadata_file.name[:-len(suffix)]
        try:
            metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        additional = metadata.get('additional_images_used') or []
        if additional:
            index[base] = list(additional)
    return index


def _reset_staged(task_folder):
    removed = []
    for name in STAGE_RESET_DIRS:
        folder = task_folder / name
        if folder.is_dir():
            shutil.rmtree(folder)
            removed.append(name)
    return removed


def stage_task_folder(task_folder, limit=None, seed=STAGE_DEFAULT_SEED,
                      reset=False, log=print):
    """Stage dropped-in image-generation results for an I2I2V video-only run."""
    task_folder = Path(task_folder)
    originals = _find_original_runs(task_folder)
    if not originals:
        return False

    for original in originals:
        log(f'📁 {task_folder.name}')
        log(f'   original run: {original.name}  [{_report_original_mode(original)}]')

        if reset:
            cleared = _reset_staged(task_folder)
            if cleared:
                log(f"   reset: cleared {', '.join(cleared)}")

        all_outputs = _stage_images_in(original / 'Generated_Output')
        total = len(all_outputs)
        if limit is not None and 0 < limit < total:
            rng = random.Random(f'{seed}:{original.name}')
            outputs = sorted(rng.sample(all_outputs, limit), key=lambda p: p.name.lower())
            log(f'   sampling: {limit} of {total} outputs (seed {seed})')
        else:
            outputs = all_outputs

        frames_dir = task_folder / 'Generated_Frames'
        copied_frames = 0
        frame_bases = set()
        for output in outputs:
            base = _stage_frame_base(output)
            frame_bases.add(base)
            copied_frames += _stage_copy_missing(
                output, frames_dir / f'{base}_image{output.suffix}'
            )

        real_sources = _stage_images_in(original / 'Source')
        real_stems = {source.stem for source in real_sources}
        copied_sources = 0
        copied_originals = 0
        for source in real_sources:
            if source.stem in frame_bases:
                copied_sources += _stage_copy_missing(
                    source, task_folder / 'Source' / source.name
                )
            else:
                copied_originals += _stage_copy_missing(
                    source, task_folder / 'Original_Source' / source.name
                )

        additional_index = _read_additional_index(original)
        referenced = {
            name for base in frame_bases
            for name in additional_index.get(base, [])
        }
        original_additional = {
            image.name: image for image in _stage_images_in(original / 'Additional')
        }
        additional_to_copy = (
            [original_additional[name] for name in referenced
             if name in original_additional]
            if referenced else list(original_additional.values())
        )
        copied_additional = sum(
            _stage_copy_missing(
                image, task_folder / 'Additional' / image.name
            )
            for image in additional_to_copy
        )

        self_referential = 0
        for output in outputs:
            base = _stage_frame_base(output)
            if base not in real_stems:
                self_referential += _stage_copy_missing(
                    output, task_folder / 'Source' / f'{base}{output.suffix}'
                )

        summary = (
            f'   staged: {copied_sources} source, '
            f'{self_referential} self-referential source, '
            f'{copied_frames} frames, {copied_additional} additional'
        )
        if copied_originals:
            summary += f', {copied_originals} preserved in Original_Source'
        log(summary)
    return True


class I2i2vHandler(BaseAPIHandler):
    """Orchestrates image-gen → Kling video-gen as one pipeline.

    Class name uses I2i2v (not I2I2V) so the registry's CamelCase→snake_case
    conversion yields `i2i2v`.
    """

    VALID_ASPECT_RATIOS = [
        'auto', '1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4',
        '9:16', '16:9', '21:9',
    ]
    BASE64_MIN_LEN = 2048

    # Max images the image-gen step accepts per call, per model. Mirrors the
    # image-generation handlers so multi-image pairing / random source selection
    # are clamped identically here.
    MODEL_MAX_IMAGES = {
        'gemini-2.5-flash-image': 3,
        'gemini-3-pro-image-preview': 14,
        'gemini-3.1-flash-image-preview': 14,
        'gpt-image-1': 10,
        'gpt-image-1.5': 10,
        'gpt-image-2': 10,
    }
    DEFAULT_MODEL_MAX_IMAGES = 3

    # These image-selection settings may be declared once at the config root.
    # A task-level value takes precedence over its root-level default.
    GLOBAL_TASK_DEFAULT_KEYS = (
        'use_random_source_selection',
        'min_images',
        'max_images',
        'num_iterations',
        'use_deterministic_random',
        'random_seed',
        'video_resolution',
    )

    def __init__(self, processor):
        super().__init__(processor)
        self._kling_client = None  # lazy init
        # Guards the lazy Kling-client init so concurrent workers don't each
        # race to create a separate client on first use.
        self._kling_client_lock = threading.Lock()
        # Bounds concurrent image-gen calls on the shared image testbed client.
        # A permit count of 1 (default) preserves the serial-pipeline behaviour;
        # the two-phase concurrent path swaps in a wider semaphore sized by
        # `image_concurrency` for the duration of the task.
        self._image_semaphore = threading.Semaphore(1)
        # Maps str(source_path) → image-gen seconds for frames the producer
        # generated ahead of time, so the consumer can report honest timings.
        self._prefetch_times = {}
        # Maps str(source_path) → image-input info (additional/selected images)
        # for prefetched frames, so metadata stays complete when the video stage
        # reuses a frame instead of regenerating it.
        self._prefetch_inputs = {}
        # Per-task caches for multi-image pairing.
        self._additional_pools = {}   # task_key → {'pools': [[Path,...]], 'mode': str}
        self._source_indices = {}     # task_key → {str(source_path): sorted_index}
        self._pool_lock = threading.Lock()

    def _get_kling_client(self):
        """Lazily create the Kling Gradio client (separate testbed).

        Double-checked locking keeps concurrent-mode workers from each building
        their own client on first use.
        """
        if self._kling_client is None:
            with self._kling_client_lock:
                if self._kling_client is None:
                    endpoint = self.api_defs.get(
                        'kling_endpoint',
                        'http://192.168.31.161/external-testbed/kling/',
                    )
                    headers = {}
                    cookie = self.config.get('testbed_cookie') or self.processor._testbed_cookie
                    if cookie:
                        headers['Cookie'] = cookie
                    self._kling_client = Client(endpoint, headers=headers or None)
                    self.logger.info(f"✓ Kling client initialized: {endpoint}")
        return self._kling_client

    def _get_stage_concurrency(self, task, key):
        """Resolve a per-stage concurrency cap.

        Lookup order: per-task/root ``key`` (e.g. ``image_concurrency`` or
        ``video_concurrency``) → fall back to the shared ``concurrent_requests``
        (per-task → root → 1). Clamped to [1, MAX_CONCURRENT_REQUESTS].

        Args:
            task: Task configuration dictionary.
            key: Stage-specific concurrency key to look up first.

        Returns:
            int: Worker count for this stage.
        """
        raw = task.get(key, self.config.get(key))
        if raw is None:
            return self._get_concurrent_requests(task)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            return self._get_concurrent_requests(task)
        return max(1, min(val, self.MAX_CONCURRENT_REQUESTS))

    def _reuse_stage_options(self, config):
        """Read the reuse-original-frames staging options from config.

        Returns ``(enabled, limit, seed, reset)``. Staging is a no-op unless a
        task folder actually contains a dropped-in original-run folder, so it is
        enabled by default; set ``reuse_original_frames: false`` to disable.
        """
        enabled = config.get('reuse_original_frames', True)
        limit = config.get('reuse_original_limit')
        if limit is not None:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                self.logger.warning(f"⚠️ Ignoring non-integer reuse_original_limit: {limit!r}")
                limit = None
        seed = config.get('reuse_original_seed', STAGE_DEFAULT_SEED)
        reset = bool(config.get('reuse_original_reset', False))
        return enabled, limit, seed, reset

    def validate_structure(self, tasks, config):
        """Validate per-task Source/ layout and prepare enhanced tasks.

        Before validating each task, stage any dropped-in original-run folder
        (video-only reuse) so ``runall`` picks it up automatically. Controlled by
        the ``reuse_original_*`` config options; a no-op when no original folder
        is present.
        """
        valid_tasks = []
        invalid_images = []

        stage_enabled, stage_limit, stage_seed, stage_reset = self._reuse_stage_options(config)
        global_task_defaults = {
            key: config[key]
            for key in self.GLOBAL_TASK_DEFAULT_KEYS
            if key in config
        }

        for i, task in enumerate(tasks, 1):
            # Root values are defaults only; explicit per-task settings win.
            task = {**global_task_defaults, **task}
            folder = Path(task.get('folder', ''))
            if not folder or str(folder) == '':
                self.logger.warning(f"⚠️ Task {i}: Missing folder path")
                continue

            folder.mkdir(parents=True, exist_ok=True)

            if stage_enabled:
                stage_task_folder(
                    folder, limit=stage_limit, seed=stage_seed,
                    reset=stage_reset, log=self.logger.info,
                )

            source_folder = folder / "Source"
            source_folder.mkdir(exist_ok=True)

            image_files = self.processor._get_files_by_type(source_folder, 'image')
            if not image_files:
                self.logger.warning(f"⚠️ Task {i}: No images found in {source_folder}")
                continue

            valid_count = 0
            for img_file in image_files:
                is_valid, reason = self.validate_file(img_file)
                if not is_valid:
                    invalid_images.append({
                        'folder': folder.name, 'filename': img_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1

            if valid_count == 0:
                self.logger.warning(f"⚠️ Task {i}: No valid images in {source_folder}")
                continue

            frames_folder = folder / "Generated_Frames"
            output_folder = folder / "Generated_Video"
            metadata_folder = folder / "Metadata"
            frames_folder.mkdir(parents=True, exist_ok=True)
            output_folder.mkdir(parents=True, exist_ok=True)
            metadata_folder.mkdir(parents=True, exist_ok=True)

            enhanced_task = task.copy()
            enhanced_task.update({
                'folder': str(folder),
                'folder_name': folder.name,
                'style_name': task.get('style_name', folder.name),
                'source_dir': str(source_folder),
                'frames_dir': str(frames_folder),
                'generated_dir': str(output_folder),
                'metadata_dir': str(metadata_folder),
                'task_num': i,
            })
            valid_tasks.append(enhanced_task)
            self.logger.info(f"✓ Task {i}: {valid_count}/{len(image_files)} valid images")

        if invalid_images:
            self.processor.write_invalid_report(invalid_images, "i2i2v")
            raise ValidationError(f"{len(invalid_images)} invalid images found")

        if not valid_tasks:
            raise Exception("No valid i2i2v tasks found")
        return valid_tasks

    def _resolve_aspect_ratio(self, value):
        """Validate aspect ratio or fall back to 'auto'."""
        ratio = str(value or '').strip()
        if ratio in self.VALID_ASPECT_RATIOS:
            return ratio
        return 'auto'

    def _resolve_sound_enabled(self, task_config, api_params):
        """Resolve the Kling ``sound_enabled`` flag.

        Lookup order: per-task ``video_sound_enabled`` → ``api_params``
        ``video_sound_enabled`` → default ``True``. Accepts bools or common
        string/int truthy-falsey representations from YAML.
        """
        raw = task_config.get('video_sound_enabled')
        if raw is None:
            raw = api_params.get('video_sound_enabled', True)
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() not in ('false', '0', 'no', 'off', '')

    def _existing_generated_image(self, frames_folder, base_name):
        """Find a previously generated intermediate image for this source."""
        frames_folder = Path(frames_folder)
        for ext in ('.png', '.jpg', '.jpeg', '.webp'):
            candidate = frames_folder / f"{base_name}_image{ext}"
            if candidate.exists():
                return candidate
        return None

    def _model_max_images(self, task_config):
        """Max images the image-gen step accepts for this task's model."""
        model = task_config.get('image_model') or \
            self.api_defs.get('api_params', {}).get('image_model', '')
        return self.MODEL_MAX_IMAGES.get(model, self.DEFAULT_MODEL_MAX_IMAGES)

    def _load_additional_pool(self, task_config):
        """Load and cache the Additional-folder image pools for a task.

        Mirrors the image-generation handlers: one pool per configured folder
        (defaulting to the task's ``Additional/`` folder), each sorted by name.
        Returns a dict ``{'pools': [[Path, ...], ...], 'mode': str}``.
        """
        task_key = str(task_config.get('folder', ''))
        with self._pool_lock:
            if task_key not in self._additional_pools:
                cfg = task_config.get('multi_image_config') or {}
                folders = cfg.get('folders')
                if not folders:
                    folders = [str(Path(task_config.get('folder', '')) / 'Additional')]
                pools = []
                for fp in folders:
                    folder = Path(fp)
                    if folder.is_dir():
                        imgs = self.processor._get_files_by_type(folder, 'image')
                        imgs = sorted(imgs, key=lambda x: x.name.lower())
                        if imgs:
                            pools.append(imgs)
                            self.logger.info(f"   📂 Loaded {len(imgs)} additional images from {folder.name}")
                self._additional_pools[task_key] = {
                    'pools': pools,
                    'mode': cfg.get('mode', 'sequential'),
                }
            return self._additional_pools[task_key]

    def _source_index(self, source_path, task_config):
        """Sorted-order index of a source file (for sequential pairing)."""
        task_key = str(task_config.get('folder', ''))
        with self._pool_lock:
            if task_key not in self._source_indices:
                source_folder = Path(task_config.get('folder', '')) / 'Source'
                src = self.processor._get_files_by_type(source_folder, 'image') \
                    if source_folder.is_dir() else []
                src = sorted(src, key=lambda x: x.name.lower())
                self._source_indices[task_key] = {str(p): i for i, p in enumerate(src)}
            return self._source_indices[task_key].get(str(source_path), 0)

    def _get_additional_images(self, source_path, task_config):
        """Pick one additional image per configured folder for a source image.

        Sequential mode pairs by the source's sorted index (cycling if a pool is
        smaller); random_pairing picks at random. Capped at model_max − 1 so the
        source image itself always fits. Returns a list of path strings.
        """
        if not task_config.get('use_multi_image', False):
            return []
        data = self._load_additional_pool(task_config)
        pools = data['pools']
        if not pools:
            return []
        max_additional = self._model_max_images(task_config) - 1
        if max_additional <= 0:
            return []
        idx = self._source_index(source_path, task_config)
        picks = []
        for pool in pools:
            if not pool:
                continue
            if data['mode'] == 'random_pairing':
                picks.append(str(random.choice(pool)))
            else:
                picks.append(str(pool[idx % len(pool)]))
        return picks[:max_additional]

    def _build_image_inputs(self, source_path, task_config):
        """Resolve the ordered image inputs for the image-gen call.

        Returns ``(paths, info)`` where ``paths`` is a list of file paths (the
        primary/source first) and ``info`` records what was added, for metadata.

        Precedence: an explicit ``_selected_images`` list (random source
        selection) wins; otherwise multi-image pairing appends Additional-folder
        images; otherwise just the single source image.
        """
        selected = task_config.get('_selected_images')
        if selected:
            paths = [Path(p) for p in selected]
            return paths, {'selected_source_images': [p.name for p in paths]}
        additional = self._get_additional_images(source_path, task_config)
        if additional:
            paths = [Path(source_path)] + [Path(p) for p in additional]
            return paths, {'additional_images_used': [Path(p).name for p in additional]}
        return [Path(source_path)], {}

    def _call_image_api(self, source_path, task_config):
        """Generate an image via /nano_banana or /openai_image.

        Returns:
            tuple: (Path-to-generated-image, debug_info_dict)
        """
        api_params = self.api_defs.get('api_params', {})
        service = task_config.get('image_service') or api_params.get('image_service', 'nano_banana')
        service = str(service).strip().lower()

        if service not in ('nano_banana', 'openai_image'):
            raise ValueError(
                f"image_service must be 'nano_banana' or 'openai_image' (got {service!r})"
            )

        api_name = self.api_defs.get('image_api_names', {}).get(
            service, f"/{service}"
        )

        model = task_config.get('image_model') or api_params.get('image_model')
        resolution = str(task_config.get('image_resolution') or api_params.get('image_resolution', '1K'))
        aspect_ratio = self._resolve_aspect_ratio(
            task_config.get('image_aspect_ratio') or api_params.get('image_aspect_ratio')
        )
        prompt = task_config.get('image_prompt', '')
        if not prompt:
            raise ValueError("image_prompt is empty")

        image_inputs, input_info = self._build_image_inputs(source_path, task_config)
        images_list = [handle_file(str(p)) for p in image_inputs]
        debug = {'service': service, 'model': model, **input_info}

        # Note prefetch (producer) vs inline (consumer fallback) so the source
        # of the image-gen call is clear when stages interleave.
        where = 'prefetch' if threading.current_thread().name.startswith('i2i2v-prefetch') else 'inline'
        extra = f", images={len(images_list)}" if len(images_list) > 1 else ""
        self.logger.info(
            f"   🖼️ [IMG] {where} · service={service}, model={model}, "
            f"resolution={resolution}, aspect={aspect_ratio}{extra}"
        )

        if service == 'openai_image':
            quality = str(task_config.get('image_quality') or api_params.get('image_quality', 'auto'))
            with self._image_semaphore:
                result = self.client.predict(
                    prompt=prompt,
                    model=model,
                    quality=quality,
                    resolution=resolution,
                    aspect_ratio=aspect_ratio,
                    images=images_list,
                    api_name=api_name,
                )
            return self._parse_openai_image_response(result), debug
        else:
            with self._image_semaphore:
                result = self.client.predict(
                    prompt=prompt,
                    model=model,
                    images=images_list,
                    resolution=resolution,
                    aspect_ratio=aspect_ratio,
                    api_name=api_name,
                )
            return self._parse_nano_banana_response(result), debug

    def _parse_nano_banana_response(self, result):
        """Extract base64 image bytes from a /nano_banana response.

        Response shape: (response_id, error_msg, response_data) where
        response_data is a list of {type, data} dicts with base64 image data.
        """
        if not isinstance(result, (list, tuple)) or len(result) < 3:
            raise RuntimeError(f"Unexpected nano_banana response shape: {type(result).__name__}")
        response_id, error_msg, response_data = result[0], result[1], result[2]

        if error_msg:
            raise RuntimeError(f"nano_banana error: {error_msg}")

        text_messages = []
        for item in response_data or []:
            if not isinstance(item, dict):
                continue
            item_type = item.get('type')
            item_data = item.get('data')
            if item_data == 'BLOCKED_MODERATION':
                raise RuntimeError("nano_banana: BLOCKED_MODERATION")
            if item_type == 'Image' and item_data:
                data_str = item_data
                if data_str.startswith('image'):
                    header, b64 = data_str.split(',', 1)
                    ext = header.split('/')[1].split(';')[0]
                else:
                    b64 = data_str
                    ext = 'png'
                if not b64.strip():
                    continue
                image_bytes = base64.b64decode(b64)
                if len(image_bytes) < 100:
                    continue
                return ('bytes', image_bytes, ext, response_id)
            elif item_type == 'Text' and item_data:
                text_messages.append(str(item_data))

        msg = '; '.join(text_messages) if text_messages else 'no image in response'
        raise RuntimeError(f"nano_banana: {msg}")

    def _parse_openai_image_response(self, result):
        """Extract file path / URL / base64 from /openai_image response.

        Response shape: (list[paths_or_dicts], status_text)
        """
        image_outputs = []
        status_text = ''
        if isinstance(result, (list, tuple)):
            if len(result) >= 1:
                image_outputs = result[0] or []
            if len(result) >= 2:
                status_text = result[1] or ''
        elif isinstance(result, str):
            image_outputs = [result]
        if isinstance(image_outputs, str):
            image_outputs = [image_outputs]

        if not image_outputs:
            raise RuntimeError(f"openai_image: no output ({status_text or 'empty response'})")

        first = image_outputs[0]
        path_str = self._extract_path(first)
        if not path_str:
            raise RuntimeError(f"openai_image: could not extract path from {first!r}")

        return ('path_or_url', path_str, status_text)

    def _extract_path(self, item):
        """Pull a usable path/URL string from a Gradio result element."""
        if not item:
            return ''
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            direct = item.get('path') or item.get('name')
            if direct:
                return direct
            if 'image' in item and item['image']:
                nested = self._extract_path(item['image'])
                if nested:
                    return nested
            return item.get('url') or ''
        if isinstance(item, (list, tuple)) and item:
            return self._extract_path(item[0])
        return ''

    def _save_generated_image(self, parsed, frames_folder, base_name):
        """Persist the parsed image-api response to disk.

        Returns:
            Path: Saved file path.
        """
        frames_folder = Path(frames_folder)
        frames_folder.mkdir(parents=True, exist_ok=True)

        kind = parsed[0]
        if kind == 'bytes':
            _, image_bytes, ext, _ = parsed
            out_path = frames_folder / f"{base_name}_image.{ext}"
            out_path.write_bytes(image_bytes)
            return out_path

        # 'path_or_url'
        _, path_str, _ = parsed

        # Local filesystem path
        if not path_str.startswith(('http://', 'https://', 'data:')):
            candidate = Path(path_str)
            if candidate.is_absolute() and candidate.exists():
                ext = candidate.suffix or '.png'
                out_path = frames_folder / f"{base_name}_image{ext}"
                shutil.copy2(candidate, out_path)
                return out_path

        # data URL
        if path_str.startswith('data:'):
            header, _, payload = path_str.partition(',')
            mime = header.split(';')[0].removeprefix('data:')
            ext = '.' + mime.split('/')[-1] if '/' in mime else '.png'
            out_path = frames_folder / f"{base_name}_image{ext}"
            out_path.write_bytes(base64.b64decode(payload))
            return out_path

        # Raw base64
        if (len(path_str) >= self.BASE64_MIN_LEN
                and not path_str.startswith(('http', '/', '.'))
                and bool(re.match(r'^[A-Za-z0-9+/=]+$', path_str[:256]))):
            out_path = frames_folder / f"{base_name}_image.png"
            out_path.write_bytes(base64.b64decode(path_str))
            return out_path

        # URL download
        if path_str.startswith(('http://', 'https://')):
            download_url = path_str
        else:
            endpoint = self.config.get('testbed') or self.api_defs.get('endpoint', '')
            download_url = endpoint.rstrip('/') + (
                path_str if path_str.startswith('/') else '/' + path_str
            )
        ext = Path(path_str.split('?')[0]).suffix or '.png'
        out_path = frames_folder / f"{base_name}_image{ext}"
        if not self.processor.download_file(download_url, out_path):
            raise RuntimeError(f"openai_image: download failed from {download_url}")
        return out_path

    def _call_kling_api(self, image_path, task_config):
        """Generate a video from `image_path` via Kling /Image2Video.

        Returns:
            tuple: (url, video_dict, video_id, task_id, error_msg)
        """
        api_params = self.api_defs.get('api_params', {})
        client = self._get_kling_client()

        model = task_config.get('video_model') or api_params.get('video_model', 'v3')
        mode = task_config.get('video_mode') or api_params.get('video_mode', 'pro')
        duration = int(task_config.get('video_duration') or api_params.get('video_duration', 5))
        prompt = task_config.get('video_prompt', '')
        negative_prompt = task_config.get('video_negative_prompt', '')
        sound_enabled = self._resolve_sound_enabled(task_config, api_params)
        resolution = str(
            task_config.get('video_resolution')
            or api_params.get('video_resolution', '720p')
        ).lower()
        if resolution not in ('720p', '1080p'):
            self.logger.warning(
                f" ⚠️ Unsupported video_resolution={resolution!r}; using '720p'"
            )
            resolution = '720p'

        self.logger.info(
            f"   🎬 [VID] kling: model={model}, mode={mode}, duration={duration}, "
            f"resolution={resolution}, sound={sound_enabled}"
        )

        result = predict_image_to_video(
            client,
            image_path,
            prompt=prompt,
            mode=mode,
            duration=duration,
            cfg=0.5,
            model=model,
            negative_prompt=negative_prompt,
            sound_enabled=sound_enabled,
            multishot_type='none',
            multishot_df={"headers": ["prompt", "duration"], "data": [], "metadata": None},
            end_frame_image=None,
            resolution=resolution,
            api_name=self.api_defs.get('kling_api_name', '/Image2Video'),
        )
        return result

    def _make_api_call(self, file_path, task_config, attempt):
        """Run image-gen → video-gen for a single source image.

        Skips image-gen if a previously generated frame is on disk
        (resume-safe behaviour requested by config).
        """
        frames_folder = Path(task_config.get('frames_dir')
                             or Path(task_config['folder']) / "Generated_Frames")
        base_name = task_config.get('_base_name') or Path(file_path).stem

        # Step 1 — image gen (or reuse)
        image_start = time.time()
        existing = self._existing_generated_image(frames_folder, base_name)
        if existing:
            generated_image_path = existing
            # Input info captured when the frame was prefetched (additional /
            # selected images), so reused-frame metadata stays complete.
            prefetch_input = self._prefetch_inputs.pop(str(file_path), {})
            prefetch_time = self._prefetch_times.pop(str(file_path), None)
            if prefetch_time is not None:
                # Frame was produced ahead of time by the prefetch worker; the
                # generation cost was hidden under the previous video render.
                self.logger.info(
                    f"   🖼️ [IMG] prefetched frame ready: {existing.name} "
                    f"({prefetch_time:.1f}s, overlapped)"
                )
                image_debug = {'reused': False, 'prefetched': True, **prefetch_input}
                image_time = prefetch_time
            else:
                self.logger.info(f"   🖼️ [IMG] reusing existing frame: {existing.name}")
                image_debug = {'reused': True, **prefetch_input}
                image_time = 0.0
        else:
            parsed, image_debug = self._call_image_api(file_path, task_config)
            generated_image_path = self._save_generated_image(parsed, frames_folder, base_name)
            image_time = time.time() - image_start
            self.logger.info(f"   🖼️ [IMG] saved: {generated_image_path.name} ({image_time:.1f}s)")

        # Step 2 — video gen
        video_start = time.time()
        video_result = self._call_kling_api(generated_image_path, task_config)
        video_time = time.time() - video_start

        return {
            'video_result': video_result,
            'generated_image_path': generated_image_path,
            'image_debug': image_debug,
            'image_time': image_time,
            'video_time': video_time,
        }

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Save video + combined metadata."""
        video_result = result['video_result']
        generated_image_path = result['generated_image_path']

        # Kling returns (url, video_dict, video_id, task_id, error)
        if isinstance(video_result, (list, tuple)):
            url = video_result[0] if len(video_result) > 0 else None
            video_dict = video_result[1] if len(video_result) > 1 else None
            video_id = video_result[2] if len(video_result) > 2 else None
            task_id = video_result[3] if len(video_result) > 3 else None
            kling_error = video_result[4] if len(video_result) > 4 else None
        else:
            url, video_dict, video_id, task_id, kling_error = None, video_result, None, None, None

        processing_time = time.time() - start_time
        output_path = Path(output_folder) / f"{base_name}.mp4"
        video_saved = False

        if not kling_error:
            if url:
                video_saved = self.processor.download_file(url, output_path)
            if not video_saved and video_dict and isinstance(video_dict, dict) and 'video' in video_dict:
                local_path = Path(video_dict['video'])
                if local_path.exists():
                    shutil.copy2(local_path, output_path)
                    video_saved = True

        style_name = task_config.get('style_name', Path(task_config.get('folder', '')).name)

        metadata = {
            'source_image': file_name,
            'style_name': style_name,
            'image_service': task_config.get('image_service', 'nano_banana'),
            'image_model': task_config.get('image_model'),
            'image_quality': task_config.get('image_quality'),
            'image_resolution': task_config.get('image_resolution'),
            'image_aspect_ratio': task_config.get('image_aspect_ratio'),
            'image_prompt': task_config.get('image_prompt', ''),
            'generated_image': generated_image_path.name if generated_image_path else None,
            'image_reused': result['image_debug'].get('reused', False),
            'additional_images_used': result['image_debug'].get('additional_images_used'),
            'selected_source_images': result['image_debug'].get('selected_source_images'),
            'image_processing_time': round(result['image_time'], 1),
            'video_model': task_config.get('video_model', 'v3'),
            'video_mode': task_config.get('video_mode', 'pro'),
            'video_duration': task_config.get('video_duration', 5),
            'video_resolution': task_config.get('video_resolution', '720p'),
            'video_prompt': task_config.get('video_prompt', ''),
            'video_negative_prompt': task_config.get('video_negative_prompt', ''),
            'video_sound_enabled': self._resolve_sound_enabled(
                task_config, self.api_defs.get('api_params', {})
            ),
            'video_id': video_id,
            'task_id': task_id,
            'output_url': url,
            'video_processing_time': round(result['video_time'], 1),
            'generated_video': output_path.name if video_saved else None,
            'kling_error': kling_error or None,
            'processing_time_seconds': round(processing_time, 1),
            'processing_timestamp': datetime.now().isoformat(),
            'attempts': attempt + 1,
            'success': video_saved,
            'api_name': self.api_name,
        }

        self.processor.save_metadata(Path(metadata_folder), base_name, file_name,
                                     metadata, task_config, log_status=True)

        if video_saved:
            self.logger.info(f"   🎬 [VID] generated ✓ {output_path.name}")
        elif kling_error:
            self.logger.warning(f"   🎬 [VID] error ✗ {kling_error}")

        return video_saved

    def _generate_frame(self, file_path, frames_folder, enhanced_task):
        """Ensure ``Generated_Frames/{name}_image.*`` exists for one source image.

        Generates the intermediate image via the image testbed when missing and
        records its wall-clock time in ``self._prefetch_times`` so the later
        video stage can report the cost as overlapped/hidden. Existing frames
        (resume) are left untouched and no time is recorded.

        Failures are swallowed and returned, not raised — the caller falls back
        to inline generation, so a bad frame never crashes a worker.

        Args:
            file_path: Source image path.
            frames_folder: Path to the Generated_Frames folder.
            enhanced_task: Task config with runtime dirs populated.

        Returns:
            tuple: (ok: bool, err: str|None)
        """
        name = Path(file_path).name
        try:
            base_name = Path(file_path).stem
            if not self._existing_generated_image(frames_folder, base_name):
                self.logger.info(f"   🖼️ [IMG] gen start → {name}")
                t0 = time.time()
                parsed, debug = self._call_image_api(file_path, enhanced_task)
                self._save_generated_image(parsed, frames_folder, base_name)
                dt = time.time() - t0
                self._prefetch_times[str(file_path)] = dt
                # Stash which images fed this frame so the video stage can record
                # them in metadata when it reuses the prefetched frame.
                self._prefetch_inputs[str(file_path)] = {
                    k: debug[k] for k in ('additional_images_used', 'selected_source_images')
                    if k in debug
                }
                self.logger.info(f"   🖼️ [IMG] gen done ✓ {name} ({dt:.1f}s)")
            return True, None
        except Exception as e:  # noqa: BLE001 — surface to caller, don't crash thread
            self.logger.warning(f"   🖼️ [IMG] gen failed ✗ {name}: {e} (will retry inline)")
            return False, str(e)

    def _prefetch_worker(self, pending, frames_folder, enhanced_task, ready_q):
        """Generate intermediate frames one (or a few) steps ahead of video-gen.

        Runs in a background thread. For each pending source image it ensures
        `Generated_Frames/{name}_image.*` exists (generating via the image
        testbed if missing), then signals readiness on `ready_q`. The queue is
        bounded, so this stays only ~prefetch_depth images ahead of the serial
        video stage instead of racing through every image up front.

        Image-gen failures are swallowed and reported via the queue — the
        consumer falls back to inline generation, so a bad frame never crashes
        the run or stalls the pipeline.
        """
        for file_path in pending:
            _ok, err = self._generate_frame(file_path, frames_folder, enhanced_task)
            ready_q.put((file_path, err))

    def _process_two_phase_concurrent(self, pending, enhanced_task, frames_folder,
                                      output_folder, metadata_folder,
                                      image_concurrency, video_concurrency):
        """Two-phase concurrent pipeline: all frames, then all videos.

        Phase 1 generates every pending frame in parallel (up to
        ``image_concurrency`` workers) against the image testbed, sized via a
        temporary semaphore swapped into ``self._image_semaphore``. Phase 2 then
        renders every video in parallel (up to ``video_concurrency`` workers) via
        ``processor.process_file``; because the frames already exist, each video
        worker reuses its pre-made frame (and reports the image cost as
        overlapped through ``self._prefetch_times``) instead of regenerating it.

        A frame that fails in Phase 1 simply won't exist, so its Phase 2 worker
        falls back to inline image-gen — the same behaviour as a prefetch miss
        in the serial path.

        Args:
            pending: Source image paths still needing processing.
            enhanced_task: Task config with runtime dirs already populated.
            frames_folder: Path to the Generated_Frames folder.
            output_folder: Path to the Generated_Video folder.
            metadata_folder: Path to the Metadata folder.
            image_concurrency: Max parallel image-gen workers (Phase 1).
            video_concurrency: Max parallel video-gen workers (Phase 2).

        Returns:
            int: Number of images that produced a video successfully.
        """
        # Phase 1 — generate all intermediate frames in parallel.
        self.logger.info(
            f" 🖼️ Phase 1/2: generating {len(pending)} frames "
            f"(up to {image_concurrency} concurrent)"
        )
        prev_semaphore = self._image_semaphore
        self._image_semaphore = threading.Semaphore(image_concurrency)
        try:
            self._run_concurrent(
                pending,
                lambda fp: self._generate_frame(fp, frames_folder, enhanced_task)[0],
                image_concurrency,
            )

            # Phase 2 — render all videos in parallel, reusing the frames above.
            self.logger.info(
                f" 🎬 Phase 2/2: generating {len(pending)} videos "
                f"(up to {video_concurrency} concurrent)"
            )

            def run_video(file_path):
                self.logger.info(f" 🎬 [VID] {file_path.name}")
                # Per-call copy so concurrent threads never mutate the same dict.
                return self.processor.process_file(
                    file_path, dict(enhanced_task), output_folder, metadata_folder
                )

            return self._run_concurrent(pending, run_video, video_concurrency)
        finally:
            self._image_semaphore = prev_semaphore
            self._prefetch_times.clear()

    def process_task(self, task, task_num, total_tasks):
        """Iterate source images and run the pipeline for each.

        Two execution modes, selected by the resolved concurrency caps:

        * Concurrent (``image_concurrency > 1`` or ``video_concurrency > 1``) —
          a two-phase pipeline: every frame is generated in parallel (capped by
          ``image_concurrency``, which can exceed the video cap since the image
          testbed has more headroom), then every video is rendered in parallel
          (capped by ``video_concurrency``).
        * Serial (both caps == 1) — image-gen (separate testbed) is pipelined
          one step ahead of the serial Kling video stage via a bounded
          producer/consumer queue, so the image cost for image N+1 is hidden
          under the video render for image N.

        Caps resolve per stage via ``image_concurrency`` / ``video_concurrency``,
        each falling back to the shared ``concurrent_requests`` (then 1).

        When ``use_random_source_selection`` is set, delegates to the
        iteration-based path instead of the 1-source-per-video pipeline.
        """
        folder = Path(task.get('folder', ''))
        source_folder = Path(task.get('source_dir', folder / "Source"))
        frames_folder = Path(task.get('frames_dir', folder / "Generated_Frames"))
        output_folder = Path(task.get('generated_dir', folder / "Generated_Video"))
        metadata_folder = Path(task.get('metadata_dir', folder / "Metadata"))

        frames_folder.mkdir(parents=True, exist_ok=True)
        output_folder.mkdir(parents=True, exist_ok=True)
        metadata_folder.mkdir(parents=True, exist_ok=True)

        if task.get('use_random_source_selection', False):
            self._process_task_random_source(
                task, task_num, total_tasks, folder, source_folder,
                frames_folder, output_folder, metadata_folder,
            )
            return

        style_name = task.get('style_name', folder.name)
        image_concurrency = self._get_stage_concurrency(task, 'image_concurrency')
        video_concurrency = self._get_stage_concurrency(task, 'video_concurrency')
        use_concurrent = image_concurrency > 1 or video_concurrency > 1
        suffix = f" (img×{image_concurrency} → vid×{video_concurrency})" if use_concurrent else ""
        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {style_name}{suffix}")

        source_files = self.processor._get_files_by_type(source_folder, 'image')
        if not source_files:
            self.logger.warning(f" ⚠️ No source images found in {source_folder}")
            return

        self.logger.info(f" 📸 Found {len(source_files)} source images")

        # Make sure runtime fields are propagated to per-file task configs
        enhanced_task = task.copy()
        enhanced_task['frames_dir'] = str(frames_folder)

        # Partition up front: already-finished images are skipped (and never
        # prefetched), so resuming a run does no redundant image-gen.
        total = len(source_files)
        pending = []
        successful = 0
        skipped = 0
        for i, file_path in enumerate(source_files, 1):
            is_complete, status = self._get_processing_status(file_path, metadata_folder)
            if is_complete:
                if status == 'success':
                    self.logger.info(f" ⏭️ {i}/{total}: {file_path.name} (already processed)")
                    successful += 1
                else:
                    self.logger.info(f" ⏭️ {i}/{total}: {file_path.name} (failed - max retries reached)")
                skipped += 1
            else:
                pending.append(file_path)

        if not pending:
            self.logger.info(f"✓ Task {task_num}: {successful}/{total} successful ({skipped} skipped)")
            return

        # Concurrent mode: two-phase parallel frames → parallel videos.
        if use_concurrent:
            successful += self._process_two_phase_concurrent(
                pending, enhanced_task, frames_folder, output_folder, metadata_folder,
                image_concurrency, video_concurrency,
            )
            self.logger.info(f"✓ Task {task_num}: {successful}/{total} successful ({skipped} skipped)")
            return

        # Producer pre-generates frames; depth-1 queue keeps it ~1 image ahead
        # of the serial video stage (override via api_defs `prefetch_depth`).
        prefetch_depth = max(1, int(self.api_defs.get('prefetch_depth', 1)))
        ready_q = queue.Queue(maxsize=prefetch_depth)
        producer = threading.Thread(
            target=self._prefetch_worker,
            args=(pending, frames_folder, enhanced_task, ready_q),
            name=f"i2i2v-prefetch-{task_num}",
            daemon=True,
        )
        producer.start()

        try:
            for idx, _expected in enumerate(pending, 1):
                file_path, prefetch_err = ready_q.get()  # in-order: single producer
                note = " · prefetch missed → inline image-gen" if prefetch_err else ""
                self.logger.info("")  # blank line separates each video block
                self.logger.info(f" {'─' * 56}")
                self.logger.info(f" 🎬 [VID] {idx}/{len(pending)} · {file_path.name}{note}")

                if self.processor.process_file(file_path, enhanced_task, output_folder, metadata_folder):
                    successful += 1

                if idx < len(pending):
                    # Paces Kling submissions; the next frame prefetches during this wait.
                    time.sleep(self.api_defs.get('rate_limit', 5))
        finally:
            # Drain any unconsumed signals so a producer blocked on a full
            # queue (e.g. consumer exited early) can finish and the thread joins.
            while producer.is_alive():
                try:
                    ready_q.get_nowait()
                except queue.Empty:
                    producer.join(timeout=1)
            self._prefetch_times.clear()

        self.logger.info(f"✓ Task {task_num}: {successful}/{total} successful ({skipped} skipped)")

    def _process_task_random_source(self, task, task_num, total_tasks, folder,
                                    source_folder, frames_folder, output_folder,
                                    metadata_folder):
        """Iteration-based pipeline for random source selection.

        Builds a reproducible selection plan (same config + Source folder =
        same selections) picking ``min_images``–``max_images`` images from the
        Source folder per iteration. Each iteration runs image-gen on the
        selected images → one frame → one Kling video, named after the
        iteration (``iterNNN_...``). Resume-safe: iterations whose metadata
        already records success/exhaustion are skipped, and an existing
        ``{base}_image.*`` frame is reused (video-only re-runs).
        """
        style_name = task.get('style_name', folder.name)
        source_images = self.processor._get_files_by_type(source_folder, 'image')
        source_images = sorted(source_images, key=lambda x: x.name.lower())
        if not source_images:
            self.logger.warning(f" ⚠️ No source images found in {source_folder}")
            return

        model_max = self._model_max_images(task)
        selection_plan, selection_mode = build_selection_plan(
            source_images, task, model_max, 1, self.logger
        )
        if not selection_plan:
            self.logger.warning(f" ⚠️ Empty selection plan for {style_name}")
            return

        num_iterations = len(selection_plan)
        workers = self._get_stage_concurrency(task, 'video_concurrency')
        suffix = f" (random source · {selection_mode})"
        self.logger.info(
            f"📁 Task {task_num}/{total_tasks}: {style_name}{suffix} — "
            f"{num_iterations} iterations, {len(source_images)} source images"
        )

        # Partition up front so already-finished iterations are skipped.
        work_items = []
        successful = 0
        skipped = 0
        for it_idx, selected in enumerate(selection_plan):
            if not selected:
                continue
            primary = selected[0]
            if len(selected) == 1:
                base_name = f"iter{it_idx:03d}_{primary.stem}"
            else:
                names = "_".join(img.stem for img in selected)
                if len(names) > 150:
                    names = names[:147] + "..."
                base_name = f"iter{it_idx:03d}_{names}"

            is_complete, status = self._get_processing_status(
                primary, metadata_folder, base_name=base_name
            )
            if is_complete:
                if status == 'success':
                    successful += 1
                skipped += 1
                continue
            work_items.append((it_idx, base_name, primary, selected))

        if not work_items:
            self.logger.info(
                f"✓ Task {task_num}: {successful}/{num_iterations} successful ({skipped} skipped)"
            )
            return

        def run_one(item):
            it_idx, base_name, primary, selected = item
            per_call = task.copy()
            per_call['frames_dir'] = str(frames_folder)
            per_call['_base_name'] = base_name
            per_call['_selected_images'] = [str(p) for p in selected]
            self.logger.info(
                f" 🎲 {it_idx + 1}/{num_iterations}: {base_name} ({len(selected)} images)"
            )
            return self.processor.process_file(
                primary, per_call, output_folder, metadata_folder
            )

        if workers > 1:
            self.logger.info(
                f" 🚀 Dispatching {len(work_items)} iterations, up to {workers} concurrent"
            )
            successful += self._run_concurrent(work_items, run_one, workers)
        else:
            for idx, item in enumerate(work_items):
                if run_one(item):
                    successful += 1
                if idx < len(work_items) - 1:
                    time.sleep(self.api_defs.get('rate_limit', 5))

        self.logger.info(
            f"✓ Task {task_num}: {successful}/{num_iterations} successful ({skipped} skipped)"
        )

    def validate_file(self, file_path, file_type='image'):
        """Validate input image with i2i2v's relaxed limits."""
        if file_type == 'video':
            return super().validate_file(file_path, file_type)
        try:
            validation_rules = self.api_defs.get('validation', {})
            file_path_obj = file_path if isinstance(file_path, Path) else Path(file_path)
            file_size_mb = file_path_obj.stat().st_size / (1024 * 1024)
            # Source-image limits match nano_banana / openai_image (the upstream image step).
            # Generated frame size is independent — the image API upscales to >=1K,
            # which clears Kling's stricter 300px minimum for the video step.
            min_dim = validation_rules.get('min_dimension', 100)
            max_size = validation_rules.get('max_size_mb', 32)

            with Image.open(file_path) as img:
                w, h = img.size
                if file_size_mb >= max_size:
                    return False, f"Size > {max_size}MB"
                if w < min_dim or h < min_dim:
                    return False, f"Dims {w}x{h} too small"
                return True, f"{w}x{h}"
        except Exception as e:
            return False, f"Error: {str(e)}"

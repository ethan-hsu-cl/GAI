"""Kling Omni Image-to-Video API Handler.

Drives the Kling testbed's /omniGenerate route (Kling O1 'omni' / O3
'omni-v3') in image-to-video mode: each source image is sent as img1 with
type 'start' alongside the task prompt. The video input, img2-img7 and the
element IDs are all left empty — the endpoint accepts None / '' for them even
though its docs list them as required.

Each style folder holds its own Source images; generated videos are named after
the source image plus the generation number, mirroring wan_v3_i2v.
"""
from pathlib import Path
import shutil
import time
from gradio_client import handle_file
from .base_handler import BaseAPIHandler


class KlingOmniHandler(BaseAPIHandler):
    """Kling Omni image-to-video handler."""

    # Image slots on /omniGenerate (img1 carries the source, the rest stay empty)
    IMAGE_SLOTS = 7

    # Generation settings with their endpoint defaults
    SETTING_DEFAULTS = {
        'model': 'omni-v3',
        'mode': 'pro',
        'duration': 5,
        'aspect_ratio': '16:9',
        'sound_enabled': False,
        'multishot_type': 'none',
        'image_type': 'start',
    }

    EMPTY_MULTISHOT = {"headers": ["prompt", "duration"], "data": [], "metadata": None}

    def _settings(self, task_config):
        """Resolve generation settings for one call.

        Precedence: per-task value -> config default_settings -> api_params in
        api_definitions.json -> the endpoint default in SETTING_DEFAULTS.

        Args:
            task_config: Task configuration dictionary.

        Returns:
            dict: Resolved settings keyed by setting name.
        """
        defaults = self.config.get('default_settings', {}) or {}
        api_params = self.api_defs.get('api_params', {}) or {}

        resolved = {}
        for key, endpoint_default in self.SETTING_DEFAULTS.items():
            if task_config.get(key) is not None:
                resolved[key] = task_config[key]
            elif defaults.get(key) is not None:
                resolved[key] = defaults[key]
            elif api_params.get(key) is not None:
                resolved[key] = api_params[key]
            else:
                resolved[key] = endpoint_default
        return resolved

    def validate_structure(self, tasks, config):
        """Validate Kling Omni with folder/Source images and generation_count.

        Args:
            tasks: List of task configuration dictionaries.
            config: Full processor configuration dictionary.

        Returns:
            list: Valid enhanced task dictionaries.

        Raises:
            Exception: If no valid tasks found.
        """
        valid_tasks = []
        invalid_images = []

        for i, task in enumerate(tasks, 1):
            if not task.get('prompt'):
                self.logger.warning(f"⚠️ Task {i}: Missing prompt")
                continue

            folder = Path(task.get('folder', ''))
            if not task.get('folder'):
                self.logger.warning(f"⚠️ Task {i}: Missing folder path")
                continue

            folder.mkdir(parents=True, exist_ok=True)
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

            output_folder = folder / "Generated_Video"
            metadata_folder = folder / "Metadata"
            output_folder.mkdir(parents=True, exist_ok=True)
            metadata_folder.mkdir(parents=True, exist_ok=True)

            generation_count = self._generation_count(task, config)

            enhanced_task = task.copy()
            enhanced_task.update({
                'folder': str(folder),
                'folder_name': folder.name,
                'style_name': task.get('style_name', folder.name),
                'source_dir': str(source_folder),
                'generated_dir': str(output_folder),
                'metadata_dir': str(metadata_folder),
                'generation_count': generation_count,
                'task_num': i
            })
            valid_tasks.append(enhanced_task)
            self.logger.info(
                f"✓ Task {i}: {valid_count} images × {generation_count} generations "
                f"= {valid_count * generation_count} videos"
            )

        if invalid_images:
            self.processor.write_invalid_report(invalid_images, "kling_omni")
            self.logger.warning(f"⚠️ {len(invalid_images)} invalid images found (see report)")

        if not valid_tasks:
            raise Exception("No valid Kling Omni tasks found")
        return valid_tasks

    @staticmethod
    def _generation_count(task, config):
        """Per-task generation_count, else the config-wide one, at least 1."""
        task_count = task.get('generation_count')
        count = task_count if task_count is not None else config.get('generation_count', 1)
        try:
            return max(int(count), 1)
        except (TypeError, ValueError):
            return 1

    def _make_api_call(self, file_path, task_config, attempt):
        """Call /omniGenerate with the source image as img1.

        Args:
            file_path: Path to the source image.
            task_config: Task configuration dictionary.
            attempt: Current attempt number.

        Returns:
            tuple: (video_url, video_dict, video_id, task_id, error_message).
        """
        settings = self._settings(task_config)

        images = {}
        for n in range(1, self.IMAGE_SLOTS + 1):
            images[f'img{n}'] = None
            images[f'img{n}_type'] = 'reference'
        images['img1'] = handle_file(str(file_path))
        images['img1_type'] = settings['image_type']

        return self.client.predict(
            prompt=task_config.get('prompt', ''),
            video_file=None,
            video_type='feature',
            keep_sound=False,
            **images,
            element_ids_str='',
            model=settings['model'],
            mode=settings['mode'],
            duration=int(settings['duration']),
            aspect_ratio=settings['aspect_ratio'],
            sound_enabled=bool(settings['sound_enabled']),
            multishot_type=settings['multishot_type'],
            multishot_df=task_config.get('multishot_df') or self.EMPTY_MULTISHOT,
            api_name=self.api_defs['api_name']
        )

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Save the generated video and per-generation metadata.

        Args:
            result: Tuple (video_url, video_dict, video_id, task_id, error_message).
            file_path: Path to the source image.
            task_config: Task configuration dict.
            output_folder: Path to output folder.
            metadata_folder: Path to metadata folder.
            base_name: Base name for output files.
            file_name: Source file name.
            start_time: Processing start time.
            attempt: Current attempt number.

        Returns:
            bool: True if successful, False otherwise.
        """
        url, video_dict, video_id, task_id, error = result[:5]
        settings = self._settings(task_config)
        gen_num = task_config.get('generation_number', 1)
        output_filename = f"{base_name}_{gen_num}.mp4"
        output_path = Path(output_folder) / output_filename

        self.logger.info(f"   Video ID: {video_id}, Task ID: {task_id}")

        video_saved = False
        if not error:
            if url:
                video_saved = self.processor.download_file(url, output_path)
            if not video_saved and isinstance(video_dict, dict) and video_dict.get('video'):
                local_path = Path(video_dict['video'])
                if local_path.exists():
                    shutil.copy2(local_path, output_path)
                    video_saved = True

        metadata = {
            'source_image': file_name,
            'style_name': task_config.get('style_name', ''),
            'generation_number': gen_num,
            'output_url': url,
            'video_id': video_id,
            'task_id': task_id,
            'model': settings['model'],
            'mode': settings['mode'],
            'duration': settings['duration'],
            'aspect_ratio': settings['aspect_ratio'],
            'sound_enabled': settings['sound_enabled'],
            'attempts': attempt + 1,
            'success': video_saved,
            'processing_time_seconds': round(time.time() - start_time, 1),
        }

        if video_saved:
            self.logger.info(f" ✅ Generated: {output_filename}")
            metadata['generated_video'] = output_filename
        elif error:
            self.logger.info(f" ❌ API Error: {error}")
            metadata['error'] = error
        else:
            self.logger.info("   ❌ No video returned by the API")
            metadata['error'] = 'Video download/save failed'

        # Metadata is keyed per generation so re-runs can resume mid-task
        self.processor.save_metadata(Path(metadata_folder), f"{base_name}_{gen_num}",
                                     file_name, metadata, task_config)
        return video_saved

    def failure_base_name(self, file_path, task_config):
        """Name failure records per generation, as _handle_result does."""
        base_name = super().failure_base_name(file_path, task_config)
        if file_path is None:
            return base_name
        return f"{base_name}_{task_config.get('generation_number', 1)}"

    def process_task(self, task, task_num, total_tasks):
        """Process every source image × generation_count for one style folder.

        Skip checks run single-threaded; the remaining generations run in
        parallel when concurrent_requests > 1.

        Args:
            task: Task configuration dictionary.
            task_num: Current task number.
            total_tasks: Total number of tasks.
        """
        folder = Path(task.get('folder', ''))
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Video"
        metadata_folder = folder / "Metadata"
        output_folder.mkdir(parents=True, exist_ok=True)
        metadata_folder.mkdir(parents=True, exist_ok=True)

        style_name = task.get('style_name', folder.name)
        generation_count = self._generation_count(task, self.config)
        concurrent_requests = self._get_concurrent_requests(task)

        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {style_name}")

        source_files = self.processor._get_files_by_type(source_folder, 'image')
        if not source_files:
            self.logger.warning(f" ⚠️ No source images found in {source_folder}")
            return

        total = len(source_files) * generation_count
        self.logger.info(
            f" 📸 Found {len(source_files)} source images × {generation_count} generations = {total} total"
        )

        successful = 0
        skipped = 0
        work = []
        for file_path in source_files:
            for gen_num in range(1, generation_count + 1):
                gen_base = f"{file_path.stem}_{gen_num}"
                is_complete, status = self._get_processing_status(
                    file_path, metadata_folder, base_name=gen_base)
                if is_complete:
                    reason = 'already processed' if status == 'success' else 'failed - max retries reached'
                    self.logger.info(f" ⏭️ {gen_base} ({reason})")
                    successful += status == 'success'
                    skipped += 1
                    continue
                task_with_gen = dict(task)
                task_with_gen['generation_number'] = gen_num
                task_with_gen['style_name'] = style_name
                work.append((file_path, task_with_gen))

        def run_one(item):
            file_path, task_with_gen = item
            self.logger.info(
                f" 🎬 {file_path.name} → {file_path.stem}_{task_with_gen['generation_number']}.mp4"
            )
            return self.processor.process_file(file_path, task_with_gen,
                                               output_folder, metadata_folder)

        if concurrent_requests > 1 and len(work) > 1:
            self.logger.info(
                f" 🚀 Dispatching {len(work)} API calls with up to {concurrent_requests} in parallel"
            )
            successful += self._run_concurrent(work, run_one, concurrent_requests)
        else:
            for i, item in enumerate(work, 1):
                if run_one(item):
                    successful += 1
                if i < len(work):
                    time.sleep(self.api_defs.get('rate_limit', 3))

        self.logger.info(f"✓ Task {task_num}: {successful}/{total} successful ({skipped} skipped)")

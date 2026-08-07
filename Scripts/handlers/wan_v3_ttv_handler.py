"""Wan V3 Text-to-Video API Handler.

Drives the /wan_v3 route in prompt-only mode: every media input (reference image
and video galleries, audio, first/last frame, document, web page URL) is left
empty, so the endpoint generates purely from the text prompt.
"""
from pathlib import Path
import time
from .wan_v3_base import WanV3BaseHandler


class WanV3TTVHandler(WanV3BaseHandler):
    """
    Wan V3 Text-to-Video handler.

    Generates videos from text prompts alone. All generations for a config land in
    a single root output_folder, mirroring the other TTV handlers.
    """

    def validate_structure(self, tasks, config):
        """Validate Wan V3 TTV text-to-video structure.

        Args:
            tasks: List of task configuration dictionaries.
            config: Full processor configuration dictionary.

        Returns:
            list: Valid task dictionaries.

        Raises:
            Exception: If no valid tasks found.
        """
        return self._validate_text_to_video_structure(tasks)

    def _make_api_call(self, file_path, task_config, attempt):
        """Make Wan V3 TTV API call (prompt only).

        Args:
            file_path: Ignored (text-to-video has no input file).
            task_config: Task configuration dict.
            attempt: Current attempt number.

        Returns:
            tuple: API response tuple.
        """
        return self._predict_wan_v3(task_config)

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Wan V3 TTV API result.

        Response tuple:
            [0] generated video dict {video: filepath, subtitles: filepath|None}
            [1] task ID

        Args:
            result: Tuple containing API response fields.
            file_path: Ignored (text-to-video).
            task_config: Task configuration dict.
            output_folder: Path to output folder.
            metadata_folder: Path to metadata folder.
            base_name: Base name for output files.
            file_name: Ignored (text-to-video).
            start_time: Processing start time.
            attempt: Current attempt number.

        Returns:
            bool: True if successful, False otherwise.
        """
        video_dict, task_id = self._parse_wan_v3_result(result)

        if task_id:
            self.logger.info(f"   Task ID: {task_id}")

        style_name = task_config.get('style_name', 'wan_v3_ttv')
        gen_num = task_config.get('generation_number', 1)

        output_video_name = f"{base_name}_generated.mp4"
        output_path = Path(output_folder) / output_video_name
        video_saved = self._save_video(video_dict, output_path)

        processing_time = time.time() - start_time
        metadata = {
            'style_name': style_name,
            'generation_number': gen_num,
            **self._wan_v3_metadata(task_config, task_id, processing_time, attempt, video_saved)
        }

        if not video_saved:
            self.logger.info("   ❌ No video returned by the API")
            metadata['error'] = 'Video download/save failed'
            self.processor.save_metadata(Path(metadata_folder), base_name, file_name,
                                         metadata, task_config)
            return False

        self.logger.info(f"   ✅ Generated: {output_path.name}")

        metadata['generated_video'] = output_video_name
        subtitles = self._subtitles(video_dict)
        if subtitles:
            metadata['subtitles'] = subtitles

        self.processor.save_metadata(Path(metadata_folder), base_name, file_name,
                                     metadata, task_config, log_status=True)

        return True

    def process_task(self, task, task_num, total_tasks):
        """Process entire Wan V3 TTV task.

        Each task generates one or more videos based on generation_count.

        Args:
            task: Task configuration dictionary.
            task_num: Current task number.
            total_tasks: Total number of tasks.
        """
        root_folder = Path(self.config.get('output_folder', ''))

        output_folder = root_folder / "Generated_Video"
        metadata_folder = root_folder / "Metadata"

        output_folder.mkdir(parents=True, exist_ok=True)
        metadata_folder.mkdir(parents=True, exist_ok=True)

        style_name = task.get('style_name', f'Task{task_num}')
        task_count = task.get('generation_count')
        global_count = self.config.get('generation_count', 1)
        generation_count = task_count if task_count is not None else global_count

        if generation_count < 1:
            generation_count = 1

        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {style_name} ({generation_count} generations)")

        successful = 0
        skipped = 0
        max_retries = self.api_defs.get('max_retries', 3)
        for gen_num in range(1, generation_count + 1):
            base_name = f"{self._safe_style(style_name)}-{gen_num}"
            metadata_file = metadata_folder / f"{base_name}_metadata.json"

            if metadata_file.exists():
                try:
                    import json
                    with open(metadata_file, 'r') as f:
                        meta = json.load(f)
                    if meta.get('success', False):
                        self.logger.info(f" ⏭️ Generation {gen_num}/{generation_count}: {style_name}-{gen_num} (already processed)")
                        skipped += 1
                        successful += 1
                        continue
                    attempts = meta.get('attempts', 0)
                    if not meta.get('success', False) and attempts >= max_retries:
                        self.logger.info(f" ⏭️ Generation {gen_num}/{generation_count}: {style_name}-{gen_num} (failed - max retries reached)")
                        skipped += 1
                        continue
                except (json.JSONDecodeError, IOError):
                    pass

            self.logger.info(f" 🎬 Generation {gen_num}/{generation_count}: {style_name}-{gen_num}")

            task_with_gen = task.copy()
            task_with_gen['generation_number'] = gen_num
            task_with_gen['style_name'] = style_name

            if 'design_link' not in task_with_gen:
                task_with_gen['design_link'] = self.config.get('design_link', '')
            if 'source_video_link' not in task_with_gen:
                task_with_gen['source_video_link'] = self.config.get('source_video_link', '')

            if self.processor.process_file(None, task_with_gen, output_folder, metadata_folder):
                successful += 1

            if gen_num < generation_count:
                time.sleep(self.api_defs.get('rate_limit', 3))

        self.logger.info(f"✓ Task {task_num}: {successful}/{generation_count} successful ({skipped} skipped)")

    @staticmethod
    def _safe_style(style_name):
        """Convert a style name into a filesystem-safe base name component."""
        safe = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in style_name)
        return safe.strip().replace(' ', '_')

    def process(self, file_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process a single Wan V3 TTV generation.

        Args:
            file_path: Ignored (text-to-video has no input file).
            task_config: Task configuration dict.
            output_folder: Path to output folder.
            metadata_folder: Path to metadata folder.
            attempt: Current attempt number.
            max_retries: Maximum number of retries.

        Returns:
            bool: True if successful, False otherwise.
        """
        style_name = task_config.get('style_name', 'wan_v3_ttv')
        gen_num = task_config.get('generation_number', 1)
        base_name = f"{self._safe_style(style_name)}-{gen_num}"

        file_name = None
        start_time = time.time()

        try:
            result = self._make_api_call(file_path, task_config, attempt)

            success = self._handle_result(result, file_path, task_config, output_folder,
                                          metadata_folder, base_name, file_name, start_time, attempt)

            if not success and attempt < max_retries - 1:
                time.sleep(5)
                return False

            return success

        except Exception as e:
            self.logger.error(f"   ❌ Error: {e}")
            raise

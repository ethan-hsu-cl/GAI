"""Wan V3 Video-to-Video API Handler.

Drives the /wan_v3 route in reference-video mode: each source video is sent as
the single entry of the "Reference Videos (max 5)" gallery alongside the task
prompt. The reference-image gallery, audio, first/last frame, document, and web
page URL are all left empty.

Each style folder holds its own Source videos; generated videos are named after
the source video plus the generation number, mirroring wan_v3_i2v.
"""
from pathlib import Path
import json
import time
from .wan_v3_base import WanV3BaseHandler


class WanV3V2vHandler(WanV3BaseHandler):
    """
    Wan V3 video-to-video handler.

    Handles video-to-video generation where each style folder contains source
    videos and generated videos are named based on the source video.
    """

    def validate_structure(self, tasks, config):
        """Validate Wan V3 V2V with folder/Source videos and generation_count.

        Args:
            tasks: List of task configuration dictionaries.
            config: Full processor configuration dictionary.

        Returns:
            list: Valid enhanced task dictionaries.

        Raises:
            Exception: If no valid tasks found.
        """
        valid_tasks = []
        invalid_videos = []

        for i, task in enumerate(tasks, 1):
            if not task.get('prompt'):
                self.logger.warning(f"⚠️ Task {i}: Missing prompt")
                continue

            folder = Path(task.get('folder', ''))
            if not folder or str(folder) == '':
                self.logger.warning(f"⚠️ Task {i}: Missing folder path")
                continue

            folder.mkdir(parents=True, exist_ok=True)
            source_folder = folder / "Source"
            source_folder.mkdir(exist_ok=True)

            video_files = self.processor._get_files_by_type(source_folder, 'video')
            if not video_files:
                self.logger.warning(f"⚠️ Task {i}: No videos found in {source_folder}")
                continue

            valid_count = 0
            for video_file in video_files:
                is_valid, reason = self.validate_file(video_file, 'video')
                if not is_valid:
                    invalid_videos.append({
                        'folder': folder.name, 'filename': video_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1

            if valid_count == 0:
                self.logger.warning(f"⚠️ Task {i}: No valid videos in {source_folder}")
                continue

            output_folder = folder / "Generated_Video"
            metadata_folder = folder / "Metadata"
            output_folder.mkdir(parents=True, exist_ok=True)
            metadata_folder.mkdir(parents=True, exist_ok=True)

            task_count = task.get('generation_count')
            global_count = config.get('generation_count', 1)
            generation_count = task_count if task_count is not None else global_count

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
            total_expected = valid_count * generation_count
            self.logger.info(
                f"✓ Task {i}: {valid_count} videos × {generation_count} generations = {total_expected} videos"
            )

        if invalid_videos:
            self.processor.write_invalid_report(invalid_videos, "wan_v3_v2v")
            self.logger.warning(f"⚠️ {len(invalid_videos)} invalid videos found (see report)")

        if not valid_tasks:
            raise Exception("No valid Wan V3 V2V tasks found")
        return valid_tasks

    def _make_api_call(self, file_path, task_config, attempt):
        """Make Wan V3 V2V API call with the source video in the video gallery.

        Args:
            file_path: Path to the source video.
            task_config: Task configuration dictionary.
            attempt: Current attempt number.

        Returns:
            tuple: API response tuple.
        """
        return self._predict_wan_v3(
            task_config,
            videos=self._video_gallery([file_path])
        )

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Wan V3 V2V API result.

        Args:
            result: Tuple containing (video_dict, task_id).
            file_path: Path to the source video.
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
        video_dict, task_id = self._parse_wan_v3_result(result)

        if task_id:
            self.logger.info(f"   Task ID: {task_id}")

        gen_num = task_config.get('generation_number', 1)
        output_filename = f"{base_name}_{gen_num}.mp4"
        output_path = Path(output_folder) / output_filename
        video_saved = self._save_video(video_dict, output_path)

        processing_time = time.time() - start_time
        metadata = {
            'source_video': file_name,
            'style_name': task_config.get('style_name', ''),
            'generation_number': gen_num,
            **self._wan_v3_metadata(task_config, task_id, processing_time, attempt, video_saved)
        }

        if video_saved:
            self.logger.info(f" ✅ Generated: {output_path.name}")
            metadata['generated_video'] = output_filename
            subtitles = self._subtitles(video_dict)
            if subtitles:
                metadata['subtitles'] = subtitles
        else:
            self.logger.info("   ❌ No video returned by the API")
            metadata['error'] = 'Video download/save failed'

        # Metadata is keyed per generation so re-runs can resume mid-task
        gen_base_name = f"{base_name}_{gen_num}"
        self.processor.save_metadata(Path(metadata_folder), gen_base_name, file_name,
                                     metadata, task_config)

        return video_saved

    def failure_base_name(self, file_path, task_config):
        """Name failure records per generation, as _handle_result does.

        Results are saved as "{base_name}_{gen_num}" and both the resume check
        and the report generator look them up that way, so a failure recorded
        under the bare source name is never read back.
        """
        base_name = super().failure_base_name(file_path, task_config)
        if file_path is None:
            return base_name
        return f"{base_name}_{task_config.get('generation_number', 1)}"

    def _get_generation_status(self, base_name, gen_num, metadata_folder):
        """Get processing status for a specific generation.

        Args:
            base_name: Base name of the source file.
            gen_num: Generation number.
            metadata_folder: Path to the metadata folder.

        Returns:
            tuple: (is_complete, status_reason) where status_reason is
                'success', 'failed_exhausted', or None if not complete.
        """
        gen_base_name = f"{base_name}_{gen_num}"
        metadata_file = Path(metadata_folder) / f"{gen_base_name}_metadata.json"

        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                if metadata.get('success', False):
                    return True, 'success'

                max_retries = self.api_defs.get('max_retries', 3)
                attempts = metadata.get('attempts', 0)
                if attempts >= max_retries:
                    return True, 'failed_exhausted'

                return False, None
            except (json.JSONDecodeError, IOError):
                return False, None
        return False, None

    def process_task(self, task, task_num, total_tasks):
        """Process entire Wan V3 V2V task.

        Iterates over source videos in the style folder and generates
        multiple videos per source based on generation_count.

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

        task_count = task.get('generation_count')
        global_count = self.config.get('generation_count', 1)
        generation_count = task_count if task_count is not None else global_count

        if generation_count < 1:
            generation_count = 1

        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {style_name}")

        source_files = self.processor._get_files_by_type(source_folder, 'video')

        if not source_files:
            self.logger.warning(f" ⚠️ No source videos found in {source_folder}")
            return

        # Drop invalid sources before any upload. The backend enforces a 15 s cap
        # on the reference video and rejects a longer one only after the whole
        # file has been uploaded, so skipping here saves a full upload per file
        # instead of trading it for an InvalidParameter failure.
        valid_files, rejected = [], []
        for f in source_files:
            is_valid, reason = self.validate_file(f, 'video')
            (valid_files if is_valid else rejected).append(f if is_valid else (f, reason))

        if rejected:
            self.logger.warning(
                f" ⚠️ Skipping {len(rejected)} source video(s) that fail validation:"
            )
            for f, reason in rejected:
                self.logger.warning(f"      {f.name}: {reason}")

        if not valid_files:
            self.logger.warning(
                f" ⚠️ No valid source videos in {source_folder} — nothing to generate"
            )
            return

        source_files = valid_files
        total_generations = len(source_files) * generation_count
        self.logger.info(
            f" 🎞️ Found {len(source_files)} source videos × {generation_count} generations "
            f"= {total_generations} total"
        )

        successful = 0
        skipped = 0
        current = 0

        for file_path in source_files:
            base_name = file_path.stem
            file_name = file_path.name

            for gen_num in range(1, generation_count + 1):
                current += 1

                is_complete, status = self._get_generation_status(base_name, gen_num, metadata_folder)
                if is_complete:
                    if status == 'success':
                        self.logger.info(f" ⏭️ {current}/{total_generations}: {base_name}_{gen_num} (already processed)")
                        successful += 1
                    else:  # failed_exhausted
                        self.logger.info(f" ⏭️ {current}/{total_generations}: {base_name}_{gen_num} (failed - max retries reached)")
                    skipped += 1
                    continue

                self.logger.info(f" 🎬 {current}/{total_generations}: {file_name} → {base_name}_{gen_num}.mp4")

                task_with_gen = task.copy()
                task_with_gen['generation_number'] = gen_num
                task_with_gen['style_name'] = style_name

                if self.processor.process_file(file_path, task_with_gen, output_folder, metadata_folder):
                    successful += 1

                if current < total_generations:
                    time.sleep(self.api_defs.get('rate_limit', 3))

        self.logger.info(f"✓ Task {task_num}: {successful}/{total_generations} successful ({skipped} skipped)")

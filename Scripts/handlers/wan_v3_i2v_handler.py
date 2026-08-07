"""Wan V3 Image-to-Video API Handler.

Drives the /wan_v3 route in first-frame mode: each source image is sent as
``first_frame`` alongside the task prompt. The reference galleries, audio,
last_frame, document, and web page URL are all left empty.

Each style folder holds its own Source images; generated videos are named after
the source image plus the generation number.
"""
from pathlib import Path
from gradio_client import handle_file
import time
from .wan_v3_base import WanV3BaseHandler


class WanV3I2vHandler(WanV3BaseHandler):
    """
    Wan V3 image-to-video handler.

    Handles image-to-video generation where each style folder contains source
    images and generated videos are named based on the source image.
    """

    def validate_structure(self, tasks, config):
        """Validate Wan V3 I2V with folder/Source images and generation_count.

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
            if not folder or str(folder) == '':
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
                f"✓ Task {i}: {valid_count} images × {generation_count} generations = {total_expected} videos"
            )

        if invalid_images:
            self.processor.write_invalid_report(invalid_images, "wan_v3_i2v")
            self.logger.warning(f"⚠️ {len(invalid_images)} invalid images found (see report)")

        if not valid_tasks:
            raise Exception("No valid Wan V3 I2V tasks found")
        return valid_tasks

    def _make_api_call(self, file_path, task_config, attempt):
        """Make Wan V3 I2V API call with the source image as the first frame.

        Args:
            file_path: Path to the source image.
            task_config: Task configuration dictionary.
            attempt: Current attempt number.

        Returns:
            tuple: API response tuple.
        """
        return self._predict_wan_v3(
            task_config,
            first_frame=handle_file(str(file_path))
        )

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Wan V3 I2V API result.

        Args:
            result: Tuple containing (video_dict, task_id).
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
        video_dict, task_id = self._parse_wan_v3_result(result)

        if task_id:
            self.logger.info(f"   Task ID: {task_id}")

        gen_num = task_config.get('generation_number', 1)
        output_filename = f"{base_name}_{gen_num}.mp4"
        output_path = Path(output_folder) / output_filename
        video_saved = self._save_video(video_dict, output_path)

        processing_time = time.time() - start_time
        metadata = {
            'source_image': file_name,
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
                import json
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
        """Process entire Wan V3 I2V task.

        Iterates over source images in the style folder and generates
        multiple videos per image based on generation_count.

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

        source_files = self.processor._get_files_by_type(source_folder, 'image')

        if not source_files:
            self.logger.warning(f" ⚠️ No source images found in {source_folder}")
            return

        total_generations = len(source_files) * generation_count
        self.logger.info(
            f" 📸 Found {len(source_files)} source images × {generation_count} generations "
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

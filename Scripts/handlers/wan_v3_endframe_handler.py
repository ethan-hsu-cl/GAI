"""Wan V3 Endframe API Handler.

Drives the /wan_v3 route in first+last frame mode: an A image is sent as
``first_frame`` and its paired B image as ``last_frame``, so the endpoint
generates the transition between them. The reference galleries, audio, document,
and web page URL are left empty.

Pairs are formed either by the A/B naming convention ("Name_A 1024x1024.jpg" /
"Name_B 1024x1024.jpg") or sequentially by sorted filename, matching the Kling
Endframe pairing modes.
"""
from pathlib import Path
from gradio_client import handle_file
import time
from .wan_v3_base import WanV3BaseHandler


class WanV3EndframeHandler(WanV3BaseHandler):
    """
    Wan V3 Endframe handler for generating videos from start and end frame images.

    Processes image pairs (A and B) where A is the starting frame and B is the
    ending frame. Supports both A/B naming convention and sequential pairing.
    """

    def validate_structure(self, tasks, config):
        """Validate Wan V3 Endframe structure with image pairs.

        Args:
            tasks: List of task configuration dictionaries.
            config: Full processor configuration dictionary.

        Returns:
            list: Valid task dictionaries.

        Raises:
            ValidationError: If invalid files are found.
        """
        from .base_handler import ValidationError

        valid_tasks = []
        invalid_images = []

        for i, task in enumerate(tasks, 1):
            folder = Path(task['folder'])
            folder.mkdir(parents=True, exist_ok=True)
            source_folder = folder / "Source"
            source_folder.mkdir(exist_ok=True)

            image_files = self.processor._get_files_by_type(source_folder, 'image')
            if not image_files:
                self.logger.warning(f"⚠️ Task {i}: No images found in {source_folder}")
                continue

            if task.get('pairing_mode', 'ab_naming') == 'sequential':
                pairs = self._group_sequential_pairs(image_files)
            else:
                pairs = self._group_image_pairs(image_files)

            if not pairs:
                self.logger.warning(f"⚠️ Task {i}: No valid image pairs found")
                continue

            valid_pairs = 0
            for start_img, end_img in pairs:
                start_valid, start_msg = self.validate_file(start_img, 'image')
                end_valid, end_msg = self.validate_file(end_img, 'image')
                if not start_valid:
                    invalid_images.append({
                        'folder': folder.name, 'filename': start_img.name, 'reason': start_msg
                    })
                if not end_valid:
                    invalid_images.append({
                        'folder': folder.name, 'filename': end_img.name, 'reason': end_msg
                    })
                if start_valid and end_valid:
                    valid_pairs += 1

            if valid_pairs > 0:
                (folder / "Generated_Video").mkdir(parents=True, exist_ok=True)
                (folder / "Metadata").mkdir(parents=True, exist_ok=True)
                valid_tasks.append(task)
                self.logger.info(f"✓ Task {i}: {valid_pairs}/{len(pairs)} valid image pairs")

        if invalid_images:
            self.processor.write_invalid_report(invalid_images, "wan_v3_endframe")
            raise ValidationError(f"{len(invalid_images)} invalid images found")

        if not valid_tasks:
            raise Exception("No valid Wan V3 Endframe tasks found")
        return valid_tasks

    def _group_image_pairs(self, all_images):
        """Group images into start/end pairs based on the A/B naming convention.

        Expects naming pattern: "name_A resolution.ext" and "name_B resolution.ext"

        Args:
            all_images: List of Path objects for all images in the folder.

        Returns:
            list: Sorted list of (start_image, end_image) tuples.
        """
        image_dict = {}

        for img_path in all_images:
            name = img_path.stem  # e.g., "Anime Awakening_A 1024x1024"

            parts = name.rsplit('_', 1)
            if len(parts) != 2:
                continue

            frame_marker = parts[1].split()[0] if parts[1] else None

            # Resolution is the trailing token; the rest is the base name
            name_parts = name.split()
            if len(name_parts) < 2:
                continue
            resolution = name_parts[-1]
            base_name = ' '.join(name_parts[:-1])

            base_key = base_name.rsplit('_', 1)[0] + '_' + resolution

            if frame_marker in ['A', 'B']:
                image_dict.setdefault(base_key, {})[frame_marker] = img_path

        pairs = []
        for base_key, frames in image_dict.items():
            if 'A' in frames and 'B' in frames:
                pairs.append((frames['A'], frames['B']))
            else:
                missing = 'A' if 'A' not in frames else 'B'
                self.logger.warning(f" ⚠️  Missing frame {missing} for {base_key}")

        pairs.sort(key=lambda x: x[0].name)
        return pairs

    def _group_sequential_pairs(self, all_images):
        """Group images sequentially by sorted filename order.

        First half of the images become start frames, second half end frames.
        With 6 images the pairs are (1,4), (2,5), (3,6).

        Args:
            all_images: List of Path objects for all images in the folder.

        Returns:
            list: List of (start_image, end_image) tuples.
        """
        if not all_images:
            return []

        sorted_images = sorted(all_images, key=lambda x: x.name.lower())
        total_count = len(sorted_images)

        if total_count < 2:
            self.logger.warning(f" ⚠️  Need at least 2 images for sequential pairing, found {total_count}")
            return []

        half_count = total_count // 2
        start_images = sorted_images[:half_count]
        end_images = sorted_images[half_count:half_count * 2]

        if total_count % 2 != 0:
            self.logger.warning(f" ⚠️  Odd number of images ({total_count}), last image will be unused")

        return list(zip(start_images, end_images))

    def process_task(self, task, task_num, total_tasks):
        """Process an entire Wan V3 Endframe task, pair by pair.

        Args:
            task: Task configuration dictionary.
            task_num: Current task number.
            total_tasks: Total number of tasks.
        """
        folder = Path(task.get('folder', task.get('folder_path', '')))
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Video"
        metadata_folder = folder / "Metadata"

        output_folder.mkdir(parents=True, exist_ok=True)
        metadata_folder.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {folder.name}")

        pairing_mode = task.get('pairing_mode', 'ab_naming')

        generation_count = task.get('generation_count')
        if generation_count is None:
            generation_count = self.config.get('generation_count', 1)
        if generation_count < 1:
            generation_count = 1

        all_images = self._get_task_files(task, source_folder)

        if pairing_mode == 'sequential':
            self.logger.info(" 🔄 Using sequential pairing mode")
            image_pairs = self._group_sequential_pairs(all_images)
        else:
            self.logger.info(" 🔤 Using A/B naming convention pairing")
            image_pairs = self._group_image_pairs(all_images)

        if not image_pairs:
            self.logger.warning(f" ⚠️  No valid image pairs found in {source_folder}")
            return

        self.logger.info(f" 📸 Found {len(image_pairs)} image pairs")
        if generation_count > 1:
            self.logger.info(f" 🔁 Will generate {generation_count} videos per pair")

        successful = 0
        skipped = 0
        total_generations = len(image_pairs) * generation_count

        for pair_idx, (start_image, end_image) in enumerate(image_pairs, 1):
            self.logger.info(f" 🖼️  Pair {pair_idx}/{len(image_pairs)}: {start_image.name} → {end_image.name}")

            for gen_num in range(1, generation_count + 1):
                # Metadata is named per generation once generation_count > 1, so the
                # skip check has to look under the same name the result was saved as.
                if generation_count > 1:
                    gen_base_name = f"{start_image.stem}_generated_{gen_num}"
                else:
                    gen_base_name = start_image.stem

                is_complete, status = self._get_processing_status(
                    start_image, metadata_folder, base_name=gen_base_name)
                if is_complete:
                    if status == 'success':
                        self.logger.info(f"   ⏭️ Generation {gen_num}/{generation_count} (already processed)")
                        successful += 1
                    else:  # failed_exhausted
                        self.logger.info(f"   ⏭️ Generation {gen_num}/{generation_count} (failed - max retries reached)")
                    skipped += 1
                    continue

                if generation_count > 1:
                    self.logger.info(f"   Generation {gen_num}/{generation_count}")

                pair_task = task.copy()
                pair_task['end_image'] = str(end_image)
                pair_task['generation_number'] = gen_num
                pair_task['total_generations'] = generation_count

                if self.processor.process_file(start_image, pair_task, output_folder, metadata_folder):
                    successful += 1

                if gen_num < generation_count or pair_idx < len(image_pairs):
                    time.sleep(self.api_defs.get('rate_limit', 3))

        self.logger.info(f"✓ Task {task_num}: {successful}/{total_generations} successful ({skipped} skipped)")

    def _make_api_call(self, file_path, task_config, attempt):
        """Make Wan V3 Endframe API call with both start and end images.

        Args:
            file_path: Path to the starting frame image (A).
            task_config: Task configuration containing the end_image path.
            attempt: Current attempt number.

        Returns:
            tuple: API response tuple.
        """
        end_image_path = task_config.get('end_image')
        if not end_image_path:
            raise ValueError("End image path not provided in task configuration")

        end_image_path = Path(end_image_path)
        if not end_image_path.exists():
            raise FileNotFoundError(f"End image not found: {end_image_path}")

        return self._predict_wan_v3(
            task_config,
            first_frame=handle_file(str(file_path)),
            last_frame=handle_file(str(end_image_path))
        )

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Wan V3 Endframe API result.

        Args:
            result: Tuple containing (video_dict, task_id).
            file_path: Path to the starting frame image.
            task_config: Task configuration.
            output_folder: Output directory path.
            metadata_folder: Metadata directory path.
            base_name: Base filename without extension.
            file_name: Full filename with extension.
            start_time: Processing start timestamp.
            attempt: Current attempt number.

        Returns:
            bool: True if successful, False otherwise.
        """
        video_dict, task_id = self._parse_wan_v3_result(result)

        if task_id:
            self.logger.info(f" Task ID: {task_id}")

        gen_num = task_config.get('generation_number', 1)
        total_gens = task_config.get('total_generations', 1)

        if total_gens > 1:
            output_filename = f"{base_name}_generated_{gen_num}.mp4"
            metadata_base_name = f"{base_name}_generated_{gen_num}"
        else:
            output_filename = f"{base_name}_generated.mp4"
            metadata_base_name = base_name

        output_path = Path(output_folder) / output_filename
        video_saved = self._save_video(video_dict, output_path)

        processing_time = time.time() - start_time
        metadata = {
            'start_image': file_name,
            'end_image': Path(task_config['end_image']).name,
            **self._wan_v3_metadata(task_config, task_id, processing_time, attempt, video_saved)
        }

        if total_gens > 1:
            metadata['generation_number'] = gen_num
            metadata['total_generations'] = total_gens

        if video_saved:
            self.logger.info(f" ✅ Generated: {output_path.name}")
            metadata['generated_video'] = output_filename
            subtitles = self._subtitles(video_dict)
            if subtitles:
                metadata['subtitles'] = subtitles
        else:
            self.logger.info("   ❌ No video returned by the API")
            metadata['error'] = 'Video download/save failed'

        self.processor.save_metadata(Path(metadata_folder), metadata_base_name, file_name,
                                     metadata, task_config, log_status=True)

        return video_saved

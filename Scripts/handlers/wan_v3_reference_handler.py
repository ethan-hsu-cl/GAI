"""Wan V3 Reference API Handler.

Drives the /wan_v3 route in reference-gallery mode: the source image plus every
reference image are sent together in the ``images`` Gallery input (max 10), with
the task prompt describing how they should be combined. first_frame/last_frame,
the video and audio inputs, the document, and the web page URL are left empty.

Folder layout is base_folder/<effect>/{Source,Reference}: each source image is
paired with all reference images in that effect folder.
"""
from pathlib import Path
import time
from PIL import Image
from .wan_v3_base import WanV3BaseHandler


class WanV3ReferenceHandler(WanV3BaseHandler):
    """Wan V3 reference-image handler."""

    def validate_structure(self, tasks, config):
        """Validate Wan V3 Reference with base_folder, Source and Reference per effect.

        Creates the effect folders for configured tasks, discovers effect folders
        under base_folder, validates source and reference images, and detects the
        closest supported aspect ratio for each source.

        Args:
            tasks: List of task configuration dictionaries.
            config: Full processor configuration dictionary.

        Returns:
            list: Valid task dictionaries with image_sets.

        Raises:
            Exception: If validation errors are found.
        """
        base_folder = Path(config.get('base_folder', ''))
        base_folder.mkdir(parents=True, exist_ok=True)

        configured_tasks = {t['effect']: t for t in tasks if t.get('effect')}
        valid_tasks = []
        errors = []

        for effect_name in configured_tasks:
            task_folder = base_folder / effect_name
            task_folder.mkdir(parents=True, exist_ok=True)
            (task_folder / 'Source').mkdir(exist_ok=True)
            (task_folder / 'Reference').mkdir(exist_ok=True)

        for folder in sorted(base_folder.iterdir()):
            if not (folder.is_dir() and not folder.name.startswith(('.', '_'))
                    and (folder / 'Source').exists() and (folder / 'Reference').exists()):
                continue

            if folder.name in configured_tasks:
                task = configured_tasks[folder.name].copy()
                task['folder_path'] = str(folder)
                self.logger.info(f"✓ Matched: {folder.name}")
            else:
                task = {
                    'effect': folder.name,
                    'folder_path': str(folder),
                    'prompt': config.get('default_prompt', '')
                }
                self.logger.info(f"⚠️ No config match: {folder.name} -> using defaults")

            result, task_errors = self._validate_reference_task(task)
            if result:
                valid_tasks.append(result)
            else:
                errors.extend(task_errors)

        if errors:
            for error in errors:
                self.logger.error(f"❌ {error}")
            raise Exception(f"{len(errors)} validation errors")

        if not valid_tasks:
            raise Exception("No valid Wan V3 Reference tasks found")
        return valid_tasks

    def _validate_reference_task(self, task):
        """Validate a single reference task's Source and Reference images.

        Args:
            task: Task dictionary with 'folder_path' and 'effect' keys.

        Returns:
            tuple: (task_dict_or_None, list_of_errors)
        """
        fp = Path(task['folder_path'])
        src_dir, ref_dir = fp / 'Source', fp / 'Reference'

        src_imgs = self.processor._get_files_by_type(src_dir, 'image')
        if not src_imgs:
            return None, [f"{task['effect']}: No source images"]

        ref_imgs = self._find_reference_images(ref_dir)
        if not ref_imgs:
            return None, [f"{task['effect']}: No reference images"]

        # One source + all references must fit the Gallery cap
        max_refs = self.MAX_GALLERY_IMAGES - 1
        if len(ref_imgs) > max_refs:
            self.logger.warning(
                f" ⚠️ {task['effect']}: {len(ref_imgs)} references found, using first {max_refs}"
            )
            ref_imgs = ref_imgs[:max_refs]

        valid_sets = []
        for src in src_imgs:
            invalids = []
            try:
                with Image.open(src) as img:
                    ar = self._closest_aspect_ratio(img.width, img.height)
                    self.logger.info(f" 📐 {src.name} ({img.width}x{img.height}) → {ar}")
            except Exception as e:
                invalids.append(f"{src.name}: Cannot read dims - {e}")
                continue

            for img_path in [src] + ref_imgs:
                valid, reason = self.validate_file(img_path)
                if not valid:
                    invalids.append(f"{img_path.name}: {reason}")

            if not invalids:
                valid_sets.append({
                    'source_image': src,
                    'reference_images': ref_imgs,
                    'aspect_ratio': ar,
                    'reference_count': len(ref_imgs)
                })
                self.logger.info(f" Found {len(ref_imgs)} reference images for {src.name}")

        if not valid_sets:
            return None, [f"{task['effect']}: No valid image sets"]

        for d in ['Generated_Video', 'Metadata']:
            (fp / d).mkdir(exist_ok=True)

        task.update({
            'generated_dir': str(fp / 'Generated_Video'),
            'metadata_dir': str(fp / 'Metadata'),
            'image_sets': valid_sets
        })
        return task, []

    def _find_reference_images(self, ref_dir):
        """Find reference images, honoring the image2/image3/... naming convention.

        Args:
            ref_dir: Path to the Reference directory.

        Returns:
            list: Sorted list of reference image Path objects.
        """
        refs = []
        file_types = self.api_defs['file_types']
        max_refs = self.api_defs.get('max_references', self.MAX_GALLERY_IMAGES - 1)

        for i in range(2, max_refs + 2):
            files = [f for f in ref_dir.iterdir()
                     if f.suffix.lower() in file_types and
                     (f.stem.lower().startswith(f'image{i}') or
                      f.stem.lower().startswith(f'image {i}') or
                      f.stem.split('_')[0] == str(i) or
                      f.stem.split('.')[0] == str(i))]
            if files:
                refs.append(files[0])
            else:
                break

        return refs or sorted([f for f in ref_dir.iterdir()
                               if f.suffix.lower() in file_types])[:max_refs]

    def _closest_aspect_ratio(self, w, h):
        """Detect the closest supported aspect ratio for a source image.

        Args:
            w: Image width.
            h: Image height.

        Returns:
            str: Aspect ratio string (e.g. '16:9').
        """
        r = w / h
        aspect_ratios = self.api_defs.get('aspect_ratios', ["16:9", "9:16", "1:1"])
        if "16:9" in aspect_ratios and r > 1.2:
            return "16:9"
        elif "9:16" in aspect_ratios and r < 0.8:
            return "9:16"
        return "1:1"

    def process_task(self, task, task_num, total_tasks):
        """Process image sets (source + references) rather than individual files.

        Args:
            task: Task configuration dictionary with image_sets.
            task_num: Current task number.
            total_tasks: Total number of tasks.
        """
        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {task['effect']}")

        generated_dir = Path(task['generated_dir'])
        metadata_dir = Path(task['metadata_dir'])

        successful = 0
        skipped = 0
        total_sets = len(task['image_sets'])

        for i, image_set in enumerate(task['image_sets'], 1):
            source_image = image_set['source_image']

            is_complete, status = self._get_processing_status(source_image, metadata_dir)
            if is_complete:
                if status == 'success':
                    self.logger.info(f" ⏭️ {i}/{total_sets}: {source_image.name} (already processed)")
                    successful += 1
                else:  # failed_exhausted
                    self.logger.info(f" ⏭️ {i}/{total_sets}: {source_image.name} (failed - max retries reached)")
                skipped += 1
                continue

            self.logger.info(f" 🖼️ {i}/{total_sets}: {source_image.name} + {image_set['reference_count']} refs")

            ref_task = task.copy()
            ref_task['reference_images'] = [str(ref) for ref in image_set['reference_images']]
            ref_task['ratio'] = task.get('ratio', image_set['aspect_ratio'])

            if self.processor.process_file(source_image, ref_task, generated_dir, metadata_dir):
                successful += 1

            if i < total_sets:
                time.sleep(self.api_defs.get('rate_limit', 3))

        self.logger.info(f"✓ Task {task_num}: {successful}/{total_sets} successful ({skipped} skipped)")

    def _make_api_call(self, file_path, task_config, attempt):
        """Make Wan V3 Reference API call with source + reference images.

        Args:
            file_path: Path to the source image.
            task_config: Task configuration containing reference_images.
            attempt: Current attempt number.

        Returns:
            tuple: API response tuple.
        """
        reference_images = task_config.get('reference_images', [])
        if not reference_images:
            raise ValueError("No reference images provided")

        all_images = [Path(file_path)] + [Path(ref) for ref in reference_images]

        self.logger.info(
            f" 📸 Sending 1 source + {len(reference_images)} references "
            f"({task_config.get('ratio', 'adaptive')})"
        )

        return self._predict_wan_v3(task_config, images=self._gallery(all_images))

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Wan V3 Reference API result.

        Args:
            result: Tuple containing (video_dict, task_id).
            file_path: Path to the source image.
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

        effect = task_config.get('effect', '')
        effect_clean = effect.replace(' ', '_').replace('-', '_')
        output_filename = f"{base_name}_{effect_clean}.mp4" if effect_clean else f"{base_name}_generated.mp4"
        output_path = Path(output_folder) / output_filename
        video_saved = self._save_video(video_dict, output_path)

        processing_time = time.time() - start_time
        reference_images = task_config.get('reference_images', [])

        metadata = {
            'source_image': file_name,
            'effect_name': effect,
            'reference_images': [Path(ref).name for ref in reference_images],
            'reference_count': len(reference_images),
            'total_images': len(reference_images) + 1,
            **self._wan_v3_metadata(task_config, task_id, processing_time, attempt, video_saved)
        }

        if video_saved:
            self.logger.info(f" ✅ Generated: {output_filename}")
            metadata['generated_video'] = output_filename
            subtitles = self._subtitles(video_dict)
            if subtitles:
                metadata['subtitles'] = subtitles
        else:
            self.logger.info("   ❌ No video returned by the API")
            metadata['error'] = 'Video download/save failed'

        self.processor.save_metadata(Path(metadata_folder), base_name, file_name,
                                     metadata, task_config)

        return video_saved

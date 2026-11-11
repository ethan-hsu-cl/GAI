"""YCE Reference-to-Video API Handler.

Drives the PerfectCorp YCE testbed's "Reference to Video" tab (/gen_ref_v2,
effect ``bpRef2Vid``, Seedance models). The source image goes into the
"Image 1" slot and its reference images into "Image 2", "Image 3", ...; the
prompt can address them as ``@Image 1``, ``@Image 2``, .... Reference video and
audio slots are left empty.

Folder layout and source/reference pairing are the same as Wan V3 Reference:
base_folder/<effect>/{Source,Reference}, with references named after a source
(Reference/01.jpg, Reference/01_back.jpg for Source/01.jpg) going with that
source only, otherwise every source sharing the whole Reference folder.

Image slot limits follow the model: Seedance 2.5 takes 30 images, the 2.0
series 9. Errors (including moderation blocks) come back in the Status slot as
"Error: ..." rather than raising.
"""
from pathlib import Path
import time
from datetime import datetime
from gradio_client import handle_file
from core.path_utils import safe_path_name, name_room
from .wan_v3_reference_handler import WanV3ReferenceHandler


class YceReferenceHandler(WanV3ReferenceHandler):
    """YCE (PerfectCorp Seedance) reference-to-video handler."""

    # Numbered slots the /gen_ref_v2 route exposes
    IMAGE_SLOTS = 30
    VIDEO_SLOTS = 10
    AUDIO_SLOTS = 10

    # Settings with their endpoint defaults; resolved per-task -> default_settings
    # -> api_params -> these.
    SETTING_DEFAULTS = {
        'model': 'dreamina-seedance-2-5-260628',
        'resolution': '720p',
        'generate_audio': False,
        'ratio': 'adaptive',
        'duration': 5,
        'seed': -1,
        'duration_auto': False,
        'output_format': 'mp4',
        'omni_task_type': 'auto',
    }

    @property
    def MAX_GALLERY_IMAGES(self):
        """Images per request for the configured model (source + references)."""
        model = self._settings({})['model']
        return self.IMAGE_SLOTS if '2-5' in model else 9

    def _closest_aspect_ratio(self, w, h):
        """Use the configured ratio rather than one guessed from the source.

        YCE recommends 'adaptive' on the Reference tab (the task type is
        inferred from the prompt, and edit/extend tasks reject a fixed ratio),
        so the source's shape is not forced onto the request.
        """
        return self._settings({})['ratio']

    def _make_api_call(self, file_path, task_config, attempt):
        """Call /gen_ref_v2 with the source + reference images in numbered slots.

        Args:
            file_path: Path to the source image.
            task_config: Task configuration containing reference_images.
            attempt: Current attempt number.

        Returns:
            tuple: (video, video_url, task_id, status, elapsed, debug_info).
        """
        reference_images = task_config.get('reference_images', [])
        if not reference_images:
            raise ValueError("No reference images provided")

        images = ([Path(file_path)] + [Path(r) for r in reference_images])[:self.MAX_GALLERY_IMAGES]
        s = self._settings(task_config)

        self.logger.info(
            f" 📸 Sending 1 source + {len(images) - 1} references "
            f"({s['model']}, {s['resolution']}, {s['ratio']})"
        )

        image_slots = [handle_file(str(p)) for p in images]
        image_slots += [None] * (self.IMAGE_SLOTS - len(image_slots))

        return self.client.predict(
            task_config.get('prompt', ''),
            s['model'],
            s['resolution'],
            s['generate_audio'],
            len(images),  # img_count
            0,            # vid_count
            0,            # aud_count
            s['ratio'],
            s['duration'],
            s['seed'],
            s['duration_auto'],
            s['output_format'],
            s['omni_task_type'],
            *image_slots,
            *([None] * self.VIDEO_SLOTS),
            *([None] * self.AUDIO_SLOTS),
            api_name=self.api_defs['api_name']
        )

    def _handle_result(self, result, file_path, task_config, output_folder,
                       metadata_folder, base_name, file_name, start_time, attempt):
        """Save the video and metadata from a /gen_ref_v2 response.

        Args:
            result: (video, video_url, task_id, status, elapsed, debug_info).
            file_path: Path to the source image.
            task_config: Task configuration.
            output_folder: Output directory path.
            metadata_folder: Metadata directory path.
            base_name: Base filename without extension.
            file_name: Full filename with extension.
            start_time: Processing start timestamp.
            attempt: Current attempt number.

        Returns:
            bool: True if a video was saved.
        """
        if not isinstance(result, tuple):
            raise ValueError(f"Invalid API response format: {result}")
        video, video_url, task_id, status, elapsed, debug_info = (list(result) + [None] * 6)[:6]

        if task_id:
            self.logger.info(f" Task ID: {task_id}")

        s = self._settings(task_config)
        effect = task_config.get('effect', '')
        reference_images = task_config.get('reference_images', [])

        metadata = {
            'source_image': file_name,
            'effect_name': effect,
            'reference_images': [Path(r).name for r in reference_images],
            'reference_count': len(reference_images),
            'total_images': len(reference_images) + 1,
            'task_id': task_id,
            'prompt': task_config.get('prompt', ''),
            **s,
            'status': status,
            'elapsed_time': elapsed,
        }

        error = None
        video_saved = False
        output_filename = None
        if status and str(status).lower().startswith('error'):
            error = str(status)
            self.logger.info(f"   ❌ API Error: {error}")
        else:
            ext = s['output_format'] or 'mp4'
            effect_clean = safe_path_name(effect).replace(' ', '_').replace('-', '_') if effect else ''
            output_filename = f"{base_name}_{effect_clean}.{ext}" if effect_clean else f"{base_name}_generated.{ext}"
            # Drop the effect if the name won't fit under Windows' path limit; the
            # folder already names it and the report matches on base_name
            if len(output_filename) > name_room(output_folder):
                output_filename = f"{base_name}.{ext}"
            output_path = Path(output_folder) / output_filename
            # Local Gradio copy first, then the hosted URL
            video_saved = self._save_video(video, output_path) or (
                bool(video_url) and self._save_video(video_url, output_path))
            if not video_saved:
                error = 'Video download/save failed'
                self.logger.info("   ❌ No video returned by the API")

        metadata.update({
            'processing_time_seconds': round(time.time() - start_time, 1),
            'processing_timestamp': datetime.now().isoformat(),
            'attempts': attempt + 1,
            'success': video_saved,
            'api_name': self.api_name,
        })
        if video_saved:
            self.logger.info(f" ✅ Generated: {output_filename}")
            metadata['generated_video'] = output_filename
        else:
            metadata['error'] = error
            metadata['debug_info'] = debug_info

        self.processor.save_metadata(Path(metadata_folder), base_name, file_name,
                                     metadata, task_config)
        return video_saved

"""Shared Wan V3 logic - one Gradio route (/wan_v3), four input modes.

The /wan_v3 route on the video_effect testbed accepts a prompt plus a wide set of
optional inputs: a reference-image gallery (max 10), a reference-video gallery
(max 5), reference audio (max 5), first/last frame images, a document, and a web
page URL. Each wan_v3_* handler drives the same route but fills a different
subset of those inputs so the endpoint behaves as one specific mode:

    wan_v3_ttv        prompt only
    wan_v3_i2v        prompt + first_frame
    wan_v3_endframe   prompt + first_frame + last_frame
    wan_v3_reference  prompt + images gallery (source + references)

Everything a mode doesn't use is sent empty. Generation settings (resolution,
ratio, duration, duration_auto, audio_out, thinking) are shared by all four and
resolved the same way: per-task override -> config default_settings -> the
api_definitions api_params fallback.
"""
from pathlib import Path
import shutil
from datetime import datetime
from gradio_client import handle_file
from .base_handler import BaseAPIHandler


class WanV3BaseHandler(BaseAPIHandler):
    """Common /wan_v3 call plumbing and result handling."""

    # Gallery caps enforced by the Gradio components
    MAX_GALLERY_IMAGES = 10

    # Settings shared by every wan_v3 mode, with their endpoint defaults
    SETTING_DEFAULTS = {
        'resolution': '1080P',
        'ratio': 'adaptive',
        'duration': 5,
        'duration_auto': False,
        'audio_out': True,
        'thinking': False,
    }

    def _settings(self, task_config):
        """Resolve wan_v3 generation settings for one call.

        Precedence: per-task value -> config default_settings -> api_params in
        api_definitions.json -> the endpoint default in SETTING_DEFAULTS.

        Args:
            task_config: Task configuration dictionary.

        Returns:
            dict: Resolved settings keyed by API parameter name.
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

    def _gallery(self, image_paths):
        """Wrap image paths as Gradio Gallery entries, capped at the component max.

        Args:
            image_paths: Iterable of image paths (str or Path).

        Returns:
            list: Gallery entries in {'image': FileData, 'caption': None} form.
        """
        return [
            {'image': handle_file(str(p)), 'caption': None}
            for p in list(image_paths)[:self.MAX_GALLERY_IMAGES]
        ]

    def _predict_wan_v3(self, task_config, images=None, first_frame=None, last_frame=None):
        """Call /wan_v3 with the inputs this mode uses; everything else empty.

        Args:
            task_config: Task configuration dictionary (supplies prompt + overrides).
            images: Optional list of Gallery entries for the reference-image input.
            first_frame: Optional first-frame FileData handle.
            last_frame: Optional last-frame FileData handle.

        Returns:
            tuple: API response tuple (video dict, task id).
        """
        settings = self._settings(task_config)

        return self.client.predict(
            prompt=task_config.get('prompt', ''),
            images=images or [],
            videos=[],
            audios=[],
            first_frame=first_frame,
            last_frame=last_frame,
            document=None,
            link='',
            resolution=settings['resolution'],
            ratio=settings['ratio'],
            duration=settings['duration'],
            duration_auto=settings['duration_auto'],
            audio_out=settings['audio_out'],
            thinking=settings['thinking'],
            api_name=self.api_defs['api_name']
        )

    @staticmethod
    def _parse_wan_v3_result(result):
        """Split the /wan_v3 response tuple into (video, task_id).

        Args:
            result: Raw API response.

        Returns:
            tuple: (video_dict, task_id)

        Raises:
            ValueError: If the response isn't the expected tuple.
        """
        if not isinstance(result, tuple):
            raise ValueError(f"Invalid API response format: {result}")
        video_dict = result[0] if len(result) > 0 else None
        task_id = result[1] if len(result) > 1 else None
        return video_dict, task_id

    def _save_video(self, video_dict, output_path):
        """Save the returned video, trying URL download before a local copy.

        The Video component returns {'video': filepath, 'subtitles': ...}, but the
        inner value may be a plain path or a FileData dict depending on the
        gradio_client version, so both shapes are unwrapped here.

        Args:
            video_dict: The response's video field.
            output_path: Destination path for the saved video.

        Returns:
            bool: True if a video was saved.
        """
        candidates = []
        if isinstance(video_dict, str):
            candidates.append(video_dict)
        elif isinstance(video_dict, dict):
            candidates.append(video_dict.get('url'))
            inner = video_dict.get('video')
            if isinstance(inner, dict):
                candidates.extend([inner.get('url'), inner.get('path')])
            elif inner:
                candidates.append(inner)

        for candidate in [c for c in candidates if c]:
            if str(candidate).startswith(('http://', 'https://')):
                if self.processor.download_file(candidate, output_path):
                    return True
            else:
                local_path = Path(candidate)
                if local_path.exists():
                    shutil.copy2(local_path, output_path)
                    return True
        return False

    @staticmethod
    def _subtitles(video_dict):
        """Extract the subtitles path from the response video field, if any."""
        if isinstance(video_dict, dict) and video_dict.get('subtitles'):
            return str(video_dict['subtitles'])
        return None

    def _wan_v3_metadata(self, task_config, task_id, processing_time, attempt, success):
        """Build the metadata fields common to every wan_v3 mode.

        Args:
            task_config: Task configuration dictionary.
            task_id: Task ID returned by the API.
            processing_time: Elapsed seconds for this generation.
            attempt: Current attempt number (0-based).
            success: Whether the generation succeeded.

        Returns:
            dict: Metadata fields to merge into the mode-specific metadata.
        """
        settings = self._settings(task_config)
        return {
            'task_id': task_id,
            'prompt': task_config.get('prompt', ''),
            'resolution': settings['resolution'],
            'ratio': settings['ratio'],
            'duration': settings['duration'],
            'duration_auto': settings['duration_auto'],
            'audio_out': settings['audio_out'],
            'thinking': settings['thinking'],
            'processing_time_seconds': round(processing_time, 1),
            'processing_timestamp': datetime.now().isoformat(),
            'attempts': attempt + 1,
            'success': success,
            'api_name': self.api_name,
        }

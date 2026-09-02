"""OpenAI Image API Handler.

Wraps the /openai_image gradio endpoint (gpt-image-N models). Builds on the
shared image-generation base (multi-image input, random source selection,
reference images, generations-per-source, iteration-based processing, and
429-error retry) and adds the parts unique to this endpoint:

* its own model/quality/resolution parameters (independent of Nano Banana)
* the predict() signature (adds ``quality``)

Its response format (``(list[str], str)`` of file paths + status text, instead
of Nano Banana's base64-in-response_data tuple) and its server-side timeout
retry are handled by the shared base.
"""
from gradio_client import handle_file

from .image_generation_base import BaseImageGenerationHandler


class OpenaiImageHandler(BaseImageGenerationHandler):
    """Handler for the /openai_image endpoint."""

    # Conservative per-call image cap; can be overridden per-task with max_images.
    MODEL_MAX_IMAGES = {
        'gpt-image-1': 10,
        'gpt-image-2': 10,
    }

    DEFAULT_MAX_IMAGES = 10
    DEFAULT_MIN_IMAGES = 1

    DEFAULT_MODEL = 'gpt-image-2'
    DEFAULT_QUALITY = 'auto'
    DEFAULT_RESOLUTION = '1K'

    def _make_api_call(self, file_path, task_config, attempt):
        """Build the image list (parity with nano_banana) and call /openai_image."""
        api_params = self.api_defs.get('api_params', {})
        model = task_config.get('model') or api_params.get('model', self.DEFAULT_MODEL)
        quality = str(task_config.get('quality') or api_params.get('quality', self.DEFAULT_QUALITY))
        resolution = str(task_config.get('resolution') or api_params.get('resolution', self.DEFAULT_RESOLUTION))

        images_list, aspect_ratio = self._build_images_payload(file_path, task_config)
        if images_list is None:
            return ([], "No images selected")

        max_images = self.MODEL_MAX_IMAGES.get(model, self.DEFAULT_MAX_IMAGES)
        self.logger.info(f"   Model: {model}, Quality: {quality}, Resolution: {resolution}, Aspect: {aspect_ratio}")
        self.logger.debug(f" 📷 Sending {len(images_list)} images (max {max_images} for {model})")

        prompt = task_config['prompt']
        return self.client.predict(
            prompt=prompt,
            model=model,
            quality=quality,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            images=images_list,
            api_name=self.api_defs['api_name'],
        )

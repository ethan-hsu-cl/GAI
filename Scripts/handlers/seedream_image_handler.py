"""Seedream Image API Handler.

Wraps the /seedream_image gradio endpoint (dola-seedream-N models). Builds on
the shared image-generation base (multi-image input, random source selection,
reference images, generations-per-source, iteration-based processing, 429 and
timeout retry, and saving path/URL/base64 responses) and adds the parts unique
to this endpoint: its own model constants and the predict() signature, which
carries Seedream's output format, layer decomposition, background, prompt
optimization and sequential-generation controls.

The response is ``(list[str] paths, str, str)`` — the same shape the shared
``_handle_result`` already parses, with the third element recorded under
``raw_response.extra_fields``.
"""
from .image_generation_base import BaseImageGenerationHandler


class SeedreamImageHandler(BaseImageGenerationHandler):
    """Handler for the /seedream_image endpoint."""

    # Conservative per-call image cap; can be overridden per-task with max_images.
    MODEL_MAX_IMAGES = {
        'dola-seedream-5-0-pro-260628': 10,
    }

    DEFAULT_MAX_IMAGES = 10
    DEFAULT_MIN_IMAGES = 1

    DEFAULT_MODEL = 'dola-seedream-5-0-pro-260628'
    DEFAULT_RESOLUTION = '1K'
    DEFAULT_OUTPUT_FORMAT = 'jpeg'
    DEFAULT_BACKGROUND = 'opaque'
    DEFAULT_OPTIMIZE_PROMPT_MODE = 'standard'
    DEFAULT_LAYER_DECOMPOSITION = False
    DEFAULT_SEQUENTIAL_ENABLED = False
    DEFAULT_SEQUENTIAL_MAX_IMAGES = 1

    def _make_api_call(self, file_path, task_config, attempt):
        """Build the image list (parity with openai_image) and call /seedream_image.

        Args:
            file_path: Path to the source image file.
            task_config: Task configuration dictionary.
            attempt: Current attempt number (0-indexed).

        Returns:
            tuple: API response ``(image_paths, status_text, extra)``.
        """
        api_params = self.api_defs.get('api_params', {})

        def param(name, default, cast=None):
            """Resolve a parameter: per-task → api_definitions → class default."""
            value = task_config.get(name)
            if value is None:
                value = api_params.get(name, default)
            return cast(value) if cast is not None else value

        model = param('model', self.DEFAULT_MODEL, str)
        resolution = param('resolution', self.DEFAULT_RESOLUTION, str)
        output_format = param('output_format', self.DEFAULT_OUTPUT_FORMAT, str)
        background = param('background', self.DEFAULT_BACKGROUND, str)
        optimize_prompt_mode = param('optimize_prompt_mode', self.DEFAULT_OPTIMIZE_PROMPT_MODE, str)
        layer_decomposition = param('layer_decomposition', self.DEFAULT_LAYER_DECOMPOSITION, bool)
        sequential_enabled = param('sequential_enabled', self.DEFAULT_SEQUENTIAL_ENABLED, bool)
        sequential_max_images = param('sequential_max_images', self.DEFAULT_SEQUENTIAL_MAX_IMAGES, int)

        images_list, aspect_ratio = self._build_images_payload(file_path, task_config)
        if images_list is None:
            return ([], "No images selected", "")

        max_images = self.MODEL_MAX_IMAGES.get(model, self.DEFAULT_MAX_IMAGES)
        self.logger.info(
            f"   Model: {model}, Resolution: {resolution}, Aspect: {aspect_ratio}, "
            f"Format: {output_format}, Background: {background}"
        )
        if sequential_enabled:
            self.logger.info(f" 🔢 Sequential generation enabled (max {sequential_max_images} images)")
        if layer_decomposition:
            self.logger.info(" 🧅 Layer decomposition enabled")
        self.logger.debug(f" 📷 Sending {len(images_list)} images (max {max_images} for {model})")

        return self.client.predict(
            prompt=task_config['prompt'],
            model=model,
            images=images_list,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            output_format=output_format,
            layer_decomposition=layer_decomposition,
            background=background,
            optimize_prompt_mode=optimize_prompt_mode,
            sequential_enabled=sequential_enabled,
            sequential_max_images=sequential_max_images,
            api_name=self.api_defs['api_name'],
        )

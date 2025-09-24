import os
import time
import shutil
import json
import requests
import base64
import subprocess
from datetime import datetime
from gradio_client import Client, handle_file
from PIL import Image
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import logging

"""
file download command example:
yt-dlp -f "bv*[vcodec~='^(h264|avc)']+ba[acodec~='^(mp?4a|aac)']" "https://youtube.com/playlist?list=PLSgBrV2b0XA_ofBZ4c3e85sTNBh3BKN2y&si=_5VpzvdI7hsF-a4o"
"""

class UnifiedAPIProcessor:
    """
    Enhanced Consolidated API processor supporting multiple endpoints with all individual processor features:
    - Kling Image2Video (with streaming downloads and dual-save logic)
    - Google Flash/Nano Banana (with base64 handling and parallel validation)
    - Vidu Effects (with parallel validation and optimizations)
    - Vidu Reference (with smart reference finding and aspect ratio detection)
    - Runway Video Processing (with video validation and pairing strategies)
    """

    def __init__(self, api_name, config_file=None):
        self.api_name = api_name
        self.config_file = config_file or f"batch_{api_name}_config.json"
        self.client = None
        self.config = {}
        self.api_definitions = {}

        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        self.logger = logging.getLogger(__name__)

        # Load API definitions
        self.load_api_definitions()

    def load_api_definitions(self):
        """Load API-specific configurations"""
        try:
            with open("core/api_definitions.json", 'r', encoding='utf-8') as f:
                all_definitions = json.load(f)
                self.api_definitions = all_definitions.get(self.api_name, {})
                self.logger.info(f"✓ API definitions loaded for {self.api_name}")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"❌ API definitions error: {e}")
            # Fallback to default definitions
            self.set_default_definitions()

    def set_default_definitions(self):
        """Set default API definitions with all individual processor optimizations"""
        defaults = {
            "kling": {
                "endpoint": "http://192.168.4.3:8000/kling/",
                "api_name": "/Image2Video",
                "file_types": [".jpg", ".jpeg", ".png", ".bmp", ".tiff"],
                "validation": {"max_size_mb": 10, "min_dimension": 300, "aspect_ratio": [0.4, 2.5]},
                "folders": {"input": "Source", "output": "Generated_Video", "metadata": "Metadata"},
                "rate_limit": 3, "task_delay": 10, "max_retries": 3,
                "config_structure": "task_folders",
                "output_filename": "{base_name}_generated.mp4",
                "api_params": {"mode": "std", "duration": 5, "cfg": 0.5, "model_version": "v2.1"}
            },
            "nano_banana": {
                "endpoint": "http://192.168.4.3:8000/google_flash_image/",
                "api_name": "/nano_banana",
                "file_types": [".jpg", ".jpeg", ".png", ".bmp", ".tiff"],
                "validation": {"max_size_mb": 10, "min_dimension": 100},
                "folders": {"input": "Source", "output": "Generated_Output", "metadata": "Metadata"},
                "rate_limit": 5, "task_delay": 10, "max_retries": 3,
                "special_handling": "base64_images",
                "output_filename": "{base_name}_image_{index}.{ext}",
                "parallel_validation": True
            },
            "runway": {
                "endpoint": "http://192.168.4.3:8000/runway/",
                "api_name": "/submit_1",
                "file_types": {
                    "video": [".mp4", ".mov", ".avi", ".mkv", ".webm"],
                    "image": [".jpg", ".jpeg", ".png", ".bmp"]
                },
                "validation": {
                    "video": {"max_size_mb": 500, "min_dimension": 320, "duration": [1, 30]},
                    "image": {"max_size_mb": 10, "min_dimension": 320}
                },
                "folders": {"input": "Source", "reference": "Reference", "output": "Generated_Video", "metadata": "Metadata"},
                "rate_limit": 3, "task_delay": 10, "max_retries": 3,
                "special_handling": "video_with_reference",
                "output_filename": "{base_name}_ref_{ref_stem}_runway_generated.mp4",
                "pairing_strategies": ["one_to_one", "all_combinations"],
                "available_ratios": ["1280:720", "720:1280", "1104:832", "960:960", "832:1104", "1584:672", "848:480", "640:480"],
            },
            "vidu_effects": {
                "endpoint": "http://192.168.4.3:8000/video_effect/",
                "api_name": "/effect_submit_api",
                "file_types": [".jpg", ".jpeg", ".png", ".webp"],
                "validation": {"max_size_mb": 50, "min_dimension": 128, "aspect_ratio": [0.25, 4.0]},
                "folders": {"input": "Source", "output": "Generated_Video", "metadata": "Metadata"},
                "rate_limit": 3, "task_delay": 10, "max_retries": 3,
                "api_params": {"aspect_ratio": "as input image", "area": "auto", "beast": "auto", "bgm": False},
                "output_filename": "{base_name}_{effect_name}_effect.mp4",
                "parallel_validation": True, "fast_validation": True
            },
            "vidu_reference": {
                "endpoint": "http://192.168.4.3:8000/video_effect/",
                "api_name": "/reference_api",
                "file_types": [".jpg", ".jpeg", ".png", ".webp"],
                "validation": {"max_size_mb": 50, "min_dimension": 128, "aspect_ratio": [0.25, 4.0]},
                "folders": {"input": "Source", "reference": "Reference", "output": "Generated_Video", "metadata": "Metadata"},
                "rate_limit": 3, "task_delay": 10, "max_retries": 3,
                "special_handling": "multi_image_reference",
                "output_filename": "{base_name}_{effect_clean}.mp4",
                "max_references": 6, "aspect_ratios": ["9:16", "16:9", "1:1"]
            },
            "genvideo": {
                "endpoint": "http://192.168.4.3:8000/genvideo/",
                "api_name": "/submit_img2img",
                "file_types": [".jpg", ".jpeg", ".png", ".bmp", ".tiff"],
                "validation": {"max_size_mb": 50, "min_dimension": 128},
                "folders": {"input": "Source", "output": "Generated_Image", "metadata": "Metadata"},
                "rate_limit": 3, "task_delay": 10, "max_retries": 3,
                "config_structure": "task_folders",
                "output_filename": "{base_name}_generated.png",
                "api_params": {
                    "model": "gpt-image-1",
                    "img_prompt": "Generate a portrait-oriented image of a realistic, clear plastic gashapon capsule being held between two fingers as depicted in the provided image. Inside the capsule is a Chibi-style, full-figure miniature version of the person in the uploaded photo. The focus should be on the hand holding the capsule and the clear plastic material.",
                    "quality": "low"
                },
                "model_options": ["gpt-image-1", "gemini-2.5-flash-image-preview"],
                "quality_options": ["low", "medium", "high"]
            },
            "pixverse": {
                "endpoint": "http://192.168.4.3:8000/video_effect/",
                "api_name": "/submit_3",
                "file_types": [".jpg", ".jpeg", ".png", ".bmp", ".tiff"],
                "validation": {
                    "max_size_mb": 50,
                    "min_dimension": 128,
                    "aspect_ratio": [0.25, 4.0]
                },
                "folders": {
                    "input": "Source",
                    "output": "Generated_Video", 
                    "metadata": "Metadata"
                },
                "rate_limit": 3,
                "task_delay": 10,
                "max_retries": 3,
                "parallel_validation": True
            }
        }
        self.api_definitions = defaults.get(self.api_name, {})

    def load_config(self):
        """Load and validate configuration"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                self.logger.info(f"✓ Configuration loaded from {self.config_file}")
                return True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"❌ Config error: {e}")
            return False

    def _get_video_info(self, video_path):
        """Get video information using ffprobe (from runway processor)"""
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', str(video_path)
            ], capture_output=True, text=True)

            if result.returncode != 0:
                return None

            info = json.loads(result.stdout)
            video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)

            if video_stream:
                return {
                    'width': int(video_stream.get('width', 0)),
                    'height': int(video_stream.get('height', 0)),
                    'duration': float(info['format'].get('duration', 0)),
                    'size_mb': float(info['format'].get('size', 0)) / (1024 * 1024)
                }
            return None
        except Exception:
            return None

    def validate_file(self, file_path, file_type='image'):
        """Enhanced file validation with API-specific optimizations"""
        try:
            validation_rules = self.api_definitions.get('validation', {})

            if file_type == 'video':
                # Enhanced video validation for Runway
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                video_rules = validation_rules.get('video', {})

                if file_size_mb > video_rules.get('max_size_mb', 500):
                    return False, f"Size {file_size_mb:.1f}MB too large"

                info = self._get_video_info(file_path)
                if not info:
                    return False, "Cannot read video info"

                duration_range = video_rules.get('duration', [1, 30])
                if not (duration_range[0] <= info['duration'] <= duration_range[1]):
                    return False, f"Duration {info['duration']:.1f}s invalid"

                min_dim = video_rules.get('min_dimension', 320)
                if info['width'] < min_dim or info['height'] < min_dim:
                    return False, f"Resolution {info['width']}x{info['height']} too small"

                return True, f"{info['width']}x{info['height']}, {info['duration']:.1f}s, {info['size_mb']:.1f}MB"

            else:
                # Enhanced image validation
                if self.api_name == "kling":
                    # Kling specific validation (matching working processor)
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    if file_size_mb >= 10:  # 10MB limit
                        return False, "Size > 10MB"

                    with Image.open(file_path) as img:
                        w, h = img.size
                        if w <= 300 or h <= 300:
                            return False, f"Dims {w}x{h} too small"

                        ratio = w / h
                        if not (0.4 <= ratio <= 2.5):
                            return False, f"Ratio {ratio:.2f} invalid"

                        return True, f"{w}x{h}, {ratio:.2f}"

                elif self.api_name == "runway":
                    # Runway reference image validation
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    if file_size_mb >= 10:
                        return False, "Reference image > 10MB"

                    with Image.open(file_path) as img:
                        w, h = img.size
                        if w < 320 or h < 320:
                            return False, f"Reference image {w}x{h} too small"
                        return True, f"Reference: {w}x{h}"

                elif self.api_name == "nano_banana":
                    # Nano banana specific validation (matching working processor)
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    if file_size_mb >= 10:
                        return False, "Size > 10MB"

                    with Image.open(file_path) as img:
                        w, h = img.size
                        if w <= 100 or h <= 100:
                            return False, f"Dims {w}x{h} too small"
                        return True, f"{w}x{h}"

                else:
                    # Standard image validation for vidu APIs
                    fast_validation = self.api_definitions.get('fast_validation', False)

                    if fast_validation and isinstance(file_path, Path):
                        file_size_mb = file_path.stat().st_size / (1024 * 1024)
                    else:
                        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

                    max_size = validation_rules.get('max_size_mb', 50)
                    if file_size_mb >= max_size:
                        return False, f"Size > {max_size}MB"

                    with Image.open(file_path) as img:
                        w, h = img.size
                        min_dim = validation_rules.get('min_dimension', 128)
                        if w < min_dim or h < min_dim:
                            return False, f"Dims {w}x{h} too small"

                        # Check aspect ratio if defined
                        aspect_ratio_range = validation_rules.get('aspect_ratio')
                        if aspect_ratio_range:
                            ratio = w / h
                            if not (aspect_ratio_range[0] <= ratio <= aspect_ratio_range[1]):
                                return False, f"Ratio {ratio:.2f} invalid"

                        return True, f"{w}x{h}"

        except Exception as e:
            return False, f"Error: {str(e)}"

    def validate_and_prepare(self):
        """Enhanced validation with parallel processing support"""
        if self.api_name == "kling":
            return self._validate_kling_structure()
        elif self.api_name == "nano_banana":
            return self._validate_nano_banana_structure()
        elif self.api_name == "runway":
            return self._validate_runway_structure()
        elif self.api_name == "vidu_effects":
            return self._validate_vidu_effects_structure()
        elif self.api_name == "vidu_reference":
            return self._validate_vidu_reference_structure()
        elif self.api_name == "genvideo":
            return self.validate_genvideo_structure()
        elif self.api_name == "pixverse":
            return self.validate_pixverse_structure()
        else:
            raise ValueError(f"Validation failed for unknown API: {self.api_name}")

    def _validate_kling_structure(self):
        """Enhanced Kling validation with task folder structure (from working processor)"""
        valid_tasks = []
        invalid_images = []

        for i, task in enumerate(self.config.get('tasks', [])):
            folder = Path(task['folder'])
            source_folder = folder / "Source"

            if not source_folder.exists():
                self.logger.warning(f"❌ Missing source: {source_folder}")
                continue

            # Get all image files
            image_files = [f for f in source_folder.iterdir()
                         if f.suffix.lower() in self.api_definitions['file_types']]

            if not image_files:
                self.logger.warning(f"❌ Empty source: {source_folder}")
                continue

            # Validate images and count valid ones
            valid_count = 0
            for img_file in image_files:
                is_valid, reason = self.validate_file(img_file)
                if not is_valid:
                    invalid_images.append({
                        'path': str(img_file), 'folder': str(folder),
                        'name': img_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1

            if valid_count > 0:
                # Create output directories
                (folder / "Generated_Video").mkdir(exist_ok=True)
                (folder / "Metadata").mkdir(exist_ok=True)
                valid_tasks.append(task)
                self.logger.info(f"✓ Task {i+1}: {valid_count}/{len(image_files)} valid images")

        if invalid_images:
            self.write_invalid_report(invalid_images, "kling")
            raise Exception(f"{len(invalid_images)} invalid images found")

        return valid_tasks
    def _validate_nano_banana_structure(self):
        """Enhanced Nano Banana validation with parallel processing (from working processor)"""
        valid_tasks = []
        invalid_images = []

        def process_task(task):
            folder = Path(task['folder'])
            source_folder = folder / "Source"

            if not source_folder.exists():
                return None, []

            # Get and validate images
            image_files = [f for f in source_folder.iterdir()
                         if f.suffix.lower() in self.api_definitions['file_types']]

            if not image_files:
                return None, []

            # Validate images
            invalid_for_task = []
            valid_count = 0

            for img_file in image_files:
                is_valid, reason = self.validate_file(img_file)
                if not is_valid:
                    invalid_for_task.append({
                        'path': str(img_file), 'folder': str(folder),
                        'name': img_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1

            if valid_count > 0:
                # Create output directories
                (folder / "Generated_Output").mkdir(exist_ok=True)
                (folder / "Metadata").mkdir(exist_ok=True)
                self.logger.info(f"✓ Task: {folder.name} - {valid_count}/{len(image_files)} valid images")
                return task, invalid_for_task

            return None, invalid_for_task

        # Process tasks in parallel if enabled
        if self.api_definitions.get('parallel_validation', False):
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(process_task, self.config.get('tasks', [])))
        else:
            results = [process_task(task) for task in self.config.get('tasks', [])]

        # Collect results
        for task, invalid_for_task in results:
            if task:
                valid_tasks.append(task)
            invalid_images.extend(invalid_for_task)

        if invalid_images:
            self.write_invalid_report(invalid_images, "nano_banana")
            raise Exception(f"{len(invalid_images)} invalid images found")

        return valid_tasks

    def _validate_runway_structure(self):
        """Enhanced Runway validation with optional reference image support"""
        valid_tasks = []
        invalid_videos = []
        
        for i, task in enumerate(self.config.get('tasks', []), 1):
            folder = Path(task['folder'])
            source_folder = folder / "Source"
            
            if not source_folder.exists():
                self.logger.warning(f"Missing source {source_folder}")
                continue
            
            # Check if reference is required
            use_comparison_template = task.get('use_comparison_template', False)
            reference_folder_path = task.get('reference_folder', '').strip()
            requires_reference = use_comparison_template or bool(reference_folder_path)
            
            # Validate reference folder if required
            reference_images = []
            if requires_reference:
                if reference_folder_path:
                    ref_folder = Path(reference_folder_path)
                else:
                    ref_folder = folder / "Reference"
                
                if not ref_folder.exists():
                    self.logger.warning(f"Missing reference folder {ref_folder}")
                    continue
                
                reference_images = [f for f in ref_folder.iterdir() 
                                if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp']]
                
                if not reference_images:
                    self.logger.warning(f"Empty reference folder {ref_folder}")
                    continue
            
            # Get video files
            video_files = [f for f in source_folder.iterdir() 
                        if f.suffix.lower() in self.api_definitions['file_types']['video']]
            
            if not video_files:
                self.logger.warning(f"Empty source folder {source_folder}")
                continue
            
            # Validate videos
            valid_count = 0
            for video_file in video_files:
                is_valid, reason = self.validate_file(video_file, 'video')
                if not is_valid:
                    invalid_videos.append({
                        'path': str(video_file),
                        'folder': str(folder),
                        'name': video_file.name,
                        'reason': reason
                    })
                else:
                    valid_count += 1
            
            if valid_count == 0:
                continue
            
            # Create output directories
            (folder / "Generated_Video").mkdir(exist_ok=True)
            (folder / "Metadata").mkdir(exist_ok=True)
            
            # Update task config
            task['requires_reference'] = requires_reference
            if requires_reference:
                task['reference_images'] = reference_images
            
            valid_tasks.append(task)
            self.logger.info(f"Task {i}: {valid_count}/{len(video_files)} valid videos" + 
                            (f", {len(reference_images)} reference images" if requires_reference else " (text-to-video mode)"))
        
        if invalid_videos:
            self.write_invalid_report(invalid_videos, 'runway')
            raise Exception(f"{len(invalid_videos)} invalid videos found")
        
        return valid_tasks


    def _validate_vidu_effects_structure(self):
        """Enhanced Vidu Effects validation with parallel processing"""
        base_folder = Path(self.config.get('base_folder', ''))
        if not base_folder.exists():
            raise FileNotFoundError(f"Base folder not found: {base_folder}")

        valid_tasks = []
        invalid_images = []

        def process_task(task):
            effect_name = task.get('effect', '')
            task_folder = base_folder / effect_name
            source_dir = task_folder / "Source"

            if not source_dir.exists():
                return None, []

            # Get and validate images
            image_files = [f for f in source_dir.iterdir()
                         if f.suffix.lower() in self.api_definitions['file_types']]

            if not image_files:
                return None, []

            # Validate images
            invalid_for_task = []
            valid_count = 0

            for img_file in image_files:
                is_valid, reason = self.validate_file(img_file)
                if not is_valid:
                    invalid_for_task.append({
                        'folder': effect_name, 'filename': img_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1

            if valid_count > 0:
                # Create output directories
                (task_folder / "Generated_Video").mkdir(exist_ok=True)
                (task_folder / "Metadata").mkdir(exist_ok=True)

                # Add folder paths to task
                enhanced_task = task.copy()
                enhanced_task.update({
                    'folder': str(task_folder),
                    'source_dir': str(source_dir),
                    'generated_dir': str(task_folder / "Generated_Video"),
                    'metadata_dir': str(task_folder / "Metadata")
                })

                self.logger.info(f"✓ {effect_name}: {valid_count}/{len(image_files)} valid images")
                return enhanced_task, invalid_for_task

            return None, invalid_for_task

        # Use parallel processing if enabled
        if self.api_definitions.get('parallel_validation', False):
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(process_task, self.config.get('tasks', [])))
        else:
            results = [process_task(task) for task in self.config.get('tasks', [])]

        # Collect results
        for task, invalid_for_task in results:
            if task:
                valid_tasks.append(task)
            invalid_images.extend(invalid_for_task)

        if invalid_images:
            self.write_invalid_report(invalid_images)
            raise Exception(f"{len(invalid_images)} invalid images found")

        return valid_tasks

    def _validate_vidu_reference_structure(self):
        """Enhanced Vidu Reference validation with smart reference finding"""
        base_folder = Path(self.config.get('base_folder', ''))
        if not base_folder.exists():
            raise FileNotFoundError(f"Base folder not found: {base_folder}")

        configured_tasks = {t['effect']: t for t in self.config.get('tasks', [])}
        valid_tasks = []
        errors = []

        for folder in base_folder.iterdir():
            if not (folder.is_dir() and not folder.name.startswith(('.', '_')) and
                   (folder / 'Source').exists() and (folder / 'Reference').exists()):
                continue

            # Get task config or create default
            if folder.name in configured_tasks:
                task = configured_tasks[folder.name].copy()
                task['folder_path'] = str(folder)
                self.logger.info(f"✓ Matched: {folder.name}")
            else:
                task = {
                    'effect': folder.name, 'folder_path': str(folder),
                    'prompt': self.config.get('default_prompt', ''),
                    'model': self.config.get('model', 'default'),
                    'duration': self.config.get('duration', 5),
                    'resolution': self.config.get('resolution', '1080p'),
                    'movement': self.config.get('movement', 'auto')
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

        return valid_tasks

    def _validate_reference_task(self, task):
        """Enhanced reference task validation with smart reference finding"""
        fp = Path(task['folder_path'])
        src_dir, ref_dir = fp / 'Source', fp / 'Reference'

        if not (src_dir.exists() and ref_dir.exists()):
            return None, [f"{task['effect']}: Missing Source/Reference folders"]

        src_imgs = [f for f in src_dir.iterdir()
                   if f.suffix.lower() in self.api_definitions['file_types']]

        if not src_imgs:
            return None, [f"{task['effect']}: No source images"]

        ref_imgs = self._find_reference_images(ref_dir)
        if not ref_imgs:
            return None, [f"{task['effect']}: No reference images"]

        valid_sets = []
        for src in src_imgs:
            invalids = []

            try:
                with Image.open(src) as img:
                    ar = self.closest_aspect_ratio(img.width, img.height)
                    self.logger.info(f" 📐 {src.name} ({img.width}x{img.height}) → {ar}")
            except Exception as e:
                invalids.append(f"{src.name}: Cannot read dims - {e}")
                continue

            for img in [src] + ref_imgs:
                valid, reason = self.validate_file(img)
                if not valid:
                    invalids.append(f"{img.name}: {reason}")

            if not invalids:
                valid_sets.append({
                    'source_image': src, 'reference_images': ref_imgs,
                    'all_images': [src] + ref_imgs, 'aspect_ratio': ar,
                    'reference_count': len(ref_imgs)
                })
                self.logger.info(f" Found {len(ref_imgs)} reference images for {src.name}")

        if not valid_sets:
            return None, [f"{task['effect']}: No valid image sets"]

        # Create output directories
        for d in ['Generated_Video', 'Metadata']:
            (fp / d).mkdir(exist_ok=True)

        task.update({
            'generated_dir': str(fp / 'Generated_Video'),
            'metadata_dir': str(fp / 'Metadata'),
            'image_sets': valid_sets
        })

        return task, []

    def _find_reference_images(self, ref_dir):
        """Smart reference image finding from reference_processor"""
        refs = []
        file_types = self.api_definitions['file_types']
        max_refs = self.api_definitions.get('max_references', 6)

        # Smart naming convention detection
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

        # Fallback to sorted files if no naming convention found
        return refs or sorted([f for f in ref_dir.iterdir()
                             if f.suffix.lower() in file_types])[:max_refs]

    def closest_aspect_ratio(self, w, h):
        """Enhanced aspect ratio detection from reference_processor"""
        r = w / h
        aspect_ratios = self.api_definitions.get('aspect_ratios', ["16:9", "9:16", "1:1"])

        if "16:9" in aspect_ratios and r > 1.2:
            return "16:9"
        elif "9:16" in aspect_ratios and r < 0.8:
            return "9:16"
        else:
            return "1:1"

    def write_invalid_report(self, invalid_files, api_suffix=""):
        """Enhanced invalid files report"""
        report_name = f"invalid_{self.api_name}_report.txt"
        if api_suffix:
            report_name = f"invalid_images_{api_suffix}_report.txt"

        with open(report_name, 'w', encoding='utf-8') as f:
            f.write(f"INVALID FILES ({len(invalid_files)} total)\n")
            f.write(f"Generated: {datetime.now()}\n\n")

            for file in invalid_files:
                if 'folder' in file:
                    if 'filename' in file:
                        f.write(f"❌ {file['folder']}: {file['filename']} - {file['reason']}\n")
                    else:
                        f.write(f"❌ {file['name']} in {file['folder']}: {file['reason']}\n")
                elif 'type' in file:
                    f.write(f"❌ {file['name']} ({file['type']}) in {file.get('folder', 'unknown')}: {file['reason']}\n")
                else:
                    f.write(f"❌ {file['name']} in {file.get('path', 'unknown')}: {file['reason']}\n")

    def wait_for_schedule(self):
        """Wait for scheduled time if specified"""
        start_time_str = self.config.get('schedule', {}).get('start_time', '')
        if not start_time_str:
            return

        try:
            target_hour, target_min = map(int, start_time_str.split(':'))
            now = datetime.now()
            target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)

            if target <= now:
                target = target.replace(day=target.day + 1)

            wait_seconds = (target - now).total_seconds()
            self.logger.info(f"⏰ Waiting {wait_seconds/3600:.1f}h until {target.strftime('%H:%M')}")
            time.sleep(wait_seconds)
        except ValueError:
            self.logger.warning(f"❌ Invalid time format: {start_time_str}")

    def initialize_client(self):
        """Initialize Gradio client"""
        try:
            endpoint = self.api_definitions.get('endpoint', '')

            # Handle testbed URL override for nano_banana
            if self.api_name == "nano_banana" and self.config.get('testbed'):
                endpoint = self.config['testbed']

            self.client = Client(endpoint)
            self.logger.info(f"✓ Client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Client init failed: {e}")
            return False

    def download_video_streaming(self, url, path):
        """Kling-style streaming video download method (from working processor)"""
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            return True
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return False

    def save_nano_responses(self, response_data, output_folder, base_name):
        """Save nano banana response data with base64 image handling (from working processor)"""
        if not response_data or not isinstance(response_data, list):
            return [], []

        saved_files = []
        text_responses = []

        for i, item in enumerate(response_data):
            if not isinstance(item, dict) or 'type' not in item or 'data' not in item:
                continue

            if item['type'] == "Text":
                text_responses.append({'index': i + 1, 'content': item['data']})
            elif item['type'] == "Image" and item['data'].strip():
                try:
                    # Handle base64 image data
                    if item['data'].startswith('image'):
                        header, base64_data = item['data'].split(',', 1)
                        ext = header.split('/')[1].split(';')[0]
                    else:
                        base64_data = item['data']
                        ext = 'png'

                    if len(base64_data.strip()) == 0:
                        continue

                    image_bytes = base64.b64decode(base64_data)
                    if len(image_bytes) < 100:  # Too small, likely invalid
                        continue

                    image_file = output_folder / f"{base_name}_image_{i+1}.{ext}"
                    with open(image_file, 'wb') as f:
                        f.write(image_bytes)

                    saved_files.append(str(image_file))
                except Exception as e:
                    self.logger.warning(f"Error saving image {i+1}: {e}")

        return saved_files, text_responses
    def process_file(self, file_path, task_config, output_folder, metadata_folder):
        """Enhanced file processing with API-specific optimizations"""
        max_retries = self.api_definitions.get('max_retries', 3)

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self.logger.info(f" 🔄 Retry {attempt}/{max_retries-1}")
                    time.sleep(5)

                # API-specific processing
                if self.api_name == "kling":
                    result = self.process_kling(file_path, task_config, output_folder, metadata_folder, attempt, max_retries)
                elif self.api_name == "nano_banana":
                    result = self.process_nano_banana(file_path, task_config, output_folder, metadata_folder, attempt, max_retries)
                elif self.api_name == "runway":
                    result = self.process_runway(file_path, task_config, output_folder, metadata_folder, attempt, max_retries)
                elif self.api_name == "vidu_effects":
                    result = self.process_vidu_effects(file_path, task_config, output_folder, metadata_folder, attempt, max_retries)
                elif self.api_name == "vidu_reference":
                    result = self.process_vidu_reference(file_path, task_config, output_folder, metadata_folder, attempt, max_retries)
                elif self.api_name == "genvideo":
                    result = self.process_genvideo(file_path, task_config, output_folder, metadata_folder, attempt, max_retries)
                elif self.api_name == "pixverse":
                    result = self.process_pixverse(file_path, task_config, output_folder, metadata_folder, attempt, max_retries)

                if not result and attempt < max_retries - 1:
                    continue  # Retry
                return result

            except Exception as e:
                if attempt == max_retries - 1:
                    self.save_failure_metadata(file_path, task_config, metadata_folder, str(e), attempt + 1)
                    return False
                continue

        return False

    def process_kling(self, image_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process Kling API call using the working processor approach"""
        base_name = Path(image_path).stem
        image_name = Path(image_path).name
        start_time = time.time()

        try:
            # Make API call using the exact working structure from advanced_batch_processor.py
            result = self.client.predict(
                image=handle_file(str(image_path)),
                prompt=task_config['prompt'],
                mode="std",
                duration=5,
                cfg=0.5,
                model=self.config.get('model_version', 'v2.1'),
                negative_prompt=task_config.get('negative_prompt', ''),
                api_name=self.api_definitions['api_name']
            )

            # Extract results - matching working processor logic
            url, video_dict, video_id, task_id, error = result[:5]
            self.logger.info(f" Video ID: {video_id}")
            self.logger.info(f" Task ID: {task_id}")

            # Check for API errors first
            if error:
                self.logger.info(f" ❌ API Error: {error}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    return False  # Will trigger retry
                else:
                    # Final attempt failed - save failure metadata
                    self.save_kling_metadata(Path(metadata_folder), base_name, image_name, {
                        'video_id': video_id, 'task_id': task_id, 'error': error,
                        'attempts': attempt + 1, 'success': False,
                        'processing_time_seconds': round(time.time() - start_time, 1)
                    }, task_config)
                    return False

            # Try to save video file
            output_path = Path(output_folder) / f"{base_name}_generated.mp4"
            video_saved = False

            # Method 1: Download from URL (using streaming)
            if url:
                video_saved = self.download_video_streaming(url, output_path)
                if not video_saved:
                    self.logger.info(f" ⚠️ URL download failed, trying local file...")

            # Method 2: Copy from local file
            if not video_saved and video_dict and 'video' in video_dict:
                local_path = Path(video_dict['video'])
                if local_path.exists():
                    shutil.copy2(local_path, output_path)
                    self.logger.info(f" ✓ Video copied from local file: {output_path}")
                    video_saved = True
                else:
                    self.logger.info(f" ❌ Local video file not found: {local_path}")

            if video_saved:
                # SUCCESS - Save success metadata
                self.save_kling_metadata(Path(metadata_folder), base_name, image_name, {
                    'output_url': url, 'video_id': video_id, 'task_id': task_id,
                    'generated_video': output_path.name, 'attempts': attempt + 1,
                    'success': True, 'processing_time_seconds': round(time.time() - start_time, 1)
                }, task_config)
                self.logger.info(f" ✅ Generated: {output_path.name}")
                return True
            else:
                # Video generation succeeded but file save failed
                if attempt < max_retries - 1:
                    self.logger.info(f" ❌ Video file save failed, retrying...")
                    time.sleep(5)
                    return False
                else:
                    # Final attempt - save partial success metadata
                    self.save_kling_metadata(Path(metadata_folder), base_name, image_name, {
                        'output_url': url, 'video_id': video_id, 'task_id': task_id,
                        'error': "Video file could not be saved", 'attempts': attempt + 1,
                        'success': False, 'processing_time_seconds': round(time.time() - start_time, 1)
                    }, task_config)
                    return False

        except Exception as e:
            # Save failure metadata
            processing_time = time.time() - start_time
            self.save_kling_metadata(Path(metadata_folder), base_name, image_name, {
                'error': str(e), 'success': False, 'attempts': attempt + 1,
                'processing_time_seconds': round(processing_time, 1)
            }, task_config)
            raise e

    def process_nano_banana(self, image_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process Nano Banana API call using the working google flash processor approach"""
        base_name = Path(image_path).stem
        image_name = Path(image_path).name
        start_time = time.time()

        try:
            # Get additional images (if any)
            additional_images = task_config.get('additional_images', {})

            # Make API call using the working structure from google_flash_processor.py
            result = self.client.predict(
                prompt=task_config['prompt'],
                image1=handle_file(str(image_path)),
                image2=additional_images.get('image1', ''),
                image3=additional_images.get('image2', ''),
                api_name=self.api_definitions['api_name']
            )

            # Extract results - matching working processor logic
            response_id, error_msg, response_data = result[:3]
            self.logger.info(f" Response ID: {response_id}")

            if error_msg:
                self.logger.info(f" ❌ API Error: {error_msg}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    return False

                # Save failure metadata
                self.save_nano_metadata(Path(metadata_folder), base_name, image_name, {
                    'response_id': response_id, 'error': error_msg, 'success': False,
                    'attempts': attempt + 1, 'processing_time_seconds': round(time.time() - start_time, 1)
                }, task_config)
                return False

            # Save response data using base64 handling
            saved_files, text_responses = self.save_nano_responses(response_data, Path(output_folder), base_name)
            has_images = len(saved_files) > 0

            # Retry if no images generated
            if not has_images and attempt < max_retries - 1:
                self.logger.info(f" ⚠️ No images generated, retrying...")
                time.sleep(5)
                return False

            # Save success metadata (matching working processor structure)
            processing_time = time.time() - start_time
            metadata = {
                'response_id': response_id, 'saved_files': [Path(f).name for f in saved_files],
                'text_responses': text_responses, 'success': has_images, 'attempts': attempt + 1,
                'images_generated': len(saved_files), 'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'api_name': self.api_name
            }

            self.save_nano_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)

            if has_images:
                self.logger.info(f" ✅ Generated: {len(saved_files)} images")
                return True
            else:
                self.logger.info(f" ❌ No images generated")
                return False

        except Exception as e:
            # Save failure metadata
            processing_time = time.time() - start_time
            metadata = {
                'error': str(e), 'success': False, 'attempts': attempt + 1,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'api_name': self.api_name
            }
            self.save_nano_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)
            raise e

    def process_runway(self, video_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process Runway API call with optional reference image support"""
        basename = Path(video_path).stem
        video_name = Path(video_path).name
        
        # Check if reference image is required based on config
        use_comparison_template = task_config.get('use_comparison_template', False)
        reference_folder = task_config.get('reference_folder', '').strip()
        requires_reference = bool(use_comparison_template) or bool(reference_folder)
        
        # Handle reference image conditionally
        reference_image_path = None
        ref_stem = ""
        
        if requires_reference:
            reference_image_path = task_config.get('reference_image', '')
            if not reference_image_path or not Path(reference_image_path).exists():
                raise Exception("Reference image required but not found")
            ref_stem = Path(reference_image_path).stem
        
        start_time = time.time()
        
        try:
            # Get video info for optimal ratio
            video_info = self._get_video_info(video_path)
            if video_info:
                optimal_ratio = self.get_optimal_runway_ratio(video_info['width'], video_info['height'])
                self.logger.info(f"Video {video_info['width']}x{video_info['height']} - Using ratio {optimal_ratio}")
            else:
                optimal_ratio = self.config.get('ratio', '1280:720')
                self.logger.warning(f"Could not get video info, using default ratio {optimal_ratio}")
            
            # Make API call with or without reference image
            if requires_reference:
                result = self.client.predict(
                    video_path={"video": handle_file(str(video_path))},
                    prompt=task_config['prompt'],
                    model=self.config.get('model', 'gen4_aleph'),
                    ratio=optimal_ratio,
                    reference_image=handle_file(str(reference_image_path)),
                    public_figure_moderation=self.config.get('public_figure_moderation', 'low'),
                    api_name=self.api_definitions['api_name']
                )
            else:
                # Text-to-video without reference image
                result = self.client.predict(
                    video_path={"video": handle_file(str(video_path))},
                    prompt=task_config['prompt'],
                    model=self.config.get('model', 'gen4_aleph'),
                    ratio=optimal_ratio,
                    reference_image = None,
                    public_figure_moderation=self.config.get('public_figure_moderation', 'low'),
                    api_name=self.api_definitions['api_name']
                )
            
            # Extract results
            output_url = result[0] if len(result) > 0 else None
            
            if not output_url:
                self.logger.info("No output URL received")
                processing_time = time.time() - start_time
                metadata = {
                    'source_video': video_name,
                    'source_dimensions': f"{video_info['width']}x{video_info['height']}" if video_info else "unknown",
                    'reference_image': Path(reference_image_path).name if reference_image_path else None,
                    'prompt': task_config['prompt'],
                    'model': self.config.get('model', 'gen4_aleph'),
                    'ratio': optimal_ratio,
                    'public_figure_moderation': self.config.get('public_figure_moderation', 'low'),
                    'error': "No output URL received",
                    'processing_time_seconds': round(processing_time, 1),
                    'processing_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'attempts': attempt + 1,
                    'success': False,
                    'api_name': self.api_name
                }
                
                self.save_runway_metadata(Path(metadata_folder), basename, ref_stem, video_name, 
                                        Path(reference_image_path).name if reference_image_path else None, 
                                        metadata, task_config)
                return False
            
            # Generate output filename based on whether reference is used
            if reference_image_path:
                output_filename = f"{basename}_ref_{ref_stem}_runway_generated.mp4"
            else:
                output_filename = f"{basename}_text_runway_generated.mp4"
                
            output_path = Path(output_folder) / output_filename
            
            # Download video
            video_saved = self.download_file(output_url, output_path)
            
            processing_time = time.time() - start_time
            metadata = {
                'source_video': video_name,
                'source_dimensions': f"{video_info['width']}x{video_info['height']}" if video_info else "unknown",
                'reference_image': Path(reference_image_path).name if reference_image_path else None,
                'prompt': task_config['prompt'],
                'model': self.config.get('model', 'gen4_aleph'),
                'ratio': optimal_ratio,
                'public_figure_moderation': self.config.get('public_figure_moderation', 'low'),
                'output_url': output_url,
                'generated_video': output_filename,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'attempts': attempt + 1,
                'success': video_saved,
                'api_name': self.api_name,
                'generation_type': 'image_to_video' if reference_image_path else 'text_to_video'
            }

            self.save_runway_metadata(Path(metadata_folder), basename, ref_stem, video_name,
                                    Path(reference_image_path).name if reference_image_path else None,
                                    metadata, task_config)
            
            if video_saved:
                self.logger.info(f"Generated {output_filename} (ratio {optimal_ratio})")
                return True
            else:
                self.logger.info("Video generation succeeded but file save failed")
                return False
                
        except Exception as e:
            processing_time = time.time() - start_time
            metadata = {
                'source_video': video_name,
                'source_dimensions': f"{video_info['width']}x{video_info['height']}" if 'video_info' in locals() and video_info else "unknown",
                'reference_image': Path(reference_image_path).name if reference_image_path else None,
                'prompt': task_config['prompt'],
                'model': self.config.get('model', 'gen4_aleph'),
                'ratio': optimal_ratio if 'optimal_ratio' in locals() else self.config.get('ratio', '1280:720'),
                'public_figure_moderation': self.config.get('public_figure_moderation', 'low'),
                'error': str(e),
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'attempts': attempt + 1,
                'success': False,
                'api_name': self.api_name,
                'generation_type': 'image_to_video' if reference_image_path else 'text_to_video'
            }
            
            self.save_runway_metadata(Path(metadata_folder), basename, ref_stem, video_name, 
                                    Path(reference_image_path).name if reference_image_path else None, 
                                    metadata, task_config)
            raise e

    def get_optimal_runway_ratio(self, video_width, video_height):
        input_ratio = video_width / video_height
        available_ratios = self.api_definitions.get('available_ratios', [...])
        
        # Find closest match by calculating ratio differences
        best_ratio = "1280:720"  # fallback
        smallest_difference = float('inf')
        
        for ratio_str in available_ratios:
            w, h = map(int, ratio_str.split(':'))
            ratio_value = w / h
            difference = abs(input_ratio - ratio_value)
            
            if difference < smallest_difference:
                smallest_difference = difference
                best_ratio = ratio_str
        
        return best_ratio

    def process_vidu_effects(self, image_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process Vidu Effects API call using the working effect processor approach"""
        base_name = Path(image_path).stem
        image_name = Path(image_path).name
        start_time = time.time()
        task_id = None

        try:
            # Get prompt (task-level or global)
            prompt = task_config.get('prompt', '') or self.config.get('prompt', '')
            effect = task_config.get('effect', '')

            # Make API call using the working structure from effect_processor.py
            result = self.client.predict(
                effect=effect,
                prompt=prompt,
                aspect_ratio="as input image",
                area="auto",
                beast="auto",
                bgm=False,
                images=(handle_file(str(image_path)),),
                api_name=self.api_definitions['api_name']
            )

            # Validate and extract result (matching working processor logic)
            if not isinstance(result, tuple) or len(result) < 5:
                raise ValueError(f"Invalid API response format")

            output_urls = result[0]

            task_id = result[2] if len(result) >= 3 else ''
            self.logger.info(f" Task ID: {task_id}")

            if not output_urls:
                error_msg = result 
                raise ValueError("No output URLs returned\n", error_msg)

            # Extract URL (handle both single URL and list of URLs)
            output_url = output_urls[0] if isinstance(output_urls, (tuple, list)) else output_urls

            # Download video
            effect_name = effect.replace(' ', '_').replace('-', '_')
            output_video_name = f"{base_name}_{effect_name}_effect.mp4"
            output_video_path = Path(output_folder) / output_video_name

            if not self.download_file(output_url, output_video_path):
                raise IOError("Video download failed")

            # Save success metadata (matching working processor structure)
            processing_time = time.time() - start_time
            metadata = {
                "source_image": image_name,
                "effect_category": task_config.get('category', ''),
                "effect_name": effect,
                "prompt": prompt,
                "output_url": output_url,
                "generated_video": output_video_name,
                "processing_time_seconds": round(processing_time, 1),
                "processing_timestamp": datetime.now().isoformat(),
                "task_id": task_id,
                "attempts": attempt + 1,
                "success": True,
                "api_name": self.api_name
            }

            self.save_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)
            self.logger.info(f" ✅ Generated: {output_video_name}")
            return True

        except Exception as e:
            # Save failure metadata
            processing_time = time.time() - start_time
            metadata = {
                "source_image": image_name,
                "effect_category": task_config.get('category', ''),
                "effect_name": task_config.get('effect', ''),
                "prompt": prompt if 'prompt' in locals() else '',
                "error_message": str(e),
                "processing_time_seconds": round(processing_time, 1),
                "processing_timestamp": datetime.now().isoformat(),
                "task_id": task_id if task_id else 'N/A',
                "attempts": attempt + 1,
                "success": False,
                "api_name": self.api_name
            }

            self.save_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)
            raise e

    def process_vidu_reference(self, source_image, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process Vidu Reference API call using the working reference processor approach"""
        base_name = source_image.stem
        image_name = source_image.name
        reference_images = task_config.get('reference_images', [])

        if not reference_images:
            raise Exception("No reference images provided")

        start_time = time.time()

        try:
            # Prepare all image handles (source + references) as a tuple
            all_images = [source_image] + [Path(ref_path) for ref_path in reference_images]
            img_handles = tuple(handle_file(str(img)) for img in all_images)

            # Get parameters with proper defaults
            effect = task_config.get('effect', '')
            prompt = task_config.get('prompt', '') or self.config.get('default_prompt', '')
            model = task_config.get('model', self.config.get('model', 'default'))
            duration = task_config.get('duration', self.config.get('duration', 5))
            aspect_ratio = task_config.get('aspect_ratio', '1:1')
            resolution = task_config.get('resolution', self.config.get('resolution', '1080p'))
            movement = task_config.get('movement', self.config.get('movement', 'auto'))

            self.logger.info(f" 📸 Processing: 1 source + {len(reference_images)} references ({aspect_ratio})")

            # Make API call using the working structure
            result = self.client.predict(
                model=model,
                prompt=prompt,
                duration=duration,
                aspect_ratio=aspect_ratio,
                images=img_handles,
                resolution=resolution,
                movement=movement,
                api_name=self.api_definitions['api_name']
            )

            # Validate result format
            if not isinstance(result, tuple) or len(result) < 4:
                raise ValueError("Invalid API response format")

            video_url, thumbnail_url, task_id, error_msg = result

            if error_msg:
                raise ValueError(f"API error: {error_msg}")

            if not video_url:
                raise ValueError("No video URL returned")

            # Save generated video
            effect_clean = effect.replace(' ', '_').replace('-', '_')
            output_filename = f"{base_name}_{effect_clean}.mp4"
            output_path = Path(output_folder) / output_filename

            if not self.download_file(video_url, output_path):
                raise IOError("Video download failed")

            # Save success metadata
            processing_time = time.time() - start_time
            metadata = {
                "source_image": image_name,
                "reference_images": [Path(ref).name for ref in reference_images],
                "reference_count": len(reference_images),
                "total_images": len(all_images),
                "effect_name": effect,
                "model": model,
                "prompt": prompt,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "movement": movement,
                "video_url": video_url,
                "thumbnail_url": thumbnail_url,
                "task_id": task_id,
                "generated_video": output_filename,
                "processing_time_seconds": round(processing_time, 1),
                "processing_timestamp": datetime.now().isoformat(),
                "attempts": attempt + 1,
                "success": True,
                "api_name": self.api_name
            }

            self.save_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)
            self.logger.info(f" ✅ Generated: {output_filename}")
            return True

        except Exception as e:
            # Save failure metadata
            processing_time = time.time() - start_time
            metadata = {
                "source_image": image_name,
                "reference_images": [Path(ref).name for ref in reference_images],
                "reference_count": len(reference_images),
                "effect_name": effect,
                "error_message": str(e),
                "processing_time_seconds": round(processing_time, 1),
                "processing_timestamp": datetime.now().isoformat(),
                "attempts": attempt + 1,
                "success": False,
                "api_name": self.api_name
            }

            self.save_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)
            raise e

    def save_failure_metadata(self, file_path, task_config, metadata_folder, error, attempts):
        """Enhanced failure metadata saving"""
        base_name = Path(file_path).stem
        metadata = {
            "source_file": Path(file_path).name,
            "error": error,
            "attempts": attempts,
            "success": False,
            "processing_timestamp": datetime.now().isoformat(),
            "api_name": self.api_name
        }

        # Add API-specific fields
        if 'prompt' in task_config:
            metadata['prompt'] = task_config['prompt']
        if 'effect' in task_config:
            metadata['effect'] = task_config['effect']

        metadata_file = Path(metadata_folder) / f"{base_name}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def save_metadata(self, metadata_folder, base_name, source_name, result_data, task_config):
        """Enhanced universal metadata saving"""
        metadata_file = metadata_folder / f"{base_name}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)

    def save_kling_metadata(self, metadata_folder, base_name, image_name, result_data, task_config):
        """Kling-specific metadata saving (matching working processor)"""
        metadata = {
            "source_image": image_name,
            "prompt": task_config['prompt'],
            "negative_prompt": task_config.get('negative_prompt', ''),
            "model_version": self.config.get('model_version', 'v2.1'),
            "processing_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            **result_data
        }

        metadata_file = metadata_folder / f"{base_name}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)

        status = "✓" if result_data.get('success') else "❌"
        self.logger.info(f" {status} Metadata saved: {metadata_file.name}")

    def save_nano_metadata(self, metadata_folder, base_name, image_name, result_data, task_config):
        """Nano Banana specific metadata saving (matching working processor)"""
        metadata = {
            "source_image": image_name,
            "prompt": task_config['prompt'],
            "additional_images": task_config.get('additional_images', {}),
            "processing_timestamp": datetime.now().isoformat(),
            **result_data
        }

        metadata_file = metadata_folder / f"{base_name}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    def save_runway_metadata(self, metadata_folder, base_name, ref_stem, video_name, ref_name, result_data, task_config):
        """Runway-specific metadata saving (matching working processor)"""
        metadata_file = metadata_folder / f"{base_name}_ref_{ref_stem}_runway_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=4, ensure_ascii=False)

        status = "✓" if result_data.get('success') else "❌"
        self.logger.info(f" {status} Meta {metadata_file.name}")

    def process_task(self, task, task_num, total_tasks):
        """Enhanced universal task processing with API-specific optimizations"""
        if self.api_name == "kling":
            self.process_kling_task(task, task_num, total_tasks)
        elif self.api_name == "nano_banana":
            self.process_nano_banana_task(task, task_num, total_tasks)
        elif self.api_name == "runway":
            self.process_runway_task(task, task_num, total_tasks)
        elif self.api_name == "vidu_effects":
            self.process_vidu_effects_task(task, task_num, total_tasks)
        elif self.api_name == "vidu_reference":
            self.process_vidu_reference_task(task, task_num, total_tasks)
        elif self.api_name == "genvideo":
            self.process_genvideo_task(task, task_num, total_tasks)
        elif self.api_name == "pixverse":
            self.process_pixverse_task(task, task_num, total_tasks)

    def process_kling_task(self, task, task_num, total_tasks):
        """Process Kling task with task folder structure (matching working processor)"""
        folder = Path(task['folder'])
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Video"
        metadata_folder = folder / "Metadata"

        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {folder.name}")

        # Get valid images (pre-validated)
        image_files = [f for f in source_folder.iterdir()
                      if f.suffix.lower() in self.api_definitions['file_types']]

        # Process images sequentially (to avoid API rate limits)
        successful = 0
        for i, img_file in enumerate(image_files, 1):
            self.logger.info(f" 🖼️ {i}/{len(image_files)}: {img_file.name}")

            if self.process_file(img_file, task, output_folder, metadata_folder):
                successful += 1

            if i < len(image_files):
                rate_limit = self.api_definitions.get('rate_limit', 3)
                time.sleep(rate_limit)  # Rate limiting

        self.logger.info(f"✓ Task {task_num}: {successful}/{len(image_files)} successful")

    def process_nano_banana_task(self, task, task_num, total_tasks):
        """Process Nano Banana task with base64 image handling"""
        folder = Path(task['folder'])
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Output"
        metadata_folder = folder / "Metadata"

        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {folder.name}")

        # Get all valid images
        image_files = [f for f in source_folder.iterdir()
                      if f.suffix.lower() in self.api_definitions['file_types']]

        successful = 0
        for i, img_file in enumerate(image_files, 1):
            self.logger.info(f" 🖼️ {i}/{len(image_files)}: {img_file.name}")

            if self.process_file(img_file, task, output_folder, metadata_folder):
                successful += 1

            if i < len(image_files):
                rate_limit = self.api_definitions.get('rate_limit', 5)
                time.sleep(rate_limit)

        self.logger.info(f"✓ Task {task_num}: {successful}/{len(image_files)} successful")

    def process_runway_task(self, task, task_num, total_tasks):
        """Process Runway task with optional video-reference pairing strategies"""
        folder = Path(task['folder'])
        self.logger.info(f"Task {task_num}/{total_tasks}: {folder.name}")
        
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Video"
        metadata_folder = folder / "Metadata"
        
        # Get video files
        video_files = [f for f in source_folder.iterdir() 
                    if f.suffix.lower() in self.api_definitions['file_types']['video']]
        
        requires_reference = task.get('requires_reference', False)
        
        if requires_reference:
            # Process with reference images
            reference_images = task.get('reference_images', [])
            pairing_strategy = task.get('pairing_strategy', 'one_to_one')
            
            if pairing_strategy == "all_combinations":
                # Every video with every reference image
                total_combinations = len(video_files) * len(reference_images)
                successful = 0
                
                for i, (video_file, ref_image) in enumerate(
                    [(v, r) for v in video_files for r in reference_images], 1):
                    
                    self.logger.info(f"{i}/{total_combinations}: {video_file.name} + {ref_image.name}")
                    
                    task_config = task.copy()
                    task_config['reference_image'] = str(ref_image)
                    
                    if self.process_file(str(video_file), task_config, output_folder, metadata_folder):
                        successful += 1
                    
                    if i < total_combinations:
                        rate_limit = self.api_definitions.get('rate_limit', 3)
                        time.sleep(rate_limit)
                
            else:  # one_to_one
                # Pair videos with reference images by index
                successful = 0
                pairs = list(zip(video_files, reference_images))
                
                for i, (video_file, ref_image) in enumerate(pairs, 1):
                    self.logger.info(f"{i}/{len(pairs)}: {video_file.name} + {ref_image.name}")
                    
                    task_config = task.copy()
                    task_config['reference_image'] = str(ref_image)
                    
                    if self.process_file(str(video_file), task_config, output_folder, metadata_folder):
                        successful += 1
                    
                    if i < len(pairs):
                        rate_limit = self.api_definitions.get('rate_limit', 3)
                        time.sleep(rate_limit)
        
        else:
            # Process text-to-video without reference images
            successful = 0
            
            for i, video_file in enumerate(video_files, 1):
                self.logger.info(f"{i}/{len(video_files)}: {video_file.name} (text-to-video)")
                
                if self.process_file(str(video_file), task, output_folder, metadata_folder):
                    successful += 1
                
                if i < len(video_files):
                    rate_limit = self.api_definitions.get('rate_limit', 3)
                    time.sleep(rate_limit)
        
        expected_total = (len(video_files) * len(task.get('reference_images', [])) 
                        if requires_reference and task.get('pairing_strategy') == 'all_combinations'
                        else len(video_files))
        
        self.logger.info(f"Task {task_num}: {successful}/{expected_total} successful")


    def process_vidu_effects_task(self, task, task_num, total_tasks):
        """Process Vidu Effects task"""
        effect_name = task.get('effect', '')
        source_dir = Path(task.get('source_dir', ''))
        generated_dir = task.get('generated_dir', '')
        metadata_dir = task.get('metadata_dir', '')

        self.logger.info(f"🎬 Task {task_num}/{total_tasks}: {effect_name}")

        # Get all valid images
        image_files = [f for f in source_dir.iterdir()
                      if f.suffix.lower() in self.api_definitions['file_types']]

        successful = 0
        for i, image_file in enumerate(image_files, 1):
            self.logger.info(f" 🖼️ {i}/{len(image_files)}: {image_file.name}")

            if self.process_file(str(image_file), task, generated_dir, metadata_dir):
                successful += 1

            if i < len(image_files):
                rate_limit = self.api_definitions.get('rate_limit', 3)
                time.sleep(rate_limit)

        self.logger.info(f"✓ Task {task_num}: {successful}/{len(image_files)} successful")

    def process_vidu_reference_task(self, task, task_num, total_tasks):
        """Process Vidu Reference task"""
        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {task['effect']}")

        generated_dir = Path(task['generated_dir'])
        metadata_dir = Path(task['metadata_dir'])

        successful = 0
        total_sets = len(task['image_sets'])

        for i, image_set in enumerate(task['image_sets'], 1):
            source_image = image_set['source_image']
            self.logger.info(f" 🖼️ {i}/{total_sets}: {source_image.name} + {image_set['reference_count']} refs")

            # Create task config with reference images
            ref_task = task.copy()
            ref_task['reference_images'] = [str(ref) for ref in image_set['reference_images']]
            ref_task['aspect_ratio'] = image_set['aspect_ratio']

            if self.process_file(source_image, ref_task, generated_dir, metadata_dir):
                successful += 1

            if i < total_sets:
                rate_limit = self.api_definitions.get('rate_limit', 3)
                time.sleep(rate_limit)

        self.logger.info(f"✓ Task {task_num}: {successful}/{total_sets} successful")

    def validate_genvideo_structure(self):
        """Validate genvideo folder structure and images"""
        valid_tasks = []
        invalid_images = []

        for i, task in enumerate(self.config.get('tasks', []), 1):
            folder = Path(task['folder'])
            source_folder = folder / "Source"

            if not source_folder.exists():
                self.logger.warning(f"❌ Missing source: {source_folder}")
                continue

            # Get all image files
            image_files = [f for f in source_folder.iterdir()
                          if f.suffix.lower() in self.api_definitions['file_types']]

            if not image_files:
                self.logger.warning(f"❌ Empty source: {source_folder}")
                continue

            # Validate images
            valid_count = 0
            for img_file in image_files:
                is_valid, reason = self.validate_file(img_file)
                if not is_valid:
                    invalid_images.append({
                        'path': str(img_file), 'folder': str(folder),
                        'name': img_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1

            if valid_count > 0:
                # Create output directories
                (folder / "Generated_Image").mkdir(exist_ok=True)
                (folder / "Metadata").mkdir(exist_ok=True)
                valid_tasks.append(task)
                self.logger.info(f"✓ Task {i}: {valid_count}/{len(image_files)} valid images")

        if invalid_images:
            self.write_invalid_report(invalid_images, "genvideo")
            raise Exception(f"{len(invalid_images)} invalid images found")

        return valid_tasks

    def process_genvideo(self, image_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process GenVideo API call for image-to-image generation"""
        base_name = Path(image_path).stem
        image_name = Path(image_path).name
        start_time = time.time()

        try:
            # Get parameters from task config with fallbacks to API defaults
            model = task_config.get('model', self.api_definitions['api_params']['model'])
            img_prompt = task_config.get('img_prompt', self.api_definitions['api_params']['img_prompt'])
            quality = task_config.get('quality', self.api_definitions['api_params']['quality'])

            self.logger.info(f"   Model: {model}, Quality: {quality}")

            # Make API call
            result = self.client.predict(
                model=model,
                img_prompt=img_prompt,
                input_image=handle_file(str(image_path)),
                quality=quality,
                api_name="/submit_img2img"
            )

            # Validate result
            if not result:
                raise ValueError("No result returned from API")

            self.logger.info(f"   API result type: {type(result)}, value: {result}")

            # Handle both dict and string results
            source_path = None
            output_filename = f"{base_name}_generated.png"
            output_path = Path(output_folder) / output_filename

            if isinstance(result, str):
                # API returned direct file path (actual behavior)
                source_path = Path(result)
                self.logger.info(f"   Got string result: {result}")
                
            elif isinstance(result, dict):
                # API returned dict with path/url (documented behavior)
                if 'path' in result and result['path']:
                    source_path = Path(result['path'])
                    self.logger.info(f"   Got dict result with path: {result['path']}")
                elif 'url' in result and result['url']:
                    # Handle URL case
                    self.logger.info(f"   Got dict result with URL: {result['url']}")
                    image_saved = self.download_file(result['url'], output_path)
                    source_path = None  # Already handled by download
                else:
                    raise ValueError(f"Dict result missing path/url: {result}")
            else:
                raise ValueError(f"Unexpected result type {type(result)}: {result}")

            # Copy file if we have a source path
            if source_path:
                if not source_path.exists():
                    raise ValueError(f"Generated image path does not exist: {source_path}")
                
                shutil.copy2(source_path, output_path)
                image_saved = True
                self.logger.info(f"   ✅ Copied from: {source_path}")

            processing_time = time.time() - start_time

            if image_saved:
                # Save success metadata
                metadata = {
                    "source_image": image_name,
                    "model": model,
                    "img_prompt": img_prompt,
                    "quality": quality,
                    "generated_image": output_filename,
                    "processing_time_seconds": round(processing_time, 1),
                    "processing_timestamp": datetime.now().isoformat(),
                    "attempts": attempt + 1,
                    "success": True,
                    "api_name": self.api_name,
                    "api_result": str(result)
                }
                self.save_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)
                self.logger.info(f"   ✅ Generated: {output_filename}")
                return True
            else:
                raise IOError("Image generation succeeded but file save failed")

        except Exception as e:
            # Save failure metadata
            processing_time = time.time() - start_time
            metadata = {
                "source_image": image_name,
                "model": task_config.get('model', ''),
                "img_prompt": task_config.get('img_prompt', ''),
                "quality": task_config.get('quality', ''),
                "error": str(e),
                "processing_time_seconds": round(processing_time, 1),
                "processing_timestamp": datetime.now().isoformat(),
                "attempts": attempt + 1,
                "success": False,
                "api_name": self.api_name
            }
            self.save_metadata(Path(metadata_folder), base_name, image_name, metadata, task_config)
            self.logger.error(f"   ❌ Processing failed: {str(e)}")
            raise e


    def process_genvideo_task(self, task, task_num, total_tasks):
        """Process GenVideo task with folder structure"""
        folder = Path(task['folder'])
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Image"
        metadata_folder = folder / "Metadata"

        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {folder.name}")

        # Get valid images (pre-validated)
        image_files = [f for f in source_folder.iterdir()
                      if f.suffix.lower() in self.api_definitions['file_types']]

        # Process images sequentially
        successful = 0
        for i, img_file in enumerate(image_files, 1):
            self.logger.info(f"   🖼️ {i}/{len(image_files)}: {img_file.name}")
            if self.process_file(img_file, task, output_folder, metadata_folder):
                successful += 1

            if i < len(image_files):
                rate_limit = self.api_definitions.get('rate_limit', 3)
                time.sleep(rate_limit)

        self.logger.info(f"✓ Task {task_num}: {successful}/{len(image_files)} successful")

    def validate_pixverse_structure(self):
        """Enhanced Pixverse validation with base folder structure"""
        base_folder = Path(self.config.get("base_folder", ""))
        if not base_folder.exists():
            raise FileNotFoundError(f"Base folder not found: {base_folder}")
        
        valid_tasks = []
        invalid_images = []
        
        def process_task(task):
            effect_name = task.get("effect", "")
            task_folder = base_folder / effect_name
            source_dir = task_folder / "Source"
            
            if not source_dir.exists():
                return None, []
            
            image_files = [f for f in source_dir.iterdir() 
                        if f.suffix.lower() in self.api_definitions["file_types"]]
            
            if not image_files:
                return None, []
            
            invalid_for_task = []
            valid_count = 0
            
            for img_file in image_files:
                is_valid, reason = self.validate_file(img_file)
                if not is_valid:
                    invalid_for_task.append({
                        "folder": effect_name,
                        "filename": img_file.name,
                        "reason": reason
                    })
                else:
                    valid_count += 1
            
            if valid_count == 0:
                return None, invalid_for_task
            
            (task_folder / "Generated_Video").mkdir(exist_ok=True)
            (task_folder / "Metadata").mkdir(exist_ok=True)
            
            enhanced_task = task.copy()
            enhanced_task.update({
                "folder": str(task_folder),
                "source_dir": str(source_dir),
                "generated_dir": str(task_folder / "Generated_Video"),
                "metadata_dir": str(task_folder / "Metadata")
            })
            
            self.logger.info(f"{effect_name}: {valid_count}/{len(image_files)} valid images")
            return enhanced_task, invalid_for_task
        
        if self.api_definitions.get("parallel_validation", False):
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(process_task, self.config.get("tasks", [])))
        else:
            results = [process_task(task) for task in self.config.get("tasks", [])]
        
        for task, invalid_for_task in results:
            if task:
                valid_tasks.append(task)
            invalid_images.extend(invalid_for_task)
        
        if invalid_images:
            self.write_invalid_report(invalid_images, "pixverse")
            raise Exception(f"{len(invalid_images)} invalid images found")
        
        return valid_tasks

    def process_pixverse(self, image_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process Pixverse API call using the /submit_3 endpoint"""
        basename = Path(image_path).stem
        image_name = Path(image_path).name
        start_time = time.time()
        
        try:
            # Get parameters from config with defaults
            default_settings = self.config.get("default_settings", {})
            model = default_settings.get("model", "v4.5")
            duration = default_settings.get("duration", "5s")
            motion_mode = default_settings.get("motion_mode", "normal")
            quality = default_settings.get("quality", "720p")
            style = default_settings.get("style", "none")
            
            custom_effect_id = task_config.get("custom_effect_id", "")
            # keep custom_effect_id over effect if both provided
            if custom_effect_id:
                effect = None
            else:
                effect = task_config.get("effect", "none")
            negative_prompt = task_config.get("negative_prompt", "")
            prompt = task_config.get("prompt", "")
            
            # Make API call
            result = self.client.predict(
                model=model,
                duration=duration,
                motion_mode=motion_mode,
                quality=quality,
                style=style,
                effect=effect,
                custom_effect_id=custom_effect_id,
                negative_prompt=negative_prompt,
                prompt=prompt,
                image=handle_file(str(image_path)),
                api_name=self.api_definitions["api_name"]
            )
            
            if not isinstance(result, tuple) or len(result) != 5:
                raise ValueError(f"Invalid API response format: {result}")
            
            output_url, output_video, error_message, completion_time, elapsed_time = result
            
            effect = task_config.get("effect", "none") 
            processing_time = time.time() - start_time
            base_metadata = {
                'source_image': image_name,
                'effect_name': effect,
                'model': model,
                'duration': duration,
                'motion_mode': motion_mode,
                'quality': quality,
                'style': style,
                'prompt': prompt,
                'negative_prompt': negative_prompt,
                'custom_effect_id': custom_effect_id,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': attempt + 1,
                'api_name': self.api_name,
                'completion_time': completion_time,  # CAPTURE TASK INFO
                'elapsed_time': elapsed_time,        # CAPTURE TASK INFO
                'output_url': output_url,           # CAPTURE TASK INFO
                'api_response_type': type(output_video).__name__  # DEBUG INFO
            }

            is_actual_error = error_message and not ("Success" in error_message or "VideoID:" in error_message)
            
            if is_actual_error:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    return False
                
                metadata = {
                    **base_metadata,
                    "error": error_message,
                    "success": False
                }
                self.save_metadata(Path(metadata_folder), basename, image_name, metadata, task_config)
                return False
            
            # Continue with video saving logic...
            video_saved = False
            output_video_name = f"{basename}_{effect.replace(' ', '_')}_effect.mp4"
            output_path = Path(output_folder) / output_video_name
            
            if output_url:
                video_saved = self.download_file(output_url, output_path)
            
            if not video_saved and output_video and isinstance(output_video, dict) and "video" in output_video:
                local_path = Path(output_video["video"])
                if local_path.exists():
                    shutil.copy2(local_path, output_path)
                    video_saved = True
            
            if video_saved:
                processing_time = time.time() - start_time
                success_metadata = {
                    **base_metadata,
                    'generated_video': output_video_name,
                    'video_id': error_message if error_message and 'video_id' in error_message.lower() else None,  # CAPTURE VIDEO ID
                    'task_id': error_message if error_message and 'task_id' in error_message.lower() else None,    # CAPTURE TASK ID
                    'success': True
                }
                self.save_metadata(Path(metadata_folder), basename, image_name, success_metadata, task_config)
                return True
            else:
                return False if attempt < max_retries - 1 else False
                
        except Exception as e:
            processing_time = time.time() - start_time
            # Save exception metadata with any partial info we have
            exception_metadata = {
                'source_image': image_name,
                'effect_name': effect if 'effect' in locals() else task_config.get('effect', ''),
                'model': model if 'model' in locals() else task_config.get('model', ''),
                'error': str(e),
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': attempt + 1,
                'success': False,
                'api_name': self.api_name
            }

            self.save_metadata(Path(metadata_folder), basename, image_name, exception_metadata, task_config)
            raise e


    def process_pixverse_task(self, task, task_num, total_tasks):
        """Process Pixverse task"""
        effect_name = task.get("effect", "")
        source_dir = Path(task.get("source_dir", ""))
        generated_dir = task.get("generated_dir", "")
        metadata_dir = task.get("metadata_dir", "")
        
        self.logger.info(f"Task {task_num}/{total_tasks}: {effect_name}")
        
        image_files = [f for f in source_dir.iterdir() 
                    if f.suffix.lower() in self.api_definitions["file_types"]]
        
        successful = 0
        for i, image_file in enumerate(image_files, 1):
            self.logger.info(f"{i}/{len(image_files)}: {image_file.name}")
            
            if self.process_file(str(image_file), task, generated_dir, metadata_dir):
                successful += 1
            
            if i < len(image_files):
                rate_limit = self.api_definitions.get("rate_limit", 3)
                time.sleep(rate_limit)
        
        self.logger.info(f"Task {task_num}: {successful}/{len(image_files)} successful")


    def download_file(self, url, path):
        """Standard file download method"""
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
            return True
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return False

    def run(self):
        """🚀 MAIN EXECUTION FLOW - The missing method that runall.py needs!"""
        self.logger.info(f"🚀 Starting {self.api_name.replace('_', ' ').title()} Processor")

        if not self.load_config():
            return False

        try:
            valid_tasks = self.validate_and_prepare()
        except Exception as e:
            self.logger.error(str(e))
            return False

        self.wait_for_schedule()

        if not self.initialize_client():
            return False

        start_time = time.time()

        for i, task in enumerate(valid_tasks, 1):
            try:
                self.process_task(task, i, len(valid_tasks))
                if i < len(valid_tasks):
                    task_delay = self.api_definitions.get('task_delay', 10)
                    time.sleep(task_delay)
            except Exception as e:
                self.logger.error(f"Task {i} failed: {e}")

        elapsed = time.time() - start_time
        self.logger.info(f"🎉 Completed {len(valid_tasks)} tasks in {elapsed/60:.1f} minutes")
        return True


# Factory function for easy instantiation
def create_processor(api_name, config_file=None):
    """Factory function to create API processor"""
    return UnifiedAPIProcessor(api_name, config_file)

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    import sys

    # Enhanced command line support
    if len(sys.argv) < 2:
        print("Usage: python unified_api_processor.py [api_name] [config_file]")
        print("Supported APIs: kling, nano_banana, vidu_effects, vidu_reference, runway, genvideo")
        sys.exit(1)

    api_name = sys.argv[1]
    config_file = sys.argv[2] if len(sys.argv) > 2 else None

    processor = UnifiedAPIProcessor(api_name, config_file)
    processor.run()

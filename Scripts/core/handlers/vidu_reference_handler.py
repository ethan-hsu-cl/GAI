"""Vidu Reference API handler with smart reference finding."""
import json
import time
from datetime import datetime
from pathlib import Path
from PIL import Image
from typing import Dict, List
from gradio_client import Client, handle_file

from ..services.file_manager import FileManager

from ..base.base_processor import BaseAPIHandler
from ..services.file_validator import FileValidator
from ..services.media_processor import MediaProcessor
from ..services.config_manager import ConfigManager

class ViduReferenceHandler(BaseAPIHandler):
    """Handles Vidu Reference API processing with smart reference matching."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_definitions = ConfigManager.load_api_definitions('vidu_reference')
        
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate images and reference files for Vidu Reference processing."""
        base_folder = Path(self.config.get('base_folder', ''))
        
        if not base_folder.exists():
            return []
        
        valid_tasks = []
        
        for folder in base_folder.iterdir():
            if (not folder.is_dir() or folder.name.startswith('.') or 
                not (folder / "Source").exists() or not (folder / "Reference").exists()):
                continue
            
            # Create task config for this folder
            folder_task = {
                'effect': folder.name,
                'folder_path': str(folder),
                'prompt': self.config.get('default_prompt', ''),
                'model': self.config.get('model', 'default'),
                'duration': self.config.get('duration', 5),
                'resolution': self.config.get('resolution', '1080p'),
                'movement': self.config.get('movement', 'auto')
            }
            
            # Validate this reference task
            result, errors = self._validate_reference_task(folder_task)
            if result:
                valid_tasks.extend(result.get('image_sets', []))
        
        return valid_tasks
    
    def initialize_client(self) -> bool:
        """Initialize Vidu Reference Gradio client."""
        try:
            endpoint = self.api_definitions['endpoint']
            self.client = Client(endpoint)
            self.logger.info(f"Vidu Reference client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"Vidu Reference client init failed: {e}")
            return False
    
    def process_file(self, image_set: Dict, task_config: Dict, 
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process image set with reference images using Vidu Reference API."""
        source_image = image_set['source_image']
        reference_images = image_set['reference_images']
        basename = source_image.stem
        image_name = source_image.name
        start_time = time.time()
        
        try:
            # Get parameters with defaults
            effect = task_config.get('effect', '')
            model = task_config.get('model', self.config.get('model', 'default'))
            prompt = task_config.get('prompt', self.config.get('default_prompt', ''))
            duration = task_config.get('duration', self.config.get('duration', 5))
            aspect_ratio = image_set.get('aspect_ratio', '1:1')
            resolution = task_config.get('resolution', self.config.get('resolution', '1080p'))
            movement = task_config.get('movement', self.config.get('movement', 'auto'))
            
            self.logger.info(f"Processing: 1 source + {len(reference_images)} references, aspect ratio: {aspect_ratio}")
            
            # Prepare image handles
            img_handles = [handle_file(str(source_image))]
            img_handles.extend([handle_file(str(ref)) for ref in reference_images])
            
            # Make API call
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
            
            # Generate output filename
            output_filename = f"{basename}_{effect}_clean.mp4"
            output_path = output_folder / output_filename
            
            # Download video
            video_saved = MediaProcessor.download_video_streaming(video_url, output_path)
            
            if not video_saved:
                raise IOError("Video generation succeeded but file save failed")
            
            processing_time = time.time() - start_time
            
            # Save success metadata
            metadata = {
                'source_image': image_name,
                'reference_images': [Path(ref).name for ref in reference_images],
                'reference_count': len(reference_images),
                'total_images': len(reference_images) + 1,
                'effect_name': effect,
                'model': model,
                'prompt': prompt,
                'duration': duration,
                'aspect_ratio': aspect_ratio,
                'resolution': resolution,
                'movement': movement,
                'video_url': video_url,
                'thumbnail_url': thumbnail_url,
                'task_id': task_id,
                'generated_video': output_filename,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': True,
                'api_name': 'vidu_reference'
            }
            
            self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")
            self.logger.info(f"Generated: {output_filename}")
            return True
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Save failure metadata
            metadata = {
                'source_image': image_name,
                'reference_images': [Path(ref).name for ref in reference_images],
                'reference_count': len(reference_images),
                'effect_name': effect if 'effect' in locals() else '',
                'error_message': str(e),
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': False,
                'api_name': 'vidu_reference'
            }
            
            self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")
            raise e
        
    def save_metadata(self, metadata: Dict, metadata_path: Path) -> None:
        """Save processing metadata with enhanced safety checks."""
        success = FileManager.safe_write_json(metadata, metadata_path)
        if success:
            self.logger.debug(f"Metadata saved: {metadata_path.name}")
        else:
            self.logger.error(f"Failed to save metadata: {metadata_path}")
    
    def get_output_folder_name(self) -> str:
        return self.api_definitions['folders']['output']  # Will return "Generated_Video"

    def get_rate_limit(self) -> float:
        return self.api_definitions.get('rate_limit', 3)
    
    def _validate_reference_task(self, task: Dict) -> tuple:
        """Validate a reference task with smart reference finding."""
        fp = Path(task['folder_path'])
        src_dir, ref_dir = fp / "Source", fp / "Reference"
        
        if not (src_dir.exists() and ref_dir.exists()):
            return None, [f"{task['effect']}: Missing Source/Reference folders"]
        
        # ✅ CREATE OUTPUT DIRECTORIES
        generated_dir = fp / "Generated_Video"
        metadata_dir = fp / "Metadata"
        
        try:
            generated_dir.mkdir(parents=True, exist_ok=True)
            metadata_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Created directories for {task['effect']}")
        except Exception as e:
            return None, [f"{task['effect']}: Failed to create directories - {e}"]
        
        # Rest of validation logic...
        src_imgs = [f for f in src_dir.iterdir() 
                if f.suffix.lower() in self.api_definitions['file_types']]
        if not src_imgs:
            return None, [f"{task['effect']}: No source images"]
        
        # Find reference images using smart naming
        ref_imgs = self._find_reference_images(ref_dir)
        if not ref_imgs:
            return None, [f"{task['effect']}: No reference images"]
        
        valid_sets = []
        invalids = []
        
        for src in src_imgs:
            try:
                with Image.open(src) as img:
                    ar = self._closest_aspect_ratio(img.width, img.height)
                self.logger.info(f"{src.name}: {img.width}×{img.height} → {ar}")
            except Exception as e:
                invalids.append(f"{src.name}: Cannot read dims - {e}")
                continue
            
            # Validate all images in set
            for img in [src] + ref_imgs:
                valid, reason = FileValidator.validate_image(
                    img, self.api_definitions['validation']
                )
                if not valid:
                    invalids.append(f"{img.name}: {reason}")
            
            if not invalids:
                valid_sets.append({
                    'source_image': src,
                    'reference_images': ref_imgs,
                    'all_images': [src] + ref_imgs,
                    'aspect_ratio': ar,
                    'reference_count': len(ref_imgs)
                })
                self.logger.info(f"Found {len(ref_imgs)} reference images for {src.name}")
        
        if not valid_sets:
            return None, [f"{task['effect']}: No valid image sets"]
        
        # Create output directories
        for d in ['GeneratedVideo', 'Metadata']:
            (fp / d).mkdir(exist_ok=True)
        
        task.update({
            'generated_dir': str(fp / "GeneratedVideo"),
            'metadata_dir': str(fp / "Metadata"),
            'image_sets': valid_sets
        })
        
        return task, []
    
    def _find_reference_images(self, ref_dir: Path) -> List[Path]:
        """Smart reference image finding with naming conventions."""
        refs = []
        file_types = self.api_definitions['file_types']
        max_refs = self.api_definitions.get('max_references', 6)
        
        # Smart naming convention detection
        for i in range(2, max_refs + 2):
            files = [f for f in ref_dir.iterdir() 
                    if f.suffix.lower() in file_types and (
                        f.stem.lower().startswith(f"image{i}") or
                        f.stem.lower().startswith(f"image_{i}") or
                        f.stem.split('_')[0] == str(i) or
                        f.stem.split('.')[0] == str(i)
                    )]
            if files:
                refs.append(files[0])
            else:
                break
        
        # Fallback to sorted files if no naming convention found
        return refs or sorted([f for f in ref_dir.iterdir() 
                              if f.suffix.lower() in file_types])[:max_refs]
    
    def _closest_aspect_ratio(self, w: int, h: int) -> str:
        """Find closest aspect ratio from available options."""
        r = w / h
        aspect_ratios = self.api_definitions.get('aspect_ratios', ['16:9', '9:16', '1:1'])
        
        if '16:9' in aspect_ratios and r > 1.2:
            return '16:9'
        elif '9:16' in aspect_ratios and r < 0.8:
            return '9:16'
        else:
            return '1:1'

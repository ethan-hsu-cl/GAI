"""Pixverse Effects API handler for video generation from images."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from gradio_client import Client, handle_file

from ..services.file_manager import FileManager
from ..base.base_processor import BaseAPIHandler
from ..services.file_validator import FileValidator
from ..services.media_processor import MediaProcessor
from ..services.config_manager import ConfigManager

class PixverseEffectsHandler(BaseAPIHandler):
    """Handles Pixverse Effects API processing."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_definitions = ConfigManager.load_api_definitions('pixverse_effects')
    
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate images for Pixverse Effects processing."""
        base_folder = Path(self.config.get('base_folder', ''))
        
        if not base_folder.exists():
            return []
        
        # Find image files in base folder (similar to vidu_effects pattern)
        image_files = FileValidator.get_files_by_type(
            base_folder, self.api_definitions['file_types']
        )
        
        valid_files = []
        validation_rules = self.api_definitions['validation']
        
        for img_file in image_files:
            is_valid, reason = FileValidator.validate_image(img_file, validation_rules)
            if is_valid:
                valid_files.append(img_file)
        
        # Create output directories
        output_dir = base_folder / self.api_definitions['folders']['output']
        metadata_dir = base_folder / self.api_definitions['folders']['metadata']
        self._ensure_directories_exist([output_dir, metadata_dir])
        
        # Update task config with folder paths
        task_config.update({
            'base_folder': str(base_folder),
            'output_dir': str(output_dir),
            'metadata_dir': str(metadata_dir)
        })
        
        return valid_files
    
    def initialize_client(self) -> bool:
        """Initialize Pixverse Effects Gradio client."""
        try:
            endpoint = self.api_definitions['endpoint']
            self.client = Client(endpoint)
            self.logger.info(f"Pixverse Effects client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"Pixverse Effects client init failed: {e}")
            return False
    
    def process_file(self, file_path: Path, task_config: Dict,
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process single image with Pixverse Effects API."""
        basename = file_path.stem
        image_name = file_path.name
        start_time = time.time()
        
        try:
            # Get parameters with defaults
            effect = task_config.get('effect', 'none')
            custom_effect_id = task_config.get('custom_effect_id', '')
            prompt = task_config.get('prompt', '') or self.config.get('prompt', '')
            negative_prompt = task_config.get('negative_prompt', '') or self.config.get('negative_prompt', '')
            
            # Get API parameters with defaults
            model = task_config.get('model', self.config.get('model', 'v4.5'))
            duration = task_config.get('duration', self.config.get('duration', '5s'))
            motion_mode = task_config.get('motion_mode', self.config.get('motion_mode', 'normal'))
            quality = task_config.get('quality', self.config.get('quality', '720p'))
            style = task_config.get('style', self.config.get('style', 'none'))
            
            self.logger.info(f"Processing: {image_name}, effect: {effect}")
            
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
                image=handle_file(str(file_path)),
                api_name=self.api_definitions['api_name']
            )
            
            # Validate result format (following API documentation)
            if not isinstance(result, tuple) or len(result) < 5:
                raise ValueError("Invalid API response format")
            
            output_url, video_data, error_msg, completion_time, elapsed_time = result
            
            if error_msg and error_msg.strip():
                raise ValueError(f"API error: {error_msg}")
            
            if not video_data or not isinstance(video_data, dict):
                raise ValueError("No valid video data returned")
            
            video_path = video_data.get('video')
            if not video_path:
                raise ValueError("No video path in response")
            
            # Generate output filename
            safe_effect = "".join(c for c in effect if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_effect = safe_effect.replace(' ', '_')
            output_filename = f"{basename}_{safe_effect}_effect.mp4"
            output_path = output_folder / output_filename
            
            # Download/copy video
            import shutil
            video_source = Path(video_path)
            if video_source.exists():
                shutil.copy2(video_source, output_path)
            else:
                # Try downloading if it's a URL
                video_saved = MediaProcessor.download_video_streaming(output_url, output_path)
                if not video_saved:
                    raise IOError("Video generation succeeded but file save failed")
            
            processing_time = time.time() - start_time
            
            # Save success metadata
            metadata = {
                'source_image': image_name,
                'effect_name': effect,
                'custom_effect_id': custom_effect_id,
                'model': model,
                'duration': duration,
                'motion_mode': motion_mode,
                'quality': quality,
                'style': style,
                'prompt': prompt,
                'negative_prompt': negative_prompt,
                'output_url': output_url,
                'generated_video': output_filename,
                'completion_time': completion_time,
                'elapsed_time': elapsed_time,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': True,
                'api_name': 'pixverse_effects'
            }
            
            self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")
            self.logger.info(f"Generated: {output_filename}")
            return True
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Save failure metadata
            metadata = {
                'source_image': image_name,
                'effect_name': task_config.get('effect', ''),
                'custom_effect_id': task_config.get('custom_effect_id', ''),
                'error_message': str(e),
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': False,
                'api_name': 'pixverse_effects'
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

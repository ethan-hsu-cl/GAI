"""Vidu Effects API handler with parallel validation."""
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

class ViduEffectsHandler(BaseAPIHandler):
    """Handles Vidu Effects API processing."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_definitions = ConfigManager.load_api_definitions('vidu_effects')
        
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate images for Vidu Effects processing."""
        effect_name = task_config.get('effect', '')
        base_folder = Path(self.config.get('base_folder', ''))
        task_folder = base_folder / effect_name
        source_dir = task_folder / "Source"
        
        if not source_dir.exists():
            return []
        
        # ✅ CREATE OUTPUT DIRECTORIES FOR EFFECT
        generated_dir = task_folder / "Generated_Video"
        metadata_dir = task_folder / "Metadata"
        
        self._ensure_directories_exist([generated_dir, metadata_dir])
        
        # Rest of validation logic...
        image_files = FileValidator.get_files_by_type(
            source_dir, self.api_definitions['file_types']
        )
        
        valid_files = []
        validation_rules = self.api_definitions['validation']
        
        for img_file in image_files:
            is_valid, reason = FileValidator.validate_image(img_file, validation_rules)
            if is_valid:
                valid_files.append(img_file)
        
        # Update task config with folder paths
        task_config.update({
            'folder': str(task_folder),
            'source_dir': str(source_dir),
            'generated_dir': str(generated_dir),
            'metadata_dir': str(metadata_dir)
        })
        
        return valid_files

    
    def initialize_client(self) -> bool:
        """Initialize Vidu Effects Gradio client."""
        try:
            endpoint = self.api_definitions['endpoint']
            self.client = Client(endpoint)
            self.logger.info(f"Vidu Effects client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"Vidu Effects client init failed: {e}")
            return False
    
    def process_file(self, file_path: Path, task_config: Dict, 
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process single image with Vidu Effects API."""
        basename = file_path.stem
        image_name = file_path.name
        start_time = time.time()
        
        try:
            # Get parameters with defaults
            effect = task_config.get('effect', '')
            prompt = task_config.get('prompt', '') or self.config.get('default_prompt', '')
            
            self.logger.info(f"Processing: 1 source, effect: {effect}")
            
            # Make API call
            result = self.client.predict(
                model=self.config.get('model', 'default'),
                prompt=prompt,
                duration=task_config.get('duration', self.config.get('duration', 5)),
                aspect_ratio=task_config.get('aspect_ratio', '1:1'),
                images=[handle_file(str(file_path))],
                resolution=task_config.get('resolution', self.config.get('resolution', '1080p')),
                movement=task_config.get('movement', self.config.get('movement', 'auto')),
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
            output_filename = f"{basename}_{effect}_effect.mp4"
            output_path = output_folder / output_filename
            
            # Download video
            video_saved = MediaProcessor.download_video_streaming(video_url, output_path)
            
            if not video_saved:
                raise IOError("Video generation succeeded but file save failed")
            
            processing_time = time.time() - start_time
            
            # Save success metadata
            metadata = {
                'source_image': image_name,
                'effect_category': task_config.get('category', ''),
                'effect_name': effect,
                'prompt': prompt,
                'output_url': video_url,
                'generated_video': output_filename,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': True,
                'api_name': 'vidu_effects'
            }
            
            self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")
            self.logger.info(f"Generated: {output_filename}")
            return True
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Save failure metadata
            metadata = {
                'source_image': image_name,
                'effect_category': task_config.get('category', ''),
                'effect_name': task_config.get('effect', ''),
                'prompt': prompt if 'prompt' in locals() else '',
                'error_message': str(e),
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': False,
                'api_name': 'vidu_effects'
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

"""GenVideo API handler for image-to-image generation."""
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

class GenVideoHandler(BaseAPIHandler):
    """Handles GenVideo API processing for image-to-image generation."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_definitions = ConfigManager.load_api_definitions('genvideo')
        
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate images for GenVideo processing."""
        folder = Path(task_config['folder'])
        source_folder = folder / "Source"
        
        if not source_folder.exists():
            return []
        
        image_files = FileValidator.get_files_by_type(
            source_folder, self.api_definitions['file_types']
        )
        
        valid_files = []
        validation_rules = self.api_definitions['validation']
        
        for img_file in image_files:
            is_valid, reason = FileValidator.validate_image(img_file, validation_rules)
            if is_valid:
                valid_files.append(img_file)
        
        return valid_files
    
    def initialize_client(self) -> bool:
        """Initialize GenVideo Gradio client."""
        try:
            endpoint = self.api_definitions['endpoint']
            self.client = Client(endpoint)
            self.logger.info(f"GenVideo client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"GenVideo client init failed: {e}")
            return False
    
    def process_file(self, file_path: Path, task_config: Dict, 
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process single image with GenVideo API."""
        basename = file_path.stem
        image_name = file_path.name
        start_time = time.time()
        
        try:
            # Get parameters with defaults from API definitions
            api_params = self.api_definitions.get('api_params', {})
            model = task_config.get('model', api_params.get('model', 'gpt-image-1'))
            img_prompt = task_config.get('img_prompt', api_params.get('img_prompt', ''))
            quality = task_config.get('quality', api_params.get('quality', 'low'))
            
            # Make API call
            result = self.client.predict(
                model=model,
                img_prompt=img_prompt,
                input_image=handle_file(str(file_path)),
                quality=quality,
                api_name="submit_img2img"
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
            output_filename = f"{basename}_generated.png"
            output_path = output_folder / output_filename
            
            # Download generated image
            image_saved = MediaProcessor.download_video_streaming(video_url, output_path)
            
            if not image_saved:
                raise IOError("Image generation succeeded but file save failed")
            
            processing_time = time.time() - start_time
            
            # Save success metadata
            metadata = {
                'source_image': image_name,
                'model': model,
                'img_prompt': img_prompt,
                'quality': quality,
                'generated_image': output_filename,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': True,
                'api_name': 'genvideo',
                'api_result': str(result)
            }
            
            self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")
            self.logger.info(f"Generated: {output_filename}")
            return True
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Save failure metadata
            metadata = {
                'source_image': image_name,
                'model': task_config.get('model', ''),
                'img_prompt': task_config.get('img_prompt', ''),
                'quality': task_config.get('quality', ''),
                'error': str(e),
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'attempts': 1,
                'success': False,
                'api_name': 'genvideo'
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
        return self.api_definitions['folders']['output']  # Will return "Generated_Image"
    
    def get_rate_limit(self) -> float:
        return self.api_definitions.get('rate_limit', 3)

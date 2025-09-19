"""Nano Banana API handler."""
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

class NanoBananaHandler(BaseAPIHandler):
    """Handles Nano Banana API processing."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_definitions = ConfigManager.load_api_definitions('nano_banana')
        
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate images for Nano Banana processing."""
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
        """Initialize Nano Banana Gradio client."""
        try:
            endpoint = self.api_definitions['endpoint']
            # Handle testbed override if configured
            if self.config.get('testbed'):
                endpoint = self.config['testbed']
            
            self.client = Client(endpoint)
            self.logger.info(f"Nano Banana client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"Nano Banana client init failed: {e}")
            return False
    
    def process_file(self, file_path: Path, task_config: Dict, 
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process single image with Nano Banana API."""
        basename = file_path.stem
        image_name = file_path.name
        start_time = time.time()
        
        try:
            # Get additional images if configured
            additional_images = task_config.get('additional_images', {})
            
            # Make API call
            result = self.client.predict(
                prompt=task_config.get('prompt', ''),
                image1=handle_file(str(file_path)),
                image2=additional_images.get('image1', ''),
                image3=additional_images.get('image2', ''),
                api_name=self.api_definitions['api_name']
            )
            
            # Extract results
            response_id, error_msg, response_data = result
            
            self.logger.info(f"Response ID: {response_id}")
            
            if error_msg:
                self.logger.info(f"API Error: {error_msg}")
                self._save_failure_metadata(
                    file_path, task_config, metadata_folder, error_msg, start_time
                )
                return False
            
            # Save response data (base64 images)
            saved_files, text_responses = MediaProcessor.save_base64_images(
                response_data, output_folder, basename
            )
            
            has_images = len(saved_files) > 0
            processing_time = time.time() - start_time
            
            # Save metadata
            metadata = {
                'source_image': image_name,
                'response_id': response_id,
                'saved_files': [Path(f).name for f in saved_files],
                'text_responses': text_responses,
                'success': has_images,
                'images_generated': len(saved_files),
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().isoformat(),
                'api_name': 'nano_banana'
            }
            
            self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")
            
            if has_images:
                self.logger.info(f"Generated {len(saved_files)} images")
                return True
            else:
                self.logger.info("No images generated")
                return False
                
        except Exception as e:
            self._save_failure_metadata(
                file_path, task_config, metadata_folder, str(e), start_time
            )
            raise e
    
    def save_metadata(self, metadata: Dict, metadata_path: Path) -> None:
        """Save processing metadata with enhanced safety checks."""
        success = FileManager.safe_write_json(metadata, metadata_path)
        if success:
            self.logger.debug(f"Metadata saved: {metadata_path.name}")
        else:
            self.logger.error(f"Failed to save metadata: {metadata_path}")

    
    def get_output_folder_name(self) -> str:
        return self.api_definitions['folders']['output']  # Will return "Generated_Output"
    
    def get_rate_limit(self) -> float:
        return self.api_definitions.get('rate_limit', 5)
    
    def _save_failure_metadata(self, file_path: Path, task_config: Dict, 
                              metadata_folder: Path, error: str, start_time: float) -> None:
        """Save metadata for failed processing."""
        processing_time = time.time() - start_time
        metadata = {
            'source_image': file_path.name,
            'error': error,
            'success': False,
            'processing_time_seconds': round(processing_time, 1),
            'processing_timestamp': datetime.now().isoformat(),
            'api_name': 'nano_banana'
        }
        
        basename = file_path.stem
        self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")

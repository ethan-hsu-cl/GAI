"""Kling API handler."""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from gradio_client import Client, handle_file

from ..services.file_manager import FileManager

from ..base.base_processor import BaseAPIHandler
from ..services.file_validator import FileValidator
from ..services.media_processor import MediaProcessor
from ..services.config_manager import ConfigManager

class KlingHandler(BaseAPIHandler):
    """Handles Kling Image2Video API processing."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_definitions = ConfigManager.load_api_definitions('kling')
        
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate images for Kling processing."""
        folder = Path(task_config['folder'])
        source_folder = folder / "Source"
        
        if not source_folder.exists():
            return []
        
        image_files = FileValidator.get_files_by_type(
            source_folder, self.api_definitions['file_types']
        )
        
        valid_files = []
        invalid_images = []
        
        validation_rules = self.api_definitions['validation']
        
        for img_file in image_files:
            is_valid, reason = FileValidator.validate_image(img_file, validation_rules)
            if is_valid:
                valid_files.append(img_file)
            else:
                invalid_images.append({
                    'path': str(img_file),
                    'name': img_file.name,
                    'reason': reason
                })
        
        if invalid_images:
            self._write_invalid_report(invalid_images, folder)
            
        return valid_files
    
    def initialize_client(self) -> bool:
        """Initialize Kling Gradio client."""
        try:
            endpoint = self.api_definitions['endpoint']
            self.client = Client(endpoint)
            self.logger.info(f"Kling client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"Kling client init failed: {e}")
            return False
    
    def process_file(self, file_path: Path, task_config: Dict, 
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process single image with Kling API."""
        basename = file_path.stem
        image_name = file_path.name
        start_time = time.time()
        
        try:
            # Make API call
            result = self.client.predict(
                image=handle_file(str(file_path)),
                prompt=task_config.get('prompt', ''),
                mode="std",
                duration=5,
                cfg=0.5,
                model=self.config.get('model_version', 'v2.1'),
                negative_prompt=task_config.get('negative_prompt', ''),
                api_name=self.api_definitions['api_name']
            )
            
            # Extract results
            url, video_dict, video_id, task_id, error = result
            
            self.logger.info(f"Video ID: {video_id}")
            self.logger.info(f"Task ID: {task_id}")
            
            if error:
                self.logger.info(f"API Error: {error}")
                self._save_failure_metadata(
                    file_path, task_config, metadata_folder, error, start_time
                )
                return False
            
            # Download video
            output_path = output_folder / f"{basename}_generated.mp4"
            video_saved = False
            
            if url:
                video_saved = MediaProcessor.download_video_streaming(url, output_path)
            
            if not video_saved and video_dict and 'video' in video_dict:
                local_path = Path(video_dict['video'])
                if local_path.exists():
                    video_saved = MediaProcessor.copy_local_file(local_path, output_path)
            
            # Save metadata
            processing_time = time.time() - start_time
            metadata = {
                'source_image': image_name,
                'prompt': task_config.get('prompt', ''),
                'negative_prompt': task_config.get('negative_prompt', ''),
                'model_version': self.config.get('model_version', 'v2.1'),
                'output_url': url,
                'video_id': video_id,
                'task_id': task_id,
                'generated_video': output_path.name if video_saved else None,
                'success': video_saved,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'api_name': 'kling'
            }
            
            self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")
            
            if video_saved:
                self.logger.info(f"Generated: {output_path.name}")
                return True
            else:
                self.logger.error("Video file could not be saved")
                return False
                
        except Exception as e:
            processing_time = time.time() - start_time
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
        return self.api_definitions['folders']['output']
    
    def get_rate_limit(self) -> float:
        return self.api_definitions.get('rate_limit', 3)
    
    def _write_invalid_report(self, invalid_images: List[Dict], folder: Path) -> None:
        """Write report of invalid images."""
        report_path = folder / "invalid_images_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(invalid_images, f, indent=2)
    
    def _save_failure_metadata(self, file_path: Path, task_config: Dict, 
                              metadata_folder: Path, error: str, start_time: float) -> None:
        """Save metadata for failed processing."""
        processing_time = time.time() - start_time
        metadata = {
            'source_image': file_path.name,
            'error': error,
            'success': False,
            'processing_time_seconds': round(processing_time, 1),
            'processing_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'api_name': 'kling'
        }
        
        basename = file_path.stem
        self.save_metadata(metadata, metadata_folder / f"{basename}_metadata.json")

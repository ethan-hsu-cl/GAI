"""Runway API handler with video-reference pairing strategies."""
import json
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from gradio_client import Client, handle_file

from ..services.file_manager import FileManager

from ..base.base_processor import BaseAPIHandler
from ..services.file_validator import FileValidator
from ..services.media_processor import MediaProcessor
from ..services.config_manager import ConfigManager

class RunwayHandler(BaseAPIHandler):
    """Handles Runway video processing with optional reference images."""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_definitions = ConfigManager.load_api_definitions('runway')
        
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate videos and reference images for Runway processing."""
        folder = Path(task_config['folder'])
        source_folder = folder / "Source"
        
        if not source_folder.exists():
            return []
        
        # Get video files
        video_files = FileValidator.get_files_by_type(
            source_folder, self.api_definitions['file_types']['video']
        )
        
        valid_files = []
        validation_rules = self.api_definitions['validation']
        
        for video_file in video_files:
            is_valid, reason = FileValidator.validate_video(
                video_file, validation_rules.get('video', {})
            )
            if is_valid:
                valid_files.append(video_file)
        
        # Validate reference images if required
        requires_reference = task_config.get('use_comparison_template', False)
        if requires_reference:
            ref_folder_path = task_config.get('reference_folder', '').strip()
            if ref_folder_path:
                ref_folder = Path(ref_folder_path)
            else:
                ref_folder = folder / "Reference"
            
            if ref_folder.exists():
                ref_images = FileValidator.get_files_by_type(
                    ref_folder, self.api_definitions['file_types']['image']
                )
                task_config['reference_images'] = ref_images
        
        return valid_files
    
    def initialize_client(self) -> bool:
        """Initialize Runway Gradio client."""
        try:
            endpoint = self.api_definitions['endpoint']
            self.client = Client(endpoint)
            self.logger.info(f"Runway client initialized: {endpoint}")
            return True
        except Exception as e:
            self.logger.error(f"Runway client init failed: {e}")
            return False
    
    def process_file(self, file_path: Path, task_config: Dict, 
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process single video with Runway API."""
        basename = file_path.stem
        video_name = file_path.name
        start_time = time.time()
        
        try:
            # Get video info for optimal ratio
            video_info = FileValidator._get_video_info(file_path)
            if video_info:
                optimal_ratio = self._get_optimal_runway_ratio(
                    video_info['width'], video_info['height']
                )
                self.logger.info(f"Video {video_info['width']}×{video_info['height']} - Using ratio {optimal_ratio}")
            else:
                optimal_ratio = self.config.get('ratio', '1280:720')
                self.logger.warning(f"Could not get video info, using default ratio {optimal_ratio}")
            
            # Check for reference image
            reference_image_path = task_config.get('reference_image')
            ref_stem = ""
            
            if reference_image_path:
                ref_stem = f"_ref_{Path(reference_image_path).stem}"
                output_filename = f"{basename}{ref_stem}_runway_generated.mp4"
                
                # Make API call with reference image
                result = self.client.predict(
                    video_path=handle_file(str(file_path)),
                    prompt=task_config['prompt'],
                    model=self.config.get('model', 'gen4-aleph'),
                    ratio=optimal_ratio,
                    reference_image=handle_file(str(reference_image_path)),
                    public_figure_moderation=self.config.get('public_figure_moderation', 'low'),
                    api_name=self.api_definitions['api_name']
                )
            else:
                output_filename = f"{basename}_text_runway_generated.mp4"
                
                # Text-to-video without reference image
                result = self.client.predict(
                    video_path=handle_file(str(file_path)),
                    prompt=task_config['prompt'],
                    model=self.config.get('model', 'gen4-aleph'),
                    ratio=optimal_ratio,
                    reference_image=None,
                    public_figure_moderation=self.config.get('public_figure_moderation', 'low'),
                    api_name=self.api_definitions['api_name']
                )
            
            # Extract output URL
            output_url = result[0] if len(result) > 0 else None
            
            if not output_url:
                self.logger.info("No output URL received")
                self._save_failure_metadata(
                    file_path, task_config, metadata_folder, 
                    "No output URL received", start_time, ref_stem
                )
                return False
            
            # Download video
            output_path = output_folder / output_filename
            video_saved = MediaProcessor.download_video_streaming(output_url, output_path)
            
            processing_time = time.time() - start_time
            
            # Save metadata
            metadata = {
                'source_video': video_name,
                'source_dimensions': f"{video_info['width']}×{video_info['height']}" if video_info else "unknown",
                'reference_image': Path(reference_image_path).name if reference_image_path else None,
                'prompt': task_config['prompt'],
                'model': self.config.get('model', 'gen4-aleph'),
                'ratio': optimal_ratio,
                'public_figure_moderation': self.config.get('public_figure_moderation', 'low'),
                'output_url': output_url,
                'generated_video': output_filename,
                'processing_time_seconds': round(processing_time, 1),
                'processing_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'attempts': 1,
                'success': video_saved,
                'api_name': 'runway',
                'generation_type': 'image-to-video' if reference_image_path else 'text-to-video'
            }
            
            self._save_runway_metadata(
                metadata_folder, basename, ref_stem, video_name,
                Path(reference_image_path).name if reference_image_path else None,
                metadata, task_config
            )
            
            if video_saved:
                self.logger.info(f"Generated: {output_filename} ratio {optimal_ratio}")
                return True
            else:
                self.logger.error("Video file could not be saved")
                return False
                
        except Exception as e:
            self._save_failure_metadata(
                file_path, task_config, metadata_folder, str(e), start_time, ref_stem
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
        return self.api_definitions['folders']['output']  # Will return "Generated_Video"
    
    def get_rate_limit(self) -> float:
        return self.api_definitions.get('rate_limit', 3)
    
    def _get_optimal_runway_ratio(self, video_width: int, video_height: int) -> str:
        """Find optimal ratio for Runway based on input video dimensions."""
        input_ratio = video_width / video_height
        available_ratios = self.api_definitions.get('available_ratios', [
            '1280:720', '720:1280', '1104:832', '960:960', '832:1104', 
            '1584:672', '848:480', '640:480'
        ])
        
        best_ratio = '1280:720'  # fallback
        smallest_difference = float('inf')
        
        for ratio_str in available_ratios:
            w, h = map(int, ratio_str.split(':'))
            ratio_value = w / h
            difference = abs(input_ratio - ratio_value)
            
            if difference < smallest_difference:
                smallest_difference = difference
                best_ratio = ratio_str
        
        return best_ratio
    
    def _save_runway_metadata(self, metadata_folder: Path, basename: str, 
                             ref_stem: str, video_name: str, ref_name: Optional[str],
                             result_data: Dict, task_config: Dict) -> None:
        """Save Runway-specific metadata."""
        metadata_file = metadata_folder / f"{basename}{ref_stem}_runway_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=4, ensure_ascii=False)
        
        status = "✓" if result_data.get('success') else "✗"
        self.logger.info(f"{status} Meta: {metadata_file.name}")
    
    def _save_failure_metadata(self, file_path: Path, task_config: Dict,
                              metadata_folder: Path, error: str, start_time: float,
                              ref_stem: str = "") -> None:
        """Save metadata for failed processing."""
        processing_time = time.time() - start_time
        basename = file_path.stem
        
        metadata = {
            'source_video': file_path.name,
            'error': error,
            'success': False,
            'processing_time_seconds': round(processing_time, 1),
            'processing_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'api_name': 'runway'
        }
        
        self._save_runway_metadata(
            metadata_folder, basename, ref_stem, file_path.name, None, metadata, task_config
        )

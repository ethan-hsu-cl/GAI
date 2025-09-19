"""Enhanced media processing utilities with safe file operations."""
import shutil
import requests
import base64
from pathlib import Path
from PIL import Image
from typing import List, Tuple, Optional
import logging
from .file_manager import FileManager

class MediaProcessor:
    """Enhanced utilities for media processing and downloading with safety checks."""
    
    @staticmethod
    def download_video_streaming(url: str, output_path: Path) -> bool:
        """Download video with streaming support and safety checks."""
        logger = logging.getLogger(__name__)
        
        # Use enhanced file manager for safe download
        success = FileManager.safe_download_stream(url, output_path)
        
        if success:
            # Additional validation for video files
            if output_path.exists() and output_path.stat().st_size > 1000:  # Minimum size check
                logger.info(f"Video downloaded successfully: {output_path.name} ({output_path.stat().st_size} bytes)")
                return True
            else:
                logger.error(f"Downloaded video file is too small or corrupt: {output_path}")
                return False
        
        return False
    
    @staticmethod
    def save_base64_images(response_data: List, output_folder: Path, 
                          basename: str) -> Tuple[List[str], List[str]]:
        """Save base64 encoded images with enhanced safety checks."""
        logger = logging.getLogger(__name__)
        
        if not response_data or not isinstance(response_data, list):
            logger.warning("Invalid response data for base64 images")
            return [], []
        
        # Ensure output folder exists
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Validate write permissions
        if not FileManager.validate_file_write_permissions(output_folder):
            logger.error(f"No write permissions for output folder: {output_folder}")
            return [], []
        
        saved_files = []
        text_responses = []
        
        for i, item in enumerate(response_data):
            if not isinstance(item, dict) or 'type' not in item or 'data' not in item:
                logger.warning(f"Skipping invalid response item {i+1}")
                continue
            
            if item['type'] == 'Text':
                text_responses.append({'index': i + 1, 'content': item['data']})
                
            elif item['type'] == 'Image' and item['data'].strip():
                try:
                    # Parse base64 data
                    if item['data'].startswith('data:image'):
                        header, base64_data = item['data'].split(',', 1)
                        ext = header.split('/')[1].split(';')[0]
                    else:
                        base64_data = item['data']
                        ext = 'png'
                    
                    if len(base64_data.strip()) == 0:
                        logger.warning(f"Empty base64 data for image {i+1}")
                        continue
                    
                    # Decode base64 data
                    image_bytes = base64.b64decode(base64_data)
                    if len(image_bytes) < 100:  # Too small, likely invalid
                        logger.warning(f"Image {i+1} data too small ({len(image_bytes)} bytes)")
                        continue
                    
                    # Generate safe filename
                    safe_basename = FileManager.get_safe_filename(basename)
                    image_filename = f"{safe_basename}_image_{i+1}.{ext}"
                    image_path = output_folder / image_filename
                    
                    # Save using safe file manager
                    if FileManager.safe_write_binary(image_bytes, image_path):
                        saved_files.append(str(image_path))
                        logger.debug(f"Saved image: {image_filename} ({len(image_bytes)} bytes)")
                    else:
                        logger.error(f"Failed to save image {i+1}")
                        
                except Exception as e:
                    logger.error(f"Error processing image {i+1}: {e}")
        
        logger.info(f"Saved {len(saved_files)} images, {len(text_responses)} text responses")
        return saved_files, text_responses
    
    @staticmethod
    def copy_local_file(source_path: Path, destination_path: Path) -> bool:
        """Copy file from local path to destination with safety checks."""
        return FileManager.safe_copy_file(source_path, destination_path)
    
    @staticmethod
    def validate_media_file(file_path: Path, expected_type: str = 'auto') -> bool:
        """Validate media file integrity and format."""
        logger = logging.getLogger(__name__)
        
        if not file_path.exists():
            logger.error(f"Media file does not exist: {file_path}")
            return False
        
        if file_path.stat().st_size == 0:
            logger.error(f"Media file is empty: {file_path}")
            return False
        
        try:
            if expected_type == 'image' or (expected_type == 'auto' and 
                file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']):
                # Validate image
                with Image.open(file_path) as img:
                    img.verify()
                logger.debug(f"Image validation successful: {file_path}")
                return True
                
            elif expected_type == 'video' or (expected_type == 'auto' and 
                file_path.suffix.lower() in ['.mp4', '.mov', '.avi', '.mkv']):
                # Basic video validation (size check for now)
                if file_path.stat().st_size > 1000:  # Minimum reasonable size
                    logger.debug(f"Video validation successful: {file_path}")
                    return True
                else:
                    logger.error(f"Video file too small: {file_path}")
                    return False
            else:
                # Generic file validation
                return file_path.stat().st_size > 0
                
        except Exception as e:
            logger.error(f"Media validation failed for {file_path}: {e}")
            return False

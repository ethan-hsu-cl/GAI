"""Universal file validation service."""
import os
import json
import subprocess
from pathlib import Path
from PIL import Image
from typing import List, Tuple, Dict, Optional

class FileValidator:
    """Universal file validator for all API types."""
    
    @staticmethod
    def validate_image(file_path: Path, validation_rules: Dict) -> Tuple[bool, str]:
        """Validate an image file against given rules."""
        try:
            # File size check
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            max_size = validation_rules.get('max_size_mb', 50)
            if file_size_mb > max_size:
                return False, f"Size {file_size_mb:.1f}MB > {max_size}MB"
            
            # Image dimension and aspect ratio check
            with Image.open(file_path) as img:
                w, h = img.size
                min_dim = validation_rules.get('min_dimension', 128)
                
                if w < min_dim or h < min_dim:
                    return False, f"Dims {w}×{h} too small"
                
                # Aspect ratio check if specified
                aspect_ratio_range = validation_rules.get('aspect_ratio')
                if aspect_ratio_range:
                    ratio = w / h
                    if not (aspect_ratio_range[0] <= ratio <= aspect_ratio_range[1]):
                        return False, f"Ratio {ratio:.2f} invalid"
                
                return True, f"{w}×{h}"
                
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def validate_video(file_path: Path, validation_rules: Dict) -> Tuple[bool, str]:
        """Validate a video file against given rules."""
        try:
            # File size check
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            max_size = validation_rules.get('max_size_mb', 500)
            if file_size_mb > max_size:
                return False, f"Size {file_size_mb:.1f}MB too large"
            
            # Video info check
            info = FileValidator._get_video_info(file_path)
            if not info:
                return False, "Cannot read video info"
            
            # Duration check
            duration_range = validation_rules.get('duration', [1, 30])
            if not (duration_range[0] <= info['duration'] <= duration_range[1]):
                return False, f"Duration {info['duration']:.1f}s invalid"
            
            # Dimension check
            min_dim = validation_rules.get('min_dimension', 320)
            if info['width'] < min_dim or info['height'] < min_dim:
                return False, f"Resolution {info['width']}×{info['height']} too small"
            
            return True, f"{info['width']}×{info['height']}, {info['duration']:.1f}s, {info['size_mb']:.1f}MB"
            
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def _get_video_info(video_path: Path) -> Optional[Dict]:
        """Get video information using ffprobe."""
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
    
    @staticmethod
    def get_files_by_type(folder: Path, file_types: List[str]) -> List[Path]:
        """Get all files of specified types from folder."""
        files = []
        for file_type in file_types:
            files.extend(folder.glob(f"*{file_type}"))
        return sorted(files)

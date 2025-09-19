"""Safe file operations with automatic directory creation and error handling."""
import json
import shutil
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Union
import logging

class FileManager:
    """Handles all file operations with safety checks and directory creation."""
    
    @staticmethod
    def safe_write_json(data: Dict[str, Any], file_path: Path, 
                       backup: bool = True) -> bool:
        """Safely write JSON data to file with directory creation and backup."""
        logger = logging.getLogger(__name__)
        
        try:
            # Ensure parent directory exists
            FileManager._ensure_parent_directory(file_path)
            
            # Create backup if file exists and backup is requested
            if backup and file_path.exists():
                FileManager._create_backup(file_path)
            
            # Write to temporary file first, then move (atomic operation)
            temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp")
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            
            # Atomic move from temp to final location
            shutil.move(temp_file, file_path)
            
            logger.debug(f"Successfully wrote JSON to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write JSON to {file_path}: {e}")
            # Clean up temp file if it exists
            temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            return False
    
    @staticmethod
    def safe_write_binary(data: bytes, file_path: Path, 
                         backup: bool = False) -> bool:
        """Safely write binary data to file with directory creation."""
        logger = logging.getLogger(__name__)
        
        try:
            # Ensure parent directory exists
            FileManager._ensure_parent_directory(file_path)
            
            # Create backup if file exists and backup is requested
            if backup and file_path.exists():
                FileManager._create_backup(file_path)
            
            # Write to temporary file first, then move (atomic operation)
            temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp")
            
            with open(temp_file, 'wb') as f:
                f.write(data)
            
            # Atomic move from temp to final location
            shutil.move(temp_file, file_path)
            
            logger.debug(f"Successfully wrote binary data to {file_path} ({len(data)} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write binary data to {file_path}: {e}")
            # Clean up temp file if it exists
            temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            return False
    
    @staticmethod
    def safe_copy_file(source_path: Path, destination_path: Path, 
                      backup: bool = False) -> bool:
        """Safely copy file with directory creation and validation."""
        logger = logging.getLogger(__name__)
        
        try:
            # Validate source file
            if not source_path.exists():
                logger.error(f"Source file does not exist: {source_path}")
                return False
            
            if not source_path.is_file():
                logger.error(f"Source is not a file: {source_path}")
                return False
            
            # Ensure parent directory exists
            FileManager._ensure_parent_directory(destination_path)
            
            # Create backup if destination exists and backup is requested
            if backup and destination_path.exists():
                FileManager._create_backup(destination_path)
            
            # Copy with metadata preservation
            shutil.copy2(source_path, destination_path)
            
            # Verify copy was successful
            if destination_path.exists() and destination_path.stat().st_size > 0:
                logger.debug(f"Successfully copied {source_path} to {destination_path}")
                return True
            else:
                logger.error(f"Copy verification failed for {destination_path}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to copy {source_path} to {destination_path}: {e}")
            return False
    
    @staticmethod
    def safe_download_stream(url: str, file_path: Path, 
                           chunk_size: int = 8192, timeout: int = 300) -> bool:
        """Safely download file from URL with streaming and progress."""
        logger = logging.getLogger(__name__)
        
        try:
            import requests
            
            # Ensure parent directory exists
            FileManager._ensure_parent_directory(file_path)
            
            # Download to temporary file first
            temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp")
            
            with requests.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                
                # Get expected file size from headers
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                
                with open(temp_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:  # Filter out keep-alive chunks
                            f.write(chunk)
                            downloaded_size += len(chunk)
                
                # Verify download completeness
                if total_size > 0 and downloaded_size < total_size:
                    logger.warning(f"Download incomplete: {downloaded_size}/{total_size} bytes")
                
                # Verify file was created and has content
                if temp_file.exists() and temp_file.stat().st_size > 0:
                    # Atomic move to final location
                    shutil.move(temp_file, file_path)
                    logger.debug(f"Successfully downloaded {file_path} ({downloaded_size} bytes)")
                    return True
                else:
                    logger.error(f"Downloaded file is empty or missing: {temp_file}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to download {url} to {file_path}: {e}")
            # Clean up temp file if it exists
            temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            return False
    
    @staticmethod
    def _ensure_parent_directory(file_path: Path) -> None:
        """Ensure parent directory exists for the given file path."""
        parent_dir = file_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def _create_backup(file_path: Path) -> None:
        """Create a backup of existing file."""
        if file_path.exists():
            backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
            shutil.copy2(file_path, backup_path)
    
    @staticmethod
    def validate_file_write_permissions(directory: Path) -> bool:
        """Validate that we can write to the given directory."""
        logger = logging.getLogger(__name__)
        
        try:
            # Try to create a test file
            test_file = directory / ".write_test"
            test_file.write_text("test")
            test_file.unlink()  # Clean up
            return True
        except Exception as e:
            logger.error(f"No write permissions for directory {directory}: {e}")
            return False
    
    @staticmethod
    def get_safe_filename(filename: str, max_length: int = 255) -> str:
        """Generate a safe filename by removing/replacing problematic characters."""
        import re
        
        # Replace problematic characters
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Remove control characters
        safe_name = ''.join(char for char in safe_name if ord(char) >= 32)
        
        # Limit length
        if len(safe_name) > max_length:
            name_part, ext_part = os.path.splitext(safe_name)
            max_name_length = max_length - len(ext_part)
            safe_name = name_part[:max_name_length] + ext_part
        
        return safe_name

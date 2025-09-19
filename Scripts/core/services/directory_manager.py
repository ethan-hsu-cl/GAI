"""Directory management utilities for API processing."""
import os
from pathlib import Path
from typing import List, Dict
import logging

class DirectoryManager:
    """Manages directory creation and validation for API processing."""
    
    @staticmethod
    def ensure_task_directories(task_folder: Path, api_type: str, 
                               api_definitions: Dict) -> Dict[str, Path]:
        """Ensure all required directories exist for a task."""
        logger = logging.getLogger(__name__)
        
        # Get folder names from API definitions
        folders_config = api_definitions.get('folders', {})
        
        # Default folder structure
        required_dirs = {
            'input': folders_config.get('input', 'Source'),
            'output': folders_config.get('output', 'Generated_Video'),
            'metadata': folders_config.get('metadata', 'Metadata'),
        }
        
        # Add reference folder if required
        if 'reference' in folders_config:
            required_dirs['reference'] = folders_config['reference']
        
        # Create directory paths
        dir_paths = {}
        for dir_type, dir_name in required_dirs.items():
            dir_path = task_folder / dir_name
            dir_paths[dir_type] = dir_path
            
            # Create directory if it doesn't exist (except input)
            if dir_type != 'input':
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"Ensured {dir_type} directory: {dir_path}")
                except Exception as e:
                    logger.error(f"Failed to create {dir_type} directory {dir_path}: {e}")
                    raise
        
        return dir_paths
    
    @staticmethod
    def create_output_structure(base_path: Path, structure_type: str = 'task_folders') -> None:
        """Create basic output structure based on API type."""
        logger = logging.getLogger(__name__)
        
        if structure_type == 'task_folders':
            # Standard task-based structure
            required_dirs = ['Source', 'Generated_Video', 'Generated_Output', 'Metadata']
        elif structure_type == 'base_folder':
            # Effect-based structure (for Vidu)
            required_dirs = ['Metadata']
        else:
            required_dirs = ['Generated_Video', 'Metadata']
        
        for dir_name in required_dirs:
            dir_path = base_path / dir_name
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created directory: {dir_path}")
            except Exception as e:
                logger.warning(f"Could not create directory {dir_path}: {e}")
    
    @staticmethod
    def validate_input_structure(task_config: Dict, api_definitions: Dict) -> bool:
        """Validate that required input directories exist."""
        logger = logging.getLogger(__name__)
        
        folder = Path(task_config['folder'])
        folders_config = api_definitions.get('folders', {})
        input_folder_name = folders_config.get('input', 'Source')
        input_folder = folder / input_folder_name
        
        if not input_folder.exists():
            logger.error(f"Input folder does not exist: {input_folder}")
            return False
        
        if not any(input_folder.iterdir()):
            logger.warning(f"Input folder is empty: {input_folder}")
            return False
        
        return True

    @staticmethod
    def cleanup_empty_directories(base_path: Path, preserve_dirs: List[str] = None) -> None:
        """Clean up empty directories, preserving specified ones."""
        if preserve_dirs is None:
            preserve_dirs = ['Source', 'Reference']
        
        logger = logging.getLogger(__name__)
        
        for item in base_path.iterdir():
            if item.is_dir() and item.name not in preserve_dirs:
                try:
                    # Only remove if empty
                    if not any(item.iterdir()):
                        item.rmdir()
                        logger.debug(f"Removed empty directory: {item}")
                except Exception as e:
                    logger.debug(f"Could not remove directory {item}: {e}")

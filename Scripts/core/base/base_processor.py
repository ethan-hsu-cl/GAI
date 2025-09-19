"""Abstract base class for API processors."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging

class BaseAPIHandler(ABC):
    """Abstract base class that all API handlers must implement."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = None
        
    @abstractmethod
    def validate_files(self, task_config: Dict) -> List[Path]:
        """Validate files for processing. Returns list of valid file paths."""
        pass
    
    @abstractmethod
    def process_file(self, file_path: Path, task_config: Dict, 
                    output_folder: Path, metadata_folder: Path) -> bool:
        """Process a single file. Returns True if successful."""
        pass
    
    @abstractmethod
    def initialize_client(self) -> bool:
        """Initialize the API client. Returns True if successful."""
        pass
    
    @abstractmethod
    def save_metadata(self, metadata: Dict, metadata_path: Path) -> None:
        """Save processing metadata to file."""
        pass
    
    def process_task(self, task: Dict, task_index: int, total_tasks: int) -> bool:
        """Process a single task - handles both folder structures."""
        
        # Check if this API uses base_folder structure
        config_structure = getattr(self, 'api_definitions', {}).get('config_structure', 'task_folders')
        
        if config_structure == 'base_folder':
            # For base_folder APIs (vidu_effects, vidu_reference, pixverse_effects)
            return self._process_base_folder_task(task, task_index, total_tasks)
        else:
            # For task_folders APIs (kling, nano_banana, etc.)
            return self._process_folder_task(task, task_index, total_tasks)

    def _process_base_folder_task(self, task: Dict, task_index: int, total_tasks: int) -> bool:
        """Process task for base_folder structure APIs."""
        # Let the handler's validate_files method handle file discovery
        valid_files = self.validate_files(task)
        if not valid_files:
            self.logger.error("No valid files found for processing")
            return False
        
        # Process files using handler-specific logic
        # This should be overridden by individual handlers
        return len(valid_files) > 0

    def _process_folder_task(self, task: Dict, task_index: int, total_tasks: int) -> bool:
        """Process task for task_folders structure APIs (original logic)."""
        folder = Path(task['folder'])
        self.logger.info(f"Task {task_index}/{total_tasks}: {folder.name}")
        
        # Validate files
        valid_files = self.validate_files(task)
        if not valid_files:
            self.logger.warning(f"No valid files found in {folder}")
            return False
            
        # Process each file
        successful = 0
        for i, file_path in enumerate(valid_files, 1):
            self.logger.info(f"{i}/{len(valid_files)}: {file_path.name}")
            
            output_folder = folder / self.get_output_folder_name()
            metadata_folder = folder / "Metadata"
            
            if self.process_file(file_path, task, output_folder, metadata_folder):
                successful += 1
                
            # Rate limiting
            if i < len(valid_files):
                import time
                time.sleep(self.get_rate_limit())
                
        self.logger.info(f"Task {task_index}: {successful}/{len(valid_files)} successful")
        return successful > 0


    @abstractmethod
    def get_output_folder_name(self) -> str:
        """Return the name of the output folder for this API."""
        pass
        
    @abstractmethod
    def get_rate_limit(self) -> float:
        """Return rate limit delay in seconds."""
        pass

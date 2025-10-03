"""
Base API Handler - Consolidates all common processing logic.
New APIs only need to implement the unique parts.
"""
import time
from pathlib import Path
from datetime import datetime


class BaseAPIHandler:
    """Base handler with ALL common logic. Subclasses override only what's different."""
    
    def __init__(self, processor):
        self.processor = processor
        self.api_defs = processor.api_definitions
        self.config = processor.config
        self.client = processor.client
        self.logger = processor.logger
        self.api_name = processor.api_name
    
    def process(self, file_path, task_config, output_folder, metadata_folder, attempt, max_retries):
        """Process a single file. Override _make_api_call() to customize."""
        base_name = Path(file_path).stem
        file_name = Path(file_path).name
        start_time = time.time()
        
        try:
            # Make API-specific call (subclass implements this)
            result = self._make_api_call(file_path, task_config, attempt)
            
            # Parse and save result (subclass can override)
            success = self._handle_result(result, file_path, task_config, output_folder, 
                                         metadata_folder, base_name, file_name, start_time, attempt)
            
            if not success and attempt < max_retries - 1:
                time.sleep(5)
                return False
            
            return success
            
        except Exception as e:
            self._save_failure(file_path, task_config, metadata_folder, str(e), 
                             attempt, start_time)
            raise e
    
    def _make_api_call(self, file_path, task_config, attempt):
        """Override this in subclass to make API-specific call."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _make_api_call()")
    
    def _handle_result(self, result, file_path, task_config, output_folder, 
                      metadata_folder, base_name, file_name, start_time, attempt):
        """Override this to handle API-specific result format."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _handle_result()")
    
    def _save_failure(self, file_path, task_config, metadata_folder, error, attempt, start_time):
        """Save failure metadata - common for all APIs."""
        base_name = Path(file_path).stem
        processing_time = time.time() - start_time
        
        metadata = {
            self._get_source_field(): Path(file_path).name,
            "error": error,
            "attempts": attempt + 1,
            "success": False,
            "processing_time_seconds": round(processing_time, 1),
            "processing_timestamp": datetime.now().isoformat(),
            "api_name": self.api_name
        }
        
        # Add task-specific fields
        for key in ['prompt', 'effect', 'model']:
            if key in task_config:
                metadata[key] = task_config[key]
        
        self.processor.save_metadata(Path(metadata_folder), base_name, Path(file_path).name, 
                                    metadata, task_config)
    
    def _get_source_field(self):
        """Get appropriate source field name based on API."""
        return "source_video" if self.api_name == "runway" else "source_image"
    
    def process_task(self, task, task_num, total_tasks):
        """Process entire task - common structure for most APIs."""
        folder = Path(task.get('folder', task.get('folder_path', '')))
        
        # Get folder paths (handles both structures)
        if 'source_dir' in task:
            source_folder = Path(task['source_dir'])
            output_folder = Path(task['generated_dir'])
            metadata_folder = Path(task['metadata_dir'])
        else:
            source_folder = folder / "Source"
            output_folder = self._get_output_folder(folder)
            metadata_folder = folder / "Metadata"
        
        task_name = task.get('effect', folder.name)
        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {task_name}")
        
        # Get files to process
        files = self._get_task_files(task, source_folder)
        
        # Process files
        successful = 0
        for i, file_path in enumerate(files, 1):
            self.logger.info(f" 🖼️ {i}/{len(files)}: {file_path.name}")
            
            if self.processor.process_file(file_path, task, output_folder, metadata_folder):
                successful += 1
            
            if i < len(files):
                time.sleep(self.api_defs.get('rate_limit', 3))
        
        self.logger.info(f"✓ Task {task_num}: {successful}/{len(files)} successful")
    
    def _get_output_folder(self, folder):
        """Get output folder name based on API type."""
        if self.api_name == "genvideo":
            return folder / "Generated_Image"
        elif self.api_name == "nano_banana":
            return folder / "Generated_Output"
        else:
            return folder / "Generated_Video"
    
    def _get_task_files(self, task, source_folder):
        """Get files for this task. Override for special handling."""
        file_type = 'video' if self.api_name == 'runway' else 'image'
        return self.processor._get_files_by_type(source_folder, file_type)

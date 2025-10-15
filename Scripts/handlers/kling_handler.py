"""Kling API Handler - Only unique logic."""
from pathlib import Path
from gradio_client import handle_file
import time
import shutil
from .base_handler import BaseAPIHandler


class KlingHandler(BaseAPIHandler):
    """Kling Image2Video handler."""
    
    def _make_api_call(self, file_path, task_config, attempt):
        """Make Kling API call."""
        return self.client.predict(
            image=handle_file(str(file_path)),
            prompt=task_config['prompt'],
            mode=task_config.get('mode', 'std'),
            duration=5,
            cfg=0.5,
            model=self.config.get('model_version', 'v2.1'),
            negative_prompt=task_config.get('negative_prompt', ''),
            api_name=self.api_defs['api_name']
        )
    
    def _handle_result(self, result, file_path, task_config, output_folder, 
                      metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Kling API result."""
        url, video_dict, video_id, task_id, error = result[:5]
        processing_time = time.time() - start_time
        
        self.logger.info(f" Video ID: {video_id}, Task ID: {task_id}")
        
        # Check for API error
        if error:
            self.logger.info(f" ❌ API Error: {error}")
            metadata = {
                'video_id': video_id, 'task_id': task_id, 'error': error,
                'attempts': attempt + 1, 'success': False,
                'processing_time_seconds': round(processing_time, 1)
            }
            self.processor.save_kling_metadata(Path(metadata_folder), base_name, file_name, 
                                              metadata, task_config)
            return False
        
        # Try to save video
        output_path = Path(output_folder) / f"{base_name}_generated.mp4"
        video_saved = False
        
        # Method 1: URL download
        if url:
            video_saved = self.processor.download_file(url, output_path)
        
        # Method 2: Local file copy
        if not video_saved and video_dict and 'video' in video_dict:
            local_path = Path(video_dict['video'])
            if local_path.exists():
                shutil.copy2(local_path, output_path)
                video_saved = True
        
        # Save metadata
        metadata = {
            'output_url': url, 'video_id': video_id, 'task_id': task_id,
            'generated_video': output_path.name if video_saved else None,
            'attempts': attempt + 1, 'success': video_saved,
            'processing_time_seconds': round(processing_time, 1)
        }
        
        self.processor.save_kling_metadata(Path(metadata_folder), base_name, file_name, 
                                          metadata, task_config)
        
        if video_saved:
            self.logger.info(f" ✅ Generated: {output_path.name}")
        
        return video_saved

"""Nano Banana API Handler - Only unique logic."""
from pathlib import Path
from gradio_client import handle_file
import time
from datetime import datetime
from .base_handler import BaseAPIHandler


class NanoBananaHandler(BaseAPIHandler):
    """Google Flash/Nano Banana handler."""
    
    def _make_api_call(self, file_path, task_config, attempt):
        """Make Nano Banana API call."""
        additional_images = task_config.get('additional_images', {})
        
        return self.client.predict(
            prompt=task_config['prompt'],
            image1=handle_file(str(file_path)),
            image2=additional_images.get('image1', ''),
            image3=additional_images.get('image2', ''),
            api_name=self.api_defs['api_name']
        )
    
    def _handle_result(self, result, file_path, task_config, output_folder, 
                      metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Nano Banana API result."""
        response_id, error_msg, response_data = result[:3]
        processing_time = time.time() - start_time
        
        self.logger.info(f" Response ID: {response_id}")
        
        if error_msg:
            self.logger.info(f" ❌ API Error: {error_msg}")
            metadata = {
                'response_id': response_id, 'error': error_msg, 'success': False,
                'attempts': attempt + 1, 'processing_time_seconds': round(processing_time, 1)
            }
            self.processor.save_nano_metadata(Path(metadata_folder), base_name, file_name, 
                                             metadata, task_config)
            return False
        
        # Save response data
        saved_files, text_responses = self.processor.save_nano_responses(
            response_data, Path(output_folder), base_name)
        has_images = len(saved_files) > 0
        
        # Save metadata
        metadata = {
            'response_id': response_id, 
            'saved_files': [Path(f).name for f in saved_files],
            'text_responses': text_responses, 
            'success': has_images, 
            'attempts': attempt + 1,
            'images_generated': len(saved_files), 
            'processing_time_seconds': round(processing_time, 1),
            'processing_timestamp': datetime.now().isoformat(),
            'api_name': self.api_name
        }
        
        self.processor.save_nano_metadata(Path(metadata_folder), base_name, file_name, 
                                         metadata, task_config)
        
        if has_images:
            self.logger.info(f" ✅ Generated: {len(saved_files)} images")
        else:
            self.logger.info(f" ❌ No images generated")
        
        return has_images

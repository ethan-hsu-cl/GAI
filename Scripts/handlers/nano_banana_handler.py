"""Nano Banana API Handler - Multi-Image Support."""
from pathlib import Path
from gradio_client import handle_file
import time
import random
from datetime import datetime
from .base_handler import BaseAPIHandler


class NanoBananaHandler(BaseAPIHandler):
    """Google Flash/Nano Banana handler with multi-image support."""
    
    def __init__(self, processor):
        """Initialize handler with multi-image support."""
        super().__init__(processor)
        self._additional_image_pools = {}
        self._used_combinations = set()
    
    def _load_image_pools(self, task_config):
        """Load and cache image pools from additional folders."""
        multi_image_config = task_config.get('multi_image_config', {})
        
        if not multi_image_config or not multi_image_config.get('enabled', False):
            return None
        
        mode = multi_image_config.get('mode', 'random_pairing')
        folders = multi_image_config.get('folders', [])
        
        if not folders:
            return None
        
        # Cache image pools per task
        task_key = str(task_config.get('folder', ''))
        if task_key not in self._additional_image_pools:
            pools = []
            for folder_path in folders:
                folder = Path(folder_path)
                if folder.exists():
                    images = self.processor._get_files_by_type(folder, 'image')
                    if images:
                        pools.append(images)
                        self.logger.info(f" 📂 Loaded {len(images)} images from {folder.name}")
                else:
                    self.logger.warning(f" ⚠️ Folder not found: {folder}")
            
            self._additional_image_pools[task_key] = {
                'pools': pools,
                'mode': mode,
                'allow_duplicates': multi_image_config.get('allow_duplicates', False)
            }
        
        return self._additional_image_pools[task_key]
    
    def _get_additional_images(self, file_path, task_config):
        """Get additional images based on configuration mode."""
        # Check if multi-image is explicitly disabled
        if not task_config.get('use_multi_image', True):
            return ['', '']
        
        # Check for static additional images (legacy support)
        additional_images = task_config.get('additional_images', {})
        if additional_images:
            return [
                additional_images.get('image1', ''),
                additional_images.get('image2', '')
            ]
        
        # Check for multi-image configuration
        pool_data = self._load_image_pools(task_config)
        if not pool_data or not pool_data['pools']:
            return ['', '']
        
        pools = pool_data['pools']
        mode = pool_data['mode']
        allow_duplicates = pool_data['allow_duplicates']
        
        if mode == 'random_pairing':
            return self._random_pairing(pools, file_path, allow_duplicates)
        elif mode == 'sequential':
            return self._sequential_selection(pools, file_path)
        else:
            self.logger.warning(f" ⚠️ Unknown mode '{mode}', using random_pairing")
            return self._random_pairing(pools, file_path, allow_duplicates)
    
    def _random_pairing(self, pools, file_path, allow_duplicates):
        """Randomly select one image from each pool, optionally avoiding duplicates."""
        selected = []
        max_attempts = 100
        
        for pool in pools:
            if not pool:
                selected.append('')
                continue
            
            if allow_duplicates:
                selected.append(str(random.choice(pool)))
            else:
                # Try to find unused combination
                for _ in range(max_attempts):
                    candidate = random.choice(pool)
                    combo_key = (str(file_path), str(candidate))
                    if combo_key not in self._used_combinations:
                        self._used_combinations.add(combo_key)
                        selected.append(str(candidate))
                        break
                else:
                    # If we can't find unused after max_attempts, just use random
                    selected.append(str(random.choice(pool)))
        
        # Pad with empty strings if we have fewer than 2 pools
        while len(selected) < 2:
            selected.append('')
        
        return selected[:2]  # Return only first 2
    
    def _sequential_selection(self, pools, file_path):
        """Select images sequentially from each pool based on file index."""
        # Use hash of file path to get consistent index
        file_index = hash(str(file_path)) % 10000
        selected = []
        
        for pool in pools:
            if pool:
                index = file_index % len(pool)
                selected.append(str(pool[index]))
            else:
                selected.append('')
        
        # Pad with empty strings if needed
        while len(selected) < 2:
            selected.append('')
        
        return selected[:2]
    
    def _make_api_call(self, file_path, task_config, attempt):
        """Make Nano Banana API call with multi-image support."""
        additional_imgs = self._get_additional_images(file_path, task_config)
        
        # Store the additional images used for this specific file (for metadata)
        if not hasattr(self, '_current_additional_images'):
            self._current_additional_images = {}
        self._current_additional_images[str(file_path)] = additional_imgs
        
        return self.client.predict(
            prompt=task_config['prompt'],
            image1=handle_file(str(file_path)),
            image2=handle_file(additional_imgs[0]) if additional_imgs[0] else '',
            image3=handle_file(additional_imgs[1]) if additional_imgs[1] else '',
            api_name=self.api_defs['api_name']
        )
    
    def _handle_result(self, result, file_path, task_config, output_folder, 
                      metadata_folder, base_name, file_name, start_time, attempt):
        """Handle Nano Banana API result with multi-image tracking."""
        response_id, error_msg, response_data = result[:3]
        processing_time = time.time() - start_time
        
        self.logger.info(f" Response ID: {response_id}")
        
        # Get additional images info for metadata
        additional_imgs = getattr(self, '_current_additional_images', {}).get(str(file_path), ['', ''])
        additional_imgs_info = []
        for img_path in additional_imgs:
            if img_path:
                additional_imgs_info.append(Path(img_path).name)
        
        if error_msg:
            self.logger.info(f" ❌ API Error: {error_msg}")
            metadata = {
                'response_id': response_id, 'error': error_msg, 'success': False,
                'attempts': attempt + 1, 'processing_time_seconds': round(processing_time, 1)
            }
            if additional_imgs_info:
                metadata['additional_images_used'] = additional_imgs_info
            self.processor.save_nano_metadata(Path(metadata_folder), base_name, file_name, 
                                             metadata, task_config)
            return False
        
        # Save response data
        saved_files, text_responses = self.processor.save_nano_responses(
            response_data, Path(output_folder), base_name)
        has_images = len(saved_files) > 0
        
        # Save metadata with additional image info
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
        
        if additional_imgs_info:
            metadata['additional_images_used'] = additional_imgs_info
        
        self.processor.save_nano_metadata(Path(metadata_folder), base_name, file_name, 
                                         metadata, task_config)
        
        if has_images:
            self.logger.info(f" ✅ Generated: {len(saved_files)} images")
            if additional_imgs_info:
                self.logger.info(f" 🖼️ Additional images: {', '.join(additional_imgs_info)}")
        else:
            self.logger.info(f" ❌ No images generated")
        
        return has_images

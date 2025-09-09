import os
import time
import shutil
import json
import requests
from datetime import datetime, time as dt_time
from gradio_client import Client, handle_file
from PIL import Image
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import logging

class BatchVideoProcessor:
    def __init__(self, config_file="batch_config.json"):
        self.config_file = config_file
        self.client = None
        self.config = {}
        
        # Setup logging to reduce print statements
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        self.logger = logging.getLogger(__name__)
    
    def load_config(self):
        """Load and validate configuration"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.logger.info(f"✓ Configuration loaded from {self.config_file}")
            return True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"❌ Config error: {e}")
            return False
    
    def validate_image(self, image_path):
        """Validate single image against Kling requirements"""
        try:
            # Check file size (< 10MB) without opening file
            if os.path.getsize(image_path) >= 10485760:  # 10MB in bytes
                return False, "Size > 10MB"
            
            with Image.open(image_path) as img:
                w, h = img.size
                if w <= 300 or h <= 300:
                    return False, f"Dims {w}x{h} too small"
                
                ratio = w / h
                if not (0.4 <= ratio <= 2.5):
                    return False, f"Ratio {ratio:.2f} invalid"
                
                return True, f"{w}x{h}, {ratio:.2f}"
        except Exception as e:
            return False, f"Read error: {str(e)}"

    def validate_and_prepare(self):
        """Combined validation and folder preparation"""
        valid_tasks = []
        invalid_images = []
        
        for i, task in enumerate(self.config.get('tasks', [])):
            folder = Path(task['folder'])
            source_folder = folder / "Source"
            
            if not source_folder.exists():
                self.logger.warning(f"❌ Missing source: {source_folder}")
                continue
            
            # Get all image files
            image_files = [f for f in source_folder.iterdir() 
                          if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}]
            
            if not image_files:
                self.logger.warning(f"❌ Empty source: {source_folder}")
                continue
            
            # Validate images and count valid ones
            valid_count = 0
            for img_file in image_files:
                is_valid, reason = self.validate_image(img_file)
                if not is_valid:
                    invalid_images.append({
                        'path': str(img_file),
                        'folder': str(folder),
                        'name': img_file.name,
                        'reason': reason
                    })
                else:
                    valid_count += 1
            
            if valid_count > 0:
                # Create output directories
                (folder / "Generated_Video").mkdir(exist_ok=True)
                (folder / "Metadata").mkdir(exist_ok=True)
                valid_tasks.append(task)
                self.logger.info(f"✓ Task {i+1}: {valid_count}/{len(image_files)} valid images")
        
        # Handle invalid images
        if invalid_images:
            with open("invalid_images_report.txt", 'w') as f:
                f.write(f"INVALID IMAGES ({len(invalid_images)} total)\n")
                f.write(f"Generated: {datetime.now()}\n\n")
                for img in invalid_images:
                    f.write(f"❌ {img['name']} in {img['folder']}: {img['reason']}\n")
            
            raise Exception(f"{len(invalid_images)} invalid images found. Check invalid_images_report.txt")
        
        return valid_tasks
    
    def wait_for_schedule(self):
        """Wait for scheduled time if specified"""
        start_time_str = self.config.get('schedule', {}).get('start_time', '')
        if not start_time_str:
            return
        
        try:
            target_hour, target_min = map(int, start_time_str.split(':'))
            now = datetime.now()
            target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
            
            if target <= now:
                target = target.replace(day=target.day + 1)
            
            wait_seconds = (target - now).total_seconds()
            self.logger.info(f"⏰ Waiting {wait_seconds/3600:.1f}h until {target.strftime('%H:%M')}")
            time.sleep(wait_seconds)
            
        except ValueError:
            self.logger.warning(f"❌ Invalid time format: {start_time_str}")
    
    def initialize_client(self):
        """Initialize Gradio client"""
        try:
            self.client = Client("http://192.168.4.3:8000/kling/")
            return True
        except Exception as e:
            self.logger.error(f"❌ Client init failed: {e}")
            return False
    
    def download_video(self, url, path):
        """Download video with streaming"""
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            return True
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return False
    
    def process_image(self, image_path, task_config, output_folder, metadata_folder, max_retries=3):
        """Process single image with retry logic and always save metadata"""
        base_name = image_path.stem
        image_name = image_path.name
        start_time = time.time()
        final_attempt = 0
        final_error = None
        
        for attempt in range(max_retries):
            final_attempt = attempt + 1
            try:
                if attempt > 0:
                    print(f"    🔄 Retry attempt {attempt}/{max_retries - 1}")
                
                result = self.client.predict(
                    image=handle_file(str(image_path)),
                    prompt=task_config['prompt'],
                    mode="std",
                    duration=5,
                    cfg=0.5,
                    model=self.config.get('model_version', 'v2.1'),
                    negative_prompt=task_config.get('negative_prompt', ''),
                    api_name="/Image2Video"
                )
                
                url, video_dict, video_id, task_id, error = result[:5]
                
                print(f"    Video ID: {video_id}")
                print(f"    Task ID: {task_id}")
                
                # Check for API errors first
                if error:
                    print(f"    ❌ API Error: {error}")
                    final_error = error
                    if attempt < max_retries - 1:
                        print(f"    ⏱️  Waiting 5 seconds before retry...")
                        time.sleep(5)
                        continue
                    else:
                        # Final attempt failed - save failure metadata
                        self.save_metadata(metadata_folder, base_name, image_name, {
                            'video_id': video_id,
                            'task_id': task_id,
                            'error': error,
                            'attempts': final_attempt,
                            'success': False,
                            'processing_time_seconds': round(time.time() - start_time, 1)
                        }, task_config)
                        return False
                
                # Try to save video file
                output_path = output_folder / f"{base_name}_generated.mp4"
                video_saved = False
                
                # Method 1: Download from URL
                if url:
                    video_saved = self.download_video(url, output_path)
                    if not video_saved:
                        print(f"    ⚠️  URL download failed, trying local file...")
                
                # Method 2: Copy from local file
                if not video_saved and video_dict and 'video' in video_dict:
                    local_path = Path(video_dict['video'])
                    if local_path.exists():
                        shutil.copy2(local_path, output_path)
                        print(f"    ✓ Video copied from local file: {output_path}")
                        video_saved = True
                    else:
                        print(f"    ❌ Local video file not found: {local_path}")
                
                if video_saved:
                    # SUCCESS - Save success metadata
                    self.save_metadata(metadata_folder, base_name, image_name, {
                        'output_url': url,
                        'video_id': video_id,
                        'task_id': task_id,
                        'generated_video': output_path.name,
                        'attempts': final_attempt,
                        'success': True,
                        'processing_time_seconds': round(time.time() - start_time, 1)
                    }, task_config)
                    return True
                else:
                    # Video generation succeeded but file save failed
                    final_error = "Video file could not be saved (both URL download and local copy failed)"
                    if attempt < max_retries - 1:
                        print(f"    ❌ {final_error}")
                        print(f"    ⏱️  Waiting 5 seconds before retry...")
                        time.sleep(5)
                        continue
                    else:
                        # Final attempt - save partial success metadata
                        self.save_metadata(metadata_folder, base_name, image_name, {
                            'output_url': url,
                            'video_id': video_id,
                            'task_id': task_id,
                            'error': final_error,
                            'attempts': final_attempt,
                            'success': False,
                            'processing_time_seconds': round(time.time() - start_time, 1)
                        }, task_config)
                        return False
                        
            except Exception as e:
                final_error = str(e)
                print(f"    ❌ Exception (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"    ⏱️  Waiting 5 seconds before retry...")
                    time.sleep(5)
                    continue
                else:
                    # Final attempt failed - save exception metadata
                    self.save_metadata(metadata_folder, base_name, image_name, {
                        'error': final_error,
                        'attempts': final_attempt,
                        'success': False,
                        'processing_time_seconds': round(time.time() - start_time, 1)
                    }, task_config)
                    return False
        
        return False

    
    def save_metadata(self, metadata_folder, base_name, image_name, result_data, task_config):
        """Helper method to save metadata consistently"""
        metadata = {
            "source_image": image_name,
            "prompt": task_config['prompt'],
            "negative_prompt": task_config.get('negative_prompt', ''),
            "model_version": self.config.get('model_version', 'v2.1'),
            "processing_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            **result_data  # Merge in the specific result data
        }
        
        metadata_file = metadata_folder / f"{base_name}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        
        status = "✓" if result_data.get('success', False) else "❌"
        print(f"    {status} Metadata saved: {metadata_file.name}")

    def process_task(self, task, task_num, total_tasks):
        """Process all images in a task"""
        folder = Path(task['folder'])
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Video"
        metadata_folder = folder / "Metadata"
        
        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {folder.name}")
        
        # Get valid images (pre-validated)
        image_files = [f for f in source_folder.iterdir() 
                      if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}]
        
        # Process images sequentially (to avoid API rate limits)
        successful = 0
        for i, img_file in enumerate(image_files, 1):
            self.logger.info(f"  🖼️  {i}/{len(image_files)}: {img_file.name}")
            
            if self.process_image(img_file, task, output_folder, metadata_folder):
                successful += 1
            
            if i < len(image_files):
                time.sleep(3)  # Rate limiting
        
        self.logger.info(f"✓ Task {task_num}: {successful}/{len(image_files)} successful")
    
    def run(self):
        """Main execution"""
        self.logger.info("🚀 Starting Batch Video Processor")
        
        if not self.load_config():
            return False
        
        try:
            valid_tasks = self.validate_and_prepare()
        except Exception as e:
            self.logger.error(str(e))
            return False
        
        self.wait_for_schedule()
        
        if not self.initialize_client():
            return False
        
        start_time = time.time()
        
        for i, task in enumerate(valid_tasks, 1):
            try:
                self.process_task(task, i, len(valid_tasks))
                if i < len(valid_tasks):
                    time.sleep(10)
            except Exception as e:
                self.logger.error(f"Task {i} failed: {e}")
        
        elapsed = time.time() - start_time
        self.logger.info(f"🎉 Completed {len(valid_tasks)} tasks in {elapsed/60:.1f} minutes")
        return True

if __name__ == "__main__":
    processor = BatchVideoProcessor()
    processor.run()

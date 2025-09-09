import json, logging, time, requests
from pathlib import Path
from datetime import datetime, time as dt_time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from gradio_client import Client, handle_file

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class ViduEffectProcessor:
    SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
    
    def __init__(self, config_file="batch_vidu_config.json"):
        self.config_file = config_file
        self.client = None
        self.config = {}
        
    def load_config(self):
        """Load and validate configuration"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"✓ Configuration loaded from {self.config_file}")
            return True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"❌ Config error: {e}")
            return False
    
    def validate_image_fast(self, image_path):
        """Optimized image validation"""
        try:
            # Quick size check
            if image_path.stat().st_size >= 52428800:  # 50MB
                return False, "Size > 50MB"
            
            with Image.open(image_path) as img:
                w, h = img.size
                if w < 128 or h < 128:
                    return False, f"Dims {w}x{h} too small"
                
                ratio = w / h
                if not (0.25 <= ratio <= 4.0):
                    return False, f"Ratio {ratio:.2f} invalid"
                
                return True, f"{w}x{h}"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def validate_tasks_batch(self):
        """Validate all tasks efficiently"""
        base_folder = Path(self.config.get('base_folder', ''))
        if not base_folder.exists():
            raise FileNotFoundError(f"Base folder not found: {base_folder}")
        
        valid_tasks = []
        invalid_images = []
        
        def process_task(task):
            effect_name = task.get('effect', '')
            task_folder = base_folder / effect_name
            source_dir = task_folder / "Source"
            
            if not source_dir.exists():
                return None, []
            
            # Get and validate images
            image_files = [f for f in source_dir.iterdir() 
                          if f.suffix.lower() in self.SUPPORTED_EXT]
            
            if not image_files:
                return None, []
            
            # Validate images
            invalid_for_task = []
            valid_count = 0
            for img_file in image_files:
                is_valid, reason = self.validate_image_fast(img_file)
                if not is_valid:
                    invalid_for_task.append({
                        'folder': effect_name, 'filename': img_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1
            
            if valid_count > 0:
                # Create output directories
                (task_folder / "Generated_Video").mkdir(exist_ok=True)
                (task_folder / "Metadata").mkdir(exist_ok=True)
                
                # Add folder paths to task
                enhanced_task = task.copy()
                enhanced_task.update({
                    'folder': str(task_folder),
                    'source_dir': str(source_dir),
                    'generated_dir': str(task_folder / "Generated_Video"),
                    'metadata_dir': str(task_folder / "Metadata")
                })
                logger.info(f"✓ {effect_name}: {valid_count}/{len(image_files)} valid images")
                return enhanced_task, invalid_for_task
            
            return None, invalid_for_task
        
        # Process tasks in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(process_task, self.config.get('tasks', [])))
        
        # Collect results
        for task, invalid_for_task in results:
            if task:
                valid_tasks.append(task)
            invalid_images.extend(invalid_for_task)
        
        if invalid_images:
            with open("invalid_vidu_report.txt", 'w', encoding='utf-8') as f:
                f.write(f"INVALID IMAGES ({len(invalid_images)} total)\n")
                f.write(f"Generated: {datetime.now()}\n\n")
                for img in invalid_images:
                    f.write(f"❌ {img['folder']}: {img['filename']} - {img['reason']}\n")
            raise Exception(f"{len(invalid_images)} invalid images found")
        
        return valid_tasks
    
    def wait_for_schedule(self):
        """Wait for scheduled time if specified"""
        start_time = self.config.get('schedule', {}).get('start_time', '')
        if not start_time:
            return
        
        try:
            target_hour, target_min = map(int, start_time.split(':'))
            now = datetime.now()
            target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
            
            if target <= now:
                target = target.replace(day=target.day + 1)
            
            wait_seconds = (target - now).total_seconds()
            logger.info(f"⏰ Waiting {wait_seconds/3600:.1f}h until {target.strftime('%H:%M')}")
            time.sleep(wait_seconds)
        except ValueError:
            logger.warning(f"❌ Invalid time format: {start_time}")
    
    def initialize_client(self):
        """Initialize Gradio client"""
        try:
            self.client = Client("http://192.168.4.3:8000/video_effect/")
            return True
        except Exception as e:
            logger.error(f"❌ Client init failed: {e}")
            return False
    
    def download_video_fast(self, url, path):
        """Optimized video download"""
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
    
    def save_metadata(self, metadata_dir, image_file, data):
        """Save metadata efficiently"""
        base_name = Path(image_file).stem
        metadata_file = Path(metadata_dir) / f"{base_name}_metadata.json"
        
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Metadata save failed: {e}")
            return False
    
    def process_image(self, image_path, task, output_dir, metadata_dir, max_retries=3):
        """Process single image with retry logic and metadata saving"""
        base_name = Path(image_path).stem
        start_time = time.time()
        
        # Get prompt (task-level or global)
        prompt = task.get('prompt', '') or self.config.get('prompt', '')
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"    🔄 Retry {attempt}/{max_retries-1}")
                
                # API call
                result = self.client.predict(
                    effect=task.get('effect', ''),
                    prompt=prompt,
                    aspect_ratio="as input image",
                    area="auto", beast="auto", bgm=False,
                    images=(handle_file(image_path),),
                    api_name="/effect_submit_api"
                )
                
                # Validate and extract result
                if not isinstance(result, tuple) or len(result) < 5:
                    raise ValueError(f"Invalid API response format")
                
                output_urls = result[0]
                if not output_urls:
                    raise ValueError("No output URLs returned")
                
                # Extract URL
                output_url = output_urls[0] if isinstance(output_urls, (tuple, list)) else output_urls
                
                # Download video
                effect_name = task.get('effect', '').replace(' ', '_').replace('-', '_')
                output_video_name = f"{base_name}_{effect_name}_effect.mp4"
                output_video_path = Path(output_dir) / output_video_name
                
                if not self.download_video_fast(output_url, output_video_path):
                    raise IOError("Video download failed")
                
                # Save success metadata
                processing_time = time.time() - start_time
                metadata = {
                    "source_image": Path(image_path).name,
                    "effect_category": task.get('category', ''),
                    "effect_name": task.get('effect', ''),
                    "prompt": prompt,
                    "output_url": output_url,
                    "generated_video": output_video_name,
                    "processing_time_seconds": round(processing_time, 1),
                    "processing_timestamp": datetime.now().isoformat(),
                    "attempts": attempt + 1,
                    "success": True
                }
                
                self.save_metadata(metadata_dir, Path(image_path).name, metadata)
                return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                
                # Save failure metadata
                processing_time = time.time() - start_time
                metadata = {
                    "source_image": Path(image_path).name,
                    "effect_category": task.get('category', ''),
                    "effect_name": task.get('effect', ''),
                    "prompt": prompt,
                    "error_message": str(e),
                    "processing_time_seconds": round(processing_time, 1),
                    "processing_timestamp": datetime.now().isoformat(),
                    "attempts": attempt + 1,
                    "success": False
                }
                
                self.save_metadata(metadata_dir, Path(image_path).name, metadata)
                return False
        
        return False
    
    def process_task(self, task, task_num, total_tasks):
        """Process all images in a task"""
        effect_name = task.get('effect', '')
        source_dir = Path(task.get('source_dir', ''))
        generated_dir = task.get('generated_dir', '')
        metadata_dir = task.get('metadata_dir', '')
        
        logger.info(f"🎬 Task {task_num}/{total_tasks}: {effect_name}")
        
        # Get all valid images
        image_files = [f for f in source_dir.iterdir() 
                      if f.suffix.lower() in self.SUPPORTED_EXT]
        
        successful = 0
        for i, image_file in enumerate(image_files, 1):
            logger.info(f"  🖼️  {i}/{len(image_files)}: {image_file.name}")
            
            if self.process_image(str(image_file), task, generated_dir, metadata_dir):
                successful += 1
            
            if i < len(image_files):
                time.sleep(3)  # Rate limiting
        
        logger.info(f"✓ Task {task_num}: {successful}/{len(image_files)} successful")
    
    def run(self):
        """Main execution"""
        logger.info("🎬 Starting Vidu Effect Processor")
        
        if not self.load_config():
            return False
        
        try:
            valid_tasks = self.validate_tasks_batch()
        except Exception as e:
            logger.error(str(e))
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
                logger.error(f"Task {i} failed: {e}")
        
        elapsed = time.time() - start_time
        logger.info(f"🎉 Completed {len(valid_tasks)} tasks in {elapsed/60:.1f} minutes")
        return True

if __name__ == "__main__":
    processor = ViduEffectProcessor()
    processor.run()

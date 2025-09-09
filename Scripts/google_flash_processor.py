import json, logging, os, sys, time, base64
from datetime import datetime, time as dt_time
from pathlib import Path
from gradio_client import Client, handle_file
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class GoogleFlashProcessor:
    def __init__(self, config_file="batch_nano_banana_config.json"):
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
    
    def validate_image(self, image_path):
        """Fast image validation"""
        try:
            # Quick size check
            if os.path.getsize(image_path) >= 10485760:  # 10MB
                return False, "Size > 10MB"
            
            with Image.open(image_path) as img:
                w, h = img.size
                if w <= 100 or h <= 100:
                    return False, f"Dims {w}x{h} too small"
                return True, f"{w}x{h}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def validate_and_prepare_batch(self):
        """Validate all tasks and prepare folders efficiently"""
        valid_tasks = []
        invalid_images = []
        
        def process_task(task):
            folder = Path(task['folder'])
            source_folder = folder / "Source"
            
            if not source_folder.exists():
                return None, []
                
            # Get and validate images
            image_files = [f for f in source_folder.iterdir() 
                          if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}]
            
            if not image_files:
                return None, []
            
            # Validate images
            invalid_for_task = []
            valid_count = 0
            for img_file in image_files:
                is_valid, reason = self.validate_image(img_file)
                if not is_valid:
                    invalid_for_task.append({
                        'path': str(img_file), 'folder': str(folder),
                        'name': img_file.name, 'reason': reason
                    })
                else:
                    valid_count += 1
            
            if valid_count > 0:
                # Create output directories
                (folder / "Generated_Output").mkdir(exist_ok=True)
                (folder / "Metadata").mkdir(exist_ok=True)
                logger.info(f"✓ Task: {folder.name} - {valid_count}/{len(image_files)} valid images")
                return task, invalid_for_task
            
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
            with open("invalid_images_flash_report.txt", 'w', encoding='utf-8') as f:
                f.write(f"INVALID IMAGES ({len(invalid_images)} total)\n")
                f.write(f"Generated: {datetime.now()}\n\n")
                for img in invalid_images:
                    f.write(f"❌ {img['name']} in {img['folder']}: {img['reason']}\n")
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
            self.client = Client("http://192.168.4.3:8000/google_flash_image/")
            return True
        except Exception as e:
            logger.error(f"❌ Client init failed: {e}")
            return False
    
    def save_responses(self, response_data, output_folder, base_name):
        """Save response data efficiently"""
        if not response_data or not isinstance(response_data, list):
            return [], []
        
        saved_files = []
        text_responses = []
        
        for i, item in enumerate(response_data):
            if not isinstance(item, dict) or 'type' not in item or 'data' not in item:
                continue
                
            if item['type'] == "Text":
                text_responses.append({'index': i + 1, 'content': item['data']})
                
            elif item['type'] == "Image" and item['data'].strip():
                try:
                    # Handle base64 image data
                    if item['data'].startswith('image'):
                        header, base64_data = item['data'].split(',', 1)
                        ext = header.split('/')[1].split(';')[0]
                    else:
                        base64_data = item['data']
                        ext = 'png'
                    
                    if len(base64_data.strip()) == 0:
                        continue
                    
                    image_bytes = base64.b64decode(base64_data)
                    if len(image_bytes) < 100:  # Too small, likely invalid
                        continue
                    
                    image_file = output_folder / f"{base_name}_image_{i+1}.{ext}"
                    with open(image_file, 'wb') as f:
                        f.write(image_bytes)
                    
                    saved_files.append(str(image_file))
                    
                except Exception as e:
                    logger.warning(f"Error saving image {i+1}: {e}")
        
        return saved_files, text_responses
    
    def process_image(self, image_path, task_config, output_folder, metadata_folder, max_retries=3):
        """Process single image with retry logic and metadata saving"""
        base_name = image_path.stem
        start_time = time.time()
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"    🔄 Retry {attempt}/{max_retries-1}")
                
                # API call
                additional_images = task_config.get('additional_images', {})
                result = self.client.predict(
                    prompt=task_config['prompt'],
                    image1=handle_file(str(image_path)),
                    image2=additional_images.get('image1', ''),
                    image3=additional_images.get('image2', ''),
                    api_name="/nano_banana"
                )
                
                response_id, error_msg, response_data = result[:3]
                logger.info(f"    Response ID: {response_id}")
                
                if error_msg:
                    logger.info(f"    ❌ API Error: {error_msg}")
                    if attempt < max_retries - 1:
                        time.sleep(5)
                        continue
                    # Save failure metadata
                    self.save_metadata(metadata_folder, base_name, image_path.name, {
                        'response_id': response_id, 'error': error_msg, 'success': False,
                        'attempts': attempt + 1, 'processing_time_seconds': round(time.time() - start_time, 1)
                    }, task_config)
                    return False
                
                # Save response data
                saved_files, text_responses = self.save_responses(response_data, output_folder, base_name)
                has_images = len(saved_files) > 0
                
                # Retry if no images generated
                if not has_images and attempt < max_retries - 1:
                    logger.info(f"    ⚠️  No images generated, retrying...")
                    time.sleep(5)
                    continue
                
                # Save metadata
                self.save_metadata(metadata_folder, base_name, image_path.name, {
                    'response_id': response_id, 'saved_files': [Path(f).name for f in saved_files],
                    'text_responses': text_responses, 'success': has_images, 'attempts': attempt + 1,
                    'images_generated': len(saved_files), 'processing_time_seconds': round(time.time() - start_time, 1)
                }, task_config)
                
                return has_images
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                # Save exception metadata
                self.save_metadata(metadata_folder, base_name, image_path.name, {
                    'error': str(e), 'success': False, 'attempts': attempt + 1,
                    'processing_time_seconds': round(time.time() - start_time, 1)
                }, task_config)
                return False
        
        return False
    
    def save_metadata(self, metadata_folder, base_name, image_name, result_data, task_config):
        """Save metadata efficiently"""
        metadata = {
            "source_image": image_name,
            "prompt": task_config['prompt'],
            "additional_images": task_config.get('additional_images', {}),
            "processing_timestamp": datetime.now().isoformat(),
            **result_data
        }
        
        metadata_file = metadata_folder / f"{base_name}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def process_task(self, task, task_num, total_tasks):
        """Process all images in a task"""
        folder = Path(task['folder'])
        source_folder = folder / "Source"
        output_folder = folder / "Generated_Output"
        metadata_folder = folder / "Metadata"
        
        logger.info(f"📁 Task {task_num}/{total_tasks}: {folder.name}")
        
        # Get all valid images
        image_files = [f for f in source_folder.iterdir() 
                      if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}]
        
        successful = 0
        for i, img_file in enumerate(image_files, 1):
            logger.info(f"  🖼️  {i}/{len(image_files)}: {img_file.name}")
            
            if self.process_image(img_file, task, output_folder, metadata_folder):
                successful += 1
            
            if i < len(image_files):
                time.sleep(5)  # Rate limiting
        
        logger.info(f"✓ Task {task_num}: {successful}/{len(image_files)} successful")
    
    def run(self):
        """Main execution"""
        logger.info("🚀 Starting Google Flash Batch Processor")
        
        if not self.load_config():
            return False
        
        try:
            valid_tasks = self.validate_and_prepare_batch()
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
    if len(sys.argv) > 1 and sys.argv[1] == "--migrate":
        # Migration functionality simplified
        processor = GoogleFlashProcessor()
        if processor.load_config():
            logger.info("🔄 Migration mode not needed - metadata is now handled automatically")
    else:
        processor = GoogleFlashProcessor()
        processor.run()

import os
import time
import shutil
import json
import requests
from datetime import datetime
from gradio_client import Client, handle_file
from PIL import Image
from pathlib import Path
import subprocess
import logging

class RunwayBatchVideoProcessor:
    # Class constants to avoid repeated definitions
    VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp'}
    
    def __init__(self, config_file="batch_runway_config.json"):
        self.config_file = config_file
        self.client = None
        self.config = {}
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        self.logger = logging.getLogger(__name__)

    def load_config(self):
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.logger.info(f"✓ Configuration loaded from {self.config_file}")
            return True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"❌ Config error: {e}")
            return False

    def get_video_info(self, video_path):
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_format', '-show_streams', str(video_path)
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                return None
                
            info = json.loads(result.stdout)
            video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
            
            if video_stream:
                return {
                    'width': int(video_stream.get('width', 0)),
                    'height': int(video_stream.get('height', 0)),
                    'duration': float(info['format'].get('duration', 0)),
                    'size_mb': float(info['format'].get('size', 0)) / (1024 * 1024)
                }
            return None
        except Exception:
            return None

    def validate_file(self, file_path, file_type='video'):
        """Combined validation for both videos and images"""
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            if file_type == 'video':
                if file_size_mb > 500:
                    return False, f"Size {file_size_mb:.1f}MB too large"
                
                info = self.get_video_info(file_path)
                if not info:
                    return False, "Cannot read video info"
                
                if not (1 <= info['duration'] <= 30):
                    return False, f"Duration {info['duration']:.1f}s invalid"
                
                if info['width'] < 320 or info['height'] < 320:
                    return False, f"Resolution {info['width']}x{info['height']} too small"
                
                return True, f"{info['width']}x{info['height']}, {info['duration']:.1f}s, {info['size_mb']:.1f}MB"
                
            else:  # image
                if file_size_mb >= 10:
                    return False, "Reference image > 10MB"
                
                with Image.open(file_path) as img:
                    w, h = img.size
                    if w < 320 or h < 320:
                        return False, f"Reference image {w}x{h} too small"
                    return True, f"Reference: {w}x{h}"
                    
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def validate_and_prepare(self):
        """Streamlined validation with early returns"""
        valid_tasks = []
        invalid_files = []
        
        for i, task in enumerate(self.config.get('tasks', []), 1):
            folder = Path(task['folder'])
            source_folder = folder / "Source"
            reference_folder = folder / "Reference"
            
            # Early exit for missing folders
            if not (source_folder.exists() and reference_folder.exists()):
                self.logger.warning(f"❌ Missing folders in task {i}")
                continue
            
            # Get files using list comprehensions for better performance
            video_files = [f for f in source_folder.iterdir() if f.suffix.lower() in self.VIDEO_EXTS]
            reference_images = [f for f in reference_folder.iterdir() if f.suffix.lower() in self.IMAGE_EXTS]
            
            if not (video_files and reference_images):
                self.logger.warning(f"❌ Missing videos or references in task {i}")
                continue
            
            # Validate files in batch
            valid_videos = sum(1 for f in video_files if self.validate_file(f, 'video')[0])
            valid_refs = sum(1 for f in reference_images if self.validate_file(f, 'image')[0])
            
            # Add invalid files to list (simplified)
            invalid_files.extend([
                {'name': f.name, 'folder': str(folder), 'type': 'video', 'reason': 'Invalid'}
                for f in video_files if not self.validate_file(f, 'video')[0]
            ])
            invalid_files.extend([
                {'name': f.name, 'folder': str(folder), 'type': 'reference', 'reason': 'Invalid'}
                for f in reference_images if not self.validate_file(f, 'image')[0]
            ])
            
            if valid_videos and valid_refs:
                # Create output directories
                for subdir in ["Generated_Video", "Metadata"]:
                    (folder / subdir).mkdir(exist_ok=True)
                valid_tasks.append(task)
                self.logger.info(f"✓ Task {i}: {valid_videos} videos, {valid_refs} references")
        
        if invalid_files:
            print(f"\nINVALID FILES ({len(invalid_files)} total)\nGenerated: {datetime.now()}\n")
            for file in invalid_files:
                print(f"❌ {file['name']} ({file['type']}) in {file['folder']}: {file['reason']}")
            raise Exception(f"{len(invalid_files)} invalid files found.")
        
        return valid_tasks

    def wait_for_schedule(self):
        start_time_str = self.config.get('schedule', {}).get('start_time')
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
        try:
            self.client = Client("http://192.168.4.3:8000/runway/")
            return True
        except Exception as e:
            self.logger.error(f"❌ Client init failed: {e}")
            return False

    def download_video(self, url, path):
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            return True
        except Exception:
            return False

    def process_video(self, video_path, reference_image_path, task_config, output_folder, metadata_folder, max_retries=3):
        """Streamlined video processing with reduced redundancy"""
        base_name, ref_stem = video_path.stem, reference_image_path.stem
        start_time = time.time()
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"    🔄 Retry {attempt}/{max_retries-1}")
                    time.sleep(5)
                
                result = self.client.predict(
                    video_path={"video": handle_file(str(video_path))},
                    prompt=task_config['prompt'],
                    model=self.config.get('model', 'gen4_aleph'),
                    ratio=self.config.get('ratio', '1280:720'),
                    reference_image=handle_file(str(reference_image_path)),
                    public_figure_moderation=self.config.get('public_figure_moderation', 'auto'),
                    api_name="/submit_1"
                )
                
                output_url, output_video, error_message = result[:3]
                
                if error_message and error_message.strip():
                    print(f"    ❌ API Error: {error_message}")
                    if attempt == max_retries - 1:
                        self.save_metadata(metadata_folder, base_name, ref_stem, video_path.name, 
                                         reference_image_path.name, {
                            'error': error_message, 'attempts': attempt + 1, 'success': False,
                            'processing_time_seconds': round(time.time() - start_time, 1)
                        }, task_config)
                        return False
                    continue
                
                # Try to save video
                output_path = output_folder / f"{base_name}_ref_{ref_stem}_runway_generated.mp4"
                video_saved = False
                
                # Download from URL or copy local file
                if output_url and output_url.strip():
                    video_saved = self.download_video(output_url, output_path)
                
                if not video_saved and output_video and 'video' in output_video:
                    local_path = Path(output_video['video'])
                    if local_path.exists():
                        shutil.copy2(local_path, output_path)
                        video_saved = True
                
                # Save metadata based on result
                self.save_metadata(metadata_folder, base_name, ref_stem, video_path.name, 
                                 reference_image_path.name, {
                    'output_url': output_url,
                    'generated_video': output_path.name if video_saved else None,
                    'error': None if video_saved else "File save failed",
                    'attempts': attempt + 1,
                    'success': video_saved,
                    'processing_time_seconds': round(time.time() - start_time, 1)
                }, task_config)
                
                if video_saved:
                    print(f"    ✓ Video saved: {output_path.name}")
                    return True
                elif attempt == max_retries - 1:
                    return False
                    
            except Exception as e:
                print(f"    ❌ Exception (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    self.save_metadata(metadata_folder, base_name, ref_stem, video_path.name,
                                     reference_image_path.name, {
                        'error': str(e), 'attempts': attempt + 1, 'success': False,
                        'processing_time_seconds': round(time.time() - start_time, 1)
                    }, task_config)
                    return False
        return False

    def save_metadata(self, metadata_folder, base_name, ref_stem, video_name, ref_name, result_data, task_config):
        """Simplified metadata saving"""
        metadata = {
            "source_video": video_name,
            "reference_image": ref_name,
            "prompt": task_config['prompt'],
            "model": self.config.get('model', 'gen4_aleph'),
            "ratio": self.config.get('ratio', '1280:720'),
            "public_figure_moderation": self.config.get('public_figure_moderation', 'auto'),
            "processing_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            **result_data
        }
        
        metadata_file = metadata_folder / f"{base_name}_ref_{ref_stem}_runway_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        
        status = "✓" if result_data.get('success') else "❌"
        print(f"    {status} Meta {metadata_file.name}")

    def process_task(self, task, task_num, total_tasks):
        """Optimized task processing"""
        folder = Path(task['folder'])
        self.logger.info(f"📁 Task {task_num}/{total_tasks}: {folder.name}")
        
        # Get files
        video_files = [f for f in (folder / "Source").iterdir() if f.suffix.lower() in self.VIDEO_EXTS]
        reference_images = [f for f in (folder / "Reference").iterdir() if f.suffix.lower() in self.IMAGE_EXTS]
        
        output_folder = folder / "Generated_Video"
        metadata_folder = folder / "Metadata"
        
        pairing_strategy = task.get('pairing_strategy', 'one_to_one')
        successful = 0
        
        if pairing_strategy == 'one_to_one':
            pairs = list(zip(video_files, reference_images))
            total = len(pairs)
            
            for i, (video_file, ref_file) in enumerate(pairs, 1):
                self.logger.info(f"  🎬 {i}/{total}: {video_file.name} + {ref_file.name}")
                if self.process_video(video_file, ref_file, task, output_folder, metadata_folder):
                    successful += 1
                if i < total:
                    time.sleep(3)
        else:
            total = len(video_files) * len(reference_images)
            count = 0
            
            for video_file in video_files:
                for ref_file in reference_images:
                    count += 1
                    self.logger.info(f"  🎬 {count}/{total}: {video_file.name} + {ref_file.name}")
                    if self.process_video(video_file, ref_file, task, output_folder, metadata_folder):
                        successful += 1
                    if count < total:
                        time.sleep(3)
        
        self.logger.info(f"✓ Task {task_num}: {successful}/{total if pairing_strategy == 'one_to_one' else total} successful")

    def run(self):
        """Main execution with streamlined flow"""
        self.logger.info("🚀 Starting Runway Batch Video Processor")
        
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
    processor = RunwayBatchVideoProcessor()
    processor.run()

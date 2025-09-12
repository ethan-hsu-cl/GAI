import json, logging, time, requests
from pathlib import Path
from datetime import datetime
from PIL import Image
from gradio_client import Client, handle_file

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class ViduReferenceProcessor:
    SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
    VALID_ASPECT_RATIOS = ["9:16", "16:9", "1:1"]
    
    def __init__(self, config_file="batch_vidu_reference_config.json"):
        self.config_file = config_file
        self.client = None
        self.config = {}
    
    def load_config(self):
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"✓ Loaded config from {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"❌ Config error: {e}")
            return False
    
    def closest_aspect_ratio(self, w, h):
        r = w / h
        return "16:9" if r > 1.2 else "9:16" if r < 0.8 else "1:1"
    
    def find_reference_images(self, d):
        refs = []
        for i in range(2, 8):
            files = [f for f in d.iterdir() if f.suffix.lower() in self.SUPPORTED_EXT and 
                    (f.stem.lower().startswith(f'image{i}') or f.stem.lower().startswith(f'image {i}') or 
                     f.stem.split('_')[0] == str(i) or f.stem.split('.')[0] == str(i))]
            if files: refs.append(files[0])
            else: break
        return refs or sorted([f for f in d.iterdir() if f.suffix.lower() in self.SUPPORTED_EXT])[:6]
    
    def validate_image(self, p):
        try:
            if p.stat().st_size >= 52428800: return False, "Size > 50MB"
            with Image.open(p) as img:
                w, h = img.size
                if w < 128 or h < 128: return False, f"Dims {w}x{h} too small"
                if not (0.25 <= w/h <= 4.0): return False, f"Ratio {w/h:.2f} invalid"
                return True, f"{w}x{h}"
        except Exception as e:
            return False, f"Error: {e}"
    
    def validate_task(self, task):
        fp = Path(task['folder_path'])
        src_dir, ref_dir = fp / 'Source', fp / 'Reference'
        
        if not (src_dir.exists() and ref_dir.exists()):
            return None, [f"{task['effect']}: Missing Source/Reference folders"]
        
        src_imgs = [f for f in src_dir.iterdir() if f.suffix.lower() in self.SUPPORTED_EXT]
        if not src_imgs: return None, [f"{task['effect']}: No source images"]
        
        ref_imgs = self.find_reference_images(ref_dir)
        if not ref_imgs: return None, [f"{task['effect']}: No reference images"]
        
        valid_sets = []
        for src in src_imgs:
            invalids = []
            try:
                with Image.open(src) as img:
                    ar = self.closest_aspect_ratio(img.width, img.height)
                    logger.info(f"  📐 {src.name} ({img.width}x{img.height}) → {ar}")
            except Exception as e:
                invalids.append(f"{src.name}: Cannot read dims - {e}")
                continue
            
            for img in [src] + ref_imgs:
                valid, reason = self.validate_image(img)
                if not valid: invalids.append(f"{img.name}: {reason}")
            
            if not invalids:
                valid_sets.append({
                    'source_image': src, 'reference_images': ref_imgs, 'all_images': [src] + ref_imgs,
                    'aspect_ratio': ar, 'reference_count': len(ref_imgs)
                })
                logger.info(f"  Found {len(ref_imgs)} reference images for {src.name}")
            else:
                logger.warning(f"Invalid images for {src.name}: {'; '.join(invalids)}")
        
        if not valid_sets: return None, [f"{task['effect']}: No valid image sets"]
        
        # Create output directories
        for d in ['Generated_Video', 'Metadata']: (fp / d).mkdir(exist_ok=True)
        
        task.update({'generated_dir': str(fp / 'Generated_Video'), 'metadata_dir': str(fp / 'Metadata'), 'image_sets': valid_sets})
        return task, []
    
    def print_errors(self, errors):
        if errors:
            print(f"\n{'='*60}\nERROR REPORT - {len(errors)} issues:\n{'='*60}")
            for error in errors: print(f"❌ {error}")
            print(f"{'='*60}")
        else:
            print("✅ No validation errors")
    
    def validate_all_tasks(self):
        base = Path(self.config.get('base_folder', ''))
        configured_tasks = {t['effect']: t for t in self.config.get('tasks', [])}
        valid_tasks, errors = [], []
        
        for folder in base.iterdir():
            if folder.is_dir() and not folder.name.startswith(('.', '_')) and (folder / 'Source').exists() and (folder / 'Reference').exists():
                # Get task config or create default
                if folder.name in configured_tasks:
                    task = configured_tasks[folder.name].copy()
                    task['folder_path'] = str(folder)
                    logger.info(f"✓ Matched: {folder.name}")
                else:
                    task = {'effect': folder.name, 'folder_path': str(folder), 'prompt': self.config.get('default_prompt', ''),
                           'model': self.config.get('model', 'default'), 'duration': self.config.get('duration', 5),
                           'resolution': self.config.get('resolution', '1080p'), 'movement': self.config.get('movement', 'auto')}
                    logger.info(f"⚠️ No config match: {folder.name} -> using defaults")
                
                result, task_errors = self.validate_task(task)
                if result: valid_tasks.append(result)
                else: errors.extend(task_errors)
        
        if errors:
            self.print_errors(errors)
            raise Exception(f"{len(errors)} validation errors")
        return valid_tasks
    
    def wait_schedule(self):
        start_time = self.config.get('schedule', {}).get('start_time', '')
        if not start_time: return
        try:
            h, m = map(int, start_time.split(':'))
            now = datetime.now()
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now: target = target.replace(day=target.day + 1)
            wait_secs = (target - now).total_seconds()
            logger.info(f"⏰ Waiting {wait_secs/3600:.1f}h until {target.strftime('%H:%M')}")
            time.sleep(wait_secs)
        except: logger.warning(f"❌ Invalid time format: {start_time}")
    
    def init_client(self):
        try:
            self.client = Client("http://192.168.4.3:8000/video_effect/")
            return True
        except Exception as e:
            logger.error(f"❌ Client init failed: {e}")
            return False
    
    def download_video(self, url, path):
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(16384): f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
    
    def save_metadata(self, meta_dir, src_name, data):
        try:
            with open(Path(meta_dir) / f"{Path(src_name).stem}_metadata.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Metadata save failed: {e}")
            return False
    
    def process_image_set(self, img_set, task, out_dir, meta_dir, retries=3):
        src, all_imgs, ref_count, base_name = img_set['source_image'], img_set['all_images'], img_set['reference_count'], img_set['source_image'].stem
        start_time = time.time()
        
        # Get parameters
        effect = task.get('effect', '')
        prompt = task.get('prompt', '') or self.config.get('default_prompt', '')
        model = task.get('model', self.config.get('model', 'default'))
        duration = task.get('duration', self.config.get('duration', 5))
        aspect_ratio = img_set['aspect_ratio']
        resolution = task.get('resolution', self.config.get('resolution', '1080p'))
        movement = task.get('movement', self.config.get('movement', 'auto'))
        
        for attempt in range(retries):
            if attempt > 0: logger.info(f"    🔄 Retry {attempt}/{retries-1}")
            
            try:
                img_handles = tuple(handle_file(str(img)) for img in all_imgs)
                logger.info(f"    📸 Processing: 1 source + {ref_count} references ({aspect_ratio})")
                
                result = self.client.predict(model=model, prompt=prompt, duration=duration, aspect_ratio=aspect_ratio,
                                            images=img_handles, resolution=resolution, movement=movement, api_name="/reference_api")
                
                if not isinstance(result, tuple) or len(result) < 4:
                    raise ValueError("Invalid API response format")
                
                video_url, thumbnail_url, task_id, error_msg = result
                if error_msg: raise ValueError(f"API error: {error_msg}")
                if not video_url: raise ValueError("No video URL returned")
                
                # Download video
                effect_clean = effect.replace(' ', '_').replace('-', '_')
                out_name = f"{base_name}_{effect_clean}.mp4"
                
                if not self.download_video(video_url, Path(out_dir) / out_name):
                    raise IOError("Video download failed")
                
                # Save success metadata
                proc_time = time.time() - start_time
                metadata = {"source_image": src.name, "reference_images": [i.name for i in img_set['reference_images']],
                           "reference_count": ref_count, "total_images": len(all_imgs), "effect_name": effect,
                           "model": model, "prompt": prompt, "duration": duration, "aspect_ratio": aspect_ratio,
                           "resolution": resolution, "movement": movement, "video_url": video_url,
                           "thumbnail_url": thumbnail_url, "task_id": task_id, "generated_video": out_name,
                           "processing_time_seconds": round(proc_time, 1), "processing_timestamp": datetime.now().isoformat(),
                           "attempts": attempt + 1, "success": True}
                
                self.save_metadata(meta_dir, src.name, metadata)
                return True
                
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                
                # Save failure metadata
                proc_time = time.time() - start_time
                metadata = {"source_image": src.name, "reference_images": [i.name for i in img_set['reference_images']],
                           "reference_count": ref_count, "effect_name": effect, "model": model, "prompt": prompt,
                           "duration": duration, "aspect_ratio": aspect_ratio, "resolution": resolution,
                           "movement": movement, "error_message": str(e), "processing_time_seconds": round(proc_time, 1),
                           "processing_timestamp": datetime.now().isoformat(), "attempts": attempt + 1, "success": False}
                
                self.save_metadata(meta_dir, src.name, metadata)
                return False
        return False
    
    def process_task(self, task, task_num, total):
        effect, gen_dir, meta_dir, img_sets = task.get('effect', ''), task.get('generated_dir', ''), task.get('metadata_dir', ''), task.get('image_sets', [])
        logger.info(f"🎬 Task {task_num}/{total}: {effect}")
        
        successful = 0
        for i, img_set in enumerate(img_sets, 1):
            src_name, ar, ref_count = img_set['source_image'].name, img_set['aspect_ratio'], img_set['reference_count']
            logger.info(f"  🖼️  {i}/{len(img_sets)}: {src_name} ({ar}) + {ref_count} refs")
            
            if self.process_image_set(img_set, task, gen_dir, meta_dir): successful += 1
            if i < len(img_sets): time.sleep(3)
        
        logger.info(f"✓ Task {task_num}: {successful}/{len(img_sets)} successful")
    
    def run(self):
        logger.info("🎬 Starting Vidu Reference Processor")
        
        if not self.load_config(): return False
        
        try: valid_tasks = self.validate_all_tasks()
        except Exception as e:
            logger.error(str(e))
            return False
        
        if not valid_tasks:
            logger.error("❌ No valid tasks found")
            return False
        
        self.wait_schedule()
        if not self.init_client(): return False
        
        start_time = time.time()
        for i, task in enumerate(valid_tasks, 1):
            try:
                self.process_task(task, i, len(valid_tasks))
                if i < len(valid_tasks): time.sleep(10)
            except Exception as e:
                logger.error(f"Task {i} failed: {e}")
        
        elapsed = time.time() - start_time
        logger.info(f"🎉 Completed {len(valid_tasks)} tasks in {elapsed/60:.1f} minutes")
        return True

if __name__ == "__main__":
    processor = ViduReferenceProcessor()
    processor.run()

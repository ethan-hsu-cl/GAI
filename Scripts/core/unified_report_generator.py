import json, logging, sys, re, tempfile, os
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Cm, Inches, Pt
from pptx.enum.text import PP_ALIGN

try:
    import cv2
except ImportError:
    cv2 = None

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

@dataclass
class MediaPair:
    """Universal media pair for all API types"""
    source_file: str
    source_path: Path
    api_type: str

    # Generated content - using same structure as working versions
    generated_paths: List[Path] = field(default_factory=list)
    reference_paths: List[Path] = field(default_factory=list)

    # API-specific fields
    effect_name: str = ""
    category: str = ""
    prompt: str = ""

    # Video-specific (for Runway)
    source_video_path: Optional[Path] = None

    # Metadata
    metadata: Dict = field(default_factory=dict)
    ref_metadata: Dict = field(default_factory=dict)

    # Status
    failed: bool = False
    ref_failed: bool = False

    @property
    def primary_generated(self) -> Optional[Path]:
        """Get the primary generated file"""
        return self.generated_paths[0] if self.generated_paths else None

    @property
    def primary_reference(self) -> Optional[Path]:
        """Get the primary reference file"""
        return self.reference_paths[0] if self.reference_paths else None

class UnifiedReportGenerator:
    """
    COMPLETE WORKING: Unified report generator with all methods implemented
    """

    def __init__(self, api_name: str, config_file: str = None):
        self.api_name = api_name
        self.config_file = config_file or f"config/batch_{api_name}_config.json"
        self.config = {}
        self.report_definitions = {}

        # Caches for performance (from working versions)
        self._ar_cache = {}
        self._frame_cache = {}

        # Load configurations
        self._load_config()
        self._load_report_definitions()

    def _load_config(self):
        """Load API-specific configuration"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"✓ Config loaded: {self.config_file}")
        except Exception as e:
            logger.error(f"❌ Config error: {e}")
            sys.exit(1)

    def _load_report_definitions(self):
        """Load report definitions from api_definitions.json"""
        definition_paths = [
            "core/api_definitions.json",
            "api_definitions.json", 
            "config/api_definitions.json"
        ]

        for def_path in definition_paths:
            try:
                with open(def_path, 'r', encoding='utf-8') as f:
                    all_definitions = json.load(f)
                self.report_definitions = all_definitions.get(self.api_name, {}).get('report', {})
                logger.info(f"✓ API definitions loaded from: {def_path}")
                return
            except Exception:
                continue

        logger.warning(f"⚠️ API definitions not found, using defaults")
        self._set_default_report_definitions()

    def _set_default_report_definitions(self):
        """Set default report definitions"""
        self.report_definitions = {
            "enabled": True,
            "template_path": "templates/I2V templates.pptx",
            "comparison_template_path": "templates/I2V Comparison Template.pptx",
            "output_directory": "/Users/ethanhsu/Desktop/GAI/Report",
            "use_comparison": self.api_name in ["kling", "nano_banana", "runway"]
        }

    # ================== UTILITY FUNCTIONS FROM WORKING VERSIONS ==================

    def get_cmp_filename(self, folder1: str, folder2: str, model: str = '') -> str:
        """Generate comparison filename - EXACT from nano_banana_auto_report.py"""
        m1, m2 = re.match(r'(\d{4})\s+(.+)', Path(folder1).name), re.match(r'(\d{4})\s+(.+)', Path(folder2).name)
        d, s1 = m1.groups() if m1 else (datetime.now().strftime("%m%d"), Path(folder1).name)
        _, s2 = m2.groups() if m2 else ('', Path(folder2).name)
        parts = [f"[{d}]"]
        if model and model.lower() not in s1.lower(): 
            parts.append(model)
        parts.append(f"{s1} vs {s2}")
        return ' '.join(parts)

    def get_filename(self, folder, model=''):
        """Generate filename - EXACT from nano_banana_auto_report.py"""
        m = re.match(r'(\d{4})\s+(.+)', Path(folder).name)
        d, s = m.groups() if m else (datetime.now().strftime("%m%d"), Path(folder).name)
        parts = [f"[{d}]"]
        if model and model.lower() not in s.lower(): 
            parts.append(model)
        parts.append(s)
        return ' '.join(parts)

    def calc_pos(self, path: Path, x: float, y: float, w: float, h: float) -> tuple:
        """Calculate positioned media - EXACT from nano_banana_auto_report.py"""
        try:
            with Image.open(path) as img: 
                ar = img.width/img.height
            bw, bh = Cm(w), Cm(h)
            sw, sh = (bw, bw/ar) if ar>bw/bh else (bh*ar, bh)
            return Cm(x)+(bw-sw)/2, Cm(y)+(bh-sh)/2, sw, sh
        except: 
            return Cm(x+0.5), Cm(y+0.5), Cm(w-1), Cm(h-1)

    def find_matching_video(self, base_name: str, video_files: dict) -> Optional[Path]:
        """Enhanced video matching for all APIs"""
        if base_name in video_files:
            return video_files[base_name]
        for vname, vpath in video_files.items():
            if vname.startswith(base_name + '_'):
                return vpath
        return None

    def get_aspect_ratio(self, path, is_video=False):
        """Aspect ratio calculation - EXACT from runway_auto_report.py"""
        fn = path.name.lower()
        if '9_16' in fn or 'portrait' in fn: return 9/16
        if '1_1' in fn or 'square' in fn: return 1
        if '16_9' in fn or 'landscape' in fn: return 16/9
        key = str(path)
        if key in self._ar_cache: return self._ar_cache[key]
        try:
            if is_video and cv2:
                cap = cv2.VideoCapture(str(path))
                if cap.isOpened():
                    w, h = cap.get(3), cap.get(4)
                    cap.release()
                    if w > 0 and h > 0:
                        self._ar_cache[key] = w/h
                        return w/h
            else:
                with Image.open(path) as img:
                    ar = img.width / img.height
                    self._ar_cache[key] = ar
                    return ar
        except: pass
        return 16/9

    def extract_first_frame(self, video_path):
        """Extract first frame - EXACT from runway_auto_report.py"""
        if not cv2:
            return None
        video_key = str(video_path)
        if video_key in self._frame_cache:
            return self._frame_cache[video_key]
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return None
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return None
            # Create temporary file for the frame
            temp_dir = tempfile.gettempdir()
            frame_filename = f"frame_{video_path.stem}_{hash(video_key) % 10000}.jpg"
            frame_path = Path(temp_dir) / frame_filename
            # Save frame as JPEG
            cv2.imwrite(str(frame_path), frame)
            # Cache the result
            self._frame_cache[video_key] = str(frame_path)
            return str(frame_path)
        except Exception as e:
            logger.warning(f"Failed to extract frame from {video_path}: {e}")
            return None

    # ================== FILE PROCESSING METHODS ==================

    def normalize_key(self, name: str) -> str:
        """Universal key normalization - EXACT from vidu_auto_report.py"""
        key = name.lower().replace(' ', '_')
        key = re.sub(r'[^a-z0-9_]', '', key)
        key = re.sub(r'_(effect|generated|output|result)$', '', key)
        return key.strip('_')

    def process_batch(self, task: Dict) -> List[MediaPair]:
        """Universal batch processing for all API types"""
        if self.api_name in ["vidu_effects", "vidu_reference"]:
            return self._process_base_folder_structure(task)
        elif self.api_name == "genvideo":
            return self._process_genvideo_batch(task)
        else:
            return self._process_task_folder_structure(task)

    def _process_task_folder_structure(self, task: Dict) -> List[MediaPair]:
        """Process APIs with individual task folders"""
        folder = Path(task['folder'])
        ref_folder = Path(task.get('reference_folder', '')) if task.get('reference_folder') else None
        use_comparison = task.get('use_comparison_template', False)

        if self.api_name == "runway":
            return self._create_runway_media_pairs(folder, ref_folder, task, use_comparison)
        else:
            return self._create_standard_media_pairs(folder, ref_folder, task, use_comparison)

    def _create_standard_media_pairs(self, folder: Path, ref_folder: Optional[Path], 
                                   task: Dict, use_comparison: bool) -> List[MediaPair]:
        """Create standard media pairs for Kling/Nano Banana"""
        pairs = []

        # Define folder structure
        if self.api_name == "nano_banana":
            folders = {
                'source': folder / 'Source',
                'generated': folder / 'Generated_Output',
                'metadata': folder / 'Metadata'
            }
            file_pattern = '_image_'  # From nano_banana_auto_report.py
        else:  # kling
            folders = {
                'source': folder / 'Source',
                'generated': folder / 'Generated_Video', 
                'metadata': folder / 'Metadata'
            }
            file_pattern = '_generated'  # From unified_api_processor.py

        if not folders['source'].exists():
            return pairs

        # Get source files - EXACT from nano_banana_auto_report.py
        exts = {'.jpg', '.jpeg', '.png', '.webp'}
        src = {f.stem: f for f in folders['source'].iterdir() if f.suffix.lower() in exts}

        # Get generated files - EXACT pattern matching
        out = {}
        if folders['generated'].exists():
            for f in folders['generated'].iterdir():
                if f.suffix.lower() in (exts | {'.mp4', '.mov', '.avi'}) and file_pattern in f.name:
                    if self.api_name == "nano_banana":
                        # nano_banana: file_image_1.jpg -> file
                        base_name = f.name.split(file_pattern)[0]
                        out.setdefault(base_name, []).append(f)
                    else:
                        # kling: file_generated.mp4 -> file  
                        base_name = f.stem.replace(file_pattern, '')
                        out[base_name] = f

        # Get metadata - EXACT from nano_banana_auto_report.py
        metadata_files = {}
        if folders['metadata'].exists():
            for f in folders['metadata'].iterdir():
                if f.suffix.lower() == '.json':
                    key = f.stem.replace('_metadata', '')
                    metadata_files[key] = f

        # Reference files for comparison
        ref_files = {}
        if use_comparison and ref_folder:
            ref_generated_folder = ref_folder / ('Generated_Output' if self.api_name == "nano_banana" else 'Generated_Video')
            if ref_generated_folder.exists():
                for f in ref_generated_folder.iterdir():
                    if f.suffix.lower() in (exts | {'.mp4', '.mov', '.avi'}) and file_pattern in f.name:
                        if self.api_name == "nano_banana":
                            base_name = f.name.split(file_pattern)[0]
                            ref_files.setdefault(base_name, []).append(f)
                        else:
                            base_name = f.stem.replace(file_pattern, '')
                            ref_files[base_name] = f

        # Create pairs - EXACT from nano_banana_auto_report.py
        for b in sorted(src.keys()):
            md = {}
            md_file = metadata_files.get(b)
            if md_file and md_file.exists():
                try: 
                    with open(md_file, 'r', encoding='utf-8') as f:
                        md = json.load(f)
                except: 
                    pass

            gen_paths = out.get(b, []) if self.api_name == "nano_banana" else ([out[b]] if b in out else [])
            ref_paths = ref_files.get(b, []) if use_comparison else []

            # Ensure lists for consistency
            if not isinstance(gen_paths, list):
                gen_paths = [gen_paths] if gen_paths else []
            if not isinstance(ref_paths, list):
                ref_paths = [ref_paths] if ref_paths else []

            pair = MediaPair(
                source_file=src[b].name,
                source_path=src[b],
                api_type=self.api_name,
                generated_paths=gen_paths,
                reference_paths=ref_paths,
                metadata=md,
                failed=not gen_paths or not md.get('success', False),
                ref_failed=use_comparison and (not ref_paths)
            )
            pairs.append(pair)

        return pairs

    def _create_runway_media_pairs(self, folder: Path, ref_folder: Optional[Path],
                                 task: Dict, use_comparison: bool) -> List[MediaPair]:
        """FIXED: Create Runway media pairs - handles both reference-based and non-reference tasks"""
        folders = {k: folder/v for k,v in {'reference':'Reference','source':'Source','generated':'Generated_Video','metadata':'Metadata'}.items()}
        ref_folders = {k: ref_folder/v for k,v in {'video':'Generated_Video','metadata':'Metadata'}.items()} if ref_folder and use_comparison else {}

        if not folders['metadata'].exists():
            logger.warning(f"❌ Metadata folder not found: {folders['metadata']}")
            return []

        def load_files(folder, exts):
            return {f.stem: f for f in folder.iterdir() if f.suffix.lower() in exts} if folder and folder.exists() else {}

        reference_images = load_files(folders['reference'], {'.jpg','.jpeg','.png','.webp'})
        source_videos = load_files(folders['source'], {'.mp4','.mov'})
        generated_videos = load_files(folders['generated'], {'.mp4','.mov'})
        metadata_files = load_files(folders['metadata'], {'.json'})
        ref_videos = load_files(ref_folders.get('video', Path()), {'.mp4','.mov'})
        ref_metadata = load_files(ref_folders.get('metadata', Path()), {'.json'})

        logger.info(f"🔍 Runway files found: {len(reference_images)} refs, {len(source_videos)} sources, {len(generated_videos)} generated, {len(metadata_files)} metadata")

        def load_meta(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}

        pairs = []
        for stem, meta_path in metadata_files.items():
            md = load_meta(meta_path)
            if not md:
                continue

            # FIXED: Find matching files using metadata references
            ref_img_path = next((p for p in reference_images.values() if p.name == md.get('reference_image','')), None)
            src_vid_path = next((p for p in source_videos.values() if p.name == md.get('source_video','')), None)
            gen_vid_path = next((p for p in generated_videos.values() if p.name == md.get('generated_video','')), None)

            # FIXED: Create pair based on available content
            source_file = None
            source_path = None

            if ref_img_path:
                # Face swap task - use reference image as source
                source_file = ref_img_path.name
                source_path = ref_img_path
                logger.info(f"✓ Face Swap task - using reference image: {source_file}")
            elif src_vid_path:
                # Background removal or other task - use source video as source
                source_file = src_vid_path.name
                source_path = src_vid_path
                src_vid_path = None  # Don't duplicate in source_video_path
                logger.info(f"✓ Background Removal task - using source video: {source_file}")
            else:
                # No valid source found, skip this pair
                logger.warning(f"⚠️ No valid source found for metadata: {stem}")
                continue

            # Handle reference videos for comparison
            ref_vid_path, ref_md = None, {}
            if use_comparison:
                rbase = stem.replace('_runway_metadata', '')
                ref_vid_path = self.find_matching_video(rbase, ref_videos)
                if rbase in ref_metadata:
                    ref_md = load_meta(ref_metadata[rbase])

            pair = MediaPair(
                source_file=source_file,
                source_path=source_path,
                api_type=self.api_name,
                generated_paths=[gen_vid_path] if gen_vid_path else [],
                reference_paths=[ref_vid_path] if ref_vid_path else [],
                source_video_path=src_vid_path,
                metadata=md,
                ref_metadata=ref_md,
                failed=not gen_vid_path or not md.get('success', False),
                ref_failed=use_comparison and (not ref_vid_path or not ref_md.get('success', False))
            )
            pairs.append(pair)

        logger.info(f"✅ Created {len(pairs)} Runway media pairs")
        return pairs

    def _process_base_folder_structure(self, task: Dict) -> List[MediaPair]:
        """FIXED: Process base folder structure for vidu APIs - EXACT from working versions"""
        base_folder = Path(self.config.get('base_folder', ''))
        if not base_folder.exists():
            logger.warning(f"❌ Base folder not found: {base_folder}")
            return []

        logger.info(f"🔍 Processing Vidu base folder: {base_folder}")

        pairs = []

        if self.api_name == "vidu_effects":
            # EXACT from vidu_auto_report.py
            for task_config in self.config.get('tasks', []):
                effect, category = task_config.get('effect', ''), task_config.get('category', 'Unknown')
                if not effect:
                    continue

                folders = {k: base_folder / effect / v for k, v in
                          {'src': 'Source', 'vid': 'Generated_Video', 'meta': 'Metadata'}.items()}

                if not folders['src'].exists():
                    logger.warning(f"⚠️ Source folder not found for effect: {effect}")
                    continue

                logger.info(f"Processing Vidu effect: {effect}")

                # Get normalized file mappings - EXACT from vidu_auto_report.py
                images = {self.normalize_key(f.stem): f for f in folders['src'].iterdir()
                         if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}}

                videos = {}
                if folders['vid'].exists():
                    for f in folders['vid'].iterdir():
                        if f.suffix.lower() in {'.mp4', '.mov', '.avi'}:
                            key = self.extract_video_key(f.name, effect)
                            videos[key] = f

                logger.info(f"📊 Images: {len(images)}, Videos: {len(videos)}")

                # Create pairs - EXACT from vidu_auto_report.py
                for key, img in images.items():
                    meta_file = folders['meta'] / f"{img.stem}_metadata.json"
                    metadata = {}
                    if meta_file.exists():
                        try:
                            with open(meta_file, 'r') as f:
                                metadata = json.load(f)
                        except:
                            pass

                    vid = videos.get(key)

                    pair = MediaPair(
                        source_file=img.name,
                        source_path=img,
                        api_type=self.api_name,
                        generated_paths=[vid] if vid else [],
                        reference_paths=[],
                        effect_name=effect,
                        category=category,
                        metadata=metadata,
                        failed=not vid or not metadata.get('success', False)
                    )
                    pairs.append(pair)

        elif self.api_name == "vidu_reference":
            # EXACT from vidu_reference_auto_report.py
            try:
                # Try to discover folders automatically
                effect_names = sorted(f.name for f in base_folder.iterdir()
                                     if f.is_dir() and not f.name.startswith(('.', '_'))
                                     and (f / 'Source').exists())
                logger.info(f"🔍 Discovered {len(effect_names)} effect folders")
            except:
                # Fall back to configured tasks
                effect_names = [t.get('effect', '') for t in self.config.get('tasks', [])]
                logger.info(f"📋 Using {len(effect_names)} configured tasks")

            for effect in effect_names:
                if not effect:
                    continue

                folders = {k: base_folder / effect / v for k, v in
                          {'src': 'Source', 'vid': 'Generated_Video', 'meta': 'Metadata'}.items()}

                if not folders['src'].exists():
                    logger.warning(f"⚠️ Source folder not found for effect: {effect}")
                    continue

                logger.info(f"Processing Vidu Reference: {effect}")

                # Get images and videos - EXACT from vidu_reference_auto_report.py
                images = {self.normalize_key(f.stem): f for f in folders['src'].iterdir()
                         if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}}

                videos = {}
                if folders['vid'].exists():
                    for f in folders['vid'].iterdir():
                        if f.suffix.lower() in {'.mp4', '.mov', '.avi'}:
                            videos[self.extract_key_reference(f.name, effect)] = f

                logger.info(f"📊 Images: {len(images)}, Videos: {len(videos)}")

                # Create pairs - EXACT from vidu_reference_auto_report.py
                for key, img in images.items():
                    meta_file = folders['meta'] / f"{img.stem}_metadata.json"
                    metadata = {}
                    if meta_file.exists():
                        try:
                            with open(meta_file, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                        except:
                            pass

                    vid = videos.get(key)

                    pair = MediaPair(
                        source_file=img.name,
                        source_path=img,
                        api_type=self.api_name,
                        generated_paths=[vid] if vid else [],
                        reference_paths=[],
                        effect_name=effect,
                        category="Reference",
                        metadata=metadata,
                        failed=not vid or not metadata.get('success', False)
                    )
                    pairs.append(pair)

        logger.info(f"✅ Created {len(pairs)} Vidu media pairs")
        return pairs

    def extract_video_key(self, filename: str, effect_name: str) -> str:
        """Extract video key - EXACT from vidu_auto_report.py"""
        stem = Path(filename).stem
        effect_clean = effect_name.lower().replace(' ', '_')
        pattern = re.escape(effect_clean) + r'_effect$'
        key = re.sub(pattern, '', stem, flags=re.IGNORECASE)

        for pattern in [r'_effect$', r'_generated$', r'_output$', r'_result$']:
            key = re.sub(pattern, '', key, flags=re.IGNORECASE)

        return self.normalize_key(key)

    def extract_key_reference(self, filename: str, effect: str) -> str:
        """Extract key for reference - EXACT from vidu_reference_auto_report.py"""
        stem = Path(filename).stem
        effect_clean = self.normalize_key(effect)

        if stem.lower().endswith(f'_{effect_clean}'):
            key = stem[:-len(f'_{effect_clean}')]
        else:
            for suffix in ['_reference', '_generated', '_output', '_result']:
                if stem.lower().endswith(suffix):
                    key = stem[:-len(suffix)]
                    break
            else:
                key = stem

        return self.normalize_key(key)

    # ================== PRESENTATION CREATION ==================

    def create_presentation(self, pairs: List[MediaPair], task: Dict) -> bool:
        """Create presentation using API-specific working patterns"""
        if not pairs:
            logger.warning("No media pairs to process")
            return False

        # Determine template and comparison mode
        use_comparison = task.get('use_comparison_template', False)
        template_key = 'comparison_template_path' if use_comparison else 'template_path'
        template_path = (self.config.get(template_key) or 
                        self.report_definitions.get(template_key,
                        'templates/I2V Comparison Template.pptx' if use_comparison else 'templates/I2V templates.pptx'))

        # Load template
        try:
            ppt = Presentation(template_path) if Path(template_path).exists() else Presentation()
            template_loaded = Path(template_path).exists()
            logger.info(f"✓ Template loaded: {template_path}")
        except Exception as e:
            logger.warning(f"⚠️ Template load failed: {e}, using blank presentation")
            ppt = Presentation()
            template_loaded = False

        # Set slide dimensions
        ppt.slide_width, ppt.slide_height = Cm(33.87), Cm(19.05)

        # Create title slide
        self._create_title_slide(ppt, task, use_comparison)

        # Add content slides using API-specific methods
        if self.api_name == "runway":
            self._create_runway_slides(ppt, pairs, template_loaded, use_comparison)
        elif self.api_name == "nano_banana":
            self._create_nano_banana_slides(ppt, pairs, template_loaded, use_comparison)
        elif self.api_name in ["vidu_effects", "vidu_reference"]:
            self._create_vidu_slides(ppt, pairs, template_loaded)
        elif self.api_name == "genvideo":
            self._create_genvideo_slides(ppt, pairs, template_loaded, use_comparison)
        else:  # kling and others
            self._create_standard_slides(ppt, pairs, template_loaded, use_comparison)

        # Save presentation
        return self._save_presentation(ppt, task, use_comparison)

    def _create_title_slide(self, ppt: Presentation, task: Dict, use_comparison: bool):
        """Create title slide - using working patterns"""
        if not ppt.slides:
            return

        # Get folder names for title generation
        if self.api_name in ["vidu_effects", "vidu_reference"]:
            folder_name = Path(self.config.get('base_folder', '')).name
        else:
            folder_name = task.get('folder', Path(self.config.get('base_folder', '')).name)
            if isinstance(folder_name, str):
                folder_name = Path(folder_name).name

        api_display_names = {
            'kling': 'Kling 2.1',
            'nano_banana': 'Nano Banana',
            'runway': 'Runway',
            'vidu_effects': 'Vidu Effects',
            'vidu_reference': 'Vidu Reference',
            'genvideo': 'GenVideo'
        }

        api_display = api_display_names.get(self.api_name, self.api_name.title())

        # Generate title using working patterns
        if use_comparison and task.get('reference_folder'):
            ref_name = Path(task['reference_folder']).name
            title = self.get_cmp_filename(folder_name, ref_name, api_display)
        else:
            title = self.get_filename(folder_name, api_display)

        # Update title slide
        if ppt.slides and ppt.slides[0].shapes:
            if self.api_name == "runway":
                # Runway-specific title formatting
                slide = ppt.slides[0]
                for s in [s for s in slide.shapes if hasattr(s,'text_frame') and (not s.text_frame.text or "Results" in s.text_frame.text or any(k in s.text_frame.text for k in ["Runway","vs","["]))]:
                    slide.shapes._spTree.remove(s._element)

                if use_comparison and task.get('reference_folder'):
                    m = re.match(r'(?:\[(\d{4})\]|(\d{4}))?\s*(.*)', folder_name.strip())
                    d, s1 = (m.group(1) or m.group(2), m.group(3).strip()) if m else (datetime.now().strftime("%m%d"), folder_name.strip())
                    m2 = re.match(r'(?:\[(\d{4})\]|(\d{4}))?\s*(.*)', Path(task['reference_folder']).name.strip())
                    _, s2 = (m2.group(1) or m2.group(2), m2.group(3).strip()) if m2 else ('', Path(task['reference_folder']).name.strip())

                    tb = slide.shapes.add_textbox(Cm(5), Cm(2), Cm(24), Cm(8))
                    tf = tb.text_frame
                    p1, p2 = tf.paragraphs[0], tf.add_paragraph()
                    p1.text, p2.text = f"[{d}] Runway", f"{s1} vs {s2}"
                    for p, size in [(p1, 60), (p2, 40)]:
                        p.font.size, p.font.bold, p.alignment = Pt(size), True, PP_ALIGN.CENTER
                else:
                    m = re.match(r'(?:\[(\d{4})\]|(\d{4}))?\s*(.*)', folder_name.strip())
                    d, s = (m.group(1) or m.group(2), m.group(3).strip()) if m else (datetime.now().strftime("%m%d"), folder_name.strip())
                    tb = slide.shapes.add_textbox(Cm(5), Cm(3), Cm(24), Cm(8))
                    tf = tb.text_frame
                    p1, p2 = tf.paragraphs[0], tf.add_paragraph()
                    p1.text, p2.text = f"[{d}] Runway", s
                    for p, size in [(p1, 60), (p2, 40)]:
                        p.font.size, p.font.bold, p.alignment = Pt(size), True, PP_ALIGN.CENTER
            elif self.api_name in ["vidu_effects", "vidu_reference"]:
                # Vidu-specific title formatting - EXACT from working versions
                match = re.match(r'(\d{4})\s+(.+)', folder_name)
                date, project = match.groups() if match else (datetime.now().strftime("%m%d"), folder_name)
                title_text = f"[{date}] {api_display}\n{project}"
                ppt.slides[0].shapes[0].text_frame.text = title_text
            else:
                # Standard title update
                ppt.slides[0].shapes[0].text_frame.text = title

        # FIXED: Add links for all APIs including Vidu
        self._add_links_working_pattern(ppt, task)

    def _add_links_working_pattern(self, ppt: Presentation, task: Dict):
        """FIXED: Add hyperlinks for ALL APIs including Vidu with correct config links"""
        if not ppt.slides:
            return

        slide = ppt.slides[0]

        if self.api_name == "runway":
            # Use runway-specific link pattern
            info_box = next((s for s in slide.shapes if hasattr(s,'text_frame') and s.text_frame.text and any(k in s.text_frame.text.lower() for k in ['design','testbed','source'])), None)
            if not info_box: 
                info_box = slide.shapes.add_textbox(Cm(5), Cm(13), Cm(20), Cm(4))
            info_box.text_frame.clear()

            links = [
                ("Design: ", "Link", task.get('design_link','')), 
                ("Testbed: ", self.config.get('testbed','http://192.168.4.3:8000/runway/'), self.config.get('testbed','http://192.168.4.3:8000/runway/')), 
                ("Source + Video: ", "Link", task.get('source_video_link',''))
            ]

            for i, (pre, txt, url) in enumerate(links):
                para = info_box.text_frame.paragraphs[0] if i == 0 else info_box.text_frame.add_paragraph()
                if url:
                    para.clear()
                    r1, r2 = para.add_run(), para.add_run()
                    r1.text, r1.font.size = pre, Inches(24/72)
                    r2.text, r2.font.size = url if "Testbed:" in pre else txt, Inches(24/72)
                    r2.hyperlink.address = url
                    para.alignment = PP_ALIGN.CENTER
                else:
                    para.text, para.font.size, para.alignment = f"{pre}{txt}", Inches(24/72), PP_ALIGN.CENTER

        elif self.api_name in ["vidu_effects", "vidu_reference"]:
            # FIXED: Add Vidu-specific link pattern with testbed link included
            info_box = next((s for s in slide.shapes if hasattr(s,'text_frame') and s.text_frame.text and any(k in s.text_frame.text.lower() for k in ['design','testbed','source'])), None)
            if not info_box: 
                info_box = slide.shapes.add_textbox(Cm(5), Cm(13), Cm(20), Cm(4))
            info_box.text_frame.clear()
            
            # Use the links from the Vidu config files + add testbed
            design_link = self.config.get('design_link', 'https://platform.vidu.com/docs/templates')
            testbed_url = self.config.get('testbed', f'http://192.168.4.3:8000/video_effect/')  # ADD THIS
            source_link = self.config.get('source_video_link', '')
            
            links = [
                ("Design: ", "Link", design_link),
                ("Testbed: ", testbed_url, testbed_url),  # ADD THIS LINE
                ("Source + Video: ", "Link", source_link)
            ]

            for i, (pre, txt, url) in enumerate(links):
                para = info_box.text_frame.paragraphs[0] if i == 0 else info_box.text_frame.add_paragraph()
                if url:
                    para.clear()
                    r1, r2 = para.add_run(), para.add_run()
                    r1.text, r1.font.size = pre, Inches(24/72)
                    r2.text, r2.font.size = txt, Inches(24/72)
                    r2.hyperlink.address = url
                    para.alignment = PP_ALIGN.CENTER
                else:
                    para.text, para.font.size, para.alignment = f"{pre}{txt}", Inches(24/72), PP_ALIGN.CENTER
        else:
            # Use nano_banana/standard link pattern
            info_box = next((s for s in slide.shapes if hasattr(s, 'text_frame') and s.text_frame.text and any(x in s.text_frame.text.lower() for x in ['design','testbed','source'])), None)
            if not info_box: 
                info_box = slide.shapes.add_textbox(Cm(5), Cm(13), Cm(20), Cm(4))
            info_box.text_frame.clear()

            testbed_url = self.config.get('testbed', f'http://192.168.4.3:8000/{self.api_name}/')
            lines = ["Design: Link", f"Testbed: {testbed_url}", "Source + Video: Link"]

            for i, line in enumerate(lines):
                p = info_box.text_frame.paragraphs[0] if i==0 else info_box.text_frame.add_paragraph()
                p.text, p.font.size, p.alignment = line, Inches(24/72), PP_ALIGN.CENTER

                if "Design:" in line and task.get('design_link'):
                    self._add_hyperlink(p, "Design: ", "Link", task['design_link'])
                elif "Testbed:" in line:
                    self._add_hyperlink(p, "Testbed: ", testbed_url, testbed_url)
                elif "Source + Video:" in line and task.get('source_video_link'):
                    self._add_hyperlink(p, "Source + Video: ", "Link", task['source_video_link'])

    def _add_hyperlink(self, para, pre, link_text, url):
        """Simple hyperlink creation - EXACT from nano_banana_auto_report.py"""
        para.clear()
        r1 = para.add_run()
        r1.text, r1.font.size = pre, Inches(24/72)
        r2 = para.add_run()
        r2.text, r2.font.size = link_text, Inches(24/72)
        r2.hyperlink.address = url
        para.alignment = PP_ALIGN.CENTER

    # ================ RUNWAY SLIDES =================
    def _create_runway_slides(self, ppt, pairs, template_loaded, use_comparison):
        for i, pair in enumerate(pairs, 1):
            self._create_runway_slide(ppt, pair, i, template_loaded, use_comparison)

    def _create_runway_slide(self, ppt, pair, num, loaded, use_cmp=False):
        """FIXED: Create single Runway slide - handles both image and video sources"""
        if loaded and len(ppt.slides) >= 4:
            slide = ppt.slides.add_slide(ppt.slides[3].slide_layout)
            for p in slide.placeholders:
                if p.placeholder_format.type == 1:
                    title = f"Generation {num}: {pair.source_file}" + (" ❌ FAILED" if pair.failed else "") + (" (REF ❌)" if use_cmp and pair.ref_failed else "")
                    p.text = title
                    if (pair.failed or (use_cmp and pair.ref_failed)) and p.text_frame.paragraphs:
                        p.text_frame.paragraphs[0].font.color.rgb = RGBColor(255,0,0)
                    break

            phs = sorted([p for p in slide.placeholders if p.placeholder_format.type in {6,7,8,13,18,19}], key=lambda x: getattr(x,'left',0))
            if len(phs) >= 3:
                # FIXED: Handle different source types
                self._add_media_to_slide_runway(slide, phs[0], str(pair.source_path), 
                                               pair.source_path.suffix.lower() in {'.mp4', '.mov', '.avi'})
                self._add_media_to_slide_runway(slide, phs[1], str(pair.source_video_path) if pair.source_video_path and pair.source_video_path.exists() else None, True, None, "Source video not found")
                self._add_media_to_slide_runway(slide, phs[2], str(pair.primary_generated) if pair.primary_generated and pair.primary_generated.exists() else None, True, None, pair.metadata.get('error','Generation failed') if pair.metadata else 'Generation failed')
            elif len(phs) >= 2:
                # FIXED: Handle different source types
                self._add_media_to_slide_runway(slide, phs[0], str(pair.source_path),
                                               pair.source_path.suffix.lower() in {'.mp4', '.mov', '.avi'})
                self._add_media_to_slide_runway(slide, phs[1], str(pair.primary_generated) if pair.primary_generated and pair.primary_generated.exists() else None, True, None, pair.metadata.get('error','Generation failed') if pair.metadata else 'Generation failed')

            self._add_runway_metadata(slide, pair, use_cmp, len(phs) >= 3)
        else:
            # Manual slide creation - EXACT from runway_auto_report.py but with video source support
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            title = f"Generation {num}: {pair.source_file}" + (" ❌ FAILED" if pair.failed else "") + (" (REF ❌)" if use_cmp and pair.ref_failed else "")
            tb = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(20), Cm(2))
            tb.text_frame.text = title
            tb.text_frame.paragraphs[0].font.size = Inches(20/72)
            if pair.failed or (use_cmp and pair.ref_failed):
                tb.text_frame.paragraphs[0].font.color.rgb = RGBColor(255,0,0)

            pos = [(2.59,3.26), (13,3.26), (23.41,3.26)]
            w, h = 10, 10

            # FIXED: Add source (could be image or video)
            if pair.source_path.suffix.lower() in {'.mp4', '.mov', '.avi'}:
                # Source is video
                try:
                    first_frame = self.extract_first_frame(pair.source_path)
                    if first_frame and Path(first_frame).exists():
                        slide.shapes.add_movie(str(pair.source_path), Cm(pos[0][0]), Cm(pos[0][1]), Cm(w), Cm(h), poster_frame_image=first_frame)
                    else:
                        slide.shapes.add_movie(str(pair.source_path), Cm(pos[0][0]), Cm(pos[0][1]), Cm(w), Cm(h))
                except:
                    slide.shapes.add_movie(str(pair.source_path), Cm(pos[0][0]), Cm(pos[0][1]), Cm(w), Cm(h))
            else:
                # Source is image
                slide.shapes.add_picture(str(pair.source_path), Cm(pos[0][0]), Cm(pos[0][1]), Cm(w), Cm(h))

            # Add additional videos (source video if exists, generated video)
            video_items = []
            if pair.source_video_path:
                video_items.append((pair.source_video_path, "Additional source video not found"))
            video_items.append((pair.primary_generated, pair.metadata.get('error','Generation failed') if pair.metadata else 'Generation failed'))

            for i, (vid_path, err_msg) in enumerate(video_items, 1):
                if i >= len(pos):  # Don't exceed available positions
                    break

                if vid_path and vid_path.exists():
                    try:
                        first_frame = self.extract_first_frame(vid_path)
                        if first_frame and Path(first_frame).exists():
                            slide.shapes.add_movie(str(vid_path), Cm(pos[i][0]), Cm(pos[i][1]), Cm(w), Cm(h), poster_frame_image=first_frame)
                        else:
                            slide.shapes.add_movie(str(vid_path), Cm(pos[i][0]), Cm(pos[i][1]), Cm(w), Cm(h))
                    except:
                        slide.shapes.add_movie(str(vid_path), Cm(pos[i][0]), Cm(pos[i][1]), Cm(w), Cm(h))
                else:
                    self._add_error_box(slide, Cm(pos[i][0]), Cm(pos[i][1]), Cm(w), Cm(h), err_msg)

            self._add_runway_metadata(slide, pair, use_cmp, True)

    def _add_media_to_slide_runway(self, slide, ph, media=None, is_video=False, poster=None, error=None):
        """Add media to slide - EXACT from runway_auto_report.py"""
        l, t, w, h = ph.left, ph.top, ph.width, ph.height
        ph._element.getparent().remove(ph._element)

        if media and Path(media).exists():
            try:
                ar = self.get_aspect_ratio(Path(media), is_video)
                sw, sh = (w, w/ar) if ar > w/h else (h*ar, h)
                fl, ft = l+(w-sw)/2, t+(h-sh)/2

                if is_video:
                    # Extract first frame from video to use as poster
                    first_frame_path = self.extract_first_frame(Path(media))
                    if first_frame_path and Path(first_frame_path).exists():
                        slide.shapes.add_movie(media, fl, ft, sw, sh, poster_frame_image=first_frame_path)
                    else:
                        slide.shapes.add_movie(media, fl, ft, sw, sh)
                else:
                    slide.shapes.add_picture(media, fl, ft, sw, sh)
            except Exception as e:
                self._add_error_box(slide, l, t, w, h, f"Failed to load media: {e}")
        else:
            self._add_error_box(slide, l, t, w, h, error or "Media file not found")

    def _add_runway_metadata(self, slide, pair, use_cmp, is_three_col):
        """Add Runway metadata - EXACT from runway_auto_report.py"""
        meta = [f"{k}: {pair.metadata.get(k,'N/A') if k != 'success' else ('✓' if pair.metadata.get(k) else '❌')}" for k in ['prompt','reference_image','source_video','model','processing_time_seconds','success']] if pair.metadata else ["No metadata available"]
        if pair.metadata and len(meta) > 1 and 'processing_time_seconds' in meta[-2]: 
            meta[-2] = meta[-2].replace('processing_time_seconds', 'processing_time_seconds') + 's'
        if use_cmp and pair.ref_metadata: 
            meta.append(f"Ref Time: {pair.ref_metadata.get('processing_time_seconds','N/A')}s")

        pos = (2.32, 15.24) if is_three_col else (5.19, 15.99)
        box = slide.shapes.add_textbox(Cm(pos[0]), Cm(pos[1]), Cm(7.29), Cm(3.06))
        box.text_frame.text = "\n".join(meta)
        for p in box.text_frame.paragraphs: 
            p.font.size = Inches(10/72)

    # ================ NANO BANANA SLIDES =================
    def _create_nano_banana_slides(self, ppt, pairs, template_loaded, use_comparison):
        for pair in pairs:
            self._create_nano_banana_slide(ppt, pair, template_loaded, use_comparison)

    def _create_nano_banana_slide(self, ppt, pair, loaded, use_cmp):
        """Create single Nano Banana slide - EXACT from nano_banana_auto_report.py"""
        if loaded and len(ppt.slides)>=4:
            slide=ppt.slides.add_slide(ppt.slides[3].slide_layout)
            for p in slide.placeholders:
                if p.placeholder_format.type==1:
                    p.text="❌ GENERATION FAILED" if pair.failed else ""
                    if pair.failed and p.text_frame.paragraphs: 
                        p.text_frame.paragraphs[0].font.color.rgb=RGBColor(255,0,0)
                    break

            phs=sorted([p for p in slide.placeholders if p.placeholder_format.type in {6,7,8,13,18,19}], key=lambda x:getattr(x,'left',0))
            if use_cmp and len(phs)>=3:
                self._add_media_nano(slide, phs[0], str(pair.source_path))
                self._add_media_nano(slide, phs[1], str(pair.primary_generated) if pair.primary_generated else None, "No images generated")
                self._add_media_nano(slide, phs[2], str(pair.primary_reference) if pair.primary_reference else None, "No reference images")
            elif len(phs)>=2:
                self._add_media_nano(slide, phs[0], str(pair.source_path))
                self._add_media_nano(slide, phs[1], str(pair.primary_generated) if pair.primary_generated else None, "No images generated")
        else:
            # Manual positioning - EXACT from nano_banana_auto_report.py
            slide=ppt.slides.add_slide(ppt.slide_layouts[6])
            if pair.failed:
                tb=slide.shapes.add_textbox(Cm(2),Cm(1),Cm(20),Cm(2))
                tb.text_frame.text,tb.text_frame.paragraphs[0].font.size,tb.text_frame.paragraphs[0].font.color.rgb= "❌ GENERATION FAILED",Inches(18/72),RGBColor(255,0,0)

            # Use exact positioning from nano_banana_auto_report.py
            pos = {'source': (2.59,3.26,12.5,12.5), 'generated': (18.78,3.26,12.5,12.5), 'reference': (35,3.26,12.5,12.5)}

            slide.shapes.add_picture(str(pair.source_path), *self.calc_pos(pair.source_path, *pos['source']))
            if pair.primary_generated:
                slide.shapes.add_picture(str(pair.primary_generated), *self.calc_pos(pair.primary_generated, *pos['generated']))
            else: 
                self._add_err_nano(slide, pos['generated'], "No images generated")

            if use_cmp:
                if pair.primary_reference:
                    slide.shapes.add_picture(str(pair.primary_reference), *self.calc_pos(pair.primary_reference, *pos['reference']))
                else: 
                    self._add_err_nano(slide, pos['reference'], "No reference images")

            # Add metadata - EXACT from nano_banana_auto_report.py
            mb=slide.shapes.add_textbox(Cm(5),Cm(16),Cm(12),Cm(3))
            mb.text_frame.text=f"File Name: {pair.source_file}\nResponse ID: {pair.metadata.get('response_id','N/A') if pair.metadata else 'N/A'}\nTime: {pair.metadata.get('processing_time_seconds','N/A') if pair.metadata else 'N/A'}s"
            for p in mb.text_frame.paragraphs: 
                p.font.size=Inches(10/72)
        
        self._add_nano_banana_metadata(slide, pair)

    def _add_nano_banana_metadata(self, slide, pair):
        """FIXED: Add Nano Banana metadata - EXACT from working version"""
        mb = slide.shapes.add_textbox(Cm(5), Cm(16), Cm(12), Cm(3))
        
        response_id = pair.metadata.get('response_id', 'N/A') if pair.metadata else 'N/A'
        proc_time = pair.metadata.get('processing_time_seconds', 'N/A') if pair.metadata else 'N/A'
        
        mb.text_frame.text = f"File Name: {pair.source_file}\nResponse ID: {response_id}\nTime: {proc_time}s"
        
        for p in mb.text_frame.paragraphs: 
            p.font.size = Inches(10/72)

    def _add_media_nano(self, slide, ph, media=None, error=None):
        """Add media to nano banana slide - EXACT from nano_banana_auto_report.py"""
        l, t, w, h = ph.left, ph.top, ph.width, ph.height
        ph._element.getparent().remove(ph._element)

        if media:
            try:
                with Image.open(media) as img: 
                    ar = img.width/img.height
                sw, sh = (w, w/ar) if ar>w/h else (h*ar, h)
                slide.shapes.add_picture(str(media), l+(w-sw)/2, t+(h-sh)/2, sw, sh)
            except: 
                slide.shapes.add_picture(str(media), l+w*0.1, t+h*0.1, w*0.8, h*0.8)
        else:
            box = slide.shapes.add_textbox(l, t, w, h)
            box.text_frame.text = f"❌ GENERATION FAILED\n\n{error}"
            for p in box.text_frame.paragraphs:
                p.font.size, p.alignment, p.font.color.rgb = Inches(16/72), PP_ALIGN.CENTER, RGBColor(255,0,0)
            box.fill.solid()
            box.fill.fore_color.rgb, box.line.color.rgb, box.line.width = RGBColor(255,240,240), RGBColor(255,0,0), Inches(0.02)

    def _add_err_nano(self, slide, pos, msg):
        """Add error box for nano banana - EXACT from nano_banana_auto_report.py"""
        box = slide.shapes.add_textbox(Cm(pos[0]), Cm(pos[1]), Cm(pos[2]), Cm(pos[3]))
        box.text_frame.text = f"❌ FAILED\n\n{msg}"
        for p in box.text_frame.paragraphs:
            p.font.size, p.alignment, p.font.color.rgb = Inches(14/72), PP_ALIGN.CENTER, RGBColor(255,0,0)
        box.fill.solid()
        box.fill.fore_color.rgb, box.line.color.rgb = RGBColor(255,240,240), RGBColor(255,0,0)

    # ================ VIDU SLIDES =================
    def _create_vidu_slides(self, ppt, pairs, template_loaded):
        # for i, pair in enumerate(pairs, 1):
        #     self._create_vidu_slide(ppt, pair, i, template_loaded)

                # Group pairs by effect_name (style)
        effects_groups = {}
        for pair in pairs:
            effect_name = pair.effect_name
            if effect_name not in effects_groups:
                effects_groups[effect_name] = []
            effects_groups[effect_name].append(pair)
        
        # Process each effect group with section divider
        slide_index = 1
        for effect_name in sorted(effects_groups.keys()):
            effect_pairs = effects_groups[effect_name]
            
            # ADD SECTION DIVIDER SLIDE BEFORE EACH STYLE
            self._create_section_divider_slide(ppt, effect_name, template_loaded)
            
            # Create slides for this effect
            for pair in effect_pairs:
                self._create_vidu_slide(ppt, pair, slide_index, template_loaded)
                slide_index += 1
    
    def _create_section_divider_slide(self, ppt, style_name, template_loaded):
        """Create a section divider slide with the style name as title"""
        try:
            # Try to use "Title and Content" layout (usually index 1)
            if template_loaded and len(ppt.slide_layouts) > 1:
                slide = ppt.slides.add_slide(ppt.slide_layouts[1])  # Title and Content layout
            else:
                # Fallback to blank layout
                slide = ppt.slides.add_slide(ppt.slide_layouts[6] if len(ppt.slide_layouts) > 6 else ppt.slide_layouts[0])
            
            # Set title
            title_text = style_name.title().replace('_', ' ')
            
            # Find title placeholder
            title_placeholder = None
            for placeholder in slide.placeholders:
                if placeholder.placeholder_format.type == 1:  # Title placeholder
                    title_placeholder = placeholder
                    break
            
            if title_placeholder:
                # Use title placeholder
                title_placeholder.text = title_text
                # Style the title
                if title_placeholder.text_frame.paragraphs:
                    para = title_placeholder.text_frame.paragraphs[0]
                    para.font.size = Pt(44)
                    para.font.bold = True
                    para.alignment = PP_ALIGN.CENTER
            else:
                # Manual title creation if no placeholder found
                title_box = slide.shapes.add_textbox(Cm(2), Cm(2), Cm(30), Cm(4))
                title_box.text_frame.text = title_text
                para = title_box.text_frame.paragraphs[0]
                para.font.size = Pt(44)
                para.font.bold = True
                para.alignment = PP_ALIGN.CENTER
                
            logger.info(f"✅ Added section divider for style: {title_text}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to create section divider slide for {style_name}: {e}")
            # Create simple fallback slide
            slide = ppt.slides.add_slide(ppt.slide_layouts[0])
            title_box = slide.shapes.add_textbox(Cm(5), Cm(8), Cm(24), Cm(4))
            title_box.text_frame.text = style_name.title().replace('_', ' ')
            para = title_box.text_frame.paragraphs[0]
            para.font.size = Pt(40)
            para.font.bold = True
            para.alignment = PP_ALIGN.CENTER


    def _create_vidu_slide(self, ppt, pair, idx, loaded):
        """Create single Vidu slide - EXACT from working versions"""
        # Try template first
        if loaded and len(ppt.slides) >= 4:
            slide = ppt.slides.add_slide(ppt.slides[3].slide_layout)

            # Update title
            for p in slide.placeholders:
                if p.placeholder_format.type == 1:
                    if self.api_name == "vidu_effects":
                        title = f"Effect {idx}: {pair.effect_name} - {pair.source_file}"
                    else:  # vidu_reference
                        ref_count = pair.metadata.get('reference_count', 0) if pair.metadata else 0
                        title = f"{pair.effect_name} #{idx}: {pair.source_file} (+{ref_count} refs)"

                    if pair.failed:
                        title += " ❌ FAILED"
                    p.text = title
                    if pair.failed and p.text_frame.paragraphs:
                        p.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
                    break

            # Handle content placeholders
            content_placeholders = [p for p in slide.placeholders if p.placeholder_format.type in {6, 7, 8, 13, 18, 19}]
            content_placeholders.sort(key=lambda x: x.left if hasattr(x, 'left') else 0)

            if len(content_placeholders) >= 2:
                self._add_media_vidu(slide, content_placeholders[0], str(pair.source_path), False)
                if pair.primary_generated and pair.primary_generated.exists():
                    self._add_media_vidu(slide, content_placeholders[1], str(pair.primary_generated), True)
                else:
                    error_msg = pair.metadata.get('error_message', 'Effect failed') if pair.metadata else 'No processing'
                    self._add_error_vidu(slide, content_placeholders[1], error_msg)
        else:
            # Manual slide creation
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])

            # Title
            if self.api_name == "vidu_effects":
                title = f"Effect {idx}: {pair.effect_name} - {pair.source_file}"
            else:  # vidu_reference
                ref_count = pair.metadata.get('reference_count', 0) if pair.metadata else 0
                title = f"{pair.effect_name} #{idx}: {pair.source_file} (+{ref_count} refs)"

            if pair.failed:
                title += " ❌ FAILED"

            title_box = slide.shapes.add_textbox(Cm(1), Cm(0.5), Cm(30), Cm(2))
            title_box.text_frame.text = title
            title_box.text_frame.paragraphs[0].font.size = Inches(18/72)
            if pair.failed:
                title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)

            # Manual positioning with aspect ratio
            positions = {'img': (2.59, 3.26, 12.5, 12.5), 'vid': (18.78, 3.26, 12.5, 12.5)}

            img_x, img_y, img_w, img_h = self.calc_pos(pair.source_path, *positions['img'])
            slide.shapes.add_picture(str(pair.source_path), img_x, img_y, img_w, img_h)

            if pair.primary_generated and pair.primary_generated.exists():
                vid_x, vid_y, vid_w, vid_h = self.calc_pos(pair.primary_generated, *positions['vid'])
                try:
                    first_frame = self.extract_first_frame(pair.primary_generated)
                    if first_frame and Path(first_frame).exists():
                        slide.shapes.add_movie(str(pair.primary_generated), vid_x, vid_y, vid_w, vid_h, poster_frame_image=first_frame)
                    else:
                        slide.shapes.add_movie(str(pair.primary_generated), vid_x, vid_y, vid_w, vid_h)
                except:
                    slide.shapes.add_movie(str(pair.primary_generated), vid_x, vid_y, vid_w, vid_h)
            else:
                pos = positions['vid']
                error_box = slide.shapes.add_textbox(Cm(pos[0]), Cm(pos[1]), Cm(pos[2]), Cm(pos[3]))
                error_msg = pair.metadata.get('error_message', 'Effect failed') if pair.metadata else 'No processing'
                error_box.text_frame.text = f"❌ {'EFFECT' if self.api_name == 'vidu_effects' else 'REFERENCE'} FAILED\n\n{error_msg}"

                for p in error_box.text_frame.paragraphs:
                    p.font.size, p.alignment, p.font.color.rgb = Inches(14/72), PP_ALIGN.CENTER, RGBColor(255, 0, 0)
                error_box.fill.solid()
                error_box.fill.fore_color.rgb, error_box.line.color.rgb = RGBColor(255, 240, 240), RGBColor(255, 0, 0)

            # Add metadata - EXACT from working versions
            processing_time = pair.metadata.get('processing_time_seconds', 'N/A') if pair.metadata else 'N/A'
            status = 'FAILED' if pair.failed else 'SUCCESS'

            if self.api_name == "vidu_effects":
                meta_text = f"{pair.source_file}\n{pair.category} | {pair.effect_name}\n{processing_time}s \\ {status}"
                meta_box = slide.shapes.add_textbox(Cm(2), Cm(16.5), Cm(8), Cm(2))
            else:  # vidu_reference
                ref_count = pair.metadata.get('reference_count', 0) if pair.metadata else 0
                aspect_ratio = pair.metadata.get('detected_aspect_ratio', 'N/A') if pair.metadata else 'N/A'
                meta_text = f"{pair.source_file}\n{pair.effect_name} | +{ref_count} refs\n{aspect_ratio} | {processing_time}s\n{status}"
                meta_box = slide.shapes.add_textbox(Cm(2), Cm(16.5), Cm(10), Cm(2.5))

            meta_box.text_frame.text = meta_text
            meta_box.text_frame.word_wrap = True
            for p in meta_box.text_frame.paragraphs:
                p.font.size, p.alignment = Inches(9/72), PP_ALIGN.LEFT

    def _add_media_vidu(self, slide, placeholder, media_path, is_video=False):
        """Add media to Vidu slide - EXACT from working versions"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        aspect_ratio = self.get_aspect_ratio(Path(media_path), is_video)

        # Calculate size maintaining aspect ratio
        if aspect_ratio > p_width / p_height:
            scaled_w, scaled_h = p_width, p_width / aspect_ratio
        else:
            scaled_h, scaled_w = p_height, p_height * aspect_ratio

        # Center media
        final_left = p_left + (p_width - scaled_w) / 2
        final_top = p_top + (p_height - scaled_h) / 2

        # Remove placeholder and add media
        placeholder._element.getparent().remove(placeholder._element)

        try:
            if is_video:
                first_frame_path = self.extract_first_frame(Path(media_path))
                if first_frame_path and Path(first_frame_path).exists():
                    slide.shapes.add_movie(str(media_path), final_left, final_top, scaled_w, scaled_h, poster_frame_image=first_frame_path)
                else:
                    slide.shapes.add_movie(str(media_path), final_left, final_top, scaled_w, scaled_h)
            else:
                slide.shapes.add_picture(str(media_path), final_left, final_top, scaled_w, scaled_h)
        except:
            if is_video:
                slide.shapes.add_movie(str(media_path), final_left, final_top, scaled_w, scaled_h)
            else:
                slide.shapes.add_picture(str(media_path), final_left, final_top, scaled_w, scaled_h)

    def _add_error_vidu(self, slide, placeholder, error_msg):
        """Add error to Vidu slide - EXACT from working versions"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        placeholder._element.getparent().remove(placeholder._element)

        error_box = slide.shapes.add_textbox(p_left, p_top, p_width, p_height)
        error_name = 'EFFECT' if self.api_name == 'vidu_effects' else 'REFERENCE'
        error_box.text_frame.text = f"❌ {error_name} FAILED\n\n{error_msg}"

        for p in error_box.text_frame.paragraphs:
            p.font.size, p.alignment, p.font.color.rgb = Inches(16/72), PP_ALIGN.CENTER, RGBColor(255, 0, 0)

        error_box.fill.solid()
        error_box.fill.fore_color.rgb, error_box.line.color.rgb = RGBColor(255, 240, 240), RGBColor(255, 0, 0)
        error_box.line.width = Inches(0.02)

    # ================ STANDARD SLIDES (KLING) =================
    def _create_standard_slides(self, ppt, pairs, template_loaded, use_comparison):
        for i, pair in enumerate(pairs, 1):
            self._create_standard_slide(ppt, pair, i, template_loaded, use_comparison)

    def _create_standard_slide(self, ppt, pair, index, template_loaded, use_comparison):
        """COMPLETE: Create standard slide for Kling with proper placeholder handling and aspect ratios"""
        if template_loaded and len(ppt.slides) >= 4:
            # Use template with placeholders - EXACT pattern from other working APIs
            slide = ppt.slides.add_slide(ppt.slides[3].slide_layout)
            
            # Update title placeholder ONLY (don't add extra text boxes)
            for p in slide.placeholders:
                if p.placeholder_format.type == 1:
                    title = f"Generation {index}: {pair.source_file}"
                    if pair.failed:
                        title += " ❌ FAILED"
                    p.text = title
                    if pair.failed and p.text_frame.paragraphs:
                        p.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
                    break
            
            # Handle media placeholders with proper aspect ratio
            phs = sorted([p for p in slide.placeholders if p.placeholder_format.type in {6,7,8,13,18,19}], 
                        key=lambda x: getattr(x,'left',0))
            
            if len(phs) >= 2:
                # Source image in first placeholder
                self._add_media_standard(slide, phs[0], str(pair.source_path), False)
                
                # Generated content in second placeholder
                if pair.primary_generated and pair.primary_generated.exists():
                    is_video = pair.primary_generated.suffix.lower() in {'.mp4', '.mov', '.avi'}
                    self._add_media_standard(slide, phs[1], str(pair.primary_generated), is_video)
                else:
                    self._add_error_standard(slide, phs[1], "Generation failed")
            
            # Add metadata
            self._add_kling_metadata(slide, pair)
        
        else:
            # Manual slide creation with proper aspect ratios
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            
            # Title - only if failed (no extra text boxes)
            if pair.failed:
                title_box = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(28), Cm(2))
                title_box.text_frame.text = f"Generation {index}: {pair.source_file} ❌ FAILED"
                title_box.text_frame.paragraphs[0].font.size = Inches(18/72)
                title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
            
            # Media positioning using calc_pos for PROPER aspect ratio
            positions = [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)]
            
            # Source & Generated content with proper aspect ratios
            if pair.source_path.exists():
                x, y, w, h = self.calc_pos(pair.source_path, *positions[0])
                slide.shapes.add_picture(str(pair.source_path), x, y, w, h)
            
            if pair.primary_generated and pair.primary_generated.exists():
                x, y, w, h = self.calc_pos(pair.primary_generated, *positions[1])
                if pair.primary_generated.suffix.lower() in {'.mp4', '.mov', '.avi'}:
                    first_frame = self.extract_first_frame(pair.primary_generated)
                    if first_frame and Path(first_frame).exists():
                        slide.shapes.add_movie(str(pair.primary_generated), x, y, w, h, poster_frame_image=first_frame)
                    else:
                        slide.shapes.add_movie(str(pair.primary_generated), x, y, w, h)
                else:
                    slide.shapes.add_picture(str(pair.primary_generated), x, y, w, h)
            else:
                self._add_error_box(slide, Cm(positions[1][0]), Cm(positions[1][1]), 
                                Cm(positions[1][2]), Cm(positions[1][3]), "Generation failed")
            
            # Add metadata
            self._add_kling_metadata(slide, pair)

    def _add_media_standard(self, slide, placeholder, media_path, is_video=False):
        """Add media to placeholder with proper aspect ratio"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        placeholder._element.getparent().remove(placeholder._element)
        
        try:
            aspect_ratio = self.get_aspect_ratio(Path(media_path), is_video)
            if aspect_ratio > p_width / p_height:
                scaled_w, scaled_h = p_width, p_width / aspect_ratio
            else:
                scaled_h, scaled_w = p_height, p_height * aspect_ratio
            
            final_left = p_left + (p_width - scaled_w) / 2
            final_top = p_top + (p_height - scaled_h) / 2
            
            if is_video:
                first_frame_path = self.extract_first_frame(Path(media_path))
                if first_frame_path and Path(first_frame_path).exists():
                    slide.shapes.add_movie(str(media_path), final_left, final_top, scaled_w, scaled_h, poster_frame_image=first_frame_path)
                else:
                    slide.shapes.add_movie(str(media_path), final_left, final_top, scaled_w, scaled_h)
            else:
                slide.shapes.add_picture(str(media_path), final_left, final_top, scaled_w, scaled_h)
        except Exception as e:
            logger.warning(f"Failed to add media with aspect ratio, using fallback: {e}")
            if is_video:
                slide.shapes.add_movie(str(media_path), p_left + p_width*0.1, p_top + p_height*0.1, 
                                    p_width*0.8, p_height*0.8)
            else:
                slide.shapes.add_picture(str(media_path), p_left + p_width*0.1, p_top + p_height*0.1, 
                                    p_width*0.8, p_height*0.8)

    def _add_error_standard(self, slide, placeholder, error_msg):
        """Add error to placeholder"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        placeholder._element.getparent().remove(placeholder._element)
        
        error_box = slide.shapes.add_textbox(p_left, p_top, p_width, p_height)
        error_box.text_frame.text = f"❌ GENERATION FAILED\n\n{error_msg}"
        
        for p in error_box.text_frame.paragraphs:
            p.font.size, p.alignment, p.font.color.rgb = Inches(16/72), PP_ALIGN.CENTER, RGBColor(255, 0, 0)
        
        error_box.fill.solid()
        error_box.fill.fore_color.rgb = RGBColor(255, 240, 240)
        error_box.line.color.rgb = RGBColor(255, 0, 0)
        error_box.line.width = Inches(0.02)

    def _add_kling_metadata(self, slide, pair):
        """Add Kling metadata"""
        meta_lines = []
        if pair.metadata:
            task_id = pair.metadata.get('task_id', 'N/A')
            proc_time = pair.metadata.get('processing_time_seconds', 'N/A')
            success = '✓' if pair.metadata.get('success', False) else '❌'
            prompt = pair.metadata.get('prompt', 'N/A')
            model = pair.metadata.get('model', 'N/A')
            
            meta_lines = [
                f"Task: {task_id}",
                f"Model: {model}",
                f"Prompt: {prompt[:50]}..." if len(str(prompt)) > 50 else f"Prompt: {prompt}",
                f"Time: {proc_time}s",
                f"Status: {success}"
            ]
        else:
            meta_lines = ["No metadata available"]
        
        meta_box = slide.shapes.add_textbox(Cm(2), Cm(16), Cm(15), Cm(3))
        meta_box.text_frame.text = "\n".join(meta_lines)
        meta_box.text_frame.word_wrap = True
        for para in meta_box.text_frame.paragraphs:
            para.font.size = Inches(10/72)

    # ================== GENVIDEO SLIDES ==================
    def _process_genvideo_batch(self, task: Dict) -> List[MediaPair]:
        """Process GenVideo batch - collect source images and generated images with metadata"""
        folder = Path(task['folder'])
        source_folder = folder / "Source"
        generated_folder = folder / "Generated_Image"
        metadata_folder = folder / "Metadata"
        
        pairs = []
        
        if not source_folder.exists():
            logger.warning(f"❌ Source folder not found: {source_folder}")
            return pairs
            
        if not generated_folder.exists():
            logger.warning(f"❌ Generated folder not found: {generated_folder}")
            return pairs
        
        # Get source images
        source_images = [f for f in source_folder.iterdir() 
                        if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']]
        source_images.sort()
        
        logger.info(f"🔍 Found {len(source_images)} source images in {source_folder}")
        
        # Process each source image
        for src_img in source_images:
            base_name = src_img.stem
            
            # Find corresponding generated image
            gen_img = generated_folder / f"{base_name}_generated.png"
            
            # ✅ FIXED: Try multiple metadata file patterns
            metadata_patterns = [
                f"{base_name}_{src_img.name}_metadata.json",  # Original pattern
                f"{base_name}_metadata.json",                 # Simplified pattern
                f"{src_img.stem}_metadata.json"               # Alternative pattern
            ]
            
            metadata = {}
            meta_file = None
            
            # Try each pattern until we find the file
            for pattern in metadata_patterns:
                potential_file = metadata_folder / pattern
                if potential_file.exists():
                    meta_file = potential_file
                    logger.info(f"✓ Found metadata: {pattern}")
                    break
            
            # Load metadata if found
            if meta_file:
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    logger.info(f"✓ Loaded metadata for {src_img.name}: {list(metadata.keys())}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load metadata {meta_file}: {e}")
            else:
                logger.warning(f"⚠️ No metadata file found for {src_img.name} (tried: {metadata_patterns})")
            
            # Create media pair
            pair = MediaPair(
                source_file=src_img.name,
                source_path=src_img,
                api_type='genvideo',
                generated_paths=[gen_img] if gen_img.exists() else [],
                reference_paths=[],
                metadata=metadata,
                failed=not gen_img.exists() or not metadata.get('success', False)
            )
            pairs.append(pair)
            
            if pair.failed:
                logger.warning(f"⚠️ Failed pair: {src_img.name}")
            else:
                logger.info(f"✓ Valid pair: {src_img.name} → {gen_img.name}")
        
        logger.info(f"✅ Created {len(pairs)} GenVideo media pairs")
        return pairs


    def _create_genvideo_slides(self, ppt, pairs, template_loaded, use_comparison):
        """Create GenVideo slides with before/after image comparisons"""
        for i, pair in enumerate(pairs, 1):
            self._create_genvideo_slide(ppt, pair, i, template_loaded, use_comparison)

    def _create_genvideo_slide(self, ppt, pair, index, template_loaded, use_comparison):
        """Create single GenVideo slide with source and generated images"""
        if template_loaded and len(ppt.slides) >= 4:
            # Use template with placeholders
            slide = ppt.slides.add_slide(ppt.slides[3].slide_layout)
            
            # Update title
            for p in slide.placeholders:
                if p.placeholder_format.type == 1:
                    title = f"GenVideo {index}: {pair.source_file}"
                    if pair.failed:
                        title += " ❌ FAILED"
                    p.text = title
                    if pair.failed and p.text_frame.paragraphs:
                        p.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
                    break
            
            # Handle content placeholders
            phs = sorted([p for p in slide.placeholders if p.placeholder_format.type in {6,7,8,13,18,19}], 
                        key=lambda x: getattr(x,'left',0))
            
            if len(phs) >= 2:
                # Source image in first placeholder
                self._add_media_genvideo(slide, phs[0], str(pair.source_path))
                
                # Generated image in second placeholder
                if pair.primary_generated and pair.primary_generated.exists():
                    self._add_media_genvideo(slide, phs[1], str(pair.primary_generated))
                else:
                    error_msg = pair.metadata.get('error', 'Generation failed') if pair.metadata else 'No image generated'
                    self._add_error_genvideo(slide, phs[1], error_msg)
        
        else:
            # Manual slide creation
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            
            # Title
            title = f"GenVideo {index}: {pair.source_file}"
            if pair.failed:
                title += " ❌ FAILED"
                title_box = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(28), Cm(2))
                title_box.text_frame.text = title
                title_box.text_frame.paragraphs[0].font.size = Inches(18/72)
                title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
            
            # Manual positioning - source and generated side by side
            positions = [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)]
            
            # Source image (left)
            if pair.source_path.exists():
                x, y, w, h = self.calc_pos(pair.source_path, *positions[0])
                slide.shapes.add_picture(str(pair.source_path), x, y, w, h)
                
                # Add "Original" label
                label_box = slide.shapes.add_textbox(Cm(positions[0][0]), Cm(positions[0][1] - 0.5), Cm(positions[0][2]), Cm(0.8))
                label_box.text_frame.text = "Original Image"
                label_box.text_frame.paragraphs[0].font.size = Inches(12/72)
                label_box.text_frame.paragraphs[0].font.bold = True
                label_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            
            # Generated image (right)
            if pair.primary_generated and pair.primary_generated.exists():
                x, y, w, h = self.calc_pos(pair.primary_generated, *positions[1])
                slide.shapes.add_picture(str(pair.primary_generated), x, y, w, h)
                
                # Add "Generated" label
                label_box = slide.shapes.add_textbox(Cm(positions[1][0]), Cm(positions[1][1] - 0.5), Cm(positions[1][2]), Cm(0.8))
                label_box.text_frame.text = "Generated Image"
                label_box.text_frame.paragraphs[0].font.size = Inches(12/72)
                label_box.text_frame.paragraphs[0].font.bold = True
                label_box.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            else:
                # Error box for failed generation
                error_msg = pair.metadata.get('error', 'Generation failed') if pair.metadata else 'No image generated'
                self._add_error_box(slide, Cm(positions[1][0]), Cm(positions[1][1]), 
                                Cm(positions[1][2]), Cm(positions[1][3]), error_msg)
        
        # Add metadata
        self._add_genvideo_metadata(slide, pair)

    def _add_media_genvideo(self, slide, placeholder, media_path):
        """Add media to GenVideo slide with proper aspect ratio"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        placeholder._element.getparent().remove(placeholder._element)
        
        try:
            # Calculate proper aspect ratio
            with Image.open(media_path) as img:
                ar = img.width / img.height
            
            if ar > p_width / p_height:
                scaled_w, scaled_h = p_width, p_width / ar
            else:
                scaled_h, scaled_w = p_height, p_height * ar
            
            final_left = p_left + (p_width - scaled_w) / 2
            final_top = p_top + (p_height - scaled_h) / 2
            
            slide.shapes.add_picture(str(media_path), final_left, final_top, scaled_w, scaled_h)
        except Exception as e:
            logger.warning(f"Failed to add media with aspect ratio: {e}")
            slide.shapes.add_picture(str(media_path), p_left + p_width*0.1, p_top + p_height*0.1, 
                                    p_width*0.8, p_height*0.8)

    def _add_error_genvideo(self, slide, placeholder, error_msg):
        """Add error to GenVideo slide"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        placeholder._element.getparent().remove(placeholder._element)
        
        error_box = slide.shapes.add_textbox(p_left, p_top, p_width, p_height)
        error_box.text_frame.text = f"❌ GENERATION FAILED\n\n{error_msg}"
        
        for p in error_box.text_frame.paragraphs:
            p.font.size, p.alignment, p.font.color.rgb = Inches(16/72), PP_ALIGN.CENTER, RGBColor(255, 0, 0)
        
        error_box.fill.solid()
        error_box.fill.fore_color.rgb = RGBColor(255, 240, 240)
        error_box.line.color.rgb = RGBColor(255, 0, 0)
        error_box.line.width = Inches(0.02)

    def _add_genvideo_metadata(self, slide, pair):
        """Add GenVideo metadata information"""
        meta_lines = []
        if pair.metadata:
            model = pair.metadata.get('model', 'N/A')
            quality = pair.metadata.get('quality', 'N/A')
            proc_time = pair.metadata.get('processing_time_seconds', 'N/A')
            success = '✓' if pair.metadata.get('success', False) else '❌'
            prompt = pair.metadata.get('img_prompt', 'N/A')
            
            meta_lines = [
                f"File: {pair.source_file}",
                f"Model: {model} | Quality: {quality}",
                f"Processing Time: {proc_time}s",
                f"Status: {success}",
                f"Prompt: {prompt[:60]}..." if len(str(prompt)) > 60 else f"Prompt: {prompt}"
            ]
        else:
            meta_lines = [f"File: {pair.source_file}", "No metadata available"]
        
        meta_box = slide.shapes.add_textbox(Cm(2), Cm(16), Cm(28), Cm(3))
        meta_box.text_frame.text = "\n".join(meta_lines)
        meta_box.text_frame.word_wrap = True
        for para in meta_box.text_frame.paragraphs:
            para.font.size = Inches(10/72)

            
    # ================== ERROR HANDLING ==================

    def _add_error_box(self, slide, left, top, width, height, message: str):
        """Add error box with proper styling"""
        box = slide.shapes.add_textbox(left, top, width, height)
        box.text_frame.text = f"❌ GENERATION FAILED\n\n{message}"

        for para in box.text_frame.paragraphs:
            para.font.size = Inches(16/72)
            para.alignment = PP_ALIGN.CENTER
            para.font.color.rgb = RGBColor(255, 0, 0)

        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(255, 240, 240)
        box.line.color.rgb = RGBColor(255, 0, 0)
        box.line.width = Inches(0.02)

    # ================== SAVE AND CLEANUP ==================

    def _save_presentation(self, ppt, task, use_comparison):
        """Save the presentation"""
        try:
            # Generate filename
            if self.api_name in ["vidu_effects", "vidu_reference"]:
                folder_name = Path(self.config.get('base_folder', '')).name
            else:
                folder_name = task.get('folder', Path(self.config.get('base_folder', '')).name)
                if isinstance(folder_name, str):
                    folder_name = Path(folder_name).name

            api_display_names = {
                'kling': 'Kling 2.1',
                'nano_banana': 'Nano Banana',
                'runway': 'Runway',
                'vidu_effects': 'Vidu Effects',
                'vidu_reference': 'Vidu Reference'
            }
            api_display = api_display_names.get(self.api_name, self.api_name.title())

            if use_comparison and task.get('reference_folder'):
                ref_name = Path(task['reference_folder']).name
                filename = self.get_cmp_filename(folder_name, ref_name, api_display)
            else:
                filename = self.get_filename(folder_name, api_display)

            # Get output directory
            output_dir = Path(self.config.get('output_directory',
                            self.config.get('output', {}).get('directory',
                            self.report_definitions.get('output_directory', './'))))

            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = output_dir / f"{filename}.pptx"

            # Save
            ppt.save(str(output_path))
            logger.info(f"✅ Saved: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ Save failed: {e}")
            return False

    def _cleanup_temp_frames(self):
        """Clean up temporary frame files"""
        for frame_path in self._frame_cache.values():
            try:
                if Path(frame_path).exists():
                    os.unlink(frame_path)
            except Exception:
                pass
        self._frame_cache.clear()

    def run(self) -> bool:
        """Main execution"""
        logger.info(f"🎬 Starting {self.api_name.title()} Report Generator")

        try:
            # Process tasks
            if self.api_name in ["vidu_effects", "vidu_reference"]:
                # Base folder structure - single task
                pairs = self.process_batch({})
                if pairs:
                    success = self.create_presentation(pairs, {})
                    logger.info(f"✓ Generated report with {len(pairs)} items")
                    return success
                else:
                    logger.warning("No media pairs found")
                    return False
            else:
                # Task folder structure - multiple tasks
                tasks = self.config.get('tasks', [])
                if not tasks:
                    logger.warning("No tasks found in configuration")
                    return False

                successful = 0
                for i, task in enumerate(tasks, 1):
                    logger.info(f"📁 Task {i}/{len(tasks)}: {Path(task['folder']).name}")
                    pairs = self.process_batch(task)

                    if pairs:
                        if self.create_presentation(pairs, task):
                            successful += 1
                        else:
                            logger.error(f"❌ Task {i} presentation failed")
                    else:
                        logger.warning(f"⚠️ Task {i} has no media pairs")

                logger.info(f"🎉 Generated {successful}/{len(tasks)} presentations")
                return successful > 0

        except Exception as e:
            logger.error(f"❌ Report generation failed: {e}")
            return False
        finally:
            self._cleanup_temp_frames()

def create_report_generator(api_name, config_file=None):
    """Factory function to create report generator"""
    supported_apis = ['kling', 'nano_banana', 'vidu_effects', 'vidu_reference', 'runway', 'genvideo']  # ← ADD 'genvideo'
    
    if api_name not in supported_apis:
        raise ValueError(f"Unsupported API: {api_name}. Supported: {supported_apis}")
    
    return UnifiedReportGenerator(api_name, config_file)

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate PowerPoint reports from API processing results')
    parser.add_argument('api_name', choices=['kling', 'nano_banana', 'vidu_effects', 'vidu_reference', 'runway'],
                       help='API type to generate report for')
    parser.add_argument('--config', '-c', help='Config file path (optional)')

    args = parser.parse_args()

    generator = create_report_generator(args.api_name, args.config)
    sys.exit(0 if generator.run() else 1)

if __name__ == "__main__":
    main()

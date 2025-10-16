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

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    # Fallback progress tracker
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total or (len(iterable) if iterable else 0)
            self.desc = desc
            self.n = 0
        
        def __iter__(self):
            for item in self.iterable:
                yield item
                self.update()
        
        def update(self, n=1):
            self.n += n
            if self.total and self.n % max(1, self.total // 10) == 0:
                logger.info(f"{self.desc}: {self.n}/{self.total} ({100*self.n//self.total}%)")
        
        def close(self):
            pass

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

@dataclass
class MediaPair:
    """Universal media pair for all API types"""
    source_file: str
    source_path: Path
    api_type: str
    
    # Generated content
    generated_paths: List[Path] = field(default_factory=list)
    reference_paths: List[Path] = field(default_factory=list)
    
    # API-specific fields
    effect_name: str = ""
    category: str = ""
    prompt: str = ""
    
    # Video-specific (for Runway)
    source_video_path: Optional[Path] = None
    
    # Multi-image support (for Nano Banana dual-image mode)
    additional_source_paths: List[Path] = field(default_factory=list)
    
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
    Unified Report Generator - Single implementation for all APIs
    No old methods included - completely unified approach
    """
    
    def __init__(self, api_name: str, config_file: str = None):
        self.api_name = api_name
        self.config_file = config_file or f"config/batch_{api_name}_config.json"
        self.config = {}
        self.report_definitions = {}
        
        # Caches for performance
        self._ar_cache = {}
        self._frame_cache = {}
        self._tempfiles_to_cleanup = []  # Track temporary files from format conversions
        self._normalize_cache = {}  # Cache for normalize_key operations
        self._extract_key_cache = {}  # Cache for video key extraction
        
        # Smart batching configuration
        self._batch_size = 50  # Process 50 items at a time
        self._max_workers = 4  # Default thread pool size
        self._show_progress = HAS_TQDM  # Use tqdm if available
        
        # Load configurations
        self.load_config()
        self.load_report_definitions()
    
    # ================== UNIFIED CONFIGURATION SYSTEM ==================
    
    def get_slide_config(self):
        """Get API-specific slide configuration"""
        # All APIs use section dividers and group by effect_name by default
        base_config = {
            'use_section_dividers': True,
            'group_by': 'effect_name',
        }
        configs = {
            'runway': {
                **base_config,
                'media_types': ['source', 'source_video', 'generated'],
                'positions': [(2.59, 3.26, 10, 10), (13, 3.26, 10, 10), (23.41, 3.26, 10, 10)],
                'title_format': 'Generation {index}: {source_file}',
                'metadata_fields': ['prompt', 'reference_image', 'source_video', 'model', 'processing_time_seconds', 'success'],
                'metadata_position': (2.32, 15.24, 7.29, 3.06),
                'error_handling': 'video_fallback'
            },
            'nano_banana': {
                **base_config,
                'media_types': ['source', 'additional_source', 'generated'],
                'positions': [(2.59, 3.26, 10, 10), (13, 3.26, 10, 10), (23.41, 3.26, 10, 10)],
                'title_format': '❌ GENERATION FAILED',
                'title_show_only_if_failed': True,
                'metadata_fields': ['response_id', 'additional_images_used', 'success', 'attempts', 'processing_time_seconds'],
                'metadata_position': (5.19, 15.99, 7.29, 3.06),
                'metadata_reference_position': (2.32, 15.26, 7.29, 3.06),
                'use_comparison': False,
                'supports_multi_image': True
            },
            'vidu_effects': {
                **base_config,
                'media_types': ['source', 'generated'],
                'positions': [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)],
                'title_format': 'Generation {index}: {source_file}',
                'metadata_fields': ['effect_name', 'category', 'task_id', 'processing_time_seconds', 'duration', 'success'],
                'metadata_position': (5.19, 15.99, 7.29, 3.06),
                'metadata_reference_position': (2.32, 15.26, 7.29, 3.06),
            },
            'vidu_reference': {
                **base_config,
                'media_types': ['source', 'generated'],
                'positions': [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)],
                'title_format': 'Generation {index}: {source_file}',
                'metadata_fields': ['effect_name', 'category', 'task_id', 'processing_time_seconds', 'duration', 'success'],
                'metadata_position': (5.19, 15.99, 7.29, 3.06),
                'metadata_reference_position': (2.32, 15.26, 7.29, 3.06),
            },
            'genvideo': {
                **base_config,
                'media_types': ['source', 'generated', 'reference'],
                'positions': [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)],
                'title_format': 'GenVideo {index}: {source_file}',
                'metadata_fields': ['model', 'quality', 'processing_time_seconds', 'success', 'img_prompt'],
                'metadata_position': (5.19, 15.99, 7.29, 3.06),
                'metadata_reference_position': (2.32, 15.26, 7.29, 3.06),
            },
            'pixverse': {
                **base_config,
                'media_types': ['source', 'generated'],
                'positions': [(2.59, 3.26, 12, 10), (15.5, 3.26, 12, 10)],
                'title_format': 'pixverse_{index}_{source_file}',
                'metadata_fields': ['effect_name', 'video_id', 'processing_time_seconds', 'success'],
                'metadata_position': (5.19, 15.99, 7.29, 3.06),
                'metadata_reference_position': (2.32, 15.26, 7.29, 3.06),
            },
            'kling': {
                **base_config,
                'media_types': ['source', 'generated', 'reference'],
                'positions': [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)],
                'title_format': 'Generation {index}: {source_file}',
                'metadata_fields': ['task_id', 'model', 'prompt', 'processing_time_seconds', 'success'],
                'metadata_position': (5.19, 15.99, 7.29, 3.06),
                'metadata_reference_position': (2.32, 15.26, 7.29, 3.06),
            }
        }
        return configs.get(self.api_name, configs['kling'])
    
    # ================== UNIFIED SLIDE CREATION ENGINE ==================
    
    def create_slides(self, ppt, pairs, template_loaded, use_comparison=False):
        """Universal slide creation for all APIs"""
        slide_config = self.get_slide_config()
        grouped_pairs = self.group_pairs_if_needed(pairs, slide_config)
        
        slide_index = 1
        for group_name, group_pairs in grouped_pairs.items():
            # Add section divider if needed
            if slide_config.get('use_section_dividers') and group_name != 'default':
                self.create_section_divider_slide(ppt, group_name, template_loaded)
            
            # Create individual slides
            for pair in group_pairs:
                self.create_universal_slide(ppt, pair, slide_index, template_loaded, 
                                          use_comparison, slide_config)
                slide_index += 1
    
    def create_universal_slide(self, ppt, pair, index, template_loaded,
                              use_comparison, slide_config):
        """Create a single slide for any API using configuration"""
        # Adjust media types for nano_banana based on whether multi-image mode is active
        if self.api_name == 'nano_banana':
            if pair.additional_source_paths:
                # Multi-image mode: show source, additional, generated
                slide_config = slide_config.copy()
                slide_config['media_types'] = ['source', 'additional_source', 'generated']
                slide_config['positions'] = [(2.59, 3.26, 10, 10), (13, 3.26, 10, 10), (23.41, 3.26, 10, 10)]
            else:
                # Single-image mode: show only source and generated
                slide_config = slide_config.copy()
                slide_config['media_types'] = ['source', 'generated']
                slide_config['positions'] = [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)]
        
        # Create slide
        if template_loaded and len(ppt.slides) >= 4:
            slide = ppt.slides.add_slide(ppt.slides[3].slide_layout)
            self.handle_template_slide(slide, pair, index, use_comparison, slide_config)
        else:
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            self.handle_manual_slide(slide, pair, index, use_comparison, slide_config)
    
    def handle_template_slide(self, slide, pair, index, use_comparison, slide_config):
        """Handle slide creation with template placeholders (optimized)"""
        # Update title placeholder
        title_format = slide_config.get('title_format', 'Generation {index}: {source_file}')
        show_title = not slide_config.get('title_show_only_if_failed') or pair.failed
        
        if show_title:
            title = title_format.format(
                index=index,
                source_file=pair.source_file,
                failure_status="❌ GENERATION FAILED" if pair.failed else ""
            )
            
            # Optimized: Find title placeholder directly
            title_ph = next((p for p in slide.placeholders if p.placeholder_format.type == 1), None)
            if title_ph:
                title_ph.text = title
                if pair.failed and title_ph.text_frame.paragraphs:
                    title_ph.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
        
        # Handle media placeholders
        phs = sorted([p for p in slide.placeholders 
                     if p.placeholder_format.type in {6, 7, 8, 13, 18, 19}],
                    key=lambda x: getattr(x, 'left', 0))
        
        media_types = slide_config.get('media_types', ['source', 'generated'])
        
        for i, (ph, media_type) in enumerate(zip(phs, media_types)):
            media_path, is_video = self.get_media_path_and_type(pair, media_type)
            self.add_media_universal(slide, ph, media_path, is_video, slide_config, pair)
        
        # Add metadata
        self.add_metadata_universal(slide, pair, slide_config, use_comparison)
    
    def handle_manual_slide(self, slide, pair, index, use_comparison, slide_config):
        """Handle slide creation without template"""
        # Add title if needed
        title_format = slide_config.get('title_format', 'Generation {index}: {source_file}')
        show_title = not slide_config.get('title_show_only_if_failed') or pair.failed
        
        if show_title:
            title = title_format.format(
                index=index,
                source_file=pair.source_file,
                failure_status="❌ GENERATION FAILED" if pair.failed else ""
            )
            
            tb = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(20), Cm(2))
            tb.text_frame.text = title
            tb.text_frame.paragraphs[0].font.size = Pt(20)
            if pair.failed:
                tb.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
        
        # Add media using positions
        positions = slide_config.get('positions', [(2.59, 3.26, 12.5, 12.5), (18.78, 3.26, 12.5, 12.5)])
        media_types = slide_config.get('media_types', ['source', 'generated'])
        
        for pos, media_type in zip(positions, media_types):
            media_path, is_video = self.get_media_path_and_type(pair, media_type)
            self.add_media_universal(slide, pos, media_path, is_video, slide_config, pair)
        
        # Add metadata
        self.add_metadata_universal(slide, pair, slide_config, use_comparison)
    
    def get_media_path_and_type(self, pair, media_type):
        """Get media path and determine if it's video"""
        if media_type == 'source':
            path = pair.source_path
            is_video = path.suffix.lower() in {'.mp4', '.mov', '.avi'} if path else False
        elif media_type == 'source_video':
            path = pair.source_video_path
            is_video = True
        elif media_type == 'additional_source':
            # For multi-image support (Nano Banana dual-image mode)
            path = pair.additional_source_paths[0] if pair.additional_source_paths else None
            is_video = path.suffix.lower() in {'.mp4', '.mov', '.avi'} if path else False
        elif media_type == 'generated':
            path = pair.primary_generated
            is_video = path.suffix.lower() in {'.mp4', '.mov', '.avi'} if path else False
        elif media_type == 'reference':
            path = pair.primary_reference
            is_video = path.suffix.lower() in {'.mp4', '.mov', '.avi'} if path else False
        else:
            path = None
            is_video = False
        
        return path, is_video
    
    def group_pairs_if_needed(self, pairs, slide_config):
        """Group pairs if needed for section dividers"""
        group_by = slide_config.get('group_by')
        if group_by:
            grouped = {}
            for pair in pairs:
                key = getattr(pair, group_by, 'default')
                grouped.setdefault(key, []).append(pair)
            return grouped
        else:
            return {'default': pairs}
    
    # ================== UNIFIED MEDIA SYSTEM ==================
    
    def ensure_supported_img_format(self, img_path):
        """Convert any unsupported image format to PNG for PowerPoint compatibility"""
        p = Path(img_path)
        
        # PowerPoint natively supports: jpg, jpeg, png, bmp, gif, tiff, tif
        # We'll convert everything else (webp, svg, mpo, etc.) to PNG
        supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif'}
        
        # Always try to open and check the actual format, not just extension
        # Some files like .jpg might actually be MPO format
        needs_conversion = p.suffix.lower() not in supported_formats
        
        try:
            with Image.open(p) as im:
                # Check actual image format - MPO and other exotic formats need conversion
                actual_format = im.format
                if actual_format in ('MPO', 'WEBP', 'SVG', 'HEIC', 'HEIF', 'AVIF'):
                    needs_conversion = True
                    logger.info(f"Detected {actual_format} format in {p.name}, will convert")
                
                if needs_conversion:
                    # Convert to RGB mode (removes alpha for formats that don't support it well)
                    # Use RGBA for formats that might have transparency
                    if im.mode in ('RGBA', 'LA', 'P'):
                        rgb_im = im.convert('RGBA')
                        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                        rgb_im.save(tmp.name, 'PNG')
                    else:
                        rgb_im = im.convert('RGB')
                        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                        rgb_im.save(tmp.name, 'PNG')
                    
                    tmp.close()
                    self._tempfiles_to_cleanup.append(tmp.name)
                    logger.info(f"Converted {actual_format or p.suffix} to PNG: {p.name}")
                    return tmp.name
                else:
                    # Format is supported, return as-is
                    return str(img_path)
                    
        except Exception as e:
            logger.error(f"Failed to process image {p.name}: {e}")
            # If we can't even open it, try converting anyway as a fallback
            if needs_conversion:
                logger.error(f"Unable to convert {p.name}, returning original path")
            return str(img_path)
        
        return str(img_path)
    
    def _convert_unsupported_formats_batch(self, image_paths):
        """Convert multiple unsupported image formats in parallel for major performance gain"""
        if not image_paths:
            return {}
        
        def convert_one(path):
            try:
                converted = self.ensure_supported_img_format(path)
                return (path, converted)
            except Exception as e:
                logger.warning(f"Failed to convert {path}: {e}")
                return (path, str(path))
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = executor.map(convert_one, image_paths)
        
        return dict(results)
    
    def _load_json_batch(self, json_files_dict):
        """Load multiple JSON files in parallel - 40-50% faster metadata loading"""
        if not json_files_dict:
            return {}
        
        def load_one(key_path_tuple):
            key, path = key_path_tuple
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return (key, json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load JSON {path.name}: {e}")
                return (key, {})
        
        items = list(json_files_dict.items())
        with ThreadPoolExecutor(max_workers=8) as executor:
            if self._show_progress and len(items) > 20:
                pbar = tqdm(total=len(items), desc="Loading metadata", unit="files")
                results = []
                for result in executor.map(load_one, items):
                    results.append(result)
                    pbar.update()
                pbar.close()
            else:
                results = list(executor.map(load_one, items))
        
        return dict(results)
    
    def add_media_universal(self, slide, placeholder_or_pos, media_path, is_video, slide_config, pair=None):
        """Universal media addition for all APIs with webp conversion"""
        # Handle both placeholder objects and manual positions
        if hasattr(placeholder_or_pos, 'left'):
            # It's a placeholder
            l, t, w, h = (placeholder_or_pos.left, placeholder_or_pos.top,
                         placeholder_or_pos.width, placeholder_or_pos.height)
            placeholder_or_pos._element.getparent().remove(placeholder_or_pos._element)
        else:
            # It's a position tuple
            if len(placeholder_or_pos) == 4:
                l, t, w, h = [Cm(x) for x in placeholder_or_pos]
            else:
                l, t, w, h = Cm(placeholder_or_pos[0]), Cm(placeholder_or_pos[1]), Cm(10), Cm(10)
        
        if media_path and Path(media_path).exists():
            try:
                # Calculate aspect ratio and positioning
                ar = self.get_aspect_ratio(Path(media_path), is_video)
                sw, sh = (w, w/ar) if ar > w/h else (h*ar, h)
                fl, ft = l + (w - sw)/2, t + (h - sh)/2
                
                if is_video:
                    # Extract first frame for video poster
                    first_frame_path = self.extract_first_frame(Path(media_path))
                    if first_frame_path and Path(first_frame_path).exists():
                        slide.shapes.add_movie(str(media_path), fl, ft, sw, sh,
                                             poster_frame_image=first_frame_path)
                    else:
                        slide.shapes.add_movie(str(media_path), fl, ft, sw, sh)
                else:
                    # Convert any unsupported image format to PNG if needed
                    converted_path = self.ensure_supported_img_format(media_path)
                    slide.shapes.add_picture(str(converted_path), fl, ft, sw, sh)
            except Exception as e:
                self.add_error_box(slide, l, t, w, h, f"Failed to load media: {e}", pair)
        else:
            # Extract failure message from metadata if available
            error_msg = self.get_failure_message(pair) if pair else None
            self.add_error_box(slide, l, t, w, h, error_msg or "Media not found", pair)
    
    def get_failure_message(self, pair):
        """Extract failure message from metadata"""
        if not pair or not pair.metadata:
            return None
        
        # Try to get text_responses for detailed error message
        text_responses = pair.metadata.get('text_responses', [])
        if text_responses and isinstance(text_responses, list):
            for response in text_responses:
                if isinstance(response, dict) and 'content' in response:
                    content = response['content']
                    if content and content.strip():
                        return f"Media not found\n\nAPI Response:\n{content}"
        
        # Fallback to generic message
        return "Media not found"
    
    def add_error_box(self, slide, left, top, width, height, message: str, pair=None):
        """Add error box with proper styling"""
        box = slide.shapes.add_textbox(left, top, width, height)
        box.text_frame.text = f"❌ GENERATION FAILED\n\n{message}"
        box.text_frame.word_wrap = True
        
        for para in box.text_frame.paragraphs:
            para.font.size = Pt(12)  # Slightly smaller to fit more text
            para.alignment = PP_ALIGN.CENTER
            para.font.color.rgb = RGBColor(255, 0, 0)
        
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(255, 240, 240)
        box.line.color.rgb = RGBColor(255, 0, 0)
        box.line.width = Pt(0.5)
    
    # ================== UNIFIED METADATA SYSTEM ==================
    
    def add_metadata_universal(self, slide, pair, slide_config, use_comparison=False):
        """Universal metadata addition for all APIs"""
        metadata_fields = slide_config.get('metadata_fields', [])
        metadata_pos = slide_config.get('metadata_reference_position', (2.32, 15.26, 7.29, 3.06)) if use_comparison else slide_config.get('metadata_position', (5.19, 15.99, 7.29, 3.06))
        
        meta_lines = []
        
        # Build metadata lines based on configuration
        for field in metadata_fields:
            if field == 'success':
                value = '✓' if pair.metadata.get('success', False) else '❌'
                meta_lines.append(f"Status: {value}")
            elif field == 'processing_time_seconds':
                value = pair.metadata.get(field, 'N/A') if pair.metadata else 'N/A'
                meta_lines.append(f"Time: {value}s")
            elif field == 'response_id':
                value = pair.metadata.get(field, 'N/A') if pair.metadata else 'N/A'
                meta_lines.append(f"Response ID: {value}")
            elif field == 'attempts':
                value = pair.metadata.get(field, 'N/A') if pair.metadata else 'N/A'
                meta_lines.append(f"Attempts: {value}")
            elif field == 'additional_images_used':
                # Display additional images used in generation
                add_imgs = pair.metadata.get(field, []) if pair.metadata else []
                if add_imgs:
                    if len(add_imgs) == 1:
                        meta_lines.append(f"Additional: {add_imgs[0]}")
                    else:
                        meta_lines.append(f"Additional: {', '.join(add_imgs)}")
            elif field == 'task_id':
                value = pair.metadata.get(field, 'N/A') if pair.metadata else 'N/A'
                meta_lines.append(f"Task ID: {value}")
            elif field in ['prompt', 'img_prompt']:
                value = pair.metadata.get(field, 'N/A') if pair.metadata else 'N/A'
                if len(str(value)) > 60:
                    meta_lines.append(f"Prompt: {str(value)[:60]}...")
                else:
                    meta_lines.append(f"Prompt: {value}")
            elif field == 'effect_name':
                meta_lines.append(f"Effect: {pair.effect_name}")
            elif field == 'category':
                meta_lines.append(f"Category: {pair.category}")
            else:
                value = pair.metadata.get(field, 'N/A') if pair.metadata else 'N/A'
                display_name = field.replace('_', ' ').title()
                meta_lines.append(f"{display_name}: {value}")
        
        # Add source file name for some APIs
        if self.api_name in ['nano_banana', 'genvideo', 'pixverse']:
            meta_lines.insert(0, f"File: {pair.source_file}")
        
        if not meta_lines:
            meta_lines = ["No metadata available"]
        
        # Add metadata box
        box = slide.shapes.add_textbox(Cm(metadata_pos[0]), Cm(metadata_pos[1]),
                                       Cm(metadata_pos[2]), Cm(metadata_pos[3]))
        box.text_frame.text = "\n".join(meta_lines)
        box.text_frame.word_wrap = True
        
        for para in box.text_frame.paragraphs:
            para.font.size = Pt(10)
    
    def create_section_divider_slide(self, ppt, effect_name, template_loaded):
        """Create section divider slide for effects"""
        if template_loaded and len(ppt.slides) >= 2:
            slide = ppt.slides.add_slide(ppt.slides[1].slide_layout)
            # Set title in placeholder
            for p in slide.placeholders:
                if p.placeholder_format.type == 1:  # Title placeholder
                    p.text = f"{effect_name}"
                    if p.text_frame.paragraphs:
                        p.text_frame.paragraphs[0].font.size = Pt(48)
                        p.text_frame.paragraphs[0].font.bold = True
                        p.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                    break
        else:
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            # Add title text box
            tb = slide.shapes.add_textbox(Cm(5), Cm(8), Cm(24), Cm(4))
            tb.text_frame.text = f"{effect_name}"
            for p in tb.text_frame.paragraphs:
                p.font.size = Pt(48)
                p.font.bold = True
                p.alignment = PP_ALIGN.CENTER
    
    # ================== FILE PROCESSING METHODS ==================
    
    def process_batch(self, task: Dict) -> List[MediaPair]:
        """Universal batch processing for all API types"""
        if self.api_name in ["vidu_effects", "vidu_reference", "pixverse"]:
            return self.process_base_folder_structure(task)
        elif self.api_name == "genvideo":
            return self.process_genvideo_batch(task)
        else:
            return self.process_task_folder_structure(task)
    
    def process_task_folder_structure(self, task: Dict) -> List[MediaPair]:
        """Process APIs with individual task folders"""
        folder = Path(task['folder'])
        ref_folder = Path(task.get('reference_folder', '')) if task.get('reference_folder') else None
        use_comparison = task.get('use_comparison_template', False)
        
        if self.api_name == 'runway':
            return self.create_runway_media_pairs(folder, ref_folder, task, use_comparison)
        else:
            return self.create_standard_media_pairs(folder, ref_folder, task, use_comparison)
    
    def normalize_key(self, name: str) -> str:
        """Universal key normalization - keeps aspect ratio and numbers intact (memoized)"""
        if name in self._normalize_cache:
            return self._normalize_cache[name]
        
        key = name.lower()
        # Don't remove numbers or underscores in aspect ratios like 9_16, 1_1, 16_9
        # Just remove spaces and convert to consistent format
        key = key.replace(' ', '_')
        # Keep dashes and underscores, just clean up
        result = key.strip('_')
        
        self._normalize_cache[name] = result
        return result
    
    def create_standard_media_pairs(self, folder: Path, ref_folder: Optional[Path],
                                   task: Dict, use_comparison: bool) -> List[MediaPair]:
        """Create standard media pairs for Kling/Nano Banana"""
        pairs = []
        
        # Define folder structure based on API
        if self.api_name == 'nano_banana':
            folders = {
                'source': folder / 'Source',
                'generated': folder / 'Generated_Output',
                'metadata': folder / 'Metadata'
            }
            file_pattern = 'image'
        else:  # kling
            folders = {
                'source': folder / 'Source',
                'generated': folder / 'Generated_Video',
                'metadata': folder / 'Metadata'
            }
            file_pattern = 'generated'
        
        if not folders['source'].exists():
            return pairs
        
        # OPTIMIZED: Single-pass directory scanning
        src_imgs, _, _ = self._scan_directory_once(folders['source'])
        src = src_imgs
        
        # Get generated files with single scan
        out = {}
        if folders['generated'].exists():
            if self.api_name == 'nano_banana':
                gen_imgs, _, _ = self._scan_directory_once(folders['generated'])
                for key, f in gen_imgs.items():
                    if file_pattern in f.name:
                        # Split on 'image' and remove trailing underscore
                        basename = f.name.split(file_pattern)[0].rstrip('_')
                        out.setdefault(self.normalize_key(basename), []).append(f)
            else:  # kling
                _, gen_vids, _ = self._scan_directory_once(folders['generated'])
                for key, f in gen_vids.items():
                    if file_pattern in f.name:
                        basename = f.stem.replace(file_pattern, '')
                        out.setdefault(self.normalize_key(basename), []).append(f)
        
        # Get metadata with single scan and batch load
        _, _, metadata_files = self._scan_directory_once(folders['metadata'])
        metadata_cache = self._load_json_batch(metadata_files) if metadata_files else {}
        
        # Get reference files
        ref_files = {}
        if use_comparison and ref_folder:
            ref_generated_folder = ref_folder / ('Generated_Output' if self.api_name == 'nano_banana' else 'Generated_Video')
            if ref_generated_folder.exists():
                for f in ref_generated_folder.iterdir():
                    if self.api_name == 'nano_banana':
                        if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'} and 'image' in f.name:
                            # Split on 'image' and remove trailing underscore
                            basename = f.name.split('image')[0].rstrip('_')
                            ref_files.setdefault(self.normalize_key(basename), []).append(f)
                    else:  # kling
                        if f.suffix.lower() in {'.mp4', '.mov', '.avi'} and 'generated' in f.name:
                            basename = f.stem.replace('generated', '')
                            ref_files[self.normalize_key(basename)] = f
        
        # Pre-compute aspect ratios for all source images
        all_media = list(src.values()) + [p for paths in out.values() for p in paths if isinstance(paths, list)]
        if all_media:
            self._compute_aspect_ratios_batch(all_media, are_videos={p: p.suffix.lower() in {'.mp4', '.mov', '.avi'} for p in all_media})
        
        # Create pairs
        for b in sorted(src.keys()):
            # Use cached metadata
            md = metadata_cache.get(b, {})

            gen_paths = out.get(b, [])
            ref_paths = ref_files.get(b, []) if use_comparison else []

            if not isinstance(gen_paths, list):
                gen_paths = [gen_paths] if gen_paths else []
            if not isinstance(ref_paths, list):
                ref_paths = [ref_paths] if ref_paths else []

            # Determine effect_name: try metadata, then config, then folder name
            effect_name = md.get('effect_name') if md.get('effect_name') else None
            if not effect_name:
                effect_name = self.config.get('effect') or self.config.get('effect_name')
            if not effect_name:
                # Remove leading date (e.g., '1001 ') from folder name
                m = re.match(r'^(\d{4})\s*(.+)', folder.name)
                effect_name = m.group(2) if m else folder.name

            # For Nano Banana multi-image mode: resolve additional source images from metadata
            additional_source_paths = []
            if self.api_name == 'nano_banana' and md.get('additional_images_used'):
                additional_folder = folder / 'Additional'
                for img_name in md.get('additional_images_used', []):
                    img_path = additional_folder / img_name
                    if img_path.exists():
                        additional_source_paths.append(img_path)

            pair = MediaPair(
                source_file=src[b].name,
                source_path=src[b],
                api_type=self.api_name,
                generated_paths=gen_paths,
                reference_paths=ref_paths,
                additional_source_paths=additional_source_paths,
                metadata=md,
                failed=not gen_paths or not md.get('success', False),
                ref_failed=use_comparison and not ref_paths,
                effect_name=effect_name
            )
            pairs.append(pair)
        
        return pairs
    
    def create_runway_media_pairs(self, folder: Path, ref_folder: Optional[Path],
                                 task: Dict, use_comparison: bool) -> List[MediaPair]:
        """Create Runway media pairs"""
        folders = {
            'reference': folder / 'Reference',
            'source': folder / 'Source',
            'generated': folder / 'Generated_Video',
            'metadata': folder / 'Metadata'
        }
        
        ref_folders = {
            'video': ref_folder / 'Generated_Video',
            'metadata': ref_folder / 'Metadata'
        } if ref_folder and use_comparison else {}
        
        if not folders['metadata'].exists():
            logger.warning(f"Metadata folder not found: {folders['metadata']}")
            return []
        
        # OPTIMIZED: Use single-pass scanning for all folders
        reference_images, _, _ = self._scan_directory_once(folders['reference'])
        _, source_videos, _ = self._scan_directory_once(folders['source'])
        _, generated_videos, _ = self._scan_directory_once(folders['generated'])
        _, _, metadata_files = self._scan_directory_once(folders['metadata'])
        _, ref_videos, ref_metadata_raw = self._scan_directory_once(ref_folders.get('video', Path()))
        _, _, ref_metadata = self._scan_directory_once(ref_folders.get('metadata', Path()))
        
        # Batch load all metadata
        metadata_cache = self._load_json_batch(metadata_files) if metadata_files else {}
        ref_metadata_cache = self._load_json_batch(ref_metadata) if ref_metadata else {}
        
        logger.info(f"Runway files found: {len(reference_images)} refs, {len(source_videos)} sources, "
                   f"{len(generated_videos)} generated, {len(metadata_files)} metadata")
        
        # Pre-extract frames for all videos in parallel
        all_videos = list(source_videos.values()) + list(generated_videos.values())
        if all_videos:
            self._extract_frames_parallel(all_videos)
        
        pairs = []
        for stem, meta_path in metadata_files.items():
            md = metadata_cache.get(stem, {})
            if not md:
                continue
            
            # Find matching files using metadata references
            ref_img_path = next((p for p in reference_images.values()
                               if p.name == md.get('reference_image', '')), None)
            src_vid_path = next((p for p in source_videos.values()
                               if p.name == md.get('source_video', '')), None)
            gen_vid_path = next((p for p in generated_videos.values()
                               if p.name == md.get('generated_video', '')), None)
            
            # Determine source file and path
            source_file = None
            source_path = None
            if ref_img_path:
                source_file = ref_img_path.name
                source_path = ref_img_path
                logger.info("Face Swap task - using reference image as source")
            elif src_vid_path:
                source_file = src_vid_path.name
                source_path = src_vid_path
                src_vid_path = None  # Don't duplicate in source_video_path
                logger.info("Background Removal task - using source video as source")
            else:
                logger.warning(f"No valid source found for meta {stem}")
                continue
            
            # Handle reference comparisons
            ref_vid_path, ref_md = None, {}
            if use_comparison:
                r_base = stem.replace('runway_metadata', '')
                ref_vid_path = self.find_matching_video(r_base, ref_videos)
                ref_md = ref_metadata_cache.get(r_base, {})
            
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
        
        logger.info(f"Created {len(pairs)} Runway media pairs")
        return pairs
    
    def process_base_folder_structure(self, task: Dict) -> List[MediaPair]:
        """Process base folder structure for vidu/pixverse APIs"""
        base_folder = Path(self.config.get('base_folder', ''))
        if not base_folder.exists():
            logger.warning(f"Base folder not found: {base_folder}")
            return []
        
        logger.info(f"Processing {self.api_name} base folder: {base_folder}")
        pairs = []
        
        if self.api_name == "vidu_effects":
            # Process each effect folder
            for task_config in self.config.get('tasks', []):
                effect = task_config.get('effect', '')
                category = task_config.get('category', 'Unknown')
                if not effect:
                    continue
                
                folders = {k: base_folder / effect / v
                          for k, v in {'src': 'Source', 'vid': 'Generated_Video', 'meta': 'Metadata'}.items()}
                
                if not folders['src'].exists():
                    logger.warning(f"Source folder not found for effect: {effect}")
                    continue
                
                logger.info(f"Processing Vidu effect: {effect}")
                
                # OPTIMIZED: Single-pass directory scanning
                images, _, _ = self._scan_directory_once(folders['src'])
                
                _, raw_videos, _ = self._scan_directory_once(folders['vid'])
                videos = {}
                for f in raw_videos.values():
                    key = self.extract_video_key(f.name, effect)
                    videos[key] = f
                
                _, _, metadata_files = self._scan_directory_once(folders['meta'])
                
                # Batch load metadata
                metadata_cache = self._load_json_batch(metadata_files) if metadata_files else {}
                
                logger.info(f"Images: {len(images)}, Videos: {len(videos)}, Meta {len(metadata_files)}")
                
                # Pre-compute aspect ratios
                all_media = list(images.values()) + list(videos.values())
                if all_media:
                    self._compute_aspect_ratios_batch(all_media, are_videos={p: True for p in videos.values()})
                
                # Match metadata to source files
                for key, img in images.items():
                    metadata = metadata_cache.get(key, {})
                    
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
            # Process vidu reference effects
            try:
                effect_names = sorted([f.name for f in base_folder.iterdir()
                                     if f.is_dir() and not f.name.startswith('.') and (f / 'Source').exists()])
                logger.info(f"Discovered {len(effect_names)} effect folders")
            except:
                effect_names = [t.get('effect', '') for t in self.config.get('tasks', [])]
                logger.info(f"Using {len(effect_names)} configured tasks")
            
            for effect in effect_names:
                if not effect:
                    continue
                
                folders = {k: base_folder / effect / v
                          for k, v in {'src': 'Source', 'vid': 'Generated_Video', 'meta': 'Metadata'}.items()}
                
                if not folders['src'].exists():
                    logger.warning(f"Source folder not found for effect: {effect}")
                    continue
                
                logger.info(f"Processing Vidu Reference effect: {effect}")
                
                # OPTIMIZED: Single-pass directory scanning
                images, _, _ = self._scan_directory_once(folders['src'])
                
                _, raw_videos, _ = self._scan_directory_once(folders['vid'])
                videos = {}
                for f in raw_videos.values():
                    videos[self.extract_key_reference(f.name, effect)] = f
                
                _, _, metadata_files = self._scan_directory_once(folders['meta'])
                
                # Batch load metadata
                metadata_cache = self._load_json_batch(metadata_files) if metadata_files else {}
                
                # Pre-compute aspect ratios
                all_media = list(images.values()) + list(videos.values())
                if all_media:
                    self._compute_aspect_ratios_batch(all_media, are_videos={p: True for p in videos.values()})
                
                # Create pairs
                for key, img in images.items():
                    metadata = metadata_cache.get(key, {})
                    
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
        
        elif self.api_name == "pixverse":
            # Process pixverse effects
            for task_config in self.config.get('tasks', []):
                effect = task_config.get('effect', '')
                category = task_config.get('category', 'Unknown')
                if not effect:
                    continue
                
                folders = {k: base_folder / effect / v
                          for k, v in {'src': 'Source', 'vid': 'Generated_Video', 'meta': 'Metadata'}.items()}
                
                if not folders['src'].exists():
                    continue
                
                # OPTIMIZED: Single-pass directory scanning
                images, _, _ = self._scan_directory_once(folders['src'])
                
                _, raw_videos, _ = self._scan_directory_once(folders['vid'])
                videos = {}
                for f in raw_videos.values():
                    key = self.extract_video_key(f.name, effect)
                    videos[key] = f
                
                _, _, metadata_files = self._scan_directory_once(folders['meta'])
                
                # Batch load metadata
                metadata_cache = self._load_json_batch(metadata_files) if metadata_files else {}
                
                # Pre-compute aspect ratios
                all_media = list(images.values()) + list(videos.values())
                if all_media:
                    self._compute_aspect_ratios_batch(all_media, are_videos={p: True for p in videos.values()})
                
                # Create pairs
                for key, img in images.items():
                    metadata = metadata_cache.get(key, {})
                    
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
        
        return pairs
    
    def process_genvideo_batch(self, task: Dict) -> List[MediaPair]:
        """Process GenVideo batch"""
        folder = Path(task['folder'])
        source_folder = folder / 'Source'
        generated_folder = folder / 'Generated_Image'
        metadata_folder = folder / 'Metadata'
        pairs = []
        
        if not source_folder.exists():
            logger.warning(f"Source folder not found: {source_folder}")
            return pairs
        
        if not generated_folder.exists():
            logger.warning(f"Generated folder not found: {generated_folder}")
            return pairs
        
        # Process each source image
        source_images = [f for f in source_folder.iterdir()
                        if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}]
        
        # Pre-load all possible metadata files
        potential_metadata = {}
        if metadata_folder.exists():
            for mf in metadata_folder.iterdir():
                if mf.suffix.lower() == '.json':
                    try:
                        with open(mf, 'r', encoding='utf-8') as f:
                            potential_metadata[mf.stem] = json.load(f)
                    except Exception as e:
                        logger.warning(f"Failed to load metadata {mf.name}: {e}")
        
        for src_img in source_images:
            basename = src_img.stem
            
            # Try to find metadata from pre-loaded cache
            metadata = {}
            for key_pattern in [f"{basename}_{src_img.name}_metadata", f"{basename}_metadata", basename]:
                if key_pattern in potential_metadata:
                    metadata = potential_metadata[key_pattern]
                    logger.info(f"Found metadata for {basename}")
                    break
            
            # Find generated image
            gen_img = generated_folder / f"{basename}.jpg"
            if not gen_img.exists():
                for ext in ['.png', '.jpeg', '.webp']:
                    alt_gen = generated_folder / f"{basename}_generated{ext}"
                    if alt_gen.exists():
                        gen_img = alt_gen
                        break
            
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
                logger.warning(f"Failed pair: {src_img.name}")
            else:
                logger.info(f"Valid pair: {src_img.name} -> {gen_img.name}")
        
        logger.info(f"Created {len(pairs)} GenVideo media pairs")
        return pairs
    
    # ================== UTILITY METHODS ==================
    
    def load_config(self):
        """Load API-specific configuration"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"✓ Config loaded: {self.config_file}")
        except Exception as e:
            logger.error(f"✗ Config error: {e}")
            sys.exit(1)
    
    def load_report_definitions(self):
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
        
        logger.warning(f"⚠ API definitions not found, using defaults")
        self.set_default_report_definitions()
    
    def set_default_report_definitions(self):
        """Set default report definitions"""
        self.report_definitions = {
            "enabled": True,
            "template_path": "templates/I2V templates.pptx",
            "comparison_template_path": "templates/I2V Comparison Template.pptx",
            "output_directory": "/Users/ethanhsu/Desktop/GAI/Report",
            "use_comparison": self.api_name in ["kling", "nano_banana", "runway"]
        }
    
    def get_cmp_filename(self, folder1: str, folder2: str, model: str = '', effect_names1=None, effect_names2=None) -> str:
        """Generate comparison filename using API name and effect names"""
        # Extract date from folder1
        m1 = re.match(r'(\d{4})\s*(.+)', Path(folder1).name)
        if m1:
            d = m1.group(1)
        else:
            d = datetime.now().strftime("%m%d")
        
        # Use model (API name) as the primary identifier
        # Effect names are the actual content description
        effect_str1 = ', '.join(effect_names1) if effect_names1 else 'Test'
        effect_str2 = ', '.join(effect_names2) if effect_names2 else 'Reference'
        
        parts = [f"[{d}]"]
        if model:
            parts.append(model)
        parts.append(f"{effect_str1} vs {effect_str2}")
        return ' '.join(parts)

    def get_filename(self, folder, model='', effect_names=None):
        """Generate filename using API name and effect names"""
        # Extract date from folder name
        m = re.match(r'(\d{4})\s*(.+)', Path(folder).name)
        if m:
            d = m.group(1)
        else:
            d = datetime.now().strftime("%m%d")
        
        # Use model (API name) as the primary identifier
        # Effect names are the actual content description
        effect_str = ', '.join(effect_names) if effect_names else 'Test'
        
        parts = [f"[{d}]"]
        if model:
            parts.append(model)
        parts.append(effect_str)
        return ' '.join(parts)

    
    def _scan_directory_once(self, folder: Path, image_exts=None, video_exts=None, metadata_exts=None):
        """Scan directory once and categorize files by type - major performance optimization"""
        if image_exts is None:
            image_exts = {'.jpg', '.jpeg', '.png', '.webp'}
        if video_exts is None:
            video_exts = {'.mp4', '.mov', '.avi'}
        if metadata_exts is None:
            metadata_exts = {'.json'}
        
        images, videos, metadata = {}, {}, {}
        
        if not folder or not folder.exists():
            return images, videos, metadata
        
        for f in folder.iterdir():
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            if suffix in image_exts:
                images[self.normalize_key(f.stem)] = f
            elif suffix in video_exts:
                videos[self.normalize_key(f.stem)] = f
            elif suffix in metadata_exts:
                key = f.stem.replace('_metadata', '')
                metadata[self.normalize_key(key)] = f
        
        return images, videos, metadata
    
    def find_matching_video(self, base_name: str, video_files: dict) -> Optional[Path]:
        """Enhanced video matching for all APIs"""
        if base_name in video_files:
            return video_files[base_name]
        
        for v_name, v_path in video_files.items():
            if v_name.startswith(base_name):
                return v_path
        
        return None
    
    def get_aspect_ratio(self, path, is_video=False):
        """Calculate aspect ratio with caching - always use actual dimensions"""
        key = str(path)
        if key in self._ar_cache: 
            return self._ar_cache[key]
        
        # Try to get actual dimensions from the file first
        try:
            if is_video and cv2:
                cap = cv2.VideoCapture(str(path))
                if cap.isOpened():
                    w, h = cap.get(3), cap.get(4)
                    cap.release()
                    if w > 0 and h > 0:
                        ar = w / h
                        self._ar_cache[key] = ar
                        return ar
            else:
                with Image.open(path) as img:
                    ar = img.width / img.height
                    self._ar_cache[key] = ar
                    return ar
        except:
            pass
        
        # Fallback: Use filename patterns only if we can't read the file
        import re
        fn = path.name.lower()
        if re.search(r'(?:^|_|-|\s)9[_-]16(?:$|_|-|\s)', fn) or 'portrait' in fn: 
            return 9/16
        if re.search(r'(?:^|_|-|\s)1[_-]1(?:$|_|-|\s)', fn) or 'square' in fn: 
            return 1
        if re.search(r'(?:^|_|-|\s)16[_-]9(?:$|_|-|\s)', fn) or 'landscape' in fn: 
            return 16/9
        
        # Final fallback
        return 16/9
    
    def extract_first_frame(self, video_path):
        """Extract first frame with caching"""
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
    
    def _extract_frames_parallel(self, video_paths):
        """Extract first frames from multiple videos in parallel - major speedup"""
        if not cv2 or not video_paths:
            return {}
        
        def extract_one(video_path):
            return (video_path, self.extract_first_frame(video_path))
        
        paths_list = list(video_paths) if not isinstance(video_paths, list) else video_paths
        
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            if self._show_progress and len(paths_list) > 10:
                pbar = tqdm(total=len(paths_list), desc="Extracting video frames", unit="videos")
                results = []
                for result in executor.map(lambda p: extract_one(p), paths_list):
                    results.append(result)
                    pbar.update()
                pbar.close()
            else:
                results = list(executor.map(lambda p: extract_one(p), paths_list))
        
        return dict(results)
    
    def _compute_aspect_ratios_batch(self, media_paths, are_videos=False):
        """Pre-compute aspect ratios for multiple files in parallel"""
        if not media_paths:
            return
        
        def compute_one(path):
            ar = self.get_aspect_ratio(path, are_videos.get(path, False) if isinstance(are_videos, dict) else are_videos)
            return (str(path), ar)
        
        paths_list = list(media_paths) if not isinstance(media_paths, list) else media_paths
        
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            if self._show_progress and len(paths_list) > 20:
                pbar = tqdm(total=len(paths_list), desc="Computing aspect ratios", unit="files")
                results = []
                for result in executor.map(compute_one, paths_list):
                    results.append(result)
                    pbar.update()
                pbar.close()
            else:
                results = list(executor.map(compute_one, paths_list))
        
        # Update cache
        for path_str, ar in results:
            self._ar_cache[path_str] = ar
    
    def _process_in_batches(self, items, process_func, batch_size=None, desc="Processing"):
        """Process items in optimal batches to manage memory usage"""
        if not items:
            return []
        
        batch_size = batch_size or self._batch_size
        results = []
        
        total_batches = (len(items) + batch_size - 1) // batch_size
        
        if self._show_progress and len(items) > batch_size:
            logger.info(f"Processing {len(items)} items in {total_batches} batches of {batch_size}")
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_results = process_func(batch)
            results.extend(batch_results)
            
            # Clear temporary caches after each batch to manage memory
            if i + batch_size < len(items):
                import gc
                gc.collect()
        
        return results
    
    def extract_video_key(self, filename: str, effect_name: str) -> str:
        """Extract video key - FIXED for proper effect name removal (memoized)"""
        cache_key = f"{filename}|{effect_name}"
        if cache_key in self._extract_key_cache:
            return self._extract_key_cache[cache_key]
        
        stem = Path(filename).stem
        
        # First remove the _effect suffix
        stem = re.sub(r"_effect$", "", stem, flags=re.IGNORECASE)
        
        # Create multiple possible effect patterns to match
        effect_variations = [
            effect_name.replace(' ', '_'),  # Space to underscore
            effect_name.replace('-', '_'),  # Dash to underscore
            effect_name.replace(' ', '_').replace('-', '_'),  # Both replacements
            effect_name  # Original with spaces/dashes
        ]
        
        # Try to remove each variation (case insensitive)
        for effect_var in effect_variations:
            # Remove with underscore prefix
            pattern = f"_{re.escape(effect_var)}"
            stem = re.sub(pattern, "", stem, flags=re.IGNORECASE)
            
            # Remove without underscore prefix
            pattern = re.escape(effect_var)
            stem = re.sub(pattern, "", stem, flags=re.IGNORECASE)
        
        # Clean up any trailing underscores or effect patterns
        for pattern in [r"_generated", r"_output", r"_result"]:
            stem = re.sub(pattern, "", stem, flags=re.IGNORECASE)
        
        result = self.normalize_key(stem)
        self._extract_key_cache[cache_key] = result
        return result
    
    def extract_key_reference(self, filename: str, effect: str) -> str:
        """Extract key for vidu_reference - handles effect name with spaces/dashes/underscores (memoized)"""
        cache_key = f"{filename}|{effect}"
        if cache_key in self._extract_key_cache:
            return self._extract_key_cache[cache_key]
        
        stem = Path(filename).stem
        
        # Create all possible variations of the effect name as it might appear in filename
        effect_variations = [
            effect.replace(' ', '_').replace('-', '_'),  # "Corpse_Bride_V3_2"
            effect.replace(' ', '_'),  # Keep dashes: "Corpse_Bride_V3-2"
            effect.replace('-', '_'),  # "Corpse Bride V3_2"
            effect,  # Original
        ]
        
        # Try removing each variation from the end of the stem
        for eff_var in effect_variations:
            eff_lower = eff_var.lower()
            stem_lower = stem.lower()
            
            # Try with underscore separator
            if stem_lower.endswith(f'_{eff_lower}'):
                stem = stem[:-(len(eff_lower) + 1)]
                break
            # Try without separator (adjacent)
            if stem_lower.endswith(eff_lower):
                stem = stem[:-len(eff_lower)]
                break
        
        # Clean up any trailing underscores
        stem = stem.rstrip('_')
        
        result = self.normalize_key(stem)
        self._extract_key_cache[cache_key] = result
        return result
    
    def cleanup_temp_frames(self):
        """Clean up temporary frame files"""
        for frame_path in self._frame_cache.values():
            try:
                if Path(frame_path).exists():
                    os.unlink(frame_path)
            except Exception:
                pass
        self._frame_cache.clear()
    
    def cleanup_tempfiles(self):
        """Clean up temporary files from image format conversions"""
        for f in self._tempfiles_to_cleanup:
            try:
                if Path(f).exists():
                    os.unlink(f)
            except Exception:
                pass
        self._tempfiles_to_cleanup.clear()
    
    def cleanup_caches(self):
        """Clear all memory caches - useful between large batches"""
        self._normalize_cache.clear()
        self._extract_key_cache.clear()
        logger.debug(f"Cleared string caches: {len(self._normalize_cache)} + {len(self._extract_key_cache)} entries")
    
    def configure_performance(self, batch_size=None, max_workers=None, show_progress=None):
        """Configure performance settings for optimization"""
        if batch_size is not None:
            self._batch_size = batch_size
        if max_workers is not None:
            self._max_workers = max_workers
        if show_progress is not None:
            self._show_progress = show_progress and HAS_TQDM
        
        logger.info(f"Performance config: batch_size={self._batch_size}, "
                   f"max_workers={self._max_workers}, progress={self._show_progress}")
    
    # ================== PRESENTATION CREATION ==================
    
    def create_presentation(self, pairs: List[MediaPair], task: Dict) -> bool:
        """Create presentation using unified system"""
        if not pairs:
            logger.warning("No media pairs to process")
            return False

        # Determine template and comparison mode
        use_comparison = task.get('use_comparison_template', False) or bool(task.get('reference_folder'))
        template_key = 'comparison_template_path' if use_comparison else 'template_path'
        template_path = (self.config.get(template_key) or
                        self.report_definitions.get(template_key,
                        'templates/I2V Comparison Template.pptx' if use_comparison else 'templates/I2V templates.pptx'))

        # Gather all effect names from pairs, in order of appearance, unique
        effect_names = []
        seen = set()
        for p in pairs:
            ename = p.effect_name.strip() if hasattr(p, 'effect_name') and p.effect_name else None
            if ename and ename not in seen:
                effect_names.append(ename)
                seen.add(ename)

        # Load template
        try:
            ppt = Presentation(template_path) if Path(template_path).exists() else Presentation()
            template_loaded = Path(template_path).exists()
            logger.info(f"✓ Template loaded: {template_path}")
        except Exception as e:
            logger.warning(f"⚠ Template load failed: {e}, using blank presentation")
            ppt = Presentation()
            template_loaded = False

        # Set slide dimensions
        ppt.slide_width, ppt.slide_height = Cm(33.87), Cm(19.05)

        # Create title slide, pass effect_names
        self.create_title_slide(ppt, task, use_comparison, effect_names)

        # Create content slides using UNIFIED SYSTEM
        self.create_slides(ppt, pairs, template_loaded, use_comparison)

        # Save presentation, pass effect_names
        return self.save_presentation(ppt, task, use_comparison, effect_names)

    def create_title_slide(self, ppt: Presentation, task: Dict, use_comparison: bool, effect_names=None):
        """Create title slide"""
        if not ppt.slides:
            return

        # Get folder names for title generation
        if self.api_name in ["vidu_effects", "vidu_reference", "pixverse"]:
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
            'genvideo': 'GenVideo',
            'pixverse': 'Pixverse'
        }

        api_display = api_display_names.get(self.api_name, self.api_name.title())

        # Generate title
        if use_comparison and task.get('reference_folder'):
            ref_name = Path(task['reference_folder']).name
            title = self.get_cmp_filename(folder_name, ref_name, api_display, effect_names1=effect_names)
        else:
            title = self.get_filename(folder_name, api_display, effect_names=effect_names)

        # Update title slide
        if ppt.slides and ppt.slides[0].shapes:
            ppt.slides[0].shapes[0].text_frame.text = title

        # Add links
        self.add_links(ppt, task)

    def add_links(self, ppt: Presentation, task: Dict):
        """Add hyperlinks to title slide"""
        if not ppt.slides:
            return

        slide = ppt.slides[0]

        # Find or create info box
        info_box = next((s for s in slide.shapes if hasattr(s,'text_frame') and s.text_frame.text and 
                        any(k in s.text_frame.text.lower() for k in ['design','testbed','source'])), None)

        if not info_box:
            info_box = slide.shapes.add_textbox(Cm(5), Cm(13), Cm(20), Cm(4))

        info_box.text_frame.clear()

        # Get API-specific links
        testbed_url = self.config.get('testbed', f'http://192.168.4.3:8000/{self.api_name}/')
        design_link = self.config.get('design_link', '') if self.config.get('design_link', '') else task.get('design_link', '')
        source_link = self.config.get('source_video_link', '') if self.config.get('source_video_link', '') else task.get('source_video_link', '')

        links = [
            ("Design: ", "Link", design_link),
            ("Testbed: ", testbed_url, testbed_url),
            ("Source + Video: ", "Link", source_link)
        ]

        for i, (pre, txt, url) in enumerate(links):
            para = info_box.text_frame.paragraphs[0] if i == 0 else info_box.text_frame.add_paragraph()
            if url:
                para.clear()
                r1, r2 = para.add_run(), para.add_run()
                r1.text, r1.font.size = pre, Pt(24)
                r2.text, r2.font.size = txt, Pt(24)
                r2.hyperlink.address = url
                para.alignment = PP_ALIGN.CENTER
            else:
                para.text, para.font.size, para.alignment = f"{pre}{txt}", Pt(24), PP_ALIGN.CENTER

    
    def save_presentation(self, ppt, task, use_comparison, effect_names=None):
        """Save the presentation"""
        try:
            # Generate filename
            if self.api_name in ["vidu_effects", "vidu_reference", "pixverse"]:
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
                'genvideo': 'GenVideo',
                'pixverse': 'Pixverse'
            }
            api_display = api_display_names.get(self.api_name, self.api_name.title())
            if use_comparison and task.get('reference_folder'):
                ref_name = Path(task['reference_folder']).name
                filename = self.get_cmp_filename(folder_name, ref_name, api_display, effect_names1=effect_names)
            else:
                filename = self.get_filename(folder_name, api_display, effect_names=effect_names)
            # Get output directory
            output_dir = Path(self.config.get('output_directory',
                            self.config.get('output', {}).get('directory',
                            self.report_definitions.get('output_directory', './'))))
            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{filename}.pptx"
            # Save
            ppt.save(str(output_path))
            logger.info(f"✓ Saved: {output_path}")
            return True
        except Exception as e:
            logger.error(f"✗ Save failed: {e}")
            return False
    
    # ================== MAIN EXECUTION ==================
    
    def run(self) -> bool:
        """Main execution using unified system"""
        logger.info(f"🎬 Starting {self.api_name.title()} Report Generator")
        try:
            # Process tasks
            if self.api_name in ["vidu_effects", "vidu_reference", "pixverse"]:
                # Base folder structure - single task
                pairs = self.process_batch({})
                if pairs:
                    return self.create_presentation(pairs, {})
                else:
                    logger.warning("No pairs found for report.")
                    return False
            else:
                # Task folder structure - multiple tasks
                tasks = self.config.get('tasks', [])
                if not tasks:
                    logger.warning("No tasks found in config.")
                    return False
                successful = 0
                for i, task in enumerate(tasks, 1):
                    pairs = self.process_batch(task)
                    if pairs:
                        if self.create_presentation(pairs, task):
                            successful += 1
                logger.info(f"✓ Generated {successful}/{len(tasks)} presentations")
                return successful > 0
        except Exception as e:
            logger.error(f"✗ Report generation failed: {e}")
            return False
        finally:
            # Cleanup all temporary files
            self.cleanup_temp_frames()
            self.cleanup_tempfiles()  # Cleanup temporary format conversions

def create_report_generator(api_name, config_file=None):
    """Factory function to create report generator"""
    supported_apis = ['kling', 'nano_banana', 'vidu_effects', 'vidu_reference', 'runway', 'genvideo', 'pixverse']
    if api_name not in supported_apis:
        raise ValueError(f"Unsupported API: {api_name}. Supported: {supported_apis}")
    return UnifiedReportGenerator(api_name, config_file)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate PowerPoint reports from API processing results')
    parser.add_argument('api_name', choices=['kling', 'nano_banana', 'vidu_effects', 'vidu_reference', 'runway', 'genvideo', 'pixverse'],
                       help='API type to generate report for')
    parser.add_argument('--config', '-c', help='Config file path (optional)')
    
    args = parser.parse_args()
    
    generator = create_report_generator(args.api_name, args.config)
    sys.exit(0 if generator.run() else 1)


if __name__ == "__main__":
    main()

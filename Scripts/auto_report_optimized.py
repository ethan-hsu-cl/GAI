import json, logging, sys, re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Cm, Inches
from pptx.enum.text import PP_ALIGN
from concurrent.futures import ThreadPoolExecutor

try:
    import cv2
except ImportError:
    cv2 = None

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

@dataclass
class MediaPair:
    image_file: str
    image_path: Path
    video_file: str = None
    video_path: Path = None
    metadata: dict = None
    failed: bool = False

def get_report_filename(folder_name: str, model_name: str = '') -> str:
    """Generate standardized report filename: [date] Model Name Style Name"""
    match = re.match(r'(\d{4})\s+(.+)', folder_name)
    if match:
        date_part, style_name = match.groups()
    else:
        date_part, style_name = datetime.now().strftime("%m%d"), folder_name
    
    parts = [f"[{date_part}]"]
    if model_name and model_name.lower() not in style_name.lower():
        parts.append(model_name)
    parts.append(style_name)
    return ' '.join(parts)

class OptimizedVideoReportGenerator:
    def __init__(self, config_file: str = "batch_config.json"):
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
    
    def get_aspect_ratio(self, media_path: Path, is_video=False) -> float:
        """Fast aspect ratio detection"""
        filename = media_path.name.lower()
        if "9_16" in filename or "portrait" in filename: return 9/16
        if "1_1" in filename or "square" in filename: return 1
        if "16_9" in filename or "landscape" in filename: return 16/9
        
        try:
            if is_video and cv2:
                cap = cv2.VideoCapture(str(media_path))
                if cap.isOpened():
                    w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                    cap.release()
                    if w > 0 and h > 0: return w/h
            elif not is_video:
                with Image.open(media_path) as img:
                    return img.size[0] / img.size[1]
        except: pass
        return 16/9
    
    def add_to_placeholder(self, slide, placeholder, media_path=None, is_video=False, poster_image=None, error_msg=None):
        """Replace placeholder with media or error message"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        placeholder._element.getparent().remove(placeholder._element)
        
        if media_path:
            # Calculate scaled dimensions
            try:
                aspect_ratio = self.get_aspect_ratio(Path(media_path), is_video)
                if aspect_ratio > p_width / p_height:
                    scaled_w, scaled_h = p_width, p_width / aspect_ratio
                else:
                    scaled_w, scaled_h = p_height * aspect_ratio, p_height
                
                final_left = p_left + (p_width - scaled_w) / 2
                final_top = p_top + (p_height - scaled_h) / 2
            except:
                scaled_w, scaled_h = p_width * 0.8, p_height * 0.8
                final_left, final_top = p_left + p_width * 0.1, p_top + p_height * 0.1
            
            # Add media
            if is_video:
                if poster_image:
                    slide.shapes.add_movie(media_path, final_left, final_top, scaled_w, scaled_h, poster_frame_image=poster_image)
                else:
                    slide.shapes.add_movie(media_path, final_left, final_top, scaled_w, scaled_h)
            else:
                slide.shapes.add_picture(media_path, final_left, final_top, scaled_w, scaled_h)
        else:
            # Add error message
            fail_box = slide.shapes.add_textbox(p_left, p_top, p_width, p_height)
            fail_box.text_frame.text = f"❌ GENERATION FAILED\n\n{error_msg}"
            
            for p in fail_box.text_frame.paragraphs:
                p.font.size, p.alignment = Inches(16/72), PP_ALIGN.CENTER
                p.font.color.rgb = RGBColor(255, 0, 0)
            
            fail_box.fill.solid()
            fail_box.fill.fore_color.rgb = RGBColor(255, 240, 240)
            fail_box.line.color.rgb = RGBColor(255, 0, 0)
            fail_box.line.width = Inches(0.02)
    
    def process_folder_batch(self, task_folder):
        """Process single folder efficiently"""
        folder_path = Path(task_folder)
        folders = {'source': folder_path / "Source", 'video': folder_path / "Generated_Video", 'metadata': folder_path / "Metadata"}
        
        if not folders['source'].exists(): return folder_path, []
        
        # Build file mappings
        files = {
            'images': {f.stem: f for f in folders['source'].iterdir() if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}},
            'videos': {f.stem.replace('_generated', ''): f for f in folders['video'].iterdir() if f.suffix.lower() in {'.mp4', '.mov'}} if folders['video'].exists() else {},
            'metadata': {f.stem.replace('_metadata', ''): f for f in folders['metadata'].iterdir() if f.suffix.lower() == '.json'} if folders['metadata'].exists() else {}
        }
        
        # Create pairs
        pairs = []
        for base_name, img_file in files['images'].items():
            if base_name in files['metadata']:
                try:
                    with open(files['metadata'][base_name], 'r') as f:
                        metadata = json.load(f)
                except: metadata = {}
                
                video_file = files['videos'].get(base_name)
                pairs.append(MediaPair(
                    image_file=img_file.name, image_path=img_file,
                    video_file=video_file.name if video_file else None,
                    video_path=video_file, metadata=metadata,
                    failed=not video_file or not metadata.get('success', False)
                ))
        
        return folder_path, pairs
    
    def create_slide(self, ppt, pair, slide_num, template_loaded):
        """Create content slide"""
        if template_loaded and len(ppt.slides) >= 4:
            slide = ppt.slides.add_slide(ppt.slides[3].slide_layout)
            placeholders = sorted([p for p in slide.placeholders], key=lambda x: x.left if hasattr(x, 'left') else 0)
            
            # Update title
            for p in slide.placeholders:
                if p.placeholder_format.type == 1:
                    title = f"Generation {slide_num}: {pair.image_file}"
                    if pair.failed: title += " ❌ FAILED"
                    p.text = title
                    if pair.failed and p.text_frame.paragraphs:
                        p.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
                    break
            
            # Handle content placeholders
            content_placeholders = [p for p in placeholders if p.placeholder_format.type in {6, 7, 8, 13, 18, 19}]
            if len(content_placeholders) >= 2:
                # Add image
                try:
                    content_placeholders[0].insert_picture(str(pair.image_path))
                except:
                    self.add_to_placeholder(slide, content_placeholders[0], str(pair.image_path))
                
                # Add video or error
                if pair.video_path and pair.video_path.exists():
                    self.add_to_placeholder(slide, content_placeholders[1], str(pair.video_path), True, str(pair.image_path))
                else:
                    error_msg = pair.metadata.get('error', 'Video generation failed') if pair.metadata else 'Generation failed'
                    self.add_to_placeholder(slide, content_placeholders[1], error_msg=error_msg)
        else:
            # Fallback manual slide
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            
            # Add title
            title = f"Generation {slide_num}: {pair.image_file}" + (" ❌ FAILED" if pair.failed else "")
            title_box = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(20), Cm(2))
            title_box.text_frame.text = title
            title_box.text_frame.paragraphs[0].font.size = Inches(20/72)
            if pair.failed:
                title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
            
            # Add media at standard positions
            slide.shapes.add_picture(str(pair.image_path), Cm(2.59), Cm(3.26), Cm(12.5), Cm(12.5))
            
            if pair.video_path and pair.video_path.exists():
                try:
                    slide.shapes.add_movie(str(pair.video_path), Cm(18.78), Cm(3.26), Cm(12.5), Cm(12.5), poster_frame_image=str(pair.image_path))
                except:
                    slide.shapes.add_movie(str(pair.video_path), Cm(18.78), Cm(3.26), Cm(12.5), Cm(12.5))
            else:
                # Add error box
                error_msg = pair.metadata.get('error', 'Video generation failed') if pair.metadata else 'Generation failed'
                error_box = slide.shapes.add_textbox(Cm(18.78), Cm(3.26), Cm(12.5), Cm(12.5))
                error_box.text_frame.text = f"❌ GENERATION FAILED\n\n{error_msg}"
                
                for p in error_box.text_frame.paragraphs:
                    p.font.size, p.alignment = Inches(16/72), PP_ALIGN.CENTER
                    p.font.color.rgb = RGBColor(255, 0, 0)
                
                error_box.fill.solid()
                error_box.fill.fore_color.rgb = RGBColor(255, 240, 240)
                error_box.line.color.rgb = RGBColor(255, 0, 0)
                error_box.line.width = Inches(0.02)
        
        # Add metadata
        if pair.metadata:
            meta_text = f"Task ID: {pair.metadata.get('task_id', 'N/A')}\nVideo ID: {pair.metadata.get('video_id', 'N/A')}\n"
            meta_text += f"Time: {pair.metadata.get('processing_time_seconds', 'N/A')}s\nAttempts: {pair.metadata.get('attempts', 'N/A')}\n"
            meta_text += f"Status: {'SUCCESS' if not pair.failed else 'FAILED'}"
            if pair.failed and pair.metadata.get('error'):
                meta_text += f"\nError: {pair.metadata['error']}"
        else:
            meta_text = "No metadata available"
        
        meta_box = slide.shapes.add_textbox(Cm(5), Cm(16), Cm(12), Cm(3))
        meta_box.text_frame.text = meta_text
        for p in meta_box.text_frame.paragraphs:
            p.font.size = Inches(10/72)
    
    def create_presentation(self, folder_path, pairs):
        """Create presentation with standardized filename"""
        if not pairs: return False
        
        # Load template
        template_path = self.config.get('template_path', 'I2V templates.pptx')
        try:
            ppt = Presentation(template_path) if Path(template_path).exists() else Presentation()
            template_loaded = Path(template_path).exists()
        except:
            ppt, template_loaded = Presentation(), False
        
        ppt.slide_width, ppt.slide_height = Cm(33.87), Cm(19.05)
        
        # Update title slide
        folder_name = Path(folder_path).name
        if ppt.slides:
            match = re.match(r'(\d{4})\s+(.+)', folder_name)
            date_part, project_part = match.groups() if match else (datetime.now().strftime("%m%d"), folder_name)
            
            for shape in ppt.slides[0].shapes:
                if hasattr(shape, 'text_frame') and (not shape.text_frame.text or "Results" in shape.text_frame.text):
                    shape.text_frame.clear()
                    p1 = shape.text_frame.paragraphs[0]
                    p1.text, p1.font.size, p1.alignment = f"[{date_part}] Kling 2.1", Inches(60/72), PP_ALIGN.CENTER
                    p2 = shape.text_frame.add_paragraph()
                    p2.text, p2.font.size, p2.alignment = project_part, Inches(40/72), PP_ALIGN.CENTER
                    break
        
        # Create content slides
        for i, pair in enumerate(pairs, 1):
            self.create_slide(ppt, pair, i, template_loaded)
        
        # Save with standardized filename
        filename = get_report_filename(folder_name, "Kling 2.1")
        output_path = Path(self.config.get('output_directory', './')) / f"{filename}.pptx"
        ppt.save(str(output_path))
        logger.info(f"✓ Saved: {output_path}")
        return True
    
    def run(self):
        """Main execution"""
        tasks = self.config.get('tasks', [])
        
        # Process folders in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(self.process_folder_batch, task['folder']) for task in tasks]
            results = [future.result() for future in futures]
        
        successful = sum(1 for folder_path, pairs in results if self.create_presentation(folder_path, pairs))
        logger.info(f"✓ Generated {successful}/{len(tasks)} presentations")
        return successful > 0

if __name__ == "__main__":
    sys.exit(0 if OptimizedVideoReportGenerator().run() else 1)

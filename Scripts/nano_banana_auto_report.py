import json, logging, re, sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Cm, Inches
from pptx.enum.text import PP_ALIGN
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

@dataclass
class NanoBananaMediaPair:
    source_image_file: str
    source_image_path: Path
    generated_image_paths: List[Path] = None
    metadata: Dict = None
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

class NanoBananaReportGenerator:
    def __init__(self, config_file: str = "batch_nano_banana_config.json"):
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.positions = {'source': (2.59, 3.26, 12.5, 12.5), 'generated': (18.78, 3.26, 12.5, 12.5)}
        
    def match_files_batch(self):
        """Process folders and match files efficiently"""
        def process_folder(task_folder):
            folder_path = Path(task_folder)
            folders = {'source': folder_path / "Source", 'output': folder_path / "Generated_Output", 'metadata': folder_path / "Metadata"}
            
            if not folders['source'].exists():
                return folder_path, []
            
            # Get files
            source_files = {f.stem: f for f in folders['source'].iterdir() if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}}
            output_files = {}
            
            if folders['output'].exists():
                for f in folders['output'].iterdir():
                    if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'} and '_image_' in f.name:
                        base_name = f.name.split('_image_')[0]
                        output_files.setdefault(base_name, []).append(f)
            
            # Create pairs
            pairs = []
            for base_name in sorted(source_files.keys()):
                metadata = {}
                metadata_file = folders['metadata'] / f"{base_name}_metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                    except: pass
                
                generated_files = sorted(output_files.get(base_name, []), key=lambda x: x.name)
                pairs.append(NanoBananaMediaPair(
                    source_image_file=source_files[base_name].name,
                    source_image_path=source_files[base_name],
                    generated_image_paths=generated_files,
                    metadata=metadata,
                    failed=not generated_files or not metadata.get('success', False)
                ))
            
            return folder_path, pairs
        
        # Process in parallel
        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(process_folder, task['folder']) for task in self.config.get('tasks', [])]
            for future in futures:
                folder_path, pairs = future.result()
                results[str(folder_path)] = pairs
        return results
    
    def calc_position(self, image_path, box_x, box_y, box_w, box_h):
        """Calculate position with aspect ratio"""
        try:
            with Image.open(image_path) as img:
                aspect_ratio = img.size[0] / img.size[1]
            
            box_width, box_height = Cm(box_w), Cm(box_h)
            if aspect_ratio > box_width / box_height:
                scaled_w, scaled_h = box_width, box_width / aspect_ratio
            else:
                scaled_h, scaled_w = box_height, box_height * aspect_ratio
            
            x_offset, y_offset = (box_width - scaled_w) / 2, (box_height - scaled_h) / 2
            return Cm(box_x) + x_offset, Cm(box_y) + y_offset, scaled_w, scaled_h
        except:
            return Cm(box_x + 0.5), Cm(box_y + 0.5), Cm(box_w - 1), Cm(box_h - 1)
    
    def add_to_placeholder(self, slide, placeholder, media_path=None, error_msg=None):
        """Replace placeholder with media or error message"""
        p_left, p_top, p_width, p_height = placeholder.left, placeholder.top, placeholder.width, placeholder.height
        placeholder._element.getparent().remove(placeholder._element)
        
        if media_path:
            # Add image with aspect ratio
            try:
                with Image.open(media_path) as img:
                    aspect_ratio = img.size[0] / img.size[1]
                
                if aspect_ratio > p_width / p_height:
                    scaled_w, scaled_h = p_width, p_width / aspect_ratio
                else:
                    scaled_w, scaled_h = p_height * aspect_ratio, p_height
                
                final_left = p_left + (p_width - scaled_w) / 2
                final_top = p_top + (p_height - scaled_h) / 2
            except:
                scaled_w, scaled_h = p_width * 0.8, p_height * 0.8
                final_left, final_top = p_left + p_width * 0.1, p_top + p_height * 0.1
            
            slide.shapes.add_picture(str(media_path), final_left, final_top, scaled_w, scaled_h)
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
    
    def create_slide(self, ppt, pair, template_loaded):
        """Create content slide using template or fallback"""
        if template_loaded and len(ppt.slides) >= 4:
            slide = ppt.slides.add_slide(ppt.slides[3].slide_layout)
            
            # Handle title - only show for failures
            for p in slide.placeholders:
                if p.placeholder_format.type == 1:
                    if pair.failed:
                        p.text = "❌ GENERATION FAILED"
                        if p.text_frame.paragraphs:
                            p.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
                    else:
                        p.text = ""
                    break
            
            # Handle content placeholders
            content_placeholders = sorted([p for p in slide.placeholders if p.placeholder_format.type in [6, 7, 8, 13, 18, 19]], 
                                        key=lambda x: x.left if hasattr(x, 'left') else 0)
            
            if len(content_placeholders) >= 2:
                self.add_to_placeholder(slide, content_placeholders[0], str(pair.source_image_path))
                
                if pair.generated_image_paths:
                    self.add_to_placeholder(slide, content_placeholders[1], str(pair.generated_image_paths[0]))
                else:
                    error_msg = pair.metadata.get('error', 'No images generated') if pair.metadata else 'No images generated'
                    self.add_to_placeholder(slide, content_placeholders[1], error_msg=error_msg)
        else:
            # Fallback manual creation
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            
            if pair.failed:
                title_box = slide.shapes.add_textbox(Cm(2), Cm(1), Cm(20), Cm(2))
                title_box.text_frame.text = "❌ GENERATION FAILED"
                title_box.text_frame.paragraphs[0].font.size = Inches(18/72)
                title_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
            
            # Add source image
            src_pos = self.positions['source']
            src_x, src_y, src_w, src_h = self.calc_position(pair.source_image_path, *src_pos)
            slide.shapes.add_picture(str(pair.source_image_path), src_x, src_y, src_w, src_h)
            
            # Add generated image or error
            gen_pos = self.positions['generated']
            if pair.generated_image_paths:
                gen_x, gen_y, gen_w, gen_h = self.calc_position(pair.generated_image_paths[0], *gen_pos)
                slide.shapes.add_picture(str(pair.generated_image_paths[0]), gen_x, gen_y, gen_w, gen_h)
            else:
                error_msg = pair.metadata.get('error', 'No images generated') if pair.metadata else 'No images generated'
                error_box = slide.shapes.add_textbox(Cm(gen_pos[0]), Cm(gen_pos[1]), Cm(gen_pos[2]), Cm(gen_pos[3]))
                error_box.text_frame.text = f"❌ FAILED\n\n{error_msg}"
                
                for p in error_box.text_frame.paragraphs:
                    p.font.size, p.alignment = Inches(14/72), PP_ALIGN.CENTER
                    p.font.color.rgb = RGBColor(255, 0, 0)
                
                error_box.fill.solid()
                error_box.fill.fore_color.rgb, error_box.line.color.rgb = RGBColor(255, 240, 240), RGBColor(255, 0, 0)
        
        # Add simplified metadata
        meta_text = f"File Name: {pair.source_image_file}\n"
        meta_text += f"Response ID: {pair.metadata.get('response_id', 'N/A') if pair.metadata else 'N/A'}\n"
        meta_text += f"Time: {pair.metadata.get('processing_time_seconds', 'N/A') if pair.metadata else 'N/A'}s"
        
        meta_box = slide.shapes.add_textbox(Cm(5), Cm(16), Cm(12), Cm(3))
        meta_box.text_frame.text = meta_text
        for p in meta_box.text_frame.paragraphs:
            p.font.size = Inches(10/72)
    
    def create_presentation(self, folder_path, pairs):
        """Create presentation using template with standardized filename"""
        if not pairs:
            return False
        
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
        if ppt.slides and ppt.slides[0].shapes:
            match = re.match(r'(\d{4})\s+(.+)', folder_name)
            date_part, project_part = match.groups() if match else (datetime.now().strftime("%m%d"), folder_name)
            ppt.slides[0].shapes[0].text_frame.text = f"[{date_part}] Nano Banana\n{project_part}"
        
        # Create content slides
        for pair in pairs:
            self.create_slide(ppt, pair, template_loaded)
        
        # Save with standardized filename
        filename = get_report_filename(folder_name, "Nano Banana")
        output_dir = Path(self.config.get('output', {}).get('directory', './'))
        output_path = output_dir / f"{filename}.pptx"
        ppt.save(str(output_path))
        logger.info(f"✓ Saved: {output_path}")
        return True
    
    def run(self):
        """Main execution"""
        results = self.match_files_batch()
        successful = sum(1 for folder_path, pairs in results.items() if self.create_presentation(folder_path, pairs))
        logger.info(f"✓ Generated {successful}/{len(results)} presentations")
        return successful > 0

if __name__ == "__main__":
    sys.exit(0 if NanoBananaReportGenerator().run() else 1)

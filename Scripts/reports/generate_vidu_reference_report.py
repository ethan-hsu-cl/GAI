"""Vidu Reference report generator using refactored architecture."""
import sys
from pathlib import Path
import json
from typing import List

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.services.report_generator import ReportGenerator
from core.services.config_manager import ConfigManager
from core.models.media_pair import MediaPair

def collect_vidu_reference_media_pairs(config_file: str) -> List[MediaPair]:
    """Collect media pairs from Vidu Reference processing results."""
    config = ConfigManager.load_config(config_file)
    if not config:
        return []
    
    media_pairs = []
    
    # ✅ FIXED: Vidu Reference uses base_folder + effect structure
    base_folder = Path(config.get('base_folder', ''))
    
    if not base_folder.exists():
        print(f"Base folder not found: {base_folder}")
        return []
    
    # ✅ FIXED: Get effects from tasks array
    effects = []
    for task in config.get('tasks', []):
        effect_name = task.get('effect', '')
        if effect_name:
            effects.append(effect_name)
    
    if not effects:
        print("No effects found in tasks")
        return []
    
    # Process each effect folder
    for effect_name in effects:
        effect_folder = base_folder / effect_name
        
        if not effect_folder.exists():
            print(f"Effect folder not found: {effect_folder}")
            continue
        
        source_folder = effect_folder / 'Source'
        generated_folder = effect_folder / 'Generated_Video'
        metadata_folder = effect_folder / 'Metadata'
        reference_folder = effect_folder / 'Reference'
        
        if not source_folder.exists():
            print(f"Source folder not found: {source_folder}")
            continue
        
        # Process each source image in this effect folder
        for source_file in source_folder.glob('*.jpg'):
            basename = source_file.stem
            
            # ✅ VIDU REFERENCE PATTERNS (need to verify these)
            # Pattern 1: Try {basename}_{effect_name}_clean.mp4 (from original unified code)
            generated_video1 = generated_folder / f"{basename}_{effect_name}_clean.mp4"
            
            # Pattern 2: Try {basename}_reference.mp4  
            generated_video2 = generated_folder / f"{basename}_reference.mp4"
            
            # Pattern 3: Try {basename}_{effect_name}_effect.mp4 (similar to vidu effects)
            generated_video3 = generated_folder / f"{basename}_{effect_name}_effect.mp4"
            
            # Find which pattern exists
            generated_video = None
            for candidate in [generated_video1, generated_video2, generated_video3]:
                if candidate.exists():
                    generated_video = candidate
                    break
            
            # ✅ METADATA PATTERN: {basename}_metadata.json
            metadata_file = metadata_folder / f"{basename}_metadata.json"
            
            # ✅ REFERENCE IMAGES: Get up to 6 reference images
            reference_images = []
            if reference_folder.exists():
                # Look for reference images with various patterns
                ref_patterns = [
                    f"{basename}_ref.jpg",
                    f"{basename}_reference.jpg", 
                    f"{basename}_{effect_name}_ref.jpg"
                ]
                
                for pattern in ref_patterns:
                    ref_file = reference_folder / pattern
                    if ref_file.exists():
                        reference_images.append(ref_file)
                
                # Also get any numbered reference files
                ref_numbered = list(reference_folder.glob(f"{basename}_ref_*.jpg"))[:6]
                reference_images.extend(ref_numbered[:6-len(reference_images)])
            
            # Create media pair
            media_pair = MediaPair(
                source_file=source_file.name,
                source_path=source_file,
                api_type='vidu_reference',
                generated_paths=[generated_video] if generated_video else [],
                reference_paths=reference_images[:6],  # Limit to 6 reference images
                effect_name=effect_name,
                category=effect_name
            )
            
            # Load metadata if available
            if metadata_file.exists():
                try:
                    with open(metadata_file) as f:
                        media_pair.metadata = json.load(f)
                except:
                    pass
            
            # Set failed flag
            media_pair.failed = (
                not generated_video or 
                not media_pair.metadata.get('success', False) if media_pair.metadata else True
            )
            
            media_pairs.append(media_pair)
    
    return media_pairs

def main():
    """Generate Vidu Reference report - SIMPLIFIED VERSION."""
    config_file = 'config/batch_vidu_reference_config.json'
    
    # Collect media pairs
    media_pairs = collect_vidu_reference_media_pairs(config_file)
    
    if not media_pairs:
        print("No media pairs found")
        return
    
    print(f"Found {len(media_pairs)} media pairs")
    
    # ✅ SIMPLIFIED: Let ReportGenerator handle everything
    generator = ReportGenerator('vidu_reference', config_file)
    
    # Create a dummy output path - ReportGenerator will determine the real filename
    output_path = Path('../Report/temp.pptx')  # This will be overridden
    
    if generator.create_presentation(media_pairs, output_path):
        print("Report generation completed successfully")
    else:
        print("Failed to generate report")

if __name__ == "__main__":
    main()

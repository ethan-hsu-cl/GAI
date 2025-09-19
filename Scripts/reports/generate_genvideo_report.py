"""GenVideo report generator using refactored architecture."""
import sys
from pathlib import Path
import json
from typing import List

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.services.report_generator import ReportGenerator
from core.services.config_manager import ConfigManager
from core.models.media_pair import MediaPair

def collect_genvideo_media_pairs(config_file: str) -> List[MediaPair]:
    """Collect media pairs from GenVideo processing results."""
    config = ConfigManager.load_config(config_file)
    if not config:
        return []
    
    media_pairs = []
    
    for task in config.get('tasks', []):
        folder = Path(task['folder'])
        source_folder = folder / 'Source'
        generated_folder = folder / 'Generated_Video'
        metadata_folder = folder / 'Metadata'
        
        if not source_folder.exists():
            continue
        
        # Process each source image
        for source_file in source_folder.glob('*.jpg'):
            basename = source_file.stem
            
            # ✅ CORRECT GENVIDEO PATTERN: {basename}_generated.mp4
            generated_video = generated_folder / f"{basename}_generated.mp4"
            # ✅ CORRECT METADATA PATTERN: {basename}_metadata.json
            metadata_file = metadata_folder / f"{basename}_metadata.json"
            
            # Create media pair
            media_pair = MediaPair(
                source_file=source_file.name,
                source_path=source_file,
                api_type='genvideo',
                generated_paths=[generated_video] if generated_video.exists() else []
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
                not generated_video.exists() or 
                not media_pair.metadata.get('success', False) if media_pair.metadata else True
            )
            
            media_pairs.append(media_pair)
    
    return media_pairs

def main():
    """Generate GenVideo report - SIMPLIFIED VERSION."""
    config_file = 'config/batch_genvideo_config.json'
    
    # Collect media pairs
    media_pairs = collect_genvideo_media_pairs(config_file)
    
    if not media_pairs:
        print("No media pairs found")
        return
    
    # ✅ SIMPLIFIED: Let ReportGenerator handle everything
    generator = ReportGenerator('genvideo', config_file)
    
    # Create a dummy output path - ReportGenerator will determine the real filename
    output_path = Path('../Report/temp.pptx')  # This will be overridden
    
    if generator.create_presentation(media_pairs, output_path):
        print("Report generation completed successfully")
    else:
        print("Failed to generate report")

if __name__ == "__main__":
    main()

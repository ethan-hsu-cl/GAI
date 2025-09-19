"""Vidu Reference processor using refactored architecture."""
import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.factory import ProcessorFactory
from core.services.config_manager import ConfigManager
import logging

def main():
    """Run Vidu Reference processing."""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    # Load configuration
    config = ConfigManager.load_config('config/batch_vidu_reference_config.json')
    if not config:
        print("Failed to load configuration")
        return
    
    # Create processor
    processor = ProcessorFactory.create_processor('vidu_reference', config)
    
    # Initialize client
    if not processor.initialize_client():
        print("Failed to initialize client")
        return
    
    # Process tasks - Note: Vidu Reference works with image sets differently
    valid_tasks = processor.validate_files({'base_folder': config.get('base_folder', '')})
    
    for i, image_set in enumerate(valid_tasks, 1):
        # Each "task" is actually an image set with references
        processor.process_file(image_set, config, 
                             Path(config.get('base_folder', '')) / "GeneratedVideo",
                             Path(config.get('base_folder', '')) / "Metadata")

if __name__ == "__main__":
    main()

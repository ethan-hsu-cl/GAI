"""Kling processor using refactored architecture."""
import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.factory import ProcessorFactory
from core.services.config_manager import ConfigManager
import logging

def main():
    """Run Kling processing."""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    # Load configuration
    config = ConfigManager.load_config('config/batch_config.json')
    if not config:
        print("Failed to load configuration")
        return
    
    # Create processor
    processor = ProcessorFactory.create_processor('kling', config)
    
    # Initialize client
    if not processor.initialize_client():
        print("Failed to initialize client")
        return
    
    # Process tasks
    for i, task in enumerate(config.get('tasks', []), 1):
        processor.process_task(task, i, len(config['tasks']))

if __name__ == "__main__":
    main()

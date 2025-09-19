"""Configuration management service."""
import json
from pathlib import Path
from typing import Dict, Optional
import logging

class ConfigManager:
    """Manages configuration loading and validation."""
    
    @staticmethod
    def load_config(config_file: str) -> Optional[Dict]:
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"Config error: {e}")
            return None
    
    @staticmethod
    def load_api_definitions(api_name: str) -> Dict:
        """Load API-specific definitions."""
        try:
            with open('core/api_definitions.json', 'r', encoding='utf-8') as f:
                all_definitions = json.load(f)
                return all_definitions.get(api_name, {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"API definitions error: {e}")
            return {}  # Return empty dict instead of calling _get_default_definitions

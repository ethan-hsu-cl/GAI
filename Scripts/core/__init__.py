"""
Core package for AI Media Processing Pipeline.

This package contains the refactored, modular architecture for processing
images and videos through multiple AI APIs with integrated report generation.

Architecture:
- base/: Abstract base classes and interfaces
- services/: Shared business logic and utilities  
- handlers/: API-specific processing implementations
- models/: Data structures and models
- factory.py: Factory pattern for creating handlers
"""

# Import main factory for easy access
from .factory import ProcessorFactory

# Import key services for external use
from .services.config_manager import ConfigManager
from .services.file_validator import FileValidator
from .services.media_processor import MediaProcessor
from .services.presentation_builder import PresentationBuilder

# Import base classes for extending functionality
from .base.base_processor import BaseAPIHandler
from .base.base_reporter import BaseReporter
from .base.exceptions import ProcessingError, ValidationError, APIError, ConfigurationError

# Import models
from .models.media_pair import MediaPair
from .models.api_response import APIResponse

# Version info
__version__ = "2.0.0"
__author__ = "AI Media Processing Team"
__description__ = "Refactored modular AI media processing pipeline"

# Define what gets imported with "from core import *"
__all__ = [
    # Factory
    'ProcessorFactory',
    
    # Services
    'ConfigManager',
    'FileValidator', 
    'MediaProcessor',
    'PresentationBuilder',
    
    # Base classes
    'BaseAPIHandler',
    'BaseReporter',
    
    # Exceptions
    'ProcessingError',
    'ValidationError',
    'APIError',
    'ConfigurationError',
    
    # Models
    'MediaPair',
    'APIResponse',
]

# Package metadata
SUPPORTED_APIS = [
    'kling',           # Kling Image2Video
    'nano_banana',     # Google Flash Nano Banana
    'runway',          # Runway video generation
    'vidu_effects',    # Vidu Effects
    'vidu_reference',  # Vidu Reference
    'genvideo',        # GenVideo Image2Image
]

# Configuration
DEFAULT_CONFIG_DIR = 'config'
DEFAULT_TEMPLATE_DIR = 'templates'
DEFAULT_OUTPUT_DIR = '../Report'

def get_supported_apis():
    """Get list of supported API names."""
    return SUPPORTED_APIS.copy()

def get_version():
    """Get package version."""
    return __version__

def get_package_info():
    """Get comprehensive package information."""
    return {
        'version': __version__,
        'author': __author__,
        'description': __description__,
        'supported_apis': SUPPORTED_APIS,
        'config_dir': DEFAULT_CONFIG_DIR,
        'template_dir': DEFAULT_TEMPLATE_DIR,
        'output_dir': DEFAULT_OUTPUT_DIR,
    }

# Initialize logging for the package
import logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Package-level configuration validation
def validate_package_setup():
    """Validate that all required components are available."""
    import os
    from pathlib import Path
    
    issues = []
    
    # Check required directories
    required_dirs = ['base', 'services', 'handlers', 'models']
    for dir_name in required_dirs:
        if not (Path(__file__).parent / dir_name).exists():
            issues.append(f"Missing required directory: core/{dir_name}/")
    
    # Check for api_definitions.json
    if not (Path(__file__).parent / 'api_definitions.json').exists():
        issues.append("Missing core/api_definitions.json")
    
    # Check factory.py
    if not (Path(__file__).parent / 'factory.py').exists():
        issues.append("Missing core/factory.py")
    
    if issues:
        logging.warning(f"Package setup issues found: {', '.join(issues)}")
        return False
    
    return True

# Validate setup on import (optional - can be removed if causing issues)
try:
    _setup_valid = validate_package_setup()
    if not _setup_valid:
        logging.warning("Core package may not be properly set up")
except Exception as e:
    logging.debug(f"Setup validation failed: {e}")

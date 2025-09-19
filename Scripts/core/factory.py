"""Factory for creating API handlers."""
from typing import Dict, Type

# ✅ FIXED: Use relative imports (add the dots)
from .base.base_processor import BaseAPIHandler
from .base.exceptions import ConfigurationError
from .handlers.kling_handler import KlingHandler
from .handlers.nano_banana_handler import NanoBananaHandler
from .handlers.runway_handler import RunwayHandler
from .handlers.vidu_effects_handler import ViduEffectsHandler
from .handlers.vidu_reference_handler import ViduReferenceHandler
from .handlers.genvideo_handler import GenVideoHandler
from .handlers.pixverse_effects_handler import PixverseEffectsHandler  # Fixed name

class ProcessorFactory:
    """Factory for creating API processors."""
    
    _handlers: Dict[str, Type[BaseAPIHandler]] = {
        'kling': KlingHandler,
        'nano_banana': NanoBananaHandler,
        'runway': RunwayHandler,
        'vidu_effects': ViduEffectsHandler,
        'vidu_reference': ViduReferenceHandler,
        'genvideo': GenVideoHandler,
        'pixverse_effects': PixverseEffectsHandler,  # Added 
    }
    
    @classmethod
    def create_processor(cls, api_name: str, config: Dict) -> BaseAPIHandler:
        """Create a processor for the given API."""
        if api_name not in cls._handlers:
            raise ConfigurationError(f"Unknown API: {api_name}")
        
        handler_class = cls._handlers[api_name]
        return handler_class(config)
    
    @classmethod
    def get_available_apis(cls) -> list:
        """Get list of available API names."""
        return list(cls._handlers.keys())

"""Handler registry - Auto-discovers handlers dynamically."""
import importlib
import inspect
from pathlib import Path


class HandlerRegistry:
    """Auto-registers handlers. New APIs work automatically if handler file exists."""
    
    _handlers = {}
    _loaded = False
    
    @classmethod
    def get_handler(cls, api_name, processor):
        """Get handler for API. Auto-loads if not yet loaded."""
        if not cls._loaded:
            cls._auto_discover()
        
        handler_class = cls._handlers.get(api_name)
        if handler_class:
            return handler_class(processor)
        
        # No handler found - use generic handler
        from .base_handler import BaseAPIHandler
        return BaseAPIHandler(processor)
    
    @classmethod
    def _auto_discover(cls):
        """Auto-discover all handlers in this directory."""
        handlers_dir = Path(__file__).parent
        
        # Scan for *_handler.py files
        for handler_file in handlers_dir.glob('*_handler.py'):
            if handler_file.name == 'base_handler.py':
                continue
            
            try:
                # Import module
                module_name = handler_file.stem
                module = importlib.import_module(f'handlers.{module_name}')
                
                # Find handler class
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if name.endswith('Handler') and name != 'BaseAPIHandler':
                        # Extract API name from class name
                        # KlingHandler -> kling
                        # NanoBananaHandler -> nano_banana
                        api_name = cls._class_to_api_name(name)
                        cls._handlers[api_name] = obj
                        
            except Exception as e:
                print(f"Warning: Could not load handler {handler_file}: {e}")
        
        cls._loaded = True
    
    @classmethod
    def _class_to_api_name(cls, class_name):
        """Convert class name to API name: KlingHandler -> kling."""
        # Remove 'Handler' suffix
        name = class_name.replace('Handler', '')
        
        # Convert CamelCase to snake_case
        import re
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
        
        return name
    
    @classmethod
    def list_handlers(cls):
        """List all registered handlers."""
        if not cls._loaded:
            cls._auto_discover()
        return list(cls._handlers.keys())

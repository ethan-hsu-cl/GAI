#!/usr/bin/env python3
"""  
Google Flash/Nano Banana API Wrapper
Lightweight wrapper for the unified API processor
"""
import sys
from core.unified_api_processor import create_processor

def main():
    processor = create_processor("nano_banana")
    success = processor.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

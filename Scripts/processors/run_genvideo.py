#!/usr/bin/env python3
"""
GenVideo API Wrapper
Lightweight wrapper for the unified API processor
"""
import sys
from core.unified_api_processor import create_processor

def main():
    processor = create_processor("genvideo")
    success = processor.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

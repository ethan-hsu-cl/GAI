#!/usr/bin/env python3
"""
Kling Endframe API Wrapper
Processes image pairs (start and end frames) to generate videos.
"""
import sys
from core.unified_api_processor import create_processor

def main():
    """Run Kling Endframe API processor."""
    processor = create_processor("kling_endframe")
    success = processor.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

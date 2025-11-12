#!/usr/bin/env python3
"""
Wan 2.2 Report Generator
Lightweight wrapper for the unified report generator
"""
import sys
from core.unified_report_generator import create_report_generator

def main():
    generator = create_report_generator("wan")
    success = generator.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

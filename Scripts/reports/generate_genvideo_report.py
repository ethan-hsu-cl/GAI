#!/usr/bin/env python3
"""
GenVideo Report Generator Wrapper  
"""
import sys
from core.unified_report_generator import create_report_generator

def main():
    generator = create_report_generator("genvideo")
    success = generator.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

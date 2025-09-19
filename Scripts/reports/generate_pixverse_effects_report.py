"""Generate Pixverse Effects processing report."""

import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_report_generator import UnifiedReportGenerator

def main():
    """Generate Pixverse Effects report."""
    generator = UnifiedReportGenerator('pixverse_effects')
    generator.generate_report()

if __name__ == "__main__":
    main()

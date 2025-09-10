import sys
import logging
from advanced_batch_processor import BatchVideoProcessor
from effect_processor import ViduEffectProcessor
from google_flash_processor import GoogleFlashProcessor

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_all_processors.py [kling|vidu|nano|all]")
        sys.exit(1)

    arg = sys.argv[1].lower()
    results = {}

    if arg in ("kling", "all"):
        logger.info("\n=== Running Kling BatchVideoProcessor ===")
        kling_proc = BatchVideoProcessor()
        results['kling'] = kling_proc.run()

    if arg in ("vidu", "all"):
        logger.info("\n=== Running ViduEffectProcessor ===")
        vidu_proc = ViduEffectProcessor()
        results['vidu'] = vidu_proc.run()

    if arg in ("nano", "all"):
        logger.info("\n=== Running GoogleFlashProcessor ===")
        flash_proc = GoogleFlashProcessor()
        results['nano'] = flash_proc.run()

    logger.info(f"\nSummary: {results}")

if __name__ == "__main__":
    main()

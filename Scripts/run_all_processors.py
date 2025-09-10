import sys
import logging
from advanced_batch_processor import BatchVideoProcessor
from effect_processor import ViduEffectProcessor
from google_flash_processor import GoogleFlashProcessor

# Import the auto report generators
from nano_banana_auto_report import NanoBananaReport
from vidu_auto_report import ViduReportGenerator
from auto_report_optimized import OptimizedVideoReportGenerator

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_all_processors.py [kling|vidu|nano|all] [process|report|auto]")
        print("Commands:")
        print("  process - Run processors only")
        print("  report  - Generate reports only")
        print("  auto    - Run processor + auto-generate report (default)")
        print("Examples:")
        print("  python run_all_processors.py nano report")
        print("  python run_all_processors.py kling process")
        print("  python run_all_processors.py vidu auto")
        print("  python run_all_processors.py all")
        sys.exit(1)

    platform = sys.argv[1].lower()
    command = sys.argv[2].lower() if len(sys.argv) > 2 else "auto"
    
    # Determine what to run based on command
    if command == "process":
        run_processing, run_reports = True, False
    elif command == "report":
        run_processing, run_reports = False, True
    elif command == "auto":
        run_processing, run_reports = True, True
    else:
        logger.error(f"Unknown command: {command}")
        sys.exit(1)
    
    results = {}

    # === PROCESSING PHASE ===
    if run_processing:
        logger.info(f"\n{'='*50}")
        logger.info("RUNNING PROCESSORS")
        logger.info("="*50)
        
        if platform in ("kling", "all"):
            logger.info("\n=== Running Kling BatchVideoProcessor ===")
            try:
                kling_proc = BatchVideoProcessor()
                results['kling_processing'] = kling_proc.run()
            except Exception as e:
                logger.error(f"❌ Kling processing failed: {e}")
                results['kling_processing'] = False

        if platform in ("vidu", "all"):
            logger.info("\n=== Running ViduEffectProcessor ===")
            try:
                vidu_proc = ViduEffectProcessor()
                results['vidu_processing'] = vidu_proc.run()
            except Exception as e:
                logger.error(f"❌ Vidu processing failed: {e}")
                results['vidu_processing'] = False

        if platform in ("nano", "all"):
            logger.info("\n=== Running GoogleFlashProcessor ===")
            try:
                flash_proc = GoogleFlashProcessor()
                results['nano_processing'] = flash_proc.run()
            except Exception as e:
                logger.error(f"❌ Nano processing failed: {e}")
                results['nano_processing'] = False

    # === REPORT GENERATION PHASE ===
    if run_reports:
        logger.info(f"\n{'='*50}")
        logger.info("GENERATING REPORTS")
        logger.info("="*50)
        
        if platform in ("kling", "all"):
            logger.info("\n=== Generating Kling Report ===")
            try:
                kling_report = OptimizedVideoReportGenerator("batch_config.json")
                results['kling_report'] = kling_report.run()
            except Exception as e:
                logger.error(f"❌ Kling report failed: {e}")
                results['kling_report'] = False

        if platform in ("vidu", "all"):
            logger.info("\n=== Generating Vidu Report ===")
            try:
                vidu_report = ViduReportGenerator("batch_vidu_config.json")
                results['vidu_report'] = vidu_report.run()
            except Exception as e:
                logger.error(f"❌ Vidu report failed: {e}")
                results['vidu_report'] = False

        if platform in ("nano", "all"):
            logger.info("\n=== Generating Nano Banana Report ===")
            try:
                nano_report = NanoBananaReport("batch_nano_banana_config.json")
                results['nano_report'] = nano_report.run()
            except Exception as e:
                logger.error(f"❌ Nano Banana report failed: {e}")
                results['nano_report'] = False

    # === SUMMARY ===
    logger.info(f"\n{'='*50}")
    logger.info("FINAL SUMMARY")
    logger.info("="*50)
    
    if run_processing:
        processing_results = {k:v for k,v in results.items() if 'processing' in k}
        successful_processing = sum(1 for v in processing_results.values() if v)
        logger.info(f"📊 Processing: {successful_processing}/{len(processing_results)} successful")
        for k,v in processing_results.items():
            status = "✅ SUCCESS" if v else "❌ FAILED"
            logger.info(f"  - {k}: {status}")
    
    if run_reports:
        report_results = {k:v for k,v in results.items() if 'report' in k}
        successful_reports = sum(1 for v in report_results.values() if v)
        logger.info(f"📈 Reports: {successful_reports}/{len(report_results)} generated")
        for k,v in report_results.items():
            status = "✅ GENERATED" if v else "❌ FAILED"
            logger.info(f"  - {k}: {status}")
    
    logger.info(f"\nCommand executed: {platform} {command}")
    logger.info(f"Overall Results: {results}")
    
    # Exit with success if any operation succeeded
    return any(results.values()) if results else False

if __name__ == "__main__":
    sys.exit(0 if main() else 1)

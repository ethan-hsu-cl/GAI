import sys
import logging
from pathlib import Path

# Import unified processors and report generators
from unified_api_processor import create_processor
from unified_report_generator import create_report_generator

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# API mapping for backward compatibility
API_MAPPING = {
    'kling': 'kling',
    'vidu': 'vidu_effects', 
    'viduref': 'vidu_reference',
    'nano': 'nano_banana',
    'runway': 'runway',
    'genvideo': 'genvideo',
    'pixverse': 'pixverse',
}

# Config file mapping
CONFIG_MAPPING = {
    'kling': 'config/batch_config.json',
    'vidu_effects': 'config/batch_vidu_config.json',
    'vidu_reference': 'config/batch_vidu_reference_config.json', 
    'nano_banana': 'config/batch_nano_banana_config.json',
    'runway': 'config/batch_runway_config.json',
    'genvideo': 'config/batch_genvideo_config.json',
    'pixverse': 'config/batch_pixverse_config.json'  # Add this line
}

def show_usage():
    """Display usage information"""
    print("Usage: python runall.py [platform] [action] [options]")
    print()
    print("PLATFORMS:")
    print("  kling - Kling Image2Video processing")
    print("  vidu - Vidu Effects processing")
    print("  viduref - Vidu Reference processing")
    print("  nano - Google Flash/Nano Banana processing")
    print("  runway - Runway face swap processing")
    print("  genvideo - GenVideo image generation processing")
    print("  pixverse - Pixverse Effects processing")  # Add this line
    print("  all - Run all platforms")
    print()
    print("ACTIONS:")
    print("  process - Run API processors only")
    print("  report - Generate PowerPoint reports only")
    print("  auto - Run processor + generate report (default)")
    print()
    print("OPTIONS:")
    print("  --config FILE - Override config file path")
    print("  --parallel - Run platforms in parallel (for 'all')")
    print("  --verbose - Enable verbose logging")
    print()
    print("EXAMPLES:")
    print("  python runall.py nano report")
    print("  python runall.py kling process")
    print("  python runall.py vidu auto")
    print("  python runall.py viduref auto --verbose")
    print("  python runall.py pixverse process")  # Add this line
    print("  python runall.py all auto --parallel")
    print("  python runall.py runway process --config custom_runway_config.json")
    print("  python runall.py genvideo process")

def parse_arguments():
    """Parse command line arguments"""
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)

    args = {
        'platform': sys.argv[1].lower(),
        'action': sys.argv[2].lower() if len(sys.argv) > 2 else "auto",
        'config': None,
        'parallel': False,
        'verbose': False
    }

    # Parse options
    i = 3
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--config' and i + 1 < len(sys.argv):
            args['config'] = sys.argv[i + 1]
            i += 2
        elif arg == '--parallel':
            args['parallel'] = True
            i += 1
        elif arg == '--verbose':
            args['verbose'] = True
            i += 1
        else:
            logger.warning(f"Unknown option: {arg}")
            i += 1

    return args

def validate_arguments(args):
    """Validate parsed arguments"""
    valid_platforms = list(API_MAPPING.keys()) + ['all']
    valid_actions = ['process', 'report', 'auto']

    if args['platform'] not in valid_platforms:
        logger.error(f"Invalid platform: {args['platform']}")
        logger.error(f"Valid platforms: {', '.join(valid_platforms)}")
        return False

    if args['action'] not in valid_actions:
        logger.error(f"Invalid action: {args['action']}")
        logger.error(f"Valid actions: {', '.join(valid_actions)}")
        return False

    return True

def get_platforms_to_run(platform_arg):
    """Get list of platforms to run based on argument"""
    if platform_arg == 'all':
        return list(API_MAPPING.keys())
    else:
        return [platform_arg]

def run_processor(api_name, config_file=None):
    """Run API processor for given platform"""
    try:
        logger.info(f"🔄 Processing: {api_name.replace('_', ' ').title()}")

        processor = create_processor(api_name, config_file)
        success = processor.run()

        if success:
            logger.info(f"✅ {api_name} processing completed successfully")
        else:
            logger.error(f"❌ {api_name} processing failed")

        return success

    except Exception as e:
        logger.error(f"❌ {api_name} processing error: {e}")
        return False

def run_report_generator(api_name, config_file=None):
    """Run report generator for given platform"""
    try:
        logger.info(f"📊 Generating report: {api_name.replace('_', ' ').title()}")

        generator = create_report_generator(api_name, config_file)
        success = generator.run()

        if success:
            logger.info(f"✅ {api_name} report generated successfully")
        else:
            logger.error(f"❌ {api_name} report generation failed")

        return success

    except Exception as e:
        logger.error(f"❌ {api_name} report generation error: {e}")
        return False

def run_platform(platform, action, config_file=None):
    """Run processing and/or reporting for a single platform"""
    api_name = API_MAPPING[platform]

    # Use provided config or default
    if not config_file:
        config_file = CONFIG_MAPPING.get(api_name)

    # Check if config file exists
    if config_file and not Path(config_file).exists():
        logger.warning(f"⚠️ Config file not found: {config_file}")
        logger.info(f"Proceeding without config file for {platform}")
        config_file = None

    results = {}

    # Run processing if requested
    if action in ['process', 'auto']:
        results['processing'] = run_processor(api_name, config_file)

    # Run reporting if requested
    if action in ['report', 'auto']:
        results['reporting'] = run_report_generator(api_name, config_file)

    return results

def run_parallel(platforms, action, args):
    """Run platforms in parallel"""
    from concurrent.futures import ThreadPoolExecutor

    logger.info(f"🚀 Running {len(platforms)} platforms in parallel")

    all_results = {}

    with ThreadPoolExecutor(max_workers=min(4, len(platforms))) as executor:
        # Submit all tasks
        futures = {}
        for platform in platforms:
            config_file = args['config'] if args['config'] else CONFIG_MAPPING.get(API_MAPPING[platform])
            future = executor.submit(run_platform, platform, action, config_file)
            futures[future] = platform

        # Collect results
        for future in futures:
            platform = futures[future]
            try:
                results = future.result()
                all_results[platform] = results
            except Exception as e:
                logger.error(f"❌ {platform} failed with exception: {e}")
                all_results[platform] = {'processing': False, 'reporting': False}

    return all_results

def run_sequential(platforms, action, args):
    """Run platforms sequentially"""
    all_results = {}

    for i, platform in enumerate(platforms, 1):
        logger.info(f"{'='*60}")
        logger.info(f"PLATFORM {i}/{len(platforms)}: {platform.upper()}")
        logger.info("="*60)

        config_file = args['config'] if args['config'] else CONFIG_MAPPING.get(API_MAPPING[platform])
        results = run_platform(platform, action, config_file)
        all_results[platform] = results

    return all_results

def print_summary(all_results, action):
    """Print execution summary"""
    logger.info(f"{'='*60}")
    logger.info("EXECUTION SUMMARY")
    logger.info("="*60)

    total_platforms = len(all_results)

    if action in ['process', 'auto']:
        processing_success = sum(1 for results in all_results.values() 
                               if results.get('processing', False))
        logger.info(f"📊 Processing: {processing_success}/{total_platforms} successful")

        for platform, results in all_results.items():
            status = "✅ SUCCESS" if results.get('processing', False) else "❌ FAILED"
            logger.info(f"   {platform:10} → {status}")

    if action in ['report', 'auto']:
        reporting_success = sum(1 for results in all_results.values() 
                              if results.get('reporting', False))
        logger.info(f"📈 Reporting: {reporting_success}/{total_platforms} successful")

        for platform, results in all_results.items():
            status = "✅ GENERATED" if results.get('reporting', False) else "❌ FAILED"
            logger.info(f"   {platform:10} → {status}")

    # Overall success
    total_operations = 0
    successful_operations = 0

    for results in all_results.values():
        for operation, success in results.items():
            total_operations += 1
            if success:
                successful_operations += 1

    success_rate = (successful_operations / total_operations * 100) if total_operations > 0 else 0
    logger.info(f"🎯 Overall Success Rate: {successful_operations}/{total_operations} ({success_rate:.1f}%)")

    return successful_operations > 0

def main():
    """Main execution function"""
    # Parse arguments
    args = parse_arguments()

    # Set verbose logging if requested
    if args['verbose']:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("🔍 Verbose logging enabled")

    # Validate arguments
    if not validate_arguments(args):
        sys.exit(1)

    # Get platforms to run
    platforms = get_platforms_to_run(args['platform'])
    action = args['action']

    logger.info(f"🚀 Starting execution")
    logger.info(f"Platforms: {', '.join(platforms)}")
    logger.info(f"Action: {action}")

    # Run platforms
    if len(platforms) > 1 and args['parallel']:
        all_results = run_parallel(platforms, action, args)
    else:
        all_results = run_sequential(platforms, action, args)

    # Print summary
    success = print_summary(all_results, action)

    logger.info(f"🏁 Execution completed")
    return success

if __name__ == "__main__":
    try:
        sys.exit(0 if main() else 1)
    except KeyboardInterrupt:
        logger.info("\n⏹️ Execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)

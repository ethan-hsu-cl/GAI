"""Run all API processors and report generators - unified entry point."""

import sys
import logging
import subprocess
from pathlib import Path
from datetime import datetime

# Import from core (we're at Scripts/ root, so core/ is a subdirectory)
from core.factory import ProcessorFactory
from core.services.config_manager import ConfigManager

def run_api_processing(api_name: str, config_file: str) -> bool:
    """Run processing for a specific API."""
    print(f"🔄 Processing with {api_name.upper()}...")

    config = ConfigManager.load_config(config_file)
    if not config:
        print(f"❌ Failed to load config for {api_name}")
        return False

    processor = ProcessorFactory.create_processor(api_name, config)
    if not processor.initialize_client():
        print(f"❌ Failed to initialize {api_name} client")
        return False

    # Process tasks
    start_time = datetime.now()
    for i, task in enumerate(config.get('tasks', []), 1):
        processor.process_task(task, i, len(config['tasks']))

    duration = datetime.now() - start_time
    print(f"✅ {api_name.upper()} processing completed in {duration.total_seconds():.1f}s")
    return True

def run_api_report(api_name: str) -> bool:
    """Run report generation for a specific API."""
    print(f"📊 Generating report for {api_name.upper()}...")

    # Map API names to report generator scripts
    report_scripts = {
        'kling': 'reports/generate_kling_report.py',
        'nano_banana': 'reports/generate_nano_banana_report.py',
        'runway': 'reports/generate_runway_report.py',
        'vidu_effects': 'reports/generate_vidu_effects_report.py',
        'vidu_reference': 'reports/generate_vidu_reference_report.py',
        'genvideo': 'reports/generate_genvideo_report.py',
        'pixverse_effects': 'reports/generate_pixverse_effects_report.py',  # Added
    }

    if api_name not in report_scripts:
        print(f"❌ No report generator available for {api_name}")
        return False

    script_path = report_scripts[api_name]
    if not Path(script_path).exists():
        print(f"❌ Report script not found: {script_path}")
        return False

    try:
        # Run the report generator script
        result = subprocess.run([sys.executable, script_path], 
                               capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            print(f"✅ {api_name.upper()} report generated successfully")
            # Print any output from the report generator
            if result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    if 'report generated' in line.lower() or 'saved to' in line.lower():
                        print(f"📄 {line}")
            return True
        else:
            print(f"❌ Report generation failed for {api_name}")
            if result.stderr:
                print(f"Error: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        print(f"⏰ Report generation timeout for {api_name}")
        return False
    except Exception as e:
        print(f"❌ Failed to run report generator for {api_name}: {e}")
        return False

def run_api_auto(api_name: str, config_file: str) -> bool:
    """Run both processing and report generation for an API."""
    print(f"🚀 Auto mode: Processing + Report for {api_name.upper()}")

    # First run processing
    if not run_api_processing(api_name, config_file):
        print(f"❌ Auto mode failed: processing step failed for {api_name}")
        return False

    # Then generate report
    if not run_api_report(api_name):
        print(f"⚠️ Auto mode: processing succeeded but report generation failed for {api_name}")
        return False

    print(f"🎉 Auto mode completed successfully for {api_name.upper()}")
    return True

def show_usage():
    """Display usage information."""
    print("""
🔧 AI Media Processing Pipeline - Usage

Processing Commands:
  python runall.py kling process      # Process only
  python runall.py nano process       # Process only  
  python runall.py runway process     # Process only
  python runall.py vidu process       # Process only (vidu_effects)
  python runall.py ref process        # Process only (vidu_reference)
  python runall.py gen process        # Process only (genvideo)
  python runall.py pixverse process      # Process only (pixverse_effects)

Report Commands:
  python runall.py kling report       # Generate report only
  python runall.py nano report        # Generate report only
  python runall.py runway report      # Generate report only
  python runall.py pixverse report       # Generate report only

Auto Commands (Process + Report):
  python runall.py kling auto         # Process then generate report
  python runall.py nano auto          # Process then generate report
  python runall.py runway auto        # Process then generate report
  python runall.py vidu auto          # Process then generate report
  python runall.py ref auto           # Process then generate report
  python runall.py gen auto           # Process then generate report
  python runall.py pixverse auto         # Process then generate report

Batch Commands:
  python runall.py all process        # Process all APIs
  python runall.py all report         # Generate all reports
  python runall.py all auto           # Process + report for all APIs
  python runall.py                    # Default: process all APIs

Available APIs: kling, nano_banana, runway, vidu_effects, vidu_reference, genvideo, pixverse_effects
Short names: nano, vidu, ref, gen, pixverse
""")

def main():
    """Main entry point with enhanced command line argument handling."""
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    # API configuration mapping
    api_map = {
        'nano': 'nano_banana',
        'vidu': 'vidu_effects', 
        'ref': 'vidu_reference',
        'gen': 'genvideo',
        'pixverse': 'pixverse_effects',
    }

    config_files = {
        'kling': 'config/batch_config.json',
        'nano_banana': 'config/batch_nano_banana_config.json',
        'runway': 'config/batch_runway_config.json',
        'vidu_effects': 'config/batch_vidu_config.json',
        'vidu_reference': 'config/batch_vidu_reference_config.json',
        'genvideo': 'config/batch_genvideo_config.json',
        'pixverse_effects': 'config/batch_pixverse_config.json',  # Added
    }

    all_apis = list(config_files.keys())

    # Parse command line arguments
    if len(sys.argv) == 1:
        # Default behavior: process all APIs
        print("🚀 Default mode: Processing all APIs")
        success_count = 0
        for api_name, config_file in config_files.items():
            print(f"\n=== {api_name.upper()} ===")
            if run_api_processing(api_name, config_file):
                success_count += 1
        print(f"\n📊 Summary: {success_count}/{len(config_files)} APIs completed successfully")
        return

    if len(sys.argv) < 2:
        show_usage()
        return

    # Handle help requests
    if sys.argv[1].lower() in ['help', '-h', '--help']:
        show_usage()
        return

    # Parse API name and action
    api_arg = sys.argv[1].lower()
    action = sys.argv[2].lower() if len(sys.argv) > 2 else 'process'

    # Validate action
    if action not in ['process', 'report', 'auto']:
        print(f"❌ Invalid action '{action}'. Use: process, report, or auto")
        show_usage()
        return

    # Handle 'all' API requests
    if api_arg == 'all':
        print(f"🚀 Batch mode: {action} for all APIs")
        success_count = 0
        failed_apis = []

        for api_name, config_file in config_files.items():
            print(f"\n=== {api_name.upper()} ===")

            if action == 'process':
                success = run_api_processing(api_name, config_file)
            elif action == 'report':
                success = run_api_report(api_name)
            elif action == 'auto':
                success = run_api_auto(api_name, config_file)

            if success:
                success_count += 1
            else:
                failed_apis.append(api_name)

        # Summary
        print(f"\n📊 Batch Summary ({action.upper()}):")
        print(f"✅ Successful: {success_count}/{len(config_files)}")
        if failed_apis:
            print(f"❌ Failed: {', '.join(failed_apis)}")
        return

    # Handle single API requests
    api_name = api_map.get(api_arg, api_arg)

    if api_name not in config_files:
        print(f"❌ Unknown API: {api_arg}")
        print(f"Available APIs: {', '.join(config_files.keys())}")
        print(f"Short names: {', '.join(api_map.keys())}")
        return

    config_file = config_files[api_name]

    # Execute the requested action
    print(f"=== {api_name.upper()} - {action.upper()} ===")

    if action == 'process':
        run_api_processing(api_name, config_file)
    elif action == 'report':
        run_api_report(api_name)
    elif action == 'auto':
        run_api_auto(api_name, config_file)

if __name__ == "__main__":
    main()

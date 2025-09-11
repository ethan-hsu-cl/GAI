# AI Video Generation Automation Suite

A comprehensive automation toolkit for processing and reporting on AI video generation results from multiple platforms (Kling, Vidu, Nano Banana/Google Flash).

## 🚀 Quick Start

### Navigate to Scripts Directory

```bash
cd Scripts
```

### Simple Commands

```bash
# Process Nano Banana data and auto-generate report
python run_all_processors.py nano

# Just generate Nano Banana report (no processing)
python run_all_processors.py nano report

# Just run Nano Banana processor (no report)
python run_all_processors.py nano process

# Run processor + auto-generate report (explicit)
python run_all_processors.py nano auto
```

### All Platforms

```bash
# Run everything - all processors + all reports
python run_all_processors.py all

# Generate all reports only
python run_all_processors.py all report

# Run all processors only
python run_all_processors.py all process
```

### Platform-Specific Examples

```bash
# Kling workflow
python run_all_processors.py kling          # Process + Report
python run_all_processors.py kling process  # Process only
python run_all_processors.py kling report   # Report only

# Vidu workflow  
python run_all_processors.py vidu           # Process + Report
python run_all_processors.py vidu process   # Process only
python run_all_processors.py vidu report    # Report only

# Nano Banana workflow
python run_all_processors.py nano           # Process + Report
python run_all_processors.py nano process   # Process only  
python run_all_processors.py nano report    # Report only
```

### Command Reference

| Command | Action |
|---------|---------|
| `process` | Run data processors only (no reports) |
| `report` | Generate PowerPoint reports only (no processing) |
| `auto` | Run processor then auto-generate report (default behavior) |

### Typical Workflows

#### Development/Testing

```bash
# Test processing first
python run_all_processors.py nano process

# Then generate report if processing succeeded
python run_all_processors.py nano report
```

#### Production/Automation

```bash
# Complete end-to-end workflow
python run_all_processors.py nano auto
# or simply
python run_all_processors.py nano
```

#### Report Regeneration

```bash
# Regenerate reports after template changes
python run_all_processors.py all report
```

### Key Benefits of New Command Structure

1. **Simplified Syntax**: `nano report` instead of `nano --reports-only`
2. **Auto Mode**: Default behavior runs processing + reporting in one command
3. **Clearer Intent**: Commands clearly indicate what will happen
4. **Better Error Handling**: Each phase wrapped in try-catch blocks
5. **Flexible Workflows**: Easy to run individual steps or complete pipelines

## 📋 Prerequisites

### Required Python Packages

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install pillow python-pptx opencv-python pathlib dataclasses concurrent.futures
```

### Optional Dependencies

- **OpenCV (`cv2`)**: For video aspect ratio detection (auto-fallback if missing)
- **PIL/Pillow**: For image processing
- **python-pptx**: For PowerPoint generation

## 📁 Project Structure

```bash
project_root/
├── CL I2V/                    # CL video generations
│   ├── 0908 Hanabi_refine/
│   ├── 0908 Kabedon V2/
│   └── ...
├── Kling 1.6/                 # Kling 1.6 generations  
│   ├── 0901 Leaf Growth V1/
│   │   ├── Source/            # Input images (.jpg, .png, .webp)
│   │   ├── Generated_Video/   # Output videos (.mp4, .mov)
│   │   └── Metadata/         # Processing metadata (.json)
│   └── 0901 Leaf Growth V2/
├── Kling 2.1/                # Kling 2.1 generations
│   ├── 0811 Demon Slayer V3/
│   ├── 0815 Kabedon/
│   └── ...
├── Nano Banana/              # Nano Banana generations
│   ├── 0908 Figure Box/
│   │   ├── Source/           # Input images
│   │   ├── Generated_Output/ # Generated images/videos  
│   │   └── Metadata/        # Processing metadata
│   ├── 0910 Cosplay Event/
│   └── ...
├── Vidu/                     # Vidu effects
│   ├── 0829 8 Styles/
│   └── 0909 1 Style/
├── Wan2.2_vs_Kling/         # Comparison projects
│   ├── 0508 Reveal Me/
│   ├── 0908 Reveal Me New/
│   └── ...
├── Scripts/                  # **← WORK FROM HERE**
│   ├── run_all_processors.py        # Main orchestration script
│   ├── advanced_batch_processor.py  # Kling processor
│   ├── effect_processor.py          # Vidu processor  
│   ├── google_flash_processor.py    # Nano Banana processor
│   ├── nano_banana_auto_report.py   # Nano Banana reports
│   ├── vidu_auto_report.py         # Vidu reports
│   ├── auto_report_optimized.py    # Kling reports
│   ├── batch_config.json           # Kling configuration
│   ├── batch_vidu_config.json      # Vidu configuration
│   ├── batch_nano_banana_config.json # Nano Banana config
│   ├── I2V templates.pptx          # Standard template
│   ├── I2V Comparison Template.pptx # Comparison template
│   └── requirements.txt
└── Report/                   # Generated PowerPoint files
    ├── [0908] Nano Banana Figure Box.pptx
    ├── [0909] Kling 2.1 Angel.pptx  
    └── ...
```

## ⚙️ Configuration

### Configuration File Structure

Each platform requires a JSON configuration file in the `Scripts/` directory:

#### `batch_config.json` (Kling)

```json
{
    "template_path": "I2V templates.pptx",
    "comparison_template_path": "I2V Comparison Template.pptx",
    "output_directory": "/Users/ethanhsu/Desktop/GAI/Report",
    "model_version": "v2.1",
    "schedule": {
        "start_time": "",
        "comment": "Time format: HH:MM (24-hour format). Leave empty to start immediately"
    },
    "tasks": [
        {
            "folder": "../Wan2.2_vs_Kling/0508 Reveal Me",
            "prompt": "The main character stands up first. Suddenly, large fluttering white angel wings appear...",
            "negative_prompt": "transition, do a spin, spinning, turn around, blurry arms...",
            "design_link": "",
            "source_video_link": "",
            "reference_folder": "../Wan2.2_vs_Kling/0908 Reveal Me New",
            "use_comparison_template": true
        }
    ]
}
```

**Key Kling Features:**

- **Model Version**: Specify `"v1.6"` or `"v2.1"`
- **Comparison Mode**: Set `use_comparison_template: true` for 3-way comparisons
- **Custom Prompts**: Detailed positive and negative prompts per task
- **Reference Folders**: Point to comparison datasets
- **Scheduling**: Optional delayed execution with `start_time`

#### `batch_vidu_config.json` (Vidu)

```json
{
    "base_folder": "../Vidu/0909 1 Style",
    "output_directory": "/Users/ethanhsu/Desktop/GAI/Report",
    "template_path": "I2V templates.pptx",
    "prompt": "",
    "schedule": {
        "start_time": "",
        "comment": "Time format: HH:MM (24-hour format). Leave empty to start immediately"
    },
    "design_link": "https://platform.vidu.com/docs/templates",
    "source_video_link": "https://cyberlinkcorp-my.sharepoint.com/:f:/g/personal/...",
    "tasks": [
        {
            "category": "Funny",
            "effect": "Eat mushrooms, turn young",
            "prompt": ""
        }
    ]
}
```

**Key Vidu Features:**

- **Base Folder**: Single folder containing multiple effect subfolders
- **Effect Categorization**: Organize effects by category (Funny, Dramatic, etc.)
- **External Links**: Embed design documentation and source video links
- **Effect-Based Structure**: Each task represents a specific effect type

#### `batch_nano_banana_config.json` (Nano Banana)

```json
{
    "template_path": "I2V templates.pptx",
    "comparison_template_path": "I2V Comparison Template.pptx",
    "testbed": "http://192.168.4.3:8000/google_flash_image/",
    "output": {
        "directory": "/Users/ethanhsu/Desktop/GAI/Report"
    },
    "schedule": {
        "start_time": "",
        "comment": "Time format: HH:MM (24-hour format). Leave empty to start immediately"
    },
    "tasks": [
        {
            "folder": "../Nano Banana/0910 Cosplay Event",
            "prompt": "Generate a highly detailed photo of a girl cosplaying this illustration, at Comiket. Exactly replicate the same pose, body posture, hand gestures, facial expression, and camera framing as in the original illustration. Keep the same angle, perspective, and composition, without any deviation.",
            "reference_folder": "",
            "use_comparison_template": false,
            "design_link": "",
            "source_video_link": ""
        }
    ]
}
```

**Key Nano Banana Features:**

- **Testbed Integration**: Direct link to processing server
- **Detailed Prompts**: Comprehensive generation instructions per task
- **Comparison Support**: Optional 3-way comparison with reference folders
- **Flexible Templates**: Switch between 2-placeholder and 3-placeholder layouts
- **Comprehensive Comments**: Built-in documentation for configuration options

## 🎯 Features

### Processing Capabilities

- **Parallel processing** with ThreadPoolExecutor
- **Automatic file matching** between sources and outputs
- **Metadata extraction** from JSON files
- **Error handling** for failed generations
- **Progress logging** with detailed status updates
- **Scheduled execution** support (HH:MM format)
- **Model version selection** (Kling v1.6/v2.1)

### Report Generation

- **PowerPoint automation** with template support
- **Aspect ratio preservation** for images and videos
- **Video embedding** with poster frames
- **Error visualization** with styled failure indicators
- **Metadata display** (processing time, IDs, status)
- **Standardized naming** with date prefixes
- **Comparison mode** for A/B testing workflows

### Template System

- **Smart placeholder detection** and replacement
- **Fallback manual positioning** when templates unavailable
- **Dual template support** (standard vs comparison)
- **Hyperlink integration** for design and testbed links
- **Dynamic layout switching** based on comparison mode

## 📊 Output Examples

### Generated Reports

Reports are saved in the configured output directory with standardized filenames:

```bash
[0910] Kling 2.1 Reveal Me vs Reveal Me New.pptx
[0909] Vidu Effects 1 Style.pptx  
[0910] Nano Banana Cosplay Event.pptx
```

### Console Output

```bash
=== Running Kling BatchVideoProcessor ===
✓ Processed: ../Wan2.2_vs_Kling/0508 Reveal Me
✓ Processed: ../Wan2.2_vs_Kling/0515 Cheerleading V2

=== Generating Kling Report ===
✓ Saved: /Users/ethanhsu/Desktop/GAI/Report/[0508] Kling 2.1 Reveal Me vs Reveal Me New.pptx

📊 Processing: 2/2 successful
📈 Reports: 1/1 generated
```

## 📂 Expected Folder Structure Per Platform

### Kling Projects (`Kling 1.6/`, `Kling 2.1/`, `Wan2.2_vs_Kling/`)

```bash
0508 Reveal Me/
├── Source/              # Input images (.jpg, .png, .webp)
├── Generated_Video/     # Output videos (.mp4, .mov)  
└── Metadata/           # Processing metadata (.json)

# For comparison mode
0908 Reveal Me New/     # Reference folder
├── Source/
├── Generated_Video/
└── Metadata/
```

### Vidu Effects (`Vidu/`)

```bash
0909 1 Style/
├── Eat_mushrooms_turn_young/
│   ├── Source/          # Input images
│   ├── Generated_Video/ # Effect videos
│   └── Metadata/        # Processing logs
└── Another_Effect/
    ├── Source/
    ├── Generated_Video/
    └── Metadata/
```

### Nano Banana (`Nano Banana/`)

```bash
0910 Cosplay Event/
├── Source/              # Input images
├── Generated_Output/    # Generated images/videos
└── Metadata/           # Processing metadata (.json)
```

## 🔧 Troubleshooting

### Common Issues

#### "Configuration file missing"

- Ensure you're running from `Scripts/` directory
- Verify JSON config files exist and are valid
- Check file paths use `../` to reference parent directories

#### "Template not found"

- Ensure PowerPoint templates exist in `Scripts/` directory
- Check `template_path` and `comparison_template_path` in configuration files

#### "Output directory not accessible"

- Verify the absolute path in `output_directory` exists
- Check write permissions for the output directory
- Ensure parent directories exist

#### "No images found"

- Verify folder structure matches expected layout
- Check file paths in JSON config are relative to `Scripts/` directory
- Verify file extensions are supported (.jpg, .png, .webp)

#### "Video embedding failed"

- Ensure video files are in supported formats (.mp4, .mov)
- Check that poster images exist for video embedding

### Performance Tips

- Use `process` command to separate processing from reporting
- Process folders with fewer files first to test configuration
- Use `report` command to regenerate reports after template changes
- Enable parallel processing by ensuring adequate system resources
- Set `start_time` for scheduled execution during off-peak hours

## 📈 Advanced Usage

### Comparison Workflows

```bash
# Generate comparison reports with reference folders
python run_all_processors.py kling report    # Uses comparison_template when configured

# Process multiple comparison sets
python run_all_processors.py all process
python run_all_processors.py all report
```

### Scheduled Execution

Set `start_time` in configuration files:

```json
{
    "schedule": {
        "start_time": "02:30",
        "comment": "Start processing at 2:30 AM"
    }
}
```

### Custom Configuration

Modify JSON configuration files to:

- **Add new project folders** (use `../` for parent directories)
- **Configure absolute output paths** for centralized report storage
- **Set up comparison workflows** with reference folders
- **Customize prompts and negative prompts** for specific tasks
- **Enable scheduled execution** with start times
- **Integrate external links** for documentation and resources

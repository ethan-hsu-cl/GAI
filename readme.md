# AI Video Generation Automation Suite

A comprehensive automation toolkit for processing and reporting on AI video generation results from multiple platforms (Kling, Vidu, Nano Banana/Google Flash).

## 🚀 Quick Start

### Navigate to Scripts Directory

```bash
cd Scripts
```

### Basic Usage

```bash
# Run all processors and generate all reports
python run_all_processors.py all

# Run specific platform
python run_all_processors.py kling
python run_all_processors.py vidu  
python run_all_processors.py nano
```

### Advanced Usage

```bash
# Generate reports only (no processing)
python run_all_processors.py all --reports-only

# Run processing only (no reports)
python run_all_processors.py vidu --processing-only

# Regenerate specific report
python run_all_processors.py nano --reports-only
```

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
│   ├── 0908 Figure Box 2/
│   └── ...
├── Vidu/                     # Vidu effects
│   ├── 0829 8 Styles/
│   └── 0909 1 Style/
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
  "tasks": [
    {
      "folder": "../Kling 2.1/0909 Angel"
    },
    {
      "folder": "../Kling 2.1/0811 Demon Slayer V3"
    }
  ],
  "template_path": "I2V templates.pptx",
  "output_directory": "../Report/"
}
```

#### `batch_vidu_config.json` (Vidu)

```json
{
  "base_folder": "../Vidu/0909 1 Style",
  "tasks": [
    {
      "effect": "Parallax",
      "category": "Camera Movement"
    }
  ],
  "template_path": "I2V templates.pptx",
  "output_directory": "../Report/"
}
```

#### `batch_nano_banana_config.json` (Nano Banana)

```json
{
  "tasks": [
    {
      "folder": "../Nano Banana/0910 Figure Box 3",
      "design_link": "https://link-to-design",
      "source_video_link": "https://source-video-link",
      "use_comparison_template": false,
      "reference_folder": "../Nano Banana/0908 Figure Box 2"
    }
  ],
  "template_path": "I2V templates.pptx",
  "comparison_template_path": "I2V Comparison Template.pptx",
  "output": {
    "directory": "../Report/"
  },
  "testbed": "http://192.168.4.3:8000/video_effect/"
}
```

## 🎯 Features

### Processing Capabilities

- **Parallel processing** with ThreadPoolExecutor
- **Automatic file matching** between sources and outputs
- **Metadata extraction** from JSON files
- **Error handling** for failed generations
- **Progress logging** with detailed status updates

### Report Generation

- **PowerPoint automation** with template support
- **Aspect ratio preservation** for images and videos
- **Video embedding** with poster frames
- **Error visualization** with styled failure indicators
- **Metadata display** (processing time, IDs, status)
- **Standardized naming** with date prefixes

### Template System

- **Smart placeholder detection** and replacement
- **Fallback manual positioning** when templates unavailable
- **Comparison mode** for side-by-side analysis
- **Hyperlink integration** for design and testbed links

## 📊 Output Examples

### Generated Reports

Reports are saved in the `../Report/` directory with standardized filenames:

```bash
[0910] Kling 2.1 Angel.pptx
[0909] Vidu Effects 1 Style.pptx  
[0910] Nano Banana Figure Box 3.pptx
[0910] Nano Banana Figure Box 3 vs Figure Box 2.pptx  # Comparison mode
```

### Console Output

```bash
=== Running Kling BatchVideoProcessor ===
✓ Processed: ../Kling 2.1/0909 Angel
✓ Processed: ../Kling 2.1/0811 Demon Slayer V3

=== Generating Kling Report ===
✓ Saved: ../Report/[0909] Kling 2.1 Angel.pptx

📊 Processing: 2/2 successful
📈 Reports: 1/1 generated
```

## 📂 Expected Folder Structure Per Platform

### Kling Projects (`Kling 1.6/`, `Kling 2.1/`)

```bash
0909 Angel/
├── Source/              # Input images (.jpg, .png, .webp)
├── Generated_Video/     # Output videos (.mp4, .mov)  
└── Metadata/           # Processing metadata (.json)
```

### Vidu Effects (`Vidu/`)

```bash
0909 1 Style/
├── Effect1/
│   ├── Source/          # Input images
│   ├── Generated_Video/ # Effect videos
│   └── Metadata/        # Processing logs
└── Effect2/
    ├── Source/
    ├── Generated_Video/
    └── Metadata/
```

### Nano Banana (`Nano Banana/`)

```bash
0910 Figure Box 3/
├── Source/              # Input images
├── Generated_Output/    # Generated images/videos
└── Metadata/           # Processing metadata
```

## 🔧 Troubleshooting

### Common Issues

#### "Template not found"

- Ensure PowerPoint templates exist in `Scripts/` directory
- Check `template_path` in configuration files

#### "No images found"

- Verify folder structure matches expected layout
- Check file paths in JSON config are relative to `Scripts/` directory
- Verify file extensions are supported (.jpg, .png, .webp)

#### "Configuration file missing"

- Ensure you're running from `Scripts/` directory
- Verify JSON config files exist and are valid
- Check file paths use `../` to reference parent directories

#### "Video embedding failed"

- Ensure video files are in supported formats (.mp4, .mov)
- Check that poster images exist for video embedding

### Performance Tips

- Use `--processing-only` to separate processing from reporting
- Process folders with fewer files first to test configuration
- Use `--reports-only` to regenerate reports after template changes
- Enable parallel processing by ensuring adequate system resources

## 📈 Advanced Usage

### Batch Operations

```bash
# Process multiple platforms sequentially
python run_all_processors.py kling --processing-only
python run_all_processors.py vidu --processing-only  
python run_all_processors.py all --reports-only
```

### Integration with Testing Workflows

```bash
# In your CI/CD pipeline
python run_all_processors.py all || exit 1

# For automated testing reports
python run_all_processors.py vidu --reports-only
```

### Custom Configuration

Modify JSON configuration files to:

- Add new project folders (use `../` for parent directories)
- Change output directories
- Update template paths
- Configure comparison modes
- Set custom metadata fields

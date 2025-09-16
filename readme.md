# Automated Processing \& Reporting Automation Suite

A powerful Python automation framework for batch processing images and videos through multiple AI APIs (Kling 2.1, Google Flash/Nano Banana, Vidu Effects, Vidu Reference, and Runway) with automated PowerPoint report generation.

## 🚀 Quick Start

### **Basic Usage**

The scripts are run from the `Scripts/` directory using the `core/` subfolder:

```bash
# Navigate to Scripts directory first
cd Scripts

# Process and generate reports for a single API
python core/runall.py kling auto
python core/runall.py nano auto  
python core/runall.py vidu auto
python core/runall.py runway auto

# Process all APIs at once
python core/runall.py all auto

# Generate reports only (after processing)
python core/runall.py kling report
python core/runall.py nano report

# Process only (no reports)
python core/runall.py kling process
```

### **Advanced Usage**

```bash
# Run all APIs in parallel for faster execution
python core/runall.py all auto --parallel

# Use custom configuration file
python core/runall.py kling auto --config custom_config.json

# Enable verbose logging for debugging
python core/runall.py runway auto --verbose

# Combine options
python core/runall.py all auto --parallel --verbose
```

## 📋 Platform Commands

| Short Name | Full Name | Description |
| :-- | :-- | :-- |
| `kling` | Kling 2.1 | Image-to-video generation |
| `nano` | Nano Banana/Google Flash | Multi-image generation |
| `vidu` | Vidu Effects | Effect-based video generation |
| `viduref` | Vidu Reference | Reference-guided video generation |
| `runway` | Runway | Face swap and video processing |
| `all` | All Platforms | Process all APIs sequentially or in parallel |

## 📁 Project Structure

```bash
GAI/                                    # Project root
└── Scripts/                           # Main scripts directory
    ├── config/                        # Configuration files
    │   ├── batch_config.json         # Kling configuration
    │   ├── batch_nano_banana_config.json
    │   ├── batch_runway_config.json
    │   ├── batch_vidu_config.json
    │   └── batch_vidu_reference_config.json
    ├── core/                          # Core automation framework
    │   ├── api_definitions.json      # API specifications
    │   ├── runall.py                 # Main execution script
    │   ├── unified_api_processor.py  # API processing engine
    │   └── unified_report_generator.py # Report generation engine
    ├── processors/                    # Legacy individual processors
    ├── reports/                       # Legacy individual report generators
    ├── templates/                     # PowerPoint templates
    │   ├── I2V Comparison Template.pptx
    │   └── I2V templates.pptx
    └── requirements.txt
```

### **Task Data Folder Structure** (Kling, Nano Banana, Runway)

```bash
YourTaskFolder/
├── TaskName1/
│   ├── Source/              # Input images/videos
│   ├── Reference/           # Reference images (Runway only)
│   ├── Generated_Video/     # Auto-created output folder
│   └── Metadata/            # Auto-created metadata folder
├── TaskName2/
│   └── ...
└── config.json
```

### **Base Folder Structure** (Vidu Effects, Vidu Reference)

```bash
BaseFolder/
├── EffectName1/
│   ├── Source/              # Input images
│   ├── Reference/           # Reference images (Vidu Reference only)
│   ├── Generated_Video/     # Auto-created output folder
│   └── Metadata/            # Auto-created metadata folder
├── EffectName2/
│   └── ...
└── config.json
```

## ⚙️ Configuration Files

All configuration files are located in the `Scripts/config/` directory and follow API-specific naming conventions.

### **Kling Configuration** (`config/batch_config.json`)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "prompt": "Transform this portrait into a cinematic video",
      "negative_prompt": "blurry, low quality",
      "design_link": "https://your-design-link.com",
      "source_video_link": "https://source-video-link.com",
      "reference_folder": "/path/to/reference/folder",
      "use_comparison_template": true
    }
  ],
  "model_version": "v2.1",
  "testbed": "http://192.168.4.3:8000/kling/"
}
```

### **Nano Banana Configuration** (`config/batch_nano_banana_config.json`)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "prompt": "Generate variations of this image",
      "design_link": "https://design-link.com",
      "additional_images": {
        "image1": "/path/to/additional1.jpg",
        "image2": "/path/to/additional2.jpg"
      }
    }
  ],
  "testbed": "http://192.168.4.3:8000/google_flash_image/"
}
```

### **Vidu Effects Configuration** (`config/batch_vidu_config.json`)

```json
{
  "base_folder": "/path/to/BaseFolder",
  "tasks": [
    {
      "category": "Cinematic",
      "effect": "Zoom In",
      "prompt": "Dramatic zoom effect"
    },
    {
      "category": "Artistic", 
      "effect": "Watercolor",
      "prompt": "Watercolor painting style"
    }
  ]
}
```

### **Runway Configuration** (`config/batch_runway_config.json`)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "prompt": "Face swap transformation",
      "pairing_strategy": "one_to_one"
    }
  ],
  "model": "gen4_aleph",
  "ratio": "1280:720",
  "public_figure_moderation": "low"
}
```

## 📊 Report Generation

Reports are automatically generated in PowerPoint format with:

- **Title slides** with date and API information
- **Side-by-side comparisons** of source and generated content
- **Metadata tracking** (processing times, success rates, file details)
- **Hyperlinks** to design files and source materials
- **Error reporting** for failed generations

### **Report Templates**

PowerPoint templates are located in `Scripts/templates/`:

- `I2V templates.pptx` - Standard template
- `I2V Comparison Template.pptx` - Comparison template

### **Report Output**

- **Default location**: `/Users/ethanhsu/Desktop/GAI/Report/` (configurable)
- **Naming format**: `[MMDD] API Name Style Name.pptx`

## 🔧 Installation \& Setup

### **Prerequisites**

```bash
# Navigate to Scripts directory
cd Scripts

# Install required Python packages
pip install -r requirements.txt

# For video processing (required for Runway and video features)
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows - Download from https://ffmpeg.org/
```

### **System Requirements**

- **Python 3.8+**
- **FFmpeg** (for video processing)
- **8GB+ RAM** (for parallel processing)
- **Network access** to API endpoints (default: <http://192.168.4.3:8000/>)

### **Initial Setup**

1. Clone/download the automation suite
2. Navigate to the `Scripts/` directory
3. Create configuration files in `config/` directory
4. Set up folder structure according to your API choice
5. Place input files in appropriate `Source/` folders
6. Run validation: `python core/runall.py [platform] process --verbose`

## 📈 File Validation \& Requirements

### **Image Requirements**

- **Formats**: JPG, JPEG, PNG, BMP, TIFF, WebP (varies by API)
- **Size limits**: 10MB (Kling/Nano), 50MB (Vidu APIs)
- **Minimum dimensions**: 300px (Kling), 100px (Nano), 128px (Vidu), 320px (Runway)
- **Aspect ratios**: Varies by API (automatically validated)

### **Video Requirements** (Runway)

- **Formats**: MP4, MOV, AVI, MKV, WebM
- **Size limit**: 500MB
- **Duration**: 1-30 seconds
- **Minimum resolution**: 320px

## 🎯 API-Specific Features

### **Kling 2.1**

- **Streaming downloads** for large video files
- **Dual save logic** (URL + local file fallback)
- **Model version selection** (v2.1 default)
- **Negative prompt support**

### **Nano Banana/Google Flash**

- **Base64 image handling** for generated outputs
- **Multiple image generation** per input
- **Additional image inputs** support
- **Testbed URL override** capability

### **Vidu Effects**

- **Effect-based processing** with categories
- **Parallel validation** for faster setup
- **Auto aspect ratio detection**
- **Effect name normalization**

### **Vidu Reference**

- **Multi-image reference system** (up to 6 references)
- **Smart reference finding** with naming conventions
- **Automatic aspect ratio selection** (16:9, 9:16, 1:1)
- **Reference image validation**

### **Runway**

- **Video + reference image pairing**
- **Automatic aspect ratio optimization**
- **Pairing strategies**: one-to-one, all-combinations
- **Face swap with moderation settings**

## 🔍 Troubleshooting

### **Common Issues**

```bash
# Ensure you're in the Scripts directory
cd Scripts

# Check file validation
python core/runall.py [platform] process --verbose

# Test single API connection
python core/unified_api_processor.py kling

# Validate configuration
python -c "import json; print(json.load(open('config/batch_config.json')))"

# Check folder structure
ls -la YourTaskFolder/
```

### **Error Messages**

- **"Config error"**: Check JSON syntax in configuration files
- **"Missing source"**: Ensure `Source/` folder exists with valid files
- **"Invalid images found"**: Check file formats and sizes
- **"Client init failed"**: Verify API endpoint accessibility

### **Performance Optimization**

- Use `--parallel` flag for multiple APIs
- Enable `parallel_validation` in API definitions
- Ensure sufficient disk space for outputs
- Monitor network bandwidth for large file processing

## 📝 Output Files

### **Generated Content**

- **Videos**: `{filename}_generated.mp4` (Kling), `{filename}_{effect}_effect.mp4` (Vidu)
- **Images**: `{filename}_image_{index}.{ext}` (Nano Banana)
- **Metadata**: `{filename}_metadata.json` (all APIs)

### **Reports**

- **Location**: Configured in `core/api_definitions.json` or config files
- **Default**: `/Users/ethanhsu/Desktop/GAI/Report/`
- **Format**: PowerPoint (.pptx) with embedded media

## 🚀 Command Reference

### **Core Execution**

```bash
# Always run from Scripts directory
cd Scripts

# Basic commands
python core/runall.py [platform] [action] [options]
```

### **Supported Platforms**

- `kling` - Kling 2.1 Image2Video
- `nano` - Google Flash/Nano Banana
- `vidu` - Vidu Effects
- `viduref` - Vidu Reference
- `runway` - Runway face swap
- `all` - All platforms

### **Available Actions**

- `process` - Run API processing only
- `report` - Generate PowerPoint reports only
- `auto` - Process + generate reports (default)

### **Options**

- `--config FILE` - Custom configuration file
- `--parallel` - Run platforms in parallel (for 'all')
- `--verbose` - Enable detailed logging

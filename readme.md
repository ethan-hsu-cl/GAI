# Automated Processing & Reporting Automation Suite

A powerful Python automation framework for batch processing images and videos through multiple AI APIs with automated PowerPoint report generation. Supports 7 AI platforms: Kling 2.1, Pixverse, GenVideo, Google Flash/Nano Banana, Vidu Effects, Vidu Reference, and Runway.

## 🚀 Quick Start

### **Basic Usage**

The scripts are run from the `Scripts/` directory using the `core/` subfolder:

```bash
# Navigate to Scripts directory first
cd Scripts

# Process and generate reports for a single API
python core/runall.py kling auto
python core/runall.py pixverse auto
python core/runall.py genvideo auto
python core/runall.py nano auto  
python core/runall.py vidu auto
python core/runall.py viduref auto
python core/runall.py runway auto

# Process all APIs at once
python core/runall.py all auto

# Generate reports only (after processing)
python core/runall.py kling report
python core/runall.py pixverse report

# Process only (no reports)
python core/runall.py kling process
python core/runall.py genvideo process
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
| `kling` | Kling 2.1 | Image-to-video generation with v2.1 model |
| `pixverse` | Pixverse v4.5 | Effect-based video generation with custom effects |
| `genvideo` | GenVideo | Image-to-image transformation (Gashapon style) |
| `nano` | Nano Banana/Google Flash | Multi-image generation with AI models |
| `vidu` | Vidu Effects | Effect-based video generation with categories |
| `viduref` | Vidu Reference | Multi-reference guided video generation |
| `runway` | Runway Gen4 | Video processing with face swap and effects |
| `all` | All Platforms | Process all APIs sequentially or in parallel |

## Video Download Command Example

```bash
# File download command example:
yt-dlp -f "bv*[vcodec~='^(h264|avc)']+ba[acodec~='^(mp?4a|aac)']" "link" --cookies-from-browser chrome -o "%(title)s.%(ext)s"
```

## 📁 Project Structure

```bash
GAI/                                    # Project root
└── Scripts/                           # Main scripts directory
    ├── config/                        # Configuration files
    │   ├── batch_config.json         # Kling configuration
    │   ├── batch_pixverse_config.json # Pixverse configuration
    │   ├── batch_genvideo_config.json # GenVideo configuration
    │   ├── batch_nano_banana_config.json # Nano Banana configuration
    │   ├── batch_runway_config.json  # Runway configuration
    │   ├── batch_vidu_config.json    # Vidu Effects configuration
    │   └── batch_vidu_reference_config.json # Vidu Reference configuration
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

### **Task Data Folder Structure** (Kling, GenVideo, Nano Banana, Runway)

```bash
YourTaskFolder/
├── TaskName1/
│   ├── Source/              # Input images/videos
│   ├── Reference/           # Reference images (Runway only)
│   ├── Generated_Video/     # Auto-created output folder (videos)
│   ├── Generated_Image/     # Auto-created output folder (GenVideo)
│   └── Metadata/            # Auto-created metadata folder
├── TaskName2/
│   └── ...
└── config.json
```

### **Base Folder Structure** (Vidu Effects, Vidu Reference, Pixverse)

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
  "tasks": [{"folder": "/path/to/TaskName1", "prompt": "Generate variations"}],
  "testbed": "http://192.168.4.3:8000/google_flash_image/"
}
```

### **Vidu Effects Configuration** (`config/batch_vidu_config.json`)

```json
{
  "base_folder": "/path/to/BaseFolder",
  "tasks": [{"category": "Cinematic", "effect": "Zoom In", "prompt": "Dramatic zoom effect"}]
}
```

### **Pixverse Configuration** (`config/batch_pixverse_config.json`)

```json
{
  "base_folder": "/path/to/BaseFolder",
  "tasks": [{"style": "Anime", "effect": "Dynamic Motion", "prompt": "Add dynamic motion"}],
  "testbed": "http://192.168.4.3:8000/pixverse_image/"
}
```

### **GenVideo Configuration** (`config/batch_genvideo_config.json`)

```json
{
  "tasks": [{"folder": "/path/to/TaskName1", "prompt": "Transform into Gashapon style"}],
  "testbed": "http://192.168.4.3:8000/genvideo/"
}
```

### **Runway Configuration** (`config/batch_runway_config.json`)

```json
{
  "tasks": [{"folder": "/path/to/TaskName1", "prompt": "Face swap", "pairing_strategy": "one_to_one"}],
  "model": "gen4_aleph", "ratio": "1280:720"
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
- **Size limits**:
  - 10MB (Kling/Nano)
  - 20MB (Pixverse/GenVideo)
  - 50MB (Vidu APIs)
  - 100MB (Runway)
- **Minimum dimensions**:
  - 300px (Kling)
  - 100px (Nano/Pixverse/GenVideo)
  - 128px (Vidu)
  - 320px (Runway)
- **Aspect ratios**: Varies by API (automatically validated)

### **Video Requirements** (Runway)

- **Formats**: MP4, MOV, AVI, MKV, WebM
- **Size limit**: 500MB
- **Duration**: 1-30 seconds
- **Minimum resolution**: 320px

## 🎯 API-Specific Features

- **Kling 2.1**: Streaming downloads, dual save logic, v2.1 model, negative prompt support
- **Pixverse v4.5**: Custom effects/styles, VideoID extraction, base folder structure
- **GenVideo**: Gashapon transformation, image-to-image generation, design link tracking
- **Nano Banana**: Base64 handling, multiple images per input, additional image support
- **Vidu Effects**: Effect-based processing, parallel validation, auto aspect ratio
- **Vidu Reference**: Multi-image references (up to 6), smart reference finding, aspect ratio selection
- **Runway**: Video + image pairing, face swap, Gen4 Aleph model, one-to-one/all-combinations

## 🔍 Troubleshooting

```bash
# Validate files and configuration
python core/runall.py [platform] process --verbose

# Test API connection
python core/unified_api_processor.py [platform]
```

**Common Errors:**

- **"Config error"**: Check JSON syntax | **"Missing source"**: Add `Source/` folder with files
- **"Invalid images"**: Verify formats/sizes | **"Client init failed"**: Check API endpoint

**Performance Tips:** Use `--parallel` flag, enable `parallel_validation`, ensure disk space

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

```bash
# Always run from Scripts directory
cd Scripts

# Basic syntax
python core/runall.py [platform] [action] [options]

# Actions: process | report | auto (default)
# Options: --config FILE | --parallel | --verbose
# Platforms: See Platform Commands table above
```

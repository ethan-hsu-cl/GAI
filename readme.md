# Automated Processing & Reporting Automation Suite

A powerful Python automation framework for batch processing images and videos through multiple AI APIs with automated PowerPoint report generation. Supports 9 AI platforms: Kling 2.1, Pixverse, GenVideo, Google Flash/Nano Banana, Vidu Effects, Vidu Reference, Runway, Wan 2.2, and Google Veo.

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
python core/runall.py wan auto
python core/runall.py veo auto

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
| `klingfx` | Kling Effects | Apply premade video effects to images |
| `pixverse` | Pixverse v4.5 | Effect-based video generation with custom effects |
| `genvideo` | GenVideo | Image-to-image transformation (Gashapon style) |
| `nano` | Nano Banana/Google Flash | Multi-image generation with AI models |
| `vidu` | Vidu Effects | Effect-based video generation with categories |
| `viduref` | Vidu Reference | Multi-reference guided video generation |
| `runway` | Runway Gen4 | Video processing with face swap and effects |
| `wan` | Wan 2.2 | Image + video cross-matching with motion animation |
| `veo` | Google Veo | Text-to-video generation with AI models |
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
    │   ├── batch_vidu_reference_config.json # Vidu Reference configuration
    │   ├── batch_wan_config.json     # Wan 2.2 configuration
    │   └── batch_veo_config.json     # Google Veo configuration
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

### **Task Data Folder Structure** (Kling, GenVideo, Nano Banana, Runway, Wan 2.2)

```bash
YourTaskFolder/
├── TaskName1/
│   ├── Source/              # Input images/videos
│   ├── Source Image/        # Source images (Wan 2.2 only)
│   ├── Source Video/        # Source videos (Wan 2.2 only)
│   ├── Additional/          # Additional images for multi-image mode (Nano Banana only)
│   ├── Reference/           # Reference images (Runway only)
│   ├── Generated_Video/     # Auto-created output folder (videos)
│   ├── Generated_Output/    # Auto-created output folder (Nano Banana)
│   ├── Generated_Image/     # Auto-created output folder (GenVideo)
│   └── Metadata/            # Auto-created metadata folder
├── TaskName2/
│   └── ...
└── config.json
```

**Notes:**

- **Source/**: Primary input files (required for most APIs)
- **Source Image/** and **Source Video/**: Separate folders for Wan 2.2 (images and videos are cross-matched)
- **Additional/**: Optional folder for Nano Banana multi-image mode (contains 2nd and 3rd images)
- **Reference/**: Optional folder for Runway tasks requiring reference images
- Output folders are automatically created based on API type

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

**Common Configuration Fields** (applicable to most APIs):

- **`design_link`**: URL to design reference materials (optional)
- **`source_video_link`**: URL to source video reference (optional)
- **`reference_folder`**: Path to reference comparison folder (optional)
- **`use_comparison_template`**: Enable comparison template for reports (boolean)

### **Kling Configuration** (`config/batch_config.json`)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "prompt": "Transform this portrait into a cinematic video",
      "negative_prompt": "blurry, low quality"
    }
  ],
  "model_version": "v2.1",
  "testbed": "http://192.168.31.40:8000/kling/"
}
```

### **Kling Effects Configuration** (`config/batch_kling_effects_config.yaml`)

Applies premade video effects to images. Supports both preset effects and custom effect names.

```yaml
base_folder: ../Media Files/Kling Effects/1127 Test
testbed: http://192.168.31.40:8000/kling/

# Global settings
duration: '5'

# Effect selection (custom_effect has priority over effect)
effect: 3d_cartoon_1      # Preset effect from dropdown
custom_effect: ''          # Custom effect name (priority if specified)

tasks:
  - style_name: 3D Cartoon
    effect: 3d_cartoon_1
    custom_effect: ''       # Leave empty to use preset 'effect'
  
  - style_name: Custom Style
    effect: ''
    custom_effect: my_custom_effect  # Custom effect takes priority
```

**Effect Selection:**
- Use `effect` to select from 100+ preset effects (e.g., `3d_cartoon_1`, `anime_figure`, `japanese_anime_1`)
- Use `custom_effect` to specify a custom effect name (takes priority over `effect`)

**Available Preset Effects (partial list):**
`3d_cartoon_1`, `3d_cartoon_2`, `anime_figure`, `japanese_anime_1`, `american_comics`, `angel_wing`, `baseball`, `boss_coming`, `car_explosion`, `celebration`, `demon_transform`, `disappear`, `emoji`, `firework`, `gallery_ring`, `halloween_escape`, `jelly_jiggle`, `magic_broom`, `mushroom`, `pixelpixel`, `santa_gifts`, `steampunk`, `vampire_transform`, `zombie_transform`, and many more.

**Folder Structure:**
```
BaseFolder/
├── StyleName1/
│   ├── Source/              # Input images
│   ├── Generated_Video/     # Auto-created output folder
│   └── Metadata/            # Auto-created metadata folder
├── StyleName2/
│   └── ...
```

### **Nano Banana Configuration** (`config/batch_nano_banana_config.json`)

#### **Single-Image Mode** (Basic)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "prompt": "Generate variations",
      "use_multi_image": false
    }
  ],
  "testbed": "http://192.168.31.40:8000/google_gemini_image/"
}
```

#### **Multi-Image Mode** (Advanced)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "prompt": "Generate variations with multiple images",
      "use_multi_image": true,
      "multi_image_config": {
        "enabled": true,
        "mode": "sequential",
        "folders": ["/path/to/Additional/images/folder1"],
        "allow_duplicates": false
      }
    }
  ],
  "testbed": "http://192.168.31.40:8000/google_gemini_image/",
  "output": {
    "directory": "/Users/ethanhsu/Desktop/GAI/Report",
    "group_tasks_by": 2
  }
}
```

**Multi-Image Configuration Options:**

- **`mode`**:
  - `"sequential"`: Deterministic pairing - same source always paired with same additional images (recommended)
  - `"random_pairing"`: Random selection from additional image pools
- **`folders`**: Array of folder paths containing additional images (up to 2 additional images supported)
- **`allow_duplicates`**: `false` to avoid repeating combinations in random mode, `true` to allow
- **`group_tasks_by`**: Combine N tasks into one report (0 = individual reports per task)

### **Vidu Effects Configuration** (`config/batch_vidu_config.json`)

```json
{
  "base_folder": "/path/to/BaseFolder",
  "tasks": [
    {
      "category": "Cinematic",
      "effect": "Zoom In",
      "prompt": "Dramatic zoom effect with cinematic lighting"
    }
  ],
  "testbed": "http://192.168.31.40:8000/video_effect/"
}
```

### **Vidu Reference Configuration** (`config/batch_vidu_reference_config.json`)

```json
{
  "base_folder": "/path/to/BaseFolder",
  "tasks": [
    {
      "effect": "Style Transfer",
      "prompt": "Apply artistic style from reference images",
      "model": "viduq1",
      "duration": 5,
      "resolution": "1080p"
    }
  ],
  "testbed": "http://192.168.31.40:8000/video_effect/"
}
```

**Model Options:** `"viduq1"` (default)

**Duration Options:** `4`, `5`, `8` seconds

**Resolution Options:** `"720p"`, `"1080p"`

**Aspect Ratios:** Auto-detected or manual selection (`"9:16"`, `"16:9"`, `"1:1"`)

### **Pixverse Configuration** (`config/batch_pixverse_config.json`)

```json
{
  "base_folder": "/path/to/BaseFolder",
  "tasks": [
    {
      "effect": "Dynamic Motion",
      "prompt": "Add dynamic motion with anime style",
      "custom_effect_id": "",
      "negative_prompt": "static, blurry, low quality"
    }
  ],
  "testbed": "http://192.168.31.40:8000/pixverse_image/"
}
```

**API Parameters:**

- **Model**: v4.5
- **Duration**: 5s
- **Quality**: 720p
- **Motion Mode**: normal
- **Custom Effect ID**: Optional custom effect identifier for specialized effects

### **GenVideo Configuration** (`config/batch_genvideo_config.json`)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "img_prompt": "Generate a portrait-oriented image of a realistic, clear plastic gashapon capsule",
      "model": "gpt-image-1",
      "quality": "low"
    }
  ],
  "testbed": "http://192.168.31.40:8000/genvideo/"
}
```

**Model Options:**

- `"gpt-image-1"`: GPT-based image generation
- `"gemini-2.5-flash-image-preview"`: Gemini-based image generation

**Quality Options:** `"low"`, `"medium"`, `"high"`

### **Runway Configuration** (`config/batch_runway_config.json`)

```json
{
  "tasks": [
    {
      "folder": "/path/to/TaskName1",
      "prompt": "Face swap effect",
      "pairing_strategy": "one_to_one",
      "requires_reference": true
    }
  ],
  "model": "gen4_aleph",
  "ratio": "1280:720",
  "testbed": "http://192.168.31.40:8000/runway/"
}
```

**Pairing Strategies:**

- **`one_to_one`**: Pairs each video with one reference image (1:1 mapping)
- **`all_combinations`**: Generates all possible video-reference combinations (N×M outputs)

**Available Ratios:** `1280:720`, `720:1280`, `1104:832`, `960:960`, `832:1104`, `1584:672`, `848:480`, `640:480`

### **Wan 2.2 Configuration** (`config/batch_wan_config.json`)

```json
{
  "tasks": [
    {
      "folder": "../Media Files/Wan 2.2/1111 Test",
      "prompt": "The person is dancing, realistic video.",
      "embed": "Hello!!",
      "num_outputs": 2,
      "seed": "-1",
      "animation_mode": "move"
    }
  ],
  "testbed": "http://210.244.31.18:7008/"
}
```

**Animation Modes:**

- **`move`**: Motion-based animation mode
- **`mix`**: Mixed animation effects

**Folder Structure:**

Each task folder must contain:

- `Source Image/`: Source images for processing
- `Source Video/`: Source videos for motion reference

**Cross-Matching Behavior:**

Wan 2.2 automatically cross-matches all images with all videos:

- 4 images × 5 videos = 20 total generations
- Each combination creates a unique animated output

**Parameters:**

- **`prompt`**: Text description of the desired animation
- **`embed`**: Embedding parameter (typically `"Hello!!"`)
- **`num_outputs`**: Number of output variations (default: 2)
- **`seed`**: Random seed for generation (`"-1"` for random)
- **`animation_mode`**: `"move"` or `"mix"`

### **Veo Configuration** (`config/batch_veo_config.json`)

```json
{
  "tasks": [
    {
      "prompt": "A serene landscape with mountains and a lake at sunset",
      "negative_prompt": "",
      "model_id": "veo-3.1-generate-001",
      "duration_seconds": 8,
      "aspect_ratio": "16:9",
      "resolution": "1080p",
      "compression_quality": "optimized",
      "seed": 0,
      "enhance_prompt": true,
      "generate_audio": false,
      "person_generation": "allow_all",
      "output_folder": "../Media Files/Veo/Test1/Generated_Video"
    }
  ],
  "testbed": "http://192.168.31.40:8000/google_veo/"
}
```

**Model Options:**

- `"veo-2.0-generate-001"`: Veo 2.0 base model
- `"veo-3.0-generate-001"`: Veo 3.0 base model
- `"veo-3.0-fast-generate-001"`: Veo 3.0 fast generation
- `"veo-3.0-generate-preview"`: Veo 3.0 preview model
- `"veo-3.0-fast-generate-preview"`: Veo 3.0 fast preview
- `"veo-3.1-generate-preview"`: Veo 3.1 preview model (latest)
- `"veo-3.1-fast-generate-preview"`: Veo 3.1 fast preview

**Aspect Ratio Options:** `"16:9"`, `"9:16"`

**Resolution Options:** `"720p"`, `"1080p"`

**Compression Quality:** `"optimized"`, `"lossless"` (Veo 3+ only)

**Person Generation Options:** `"default"`, `"allow_adult"`, `"dont_allow"`, `"allow_all"`

**Parameters:**

- **`prompt`**: Text description of the video to generate (required)
- **`negative_prompt`**: Elements to avoid in generation (optional)
- **`model_id`**: AI model to use for generation
- **`duration_seconds`**: Video duration in seconds (numeric value)
- **`aspect_ratio`**: Video aspect ratio
- **`resolution`**: Output video resolution
- **`compression_quality`**: Video compression level (Veo 3+ only)
- **`seed`**: Random seed for reproducibility (0 for random)
- **`output_storage_uri`**: Cloud storage URI for output (optional)
- **`enhance_prompt`**: Auto-enhance prompt with AI (true/false)
- **`generate_audio`**: Generate audio for the video (true/false)
- **`person_generation`**: Control person generation in videos
- **`output_folder`**: Path where generated videos will be saved

**Note:** Veo is a **text-to-video** API, so no input images/videos are required. Each task generates one video from a text prompt.

## 📊 Report Generation

Reports are automatically generated in PowerPoint format with:

- **Title slides** with date and API information
- **Side-by-side comparisons** of source and generated content
- **Metadata tracking** (processing times, success rates, file details)
- **Hyperlinks** to design files and source materials
- **Error reporting** for failed generations

### **Templates & Output**

PowerPoint templates are located in `Scripts/templates/`:

- `I2V templates.pptx` - Standard template
- `I2V Comparison Template.pptx` - Comparison template

**Output Details:**

- **Default location**: `/Users/ethanhsu/Desktop/GAI/Report/` (configurable in `core/api_definitions.json` or config files)
- **Naming format**: `[MMDD] API Name Task Name.pptx`
- **Grouped reports**: When `group_tasks_by` > 0, multiple tasks combined into one report

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
- **Network access** to API endpoints (default: <http://192.168.31.40:8000/>)

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
  - 10MB (Kling)
  - 20MB (Pixverse)
  - 32MB (Nano Banana)
  - 50MB (GenVideo, Vidu Effects, Vidu Reference)
  - 500MB (Runway)
- **Minimum dimensions**:
  - 300px (Kling)
  - 100px (Nano Banana)
  - 128px (Pixverse, GenVideo, Vidu Effects, Vidu Reference)
  - 320px (Runway)
- **Aspect ratios**: Varies by API (automatically validated)
  - Kling: 0.4 - 2.5
  - Vidu Effects/Reference: 0.25 - 4.0
  - Pixverse: 0.25 - 4.0
  - Nano/GenVideo/Runway: No strict limits

### **Video Requirements** (Runway)

- **Formats**: MP4, MOV, AVI, MKV, WebM
- **Size limit**: 500MB
- **Duration**: 1-30 seconds
- **Minimum resolution**: 320px

## 🎯 API-Specific Features

- **Kling 2.1**: Streaming downloads, dual save logic, v2.1 model support, negative prompt support, custom duration/CFG settings
- **Kling Effects**: 100+ premade video effects, custom effect name support, base folder structure, automatic error data dump on failure
- **Pixverse v4.5**: Custom effects/styles, VideoID extraction, base folder structure, parallel validation, v4.5 model
- **GenVideo**: Gashapon transformation, image-to-image generation, design link tracking, multiple AI model support (GPT/Gemini)
- **Nano Banana**: Multi-image support (up to 3 images), sequential/random pairing modes, base64 image handling, deterministic reproducible outputs, grouped report generation
- **Vidu Effects**: Effect-based processing, parallel validation, auto aspect ratio detection, category organization
- **Vidu Reference**: Multi-image references (up to 6), smart reference finding, aspect ratio selection, multilingual prompt support
- **Runway Gen4**: Video + image pairing strategies (one-to-one/all-combinations), face swap, multiple aspect ratios, Gen4 Aleph model
- **Wan 2.2**: Automatic image cropping to video aspect ratio, image-video cross-matching, dual animation modes (move/mix), two-step API workflow
- **Google Veo**: Text-to-video generation (no input files required), multiple model versions (2.0 to 3.1), prompt enhancement, optional audio generation, person generation controls, lossless compression (Veo 3+)

### **Deterministic Processing**

All APIs use **deterministic file sorting** to ensure:

- ✅ **Reproducible results** - Same inputs always produce same outputs
- ✅ **Consistent pairing** - Multi-image modes use consistent image combinations across runs
- ✅ **Cross-platform stability** - Same behavior on different machines/file systems
- ✅ **Sequential ordering** - Files processed in alphabetical order by filename (case-insensitive)

This is particularly important for:

- **Nano Banana sequential mode**: Same source file always paired with same additional images
- **Vidu Reference**: Consistent reference image selection
- **Runway pairing**: Predictable video-reference combinations
- **Wan 2.2 cross-matching**: Consistent image-video pairing order
- **Report generation**: Consistent slide ordering across regenerations

## 🔍 Troubleshooting

**Common Errors:**

- **"Config error"**: Check JSON syntax | **"Missing source"**: Add `Source/` folder with files
- **"Invalid images"**: Verify formats/sizes | **"Client init failed"**: Check API endpoint

**Performance Tips:** Use `--parallel` flag, enable `parallel_validation`, ensure disk space

## 📝 Output Files

### **Generated Content**

- **Videos**:
  - Kling: `{filename}_generated.mp4`
  - Vidu Effects: `{filename}_{effect}_effect.mp4`
  - Vidu Reference: `{filename}_{effect}_reference.mp4`
  - Pixverse: `{filename}_{effect}.mp4`
  - Runway: `{filename}_runway.mp4` or `{filename}__{reference_name}_runway.mp4`
- **Images**:
  - Nano Banana: `{filename}_image_{index}.{ext}` (multiple images per source)
  - GenVideo: `{filename}_generated.{ext}`
- **Metadata**: `{filename}_metadata.json` (all APIs)

### **Metadata Content**

Each metadata JSON file includes:

- **Success status** and error messages (if any)
- **Processing time** and timestamp
- **API parameters** used (prompt, model, settings)
- **Additional images used** (Nano Banana multi-image mode)
- **Generated file names** and counts
- **Attempt count** and retry information
- **Source file information** and links

## 🔧 Advanced Features & Architecture

### **Handler System**

The framework uses an auto-discovery handler system for API processing:

- **`HandlerRegistry`** - Automatically discovers and registers API handlers from the `handlers/` directory
- **`BaseAPIHandler`** - Base class providing common processing logic (file validation, metadata saving, error handling)
- **Individual Handlers** - API-specific handlers (e.g., `KlingHandler`, `NanoBananaHandler`) override only unique behavior

**Key Methods:**

- `process()` - Process a single file with retry logic
- `process_task()` - Process entire task with file iteration
- `_make_api_call()` - API-specific call (override in subclasses)
- `_handle_result()` - API-specific result parsing (override in subclasses)

### **Report Generation System**

The unified report generator (`UnifiedReportGenerator`) provides:

**Core Features:**

- **`MediaPair`** dataclass - Unified data structure for all API types
- **Template-based slides** - Automatic placeholder detection and media insertion
- **Multi-API support** - Single codebase handles all 9+ API types
- **Grouped reports** - Combine multiple tasks into one presentation
- **Smart sorting** - Groups combination APIs (Wan, Runway) by video/reference

**Performance Optimizations:**

- `configure_performance(batch_size, max_workers, show_progress)` - Tune processing speed
- Parallel metadata loading (40-50% faster)
- Parallel frame extraction for videos
- Batch aspect ratio computation
- Automatic image format conversion (AVIF/WEBP/HEIC → JPG/PNG)

**Utility Functions:**

- `create_grouped_presentation()` - Multi-task combined reports
- `ensure_supported_img_format()` - PowerPoint compatibility
- `cleanup_caches()`, `cleanup_temp_frames()` - Memory management

### **Core Processor Features**

The unified API processor (`UnifiedAPIProcessor`) includes:

**Automatic Conversions:**

- `_convert_image_to_jpg()` - Auto-converts unsupported formats (AVIF, WEBP, HEIC) to JPG
- `_get_video_info()` - Extracts video metadata using FFprobe

**Smart Processing:**

- `_group_endframe_pairs()` - Pairs start/end images for Kling Endframe
- `get_optimal_runway_ratio()` - Finds best aspect ratio match for Runway
- `_get_files_by_type()` - Universal file retrieval with auto-conversion
- System sleep prevention using `wakepy` library (optional dependency)

**Data Handling:**

- `_capture_all_api_fields()` - Captures complete API response data
- `_make_json_serializable()` - Converts complex objects for JSON storage
- Universal metadata saving across all API types

### **Factory Functions**

Simplified object creation:

```python
# Create API processor
from core.unified_api_processor import create_processor
processor = create_processor("nano_banana", "config/custom.yaml")

# Create report generator
from core.unified_report_generator import create_report_generator
generator = create_report_generator("kling", "config/custom.yaml")
```

### **Command-Line Utilities**

The `runall.py` script provides:

- **Parallel execution** - `--parallel` flag runs multiple APIs simultaneously
- **Custom configs** - `--config FILE` override default configuration
- **Verbose logging** - `--verbose` for detailed debug output
- **Execution summaries** - Success rates and per-platform status
- **Input validation** - Validates platforms, actions, and options

### **Test Utilities**

- **`Scripts/test_nano_api.py`** - Nano Banana API testing and validation script

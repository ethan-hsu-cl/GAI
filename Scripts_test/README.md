# Automated Image/Video Processing & Report Generation Framework

A consolidated, enterprise-grade automation framework for processing images/videos through multiple AI APIs and generating PowerPoint reports. Designed for testing engineers and automation workflows.

## 🏗️ Architecture Overview

This framework provides a **unified, scalable architecture** that consolidates multiple AI API processors and report generators into a maintainable system.

### Core Components

- **unified_api_processor.py** - Universal API processing engine
- **unified_report_generator.py** - Universal PowerPoint report generator  
- **api_definitions.json** - Centralized API configuration
- **runall.py** - Master controller for batch operations
- **Individual wrapper scripts** - Backward-compatible entry points

## 🎯 Supported APIs

| API | Processing | Reporting | Description |
|-----|------------|-----------|-------------|
| **Kling** | ✅ | ✅ | Image2Video generation with reference comparison |
| **Nano Banana** | ✅ | ✅ | Google Flash image processing with multiple outputs |
| **Vidu Effects** | ✅ | ✅ | Video effects with categorized processing |
| **Vidu Reference** | ✅ | ✅ | Reference-based video generation with multi-image input |
| **Runway** | ✅ | ✅ | Face swap video processing with reference pairing |

## 📁 Directory Structure

```bash
project/
├── Core System
│   ├── unified_api_processor.py      # Universal processing engine
│   ├── unified_report_generator.py   # Universal report generator
│   ├── api_definitions.json          # API configuration
│   └── runall.py                     # Master controller
│
├── Processing Wrappers
│   ├── run_kling.py                  # Kling processor entry point
│   ├── run_nano_banana.py           # Nano Banana processor entry point
│   ├── run_vidu_effects.py         # Vidu Effects processor entry point
│   ├── run_vidu_reference.py       # Vidu Reference processor entry point
│   └── run_runway.py               # Runway processor entry point
│
├── Report Wrappers
│   ├── generate_kling_report.py     # Kling report generator
│   ├── generate_nano_banana_report.py # Nano Banana report generator
│   ├── generate_vidu_effects_report.py # Vidu Effects report generator
│   ├── generate_vidu_reference_report.py # Vidu Reference report generator
│   └── generate_runway_report.py    # Runway report generator
│
└── Configuration Files
    ├── batch_config.json             # Kling configuration
    ├── batch_nano_banana_config.json # Nano Banana configuration
    ├── batch_vidu_config.json       # Vidu Effects configuration
    ├── batch_vidu_reference_config.json # Vidu Reference configuration
    └── batch_runway_config.json     # Runway configuration
```

## 🚀 Quick Start

### 1. Basic Usage

Run a single API with automatic report generation:

```bash
python runall.py kling auto
python runall.py nano auto
python runall.py vidu auto
```

### 2. Processing Only

```bash
python runall.py kling process
python runall.py runway process
```

### 3. Reporting Only

```bash
python runall.py vidu report
python runall.py viduref report
```

### 4. Run All APIs

```bash
# Sequential execution
python runall.py all auto

# Parallel execution (faster)
python runall.py all auto --parallel
```

## 🔧 Advanced Usage

### Custom Configuration

```bash
python runall.py kling auto --config custom_kling_config.json
python runall.py runway process --config /path/to/runway_config.json
```

### Verbose Logging

```bash
python runall.py nano auto --verbose
python runall.py all auto --parallel --verbose
```

### Individual Script Usage

```bash
# Direct processing
python run_kling.py
python run_runway.py

# Direct reporting
python generate_kling_report.py
python generate_vidu_effects_report.py
```

### Advanced CLI Usage

```bash
# Universal processor (new capability)
python unified_api_processor.py --api kling

# Universal report generator (new capability)  
python unified_report_generator.py nano_banana
```

## 📋 Command Reference

### Platform Codes

- `kling` - Kling Image2Video processing
- `vidu` - Vidu Effects processing  
- `viduref` - Vidu Reference processing
- `nano` - Google Flash/Nano Banana processing
- `runway` - Runway face swap processing
- `all` - All platforms

### Actions

- `process` - Run API processors only
- `report` - Generate PowerPoint reports only
- `auto` - Run processing + generate reports (default)

### Options

- `--config FILE` - Override default config file
- `--parallel` - Run multiple platforms in parallel
- `--verbose` - Enable detailed logging

## 🏗️ Configuration

### API Definitions

The `api_definitions.json` file contains centralized configuration for all APIs:

```json
{
  "kling": {
    "endpoint": "http://192.168.4.3:8000/kling/",
    "validation": {
      "max_size_mb": 10,
      "min_dimension": 300
    },
    "report": {
      "template_path": "I2V templates.pptx",
      "use_comparison": true
    }
  }
}
```

### Individual API Configs

Each API has its own configuration file:

- `batch_config.json` - Kling settings
- `batch_nano_banana_config.json` - Nano Banana settings
- `batch_vidu_config.json` - Vidu Effects settings
- `batch_vidu_reference_config.json` - Vidu Reference settings
- `batch_runway_config.json` - Runway settings

## 📊 Folder Structure Requirements

### Standard APIs (Kling, Nano Banana, Runway)

```bash
Task_Folder/
├── Source/              # Input images/videos
├── Generated_Video/     # Output videos (created automatically)
├── Metadata/           # Processing metadata (created automatically)
└── Reference/          # Reference images (for Runway)
```

### Base Folder APIs (Vidu Effects, Vidu Reference)

```bash
Base_Folder/
├── Effect_Name_1/
│   ├── Source/         # Input images
│   ├── Generated_Video/ # Output videos
│   ├── Metadata/       # Processing metadata
│   └── Reference/      # Reference images (Vidu Reference only)
└── Effect_Name_2/
    ├── Source/
    ├── Generated_Video/
    └── ...
```

## 📈 Report Generation

### PowerPoint Templates

- **Standard Template** (`templates/I2V templates.pptx`) - 2-way comparison
- **Comparison Template** (`templates/I2V Comparison Template.pptx`) - 3-way comparison

### Report Features

- ✅ Automatic aspect ratio preservation
- ✅ Error visualization for failed generations
- ✅ Metadata display (processing time, success status)
- ✅ Hyperlink integration (design links, testbed URLs)
- ✅ Consistent formatting across all APIs

### Output Location

Reports are saved to the configured output directory:

- Default: `/Users/ethanhsu/Desktop/GAI/Report`
- Configurable per API in config files

## 🔧 Dependencies

### Required Python Packages

```bash
pip install python-pptx pillow gradio-client requests pathlib
```

### Optional Dependencies

```bash
pip install opencv-python  # For video frame extraction
```

### System Requirements

- Python 3.8+
- Access to API endpoints (configured in api_definitions.json)
- PowerPoint templates in working directory

## 🚨 Troubleshooting

### Common Issues

#### Config File Not Found

```bash
⚠️ Config file not found: batch_config.json
Proceeding without config file for kling
```

**Solution**: Ensure config files are in the working directory or specify path with `--config`

#### API Endpoint Connection Error

```bash
❌ Client init failed: Connection refused
```

**Solution**: Check API endpoints in `api_definitions.json` and ensure services are running

#### Template File Missing

```bash
❌ Template file not found: I2V templates.pptx
```

**Solution**: Ensure PowerPoint templates are in the working directory

#### Permission Denied on Output

```bash
❌ Save failed: Permission denied
```

**Solution**: Check write permissions for output directory

### Debug Mode

Enable verbose logging for detailed troubleshooting:

```bash
python runall.py kling auto --verbose
```

### Log Analysis

- ✅ `SUCCESS` - Operation completed successfully
- ❌ `FAILED` - Operation failed (check logs for details)
- ⚠️ `WARNING` - Non-critical issue (operation may continue)
- 🔄 `Processing` - Currently running
- 📊 `Generating report` - Creating PowerPoint presentation

## 🧪 Testing & Validation

### File Validation

The system automatically validates:

- File size limits (per API requirements)
- Image dimensions and aspect ratios
- Video duration and format compatibility
- Folder structure completeness

### Error Handling

- **Automatic retry** with exponential backoff
- **Graceful degradation** for missing files
- **Comprehensive error reporting** in logs and presentations
- **Partial success handling** (some items succeed, others fail)

### Performance Features

- **Parallel processing** for multiple platforms
- **Caching** for aspect ratio calculations
- **Optimized file operations** with threading
- **Memory-efficient** large file handling

## 🔄 Migration from Original Scripts

### Backward Compatibility

All existing scripts continue to work unchanged:

```bash
# Old method (still works)
python advanced_batch_processor.py
python auto_report_optimized.py

# New unified method  
python run_kling.py
python generate_kling_report.py
```

### Configuration Compatibility

All existing configuration files work without modification. The system automatically detects and uses your current settings.

### Gradual Migration

You can migrate gradually:

1. **Start**: Use `runall.py` for convenience
2. **Adopt**: Use individual wrapper scripts
3. **Advanced**: Use unified processors directly

## 📚 API-Specific Notes

### Kling Image2Video

- Supports negative prompts
- Reference folder comparison
- Model version selection (v1.6, v2.1)

### Nano Banana (Google Flash)

- Multiple generated images per source
- Base64 image handling
- Additional image inputs support

### Vidu Effects

- Base folder structure with effect categorization
- Automatic effect discovery
- Category-based organization

### Vidu Reference  

- Multi-image reference sets
- Section slides by effect style
- Automatic aspect ratio detection

### Runway Face Swap

- Video + reference image pairing
- Multiple pairing strategies
- First-frame extraction for video thumbnails

## 🎯 Best Practices

### For Testing Engineers

1. **Use `--verbose` flag** for debugging
2. **Run individual APIs first** before batch processing
3. **Validate folder structure** before processing
4. **Monitor logs** for performance bottlenecks
5. **Use parallel execution** for large batches

### For Production Use

1. **Configure appropriate timeouts** in api_definitions.json
2. **Set up proper logging** infrastructure  
3. **Monitor disk space** for output directories
4. **Use configuration version control**
5. **Implement health checks** for API endpoints

### Performance Optimization

1. **Use SSD storage** for temporary files
2. **Adjust parallel workers** based on system resources
3. **Configure appropriate batch sizes**
4. **Monitor memory usage** for large video files
5. **Use caching** for repeated operations

## 🚀 Future Enhancements

### Planned Features

- [ ] Web dashboard for monitoring
- [ ] Database integration for metrics
- [ ] Custom template designer
- [ ] Automated testing suite
- [ ] Docker containerization
- [ ] Cloud deployment support

### Adding New APIs

To add a new API:

1. Add API definition to `api_definitions.json`
2. Create wrapper scripts using templates
3. Add processing methods to unified processor
4. Test with sample data
5. Update documentation

---

## 📞 Support

For issues, questions, or contributions:

- Check troubleshooting section above
- Review log files with `--verbose` flag
- Validate configuration files format
- Ensure all dependencies are installed

---

**Built for testing engineers who demand reliability, scalability, and maintainability in their automation workflows.** 🚀

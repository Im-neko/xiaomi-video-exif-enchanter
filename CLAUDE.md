# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python tool that extracts timestamp information from Xiaomi home camera (C301) videos using OCR, then embeds them as EXIF metadata. The project provides two specialized scripts for different use cases:

### Available Scripts
1. **`exif_enchanter.py`** - Standard OCR-based processing (recommended for production)
2. **`exif_enchanter_ocr.py`** - Enhanced OCR-only version with multiple preprocessing techniques and early exit optimization

The core functionality involves reading timestamp text from the first frame, converting from JST to UTC, and using FFmpeg to embed proper EXIF metadata.

## Common Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Install with dev dependencies
pip install -e .[dev]

# Format code
black .
isort .

# Lint code
flake8 .
mypy .
```

### Testing
```bash
# Run all tests (includes tests/ subdirectory)
python -m unittest discover -s tests -p "test_*.py" -v

# Run all tests from root directory
python -m unittest discover -s . -p "test_*.py" -v

# Run specific test categories
python -m unittest tests.test_exif_enhancer -v
python -m unittest tests.test_batch_processing -v
python -m unittest tests.test_xiaomi_integration -v

# Test different script versions with sample video
python exif_enchanter.py sample.mp4 --debug
python exif_enchanter_ocr.py sample.mp4 --debug --early-exit-threshold 0.8
```

### Docker Usage
```bash
# Standard CPU processing
docker-compose run --rm xiaomi-exif-enhancer sample.mp4 --location "Test"

# GPU-accelerated processing
docker-compose -f docker-compose.gpu.yml run --rm xiaomi-exif-enhancer sample.mp4

# Batch processing
docker-compose run --rm xiaomi-exif-enhancer --batch /app/input --output-dir /app/output
```

## Architecture

### Core Processing Chain
1. **Frame Extraction** (`exif_enhancer.py:extract_first_frame`) - Extract first frame using OpenCV
2. **Timestamp Cropping** (`exif_enhancer.py:crop_timestamp_area`) - Crop top-left corner containing timestamp
3. **OCR Processing** (`exif_enhancer.py:extract_timestamp_with_ocr`) - Use EasyOCR to read timestamp text
4. **Timezone Conversion** (`exif_enhancer.py:parse_timestamp`) - Convert JST to UTC 
5. **EXIF Embedding** (`exif_enhancer.py:embed_exif_with_ffmpeg`) - Use FFmpeg to embed metadata

### Key Components

#### Core Classes (Available in all scripts)
- **`EasyOCRSingleton`** - Manages OCR engine instances to avoid memory overhead
- **`VideoErrorHandler`** - Centralized error handling with comprehensive error types
- **`BatchProcessor`** - Handles parallel processing of multiple files with progress tracking
- **`FileManager`** - File operations and path management
- **`ProgressManager`** - Progress reporting for batch operations

#### Script-Specific Classes
- **`XiaomiVideoExifEnchanter`** - Standard OCR processing class (`exif_enchanter.py`)
- **`XiaomiVideoExifEnchanterOCR`** - Enhanced OCR processing class with 24 preprocessing variants and early exit optimization (`exif_enchanter_ocr.py`)

### Docker Architecture
- **Multi-stage builds** for optimized image sizes
- **GPU support** with RTX 50 series optimizations (sm_120, CUDA 12.8)
- **Health checks** and proper error handling in containers
- **Pre-downloaded OCR models** to improve startup performance

### Error Handling
The `VideoErrorHandler` class defines comprehensive error types:
- `FRAME_EXTRACTION_FAILED` - OpenCV frame extraction issues
- `OCR_FAILED` - EasyOCR processing failures  
- `TIMESTAMP_PARSE_FAILED` - Timestamp parsing/timezone conversion issues
- `FFMPEG_FAILED` - FFmpeg EXIF embedding failures
- `FILE_NOT_FOUND`, `PERMISSION_DENIED` - File system issues

## Key Implementation Details

### OCR Configuration
- **EasyOCR** is the primary OCR engine with English/Japanese language support
- **Singleton pattern** prevents multiple OCR instances consuming excessive memory
- **Tesseract** is available as fallback OCR engine
- **Timestamp format**: Expected pattern `@ YYYY/MM/DD HH.MM.SS` in top-left corner

### Timezone Handling  
- Timestamps in videos are in **JST (Japan Standard Time)**
- Automatically converted to **UTC** for proper EXIF metadata
- Uses Python's `datetime` and `pytz` for accurate timezone conversion

### Performance Optimizations
- **Parallel processing** for batch operations using ThreadPoolExecutor
- **EasyOCR singleton** to reuse loaded models across processing
- **Docker multi-stage builds** with dependency caching
- **GPU acceleration** support for compatible hardware

### File Naming Convention
Output files follow pattern: `{original_name}_enhanced.{ext}` when not explicitly specified.

## Development Notes

### Testing Strategy
- **Unit tests** for individual components (`tests/test_exif_enhancer.py`)
- **Integration tests** using the included `sample.mp4` test file (`tests/test_sample_video.py`)
- **Batch processing tests** for multi-file scenarios (`tests/test_batch_processing.py`)
- **Issue-specific tests** for regression prevention (`tests/test_issue_*.py`)
- **Performance tests** for optimization validation (`tests/test_performance_*.py`)
- **OCR accuracy tests** with various preprocessing techniques (`tests/test_ocr_accuracy.py`)
- **Error handling tests** for comprehensive failure scenarios (`tests/test_video_error_handling.py`)
- Sample video contains timestamp `2025/05/28 19:41:14 JST` for consistent test results

### Test Categories
- **Core functionality**: Frame extraction, OCR processing, EXIF embedding
- **Batch processing**: Multi-file processing, error recovery, progress tracking
- **OCR improvements**: Various preprocessing techniques, confidence thresholds
- **File handling**: Path validation, output generation, error scenarios
- **Integration**: End-to-end processing with real video files

### GPU Support Details
- **RTX 50 series optimized**: Full CUDA 12.8 and compute capability sm_120 support
- **PyTorch nightly required**: `pip install --pre torch --index-url https://download.pytorch.org/whl/nightly/cu128`
- **Automatic Mixed Precision (AMP)**: 16-bit training for 2x speed improvement
- **Gradient accumulation**: Large effective batch sizes with limited memory
- **TensorFloat-32 (TF32)**: Hardware-accelerated matrix operations
- **cuDNN benchmark**: Automatic convolution optimization
- **DataLoader optimizations**: pin_memory, num_workers, prefetch_factor
- **Performance**: 8-10x speedup on RTX 5070 Ti vs CPU
- **Graceful fallback**: Automatic CPU processing when GPU unavailable

### Dependencies Management
- **Core dependencies**: OpenCV, EasyOCR, piexif, ffmpeg-python, NumPy, Pillow
- **Dev dependencies**: pytest, black, isort, flake8, mypy for code quality
- **System requirements**: FFmpeg and Tesseract must be installed separately

## Enhanced OCR Features

### Script Selection Guide

#### When to Use Each Script

**`exif_enchanter.py` (Standard OCR)**
- ✅ Production environments
- ✅ Stable, well-tested processing
- ✅ Lower resource requirements
- ✅ Single OCR pass

**`exif_enchanter_ocr.py` (Enhanced OCR)**
- ✅ Maximum OCR accuracy needed
- ✅ 24 preprocessing techniques with early exit optimization
- ✅ Consensus scoring for multiple OCR results
- ✅ Support for both EasyOCR and Tesseract
- ✅ Complex timestamp formats
- ✅ Parallel processing support with `--max-workers`

### Enhanced OCR Usage
```bash
# Basic enhanced OCR
python exif_enchanter_ocr.py sample.mp4 --debug

# Early exit optimization (stops when high confidence result found)
python exif_enchanter_ocr.py sample.mp4 --early-exit-threshold 0.8

# Parallel batch processing
python exif_enchanter_ocr.py --batch ./input --output ./output --max-workers 4

# GPU acceleration
python exif_enchanter_ocr.py sample.mp4 --gpu
```

### Enhanced OCR Architecture
- **24 preprocessing variants**: Super resolution, contrast enhancement, noise reduction, etc.
- **Early exit optimization**: Stops processing when high confidence results are found
- **Consensus scoring**: Combines results from multiple preprocessing techniques
- **Parallel processing**: Thread-safe multi-worker support
- **Process-safe OCR**: Independent EasyOCR instances for each worker
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python tool that extracts timestamp information from Xiaomi home camera (C301) videos using OCR and/or Machine Learning models, then embeds them as EXIF metadata. The project provides three specialized scripts for different use cases:

### Available Scripts
1. **`exif_enchanter.py`** - Standard OCR-based processing (recommended for production)
2. **`exif_enchanter_ocr.py`** - Enhanced OCR-only version with multiple preprocessing techniques
3. **`exif_enchanter_ml.py`** - ML model-based processing with OCR fallback for maximum accuracy

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
python exif_enchanter_ocr.py sample.mp4 --debug
python exif_enchanter_ml.py sample.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth --debug

# Test ML model functionality
python test_ml_model.py -v
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
- **`XiaomiVideoExifEnchanterOCR`** - Enhanced OCR processing class (`exif_enchanter_ocr.py`)
- **`XiaomiVideoExifEnchanterML`** - ML-based processing class (`exif_enchanter_ml.py`)
- **`XiaomiTimestampDataExtractor`** - ML training data extraction from processed videos
- **`XiaomiTimestampCRNN`** - Machine learning model for improved timestamp recognition

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
- **ML dependencies**: PyTorch, scikit-learn for machine learning functionality
- **Dev dependencies**: pytest, black, isort, flake8, mypy for code quality
- **System requirements**: FFmpeg and Tesseract must be installed separately

## Machine Learning Enhancement

### Script Selection Guide

#### When to Use Each Script

**`exif_enchanter.py` (Standard OCR)**
- ✅ Production environments
- ✅ Stable, well-tested processing
- ✅ Lower resource requirements
- ✅ No ML dependencies needed

**`exif_enchanter_ocr.py` (Enhanced OCR)**
- ✅ Maximum OCR accuracy needed
- ✅ Multiple preprocessing techniques
- ✅ Support for both EasyOCR and Tesseract
- ✅ Complex timestamp formats

**`exif_enchanter_ml.py` (ML-based)**
- ✅ Highest accuracy requirements
- ✅ ML training environment available
- ✅ GPU processing capability
- ✅ Fallback to OCR when ML fails

### ML Model Training
The project includes ML-based timestamp recognition improvements:

```bash
# Train ML model from successful processing results
python timestamp_ml_trainer.py --output-dir ./output --epochs 100

# Test ML model accuracy (best performing model - 100% accuracy)
python test_ml_model.py --model-path models/fixed_xiaomi_timestamp_model.pth

# Use ML model for enhanced processing
python exif_enchanter_ml.py sample.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth

# Install RTX 5070 Ti PyTorch support (see RTX5070Ti_GPU_OPTIMIZATION.md)
pip install --pre torch --index-url https://download.pytorch.org/whl/nightly/cu128
```

### ML Architecture
- **`XiaomiTimestampCRNN`** - CRNN-CTC model with attention for sequence recognition
- **`XiaomiTimestampDataExtractor`** - Extracts training data from successfully processed videos
- **`XiaomiTimestampTrainer`** - GPU-optimized trainer with AMP and gradient accumulation
- **Data augmentation** - Rotation, scaling, noise addition for robust training
- **Model persistence** - Trained models saved as `.pth` files for reuse

### GPU Training Optimizations
- **Automatic Mixed Precision**: RTX 5070 Ti Tensor Core utilization
- **Gradient accumulation**: Effective batch sizes up to 128 with 16GB VRAM
- **DataLoader optimization**: Non-blocking transfers, parallel workers
- **Performance benchmarks**: 674.1 samples/sec training throughput
- **Memory efficiency**: 1.8GB / 16.3GB VRAM usage during training
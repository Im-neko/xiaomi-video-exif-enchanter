#!/bin/bash
set -e

# Xiaomi Video EXIF Enhancer Docker Entrypoint Script

echo "🎬 Xiaomi Video EXIF Enhancer Container Started"
echo "================================================"

# 環境情報の表示
echo "📋 Container Information:"
echo "  Python Version: $(python --version)"
echo "  FFmpeg Version: $(ffmpeg -version | head -n1)"
echo "  Working Directory: $(pwd)"
echo "  User: $(whoami)"
echo "  Timezone: $TZ"

# ディレクトリの状態確認
echo ""
echo "📁 Directory Status:"
echo "  Input Directory: /app/input"
if [ -d "/app/input" ]; then
    INPUT_COUNT=$(find /app/input -name "*.mp4" -o -name "*.MP4" 2>/dev/null | wc -l)
    echo "    - Exists: ✓"
    echo "    - MP4 files found: $INPUT_COUNT"
    if [ $INPUT_COUNT -gt 0 ]; then
        echo "    - Files:"
        find /app/input -name "*.mp4" -o -name "*.MP4" 2>/dev/null | head -5 | sed 's/^/      /'
        if [ $INPUT_COUNT -gt 5 ]; then
            echo "      ... and $((INPUT_COUNT - 5)) more files"
        fi
    fi
else
    echo "    - Status: ❌ Not found"
fi

echo "  Output Directory: /app/output"
if [ -d "/app/output" ]; then
    echo "    - Exists: ✓"
    echo "    - Writable: $([ -w /app/output ] && echo '✓' || echo '❌')"
else
    echo "    - Status: ❌ Not found"
    echo "    - Creating output directory..."
    mkdir -p /app/output
    echo "    - Created: ✓"
fi

# サンプルファイルの確認
echo ""
echo "🎥 Sample File Status:"
if [ -f "/app/sample.mp4" ]; then
    SAMPLE_SIZE=$(stat -c%s "/app/sample.mp4" 2>/dev/null || echo "unknown")
    echo "  - sample.mp4: ✓ (Size: $SAMPLE_SIZE bytes)"
else
    echo "  - sample.mp4: ❌ Not found"
fi

echo ""
echo "🚀 Starting Application..."
echo "================================================"

# 引数の処理
if [ $# -eq 0 ]; then
    echo "ℹ️  No arguments provided, showing help:"
    echo ""
    exec python exif_enhancer.py --help
elif [ "$1" = "bash" ] || [ "$1" = "sh" ]; then
    echo "🐚 Starting interactive shell..."
    exec /bin/bash
elif [ "$1" = "test" ]; then
    echo "🧪 Running tests..."
    exec python -m unittest discover -v
elif [ "$1" = "sample" ]; then
    echo "🎯 Processing sample video..."
    if [ -f "/app/sample.mp4" ]; then
        exec python exif_enhancer.py sample.mp4 --location "Docker Sample Test" --debug
    else
        echo "❌ sample.mp4 not found"
        exit 1
    fi
else
    echo "▶️  Executing: python exif_enhancer.py $@"
    exec python exif_enhancer.py "$@"
fi
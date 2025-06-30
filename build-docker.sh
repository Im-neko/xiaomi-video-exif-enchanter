#!/bin/bash
# Docker イメージビルド用スクリプト

echo "🐳 Xiaomi Video EXIF Enhancer Docker イメージをビルドします..."

# ビルドオプションを選択
echo "ビルドオプションを選択してください:"
echo "1) 標準版 (CPU)"
echo "2) GPU版 (RTX 50シリーズ対応)"
echo "3) GPU版 マルチステージ (高速ビルド + 最小サイズ)"
echo "4) CPU版 マルチステージ (最小サイズ)"

read -p "選択 (1-4): " choice

case $choice in
    1)
        echo "📦 標準版をビルドします..."
        cd docker
        docker compose -f docker-compose.yml build
        ;;
    2)
        echo "🎮 GPU版 (RTX 50シリーズ対応) をビルドします..."
        cd docker
        docker compose -f docker-compose.gpu.yml build
        ;;
    3)
        echo "🚀 GPU版 マルチステージ (高速ビルド + 最小サイズ) をビルドします..."
        cd docker
        docker compose -f docker-compose.gpu.multi.yml build
        ;;
    4)
        echo "⚡ CPU版 マルチステージをビルドします..."
        docker build -f docker/Dockerfile.multi -t xiaomi-video-exif-enhancer:multi .
        ;;
    *)
        echo "❌ 無効な選択です"
        exit 1
        ;;
esac

echo "✅ ビルド完了！"
echo "実行方法:"
echo "  cd docker"
echo "  docker compose -f [対応するファイル] up"
# マルチステージビルド版 Dockerfile - Xiaomi Video EXIF Enhancer
# ビルド効率とイメージサイズを最適化

# =====================================
# Stage 1: ベースとして依存関係をインストール
# =====================================
FROM python:3.11-slim as base

# メタデータの設定
LABEL maintainer="Xiaomi Video EXIF Enhancer"
LABEL description="Multi-stage build for Xiaomi Video EXIF Enhancer"

# 環境変数の設定
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# 作業ディレクトリの設定
WORKDIR /app

# システムパッケージのアップデート（キャッシュ効率化）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # FFmpeg（映像処理用）
    ffmpeg \
    # OpenCVの依存関係
    libopencv-dev \
    python3-opencv \
    # 画像処理ライブラリの依存関係
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # ビルド用ツール（最終ステージでは削除）
    build-essential \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoclean

# =====================================
# Stage 2: Python依存関係のインストール
# =====================================
FROM base as dependencies

# Python依存関係ファイルをコピー（レイヤーキャッシュ最適化）
COPY requirements.txt .

# Python依存関係のインストール（キャッシュ最適化）
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# EasyOCRモデルの事前ダウンロード（初回実行時間短縮）
RUN python -c "import easyocr; reader = easyocr.Reader(['en', 'ja']); print('EasyOCR models downloaded successfully')"

# =====================================
# Stage 3: 最終的な実行イメージ
# =====================================
FROM python:3.11-slim as runtime

# 環境変数の設定
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# 作業ディレクトリの設定
WORKDIR /app

# 必要な実行時パッケージのみインストール（ビルドツールを除く）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopencv-dev \
    python3-opencv \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoclean

# 前のステージからPython環境をコピー
COPY --from=dependencies /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=dependencies /usr/local/bin/ /usr/local/bin/
COPY --from=dependencies /root/.EasyOCR/ /root/.EasyOCR/

# アプリケーションコードをコピー（最後に配置してコード変更時のキャッシュを活用）
COPY exif_enhancer.py .
COPY batch_processor.py .
COPY file_manager.py .
COPY progress_manager.py .
COPY output_path_generator.py .
COPY video_error_handler.py .

# 実行可能にする
RUN chmod +x exif_enhancer.py

# 非rootユーザーの作成（セキュリティ向上）
RUN groupadd -r appuser && useradd -r -g appuser -m appuser
RUN chown -R appuser:appuser /app

# データディレクトリの作成
RUN mkdir -p /app/input /app/output && \
    chown -R appuser:appuser /app/input /app/output

# 非rootユーザーに切り替え
USER appuser

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; from exif_enhancer import XiaomiVideoExifEnhancer; print('Container is healthy'); sys.exit(0)"

# ボリュームのマウントポイント
VOLUME ["/app/input", "/app/output"]

# デフォルトのエントリーポイント
ENTRYPOINT ["python", "exif_enhancer.py"]

# デフォルトコマンド（ヘルプ表示）
CMD ["--help"]
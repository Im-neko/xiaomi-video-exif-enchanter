# Xiaomi Video EXIF Enhancer Docker Image
FROM python:3.11-slim

# メタデータの設定
LABEL maintainer="Xiaomi Video EXIF Enhancer"
LABEL description="Container for processing Xiaomi camera videos with EXIF metadata enhancement"
LABEL version="1.0.0"

# 環境変数の設定
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# 作業ディレクトリの設定
WORKDIR /app

# システムパッケージのアップデートと必要なパッケージのインストール
RUN apt-get update && apt-get install -y \
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
    # システムユーティリティ
    curl \
    wget \
    unzip \
    # 開発ツール（必要に応じて）
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Pythonの依存関係ファイルをコピー
COPY requirements.txt .

# Python依存関係のインストール（キャッシュ最適化）
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# EasyOCRモデルの事前ダウンロード（初回実行時間短縮）
RUN python -c "import easyocr; reader = easyocr.Reader(['en', 'ja']); print('EasyOCR models downloaded successfully')"

# アプリケーションコードをコピー
COPY . .

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
    CMD python -c "import sys; from exif_enhancer import XiaomiVideoEXIFEnhancer; print('Container is healthy'); sys.exit(0)"

# ボリュームのマウントポイント
VOLUME ["/app/input", "/app/output"]

# デフォルトのエントリーポイント
ENTRYPOINT ["python", "exif_enhancer.py"]

# デフォルトコマンド（ヘルプ表示）
CMD ["--help"]
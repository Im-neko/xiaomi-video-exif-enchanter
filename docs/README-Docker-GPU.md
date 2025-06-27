# Docker GPU サポート

## 必要な環境

### 1. NVIDIA Driver
ホストマシンにNVIDIA GPUドライバーがインストールされている必要があります。

```bash
# ドライバー確認
nvidia-smi
```

### 2. NVIDIA Container Toolkit
Docker でGPU を使用するためのツールキットをインストール：

#### Ubuntu/Debian
```bash
# GPGキーを追加
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# インストール
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Docker デーモンを再起動
sudo systemctl restart docker
```

#### CentOS/RHEL
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.repo | sudo tee /etc/yum.repos.d/nvidia-docker.repo

sudo yum install -y nvidia-container-toolkit
sudo systemctl restart docker
```

## 使用方法

### 1. GPU対応イメージのビルド

#### 一般的なGPU（RTX 30/40シリーズなど）
```bash
# GPU対応Dockerイメージをビルド
docker build -f Dockerfile.gpu -t xiaomi-video-exif-enhancer:gpu .
```

#### RTX 50シリーズ（RTX 5070 Ti等）専用
```bash
# RTX 50シリーズ専用イメージをビルド
docker build -f Dockerfile.rtx50 -t xiaomi-video-exif-enhancer:rtx50 .
```

### 2. Docker Compose での実行

#### 一般的なGPU
```bash
# GPU対応版で実行
docker-compose -f docker-compose.gpu.yml up --build

# バッチ処理（GPU使用）
docker-compose -f docker-compose.gpu.yml run --rm xiaomi-video-exif-enhancer \
  --batch /app/input --gpu --max-workers 2
```

#### RTX 50シリーズ（安定動作優先）
```bash
# RTX 50シリーズ専用版で実行（CPUモード）
docker-compose -f docker-compose.rtx50.yml up --build

# バッチ処理（CPUモードで安定動作）
docker-compose -f docker-compose.rtx50.yml run --rm xiaomi-video-exif-enhancer \
  --batch /app/input --max-workers 2
```

### 3. 直接 docker run での実行
```bash
# GPU対応で実行
docker run --gpus all -v $(pwd)/input:/app/input -v $(pwd)/output:/app/output \
  xiaomi-video-exif-enhancer:gpu --batch /app/input --gpu

# 特定のGPUのみ使用
docker run --gpus device=0 -v $(pwd)/input:/app/input -v $(pwd)/output:/app/output \
  xiaomi-video-exif-enhancer:gpu --batch /app/input --gpu
```

## パフォーマンステスト

### GPU vs CPU 性能比較
```bash
# CPU版での処理時間測定
time docker run -v $(pwd)/input:/app/input -v $(pwd)/output:/app/output \
  xiaomi-video-exif-enhancer:latest --batch /app/input

# GPU版での処理時間測定
time docker run --gpus all -v $(pwd)/input:/app/input -v $(pwd)/output:/app/output \
  xiaomi-video-exif-enhancer:gpu --batch /app/input --gpu
```

## トラブルシューティング

### 1. RTX 50シリーズ（RTX 5070 Ti等）のCUDA互換性エラー

#### 問題
```
NVIDIA GeForce RTX 5070 Ti with CUDA capability sm_120 is not compatible with the current PyTorch installation.
Fatal error: Failed to initialize EasyOCR reader: CUDA error: no kernel image is available for execution on the device
```

#### 解決策1: RTX 50専用イメージを使用（推奨）
```bash
# RTX 50シリーズ専用イメージで安定動作
docker-compose -f docker-compose.rtx50.yml run --rm xiaomi-video-exif-enhancer \
  --batch /app/input --debug
```

#### 解決策2: 環境変数でCPUモード強制
```bash
# 既存のイメージでCPUモード強制
docker run --gpus all -e FORCE_CPU_MODE=1 \
  -v ./input:/app/input -v ./output:/app/output \
  xiaomi-video-exif-enhancer:gpu --batch /app/input --debug
```

#### 解決策3: PyTorch Nightlyビルド使用
```bash
# 最新の開発版PyTorchでビルド
docker build -f Dockerfile.gpu -t xiaomi-video-exif-enhancer:gpu-nightly .
```

### 2. GPU が認識されない場合
```bash
# コンテナ内でGPU確認
docker run --gpus all --rm xiaomi-video-exif-enhancer:gpu python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

### 2. CUDA メモリ不足エラー
```bash
# メモリ使用量を制限して実行
docker run --gpus all --memory=8g -v $(pwd)/input:/app/input -v $(pwd)/output:/app/output \
  xiaomi-video-exif-enhancer:gpu --batch /app/input --gpu --max-workers 1
```

### 3. 互換性の確認
```bash
# CUDA バージョン確認
docker run --gpus all --rm xiaomi-video-exif-enhancer:gpu nvidia-smi

# PyTorch CUDA サポート確認
docker run --gpus all --rm xiaomi-video-exif-enhancer:gpu python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA version: {torch.version.cuda}'); print(f'cuDNN version: {torch.backends.cudnn.version()}')"
```

## 最適化設定

### バッチサイズとワーカー数の調整
- GPU メモリ 8GB 以下: `--max-workers 1`
- GPU メモリ 16GB 以上: `--max-workers 2-4`
- 大量ファイル処理時: `--use-threading` を併用

### 推奨設定例
```bash
# 小規模バッチ（< 100ファイル）
docker-compose -f docker-compose.gpu.yml run --rm xiaomi-video-exif-enhancer \
  --batch /app/input --gpu --max-workers 2

# 大規模バッチ（> 1000ファイル）
docker-compose -f docker-compose.gpu.yml run --rm xiaomi-video-exif-enhancer \
  --batch /app/input --gpu --max-workers 1 --use-threading
```
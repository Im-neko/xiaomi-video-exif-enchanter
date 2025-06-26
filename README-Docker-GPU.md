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
```bash
# GPU対応Dockerイメージをビルド
docker build -f Dockerfile.gpu -t xiaomi-video-exif-enhancer:gpu .
```

### 2. Docker Compose での実行
```bash
# GPU対応版で実行
docker-compose -f docker-compose.gpu.yml up --build

# バッチ処理（GPU使用）
docker-compose -f docker-compose.gpu.yml run --rm xiaomi-video-exif-enhancer \
  --batch /app/input --gpu --max-workers 2
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

### 1. GPU が認識されない場合
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
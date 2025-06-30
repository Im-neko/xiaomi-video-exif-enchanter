# Docker使用ガイド

Xiaomi Video EXIF EnhancerをDockerコンテナで簡単に実行できます。複雑な環境構築は不要です！

## 🚀 クイックスタート

### 1. 必要なもの
- Docker
- Docker Compose（推奨）

### 2. プロジェクトの準備
```bash
# プロジェクトディレクトリに移動
cd xvee

# 入力・出力ディレクトリを作成
mkdir -p input output
```

### 3. Docker Composeでの実行（推奨）

#### ヘルプの表示
```bash
docker-compose run --rm xiaomi-exif-enhancer
```

#### サンプル動画の処理
```bash
docker-compose run --rm xiaomi-exif-enhancer sample.mp4 --location "Docker Test" --debug
```

#### 単一ファイル処理
```bash
# inputディレクトリに動画ファイルを配置してから実行
docker-compose run --rm xiaomi-exif-enhancer /app/input/your-video.mp4 --location "リビング" --output /app/output/enhanced.mp4
```

#### バッチ処理
```bash
# inputディレクトリ内のすべてのMP4ファイルを処理
docker-compose run --rm xiaomi-exif-enhancer --batch /app/input --output-dir /app/output --location "バッチ処理テスト"
```

### 4. 直接Dockerでの実行

#### イメージのビルド
```bash
docker build -t xiaomi-video-exif-enhancer .
```

#### 基本的な実行
```bash
# ヘルプ表示
docker run --rm xiaomi-video-exif-enhancer

# ボリュームマウントで実行
docker run --rm \
  -v $(pwd)/input:/app/input:ro \
  -v $(pwd)/output:/app/output:rw \
  -v $(pwd)/sample.mp4:/app/sample.mp4:ro \
  xiaomi-video-exif-enhancer \
  sample.mp4 --location "Docker Test"
```

## 📁 ディレクトリ構造

```
xiaomi-video-exif-enhancer/
├── input/          # 処理したい動画ファイルを配置
├── output/         # 処理済みファイルが出力される
├── sample.mp4      # サンプル動画（テスト用）
├── Dockerfile      # Dockerイメージ定義
├── docker-compose.yml  # Docker Compose設定
└── docker-entrypoint.sh  # エントリーポイントスクリプト
```

## 🎯 使用例

### 例1: サンプル動画のテスト
```bash
# sample.mp4の処理（デバッグモード）
docker-compose run --rm xiaomi-exif-enhancer sample --debug
```

### 例2: 単一ファイル処理
```bash
# inputディレクトリにvideo.mp4を配置
cp /path/to/your/video.mp4 input/

# 処理実行
docker-compose run --rm xiaomi-exif-enhancer \
  /app/input/video.mp4 \
  --location "リビング" \
  --output /app/output/enhanced_video.mp4
```

### 例3: バッチ処理
```bash
# 複数の動画ファイルをinputディレクトリに配置
cp /path/to/videos/*.mp4 input/

# バッチ処理実行
docker-compose run --rm xiaomi-exif-enhancer \
  --batch /app/input \
  --output-dir /app/output \
  --location "一括処理" \
  --debug
```

### 例4: 対話的シェル
```bash
# コンテナ内でシェルを起動
docker-compose run --rm xiaomi-exif-enhancer bash

# コンテナ内で直接コマンド実行
python exif_enchanter.py --help
python test_batch_processing.py
```

## 🔧 詳細設定

### 環境変数
```yaml
# docker-compose.yml内で設定
environment:
  - PYTHONUNBUFFERED=1
  - TZ=Asia/Tokyo
```

### リソース制限
```yaml
# docker-compose.yml内で設定
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '2.0'
```

### カスタムコマンド
```bash
# テスト実行
docker-compose run --rm xiaomi-exif-enhancer test

# 特定のテストファイル実行
docker-compose run --rm xiaomi-exif-enhancer python test_batch_processing.py
```

## 🐛 トラブルシューティング

### よくある問題と解決法

#### 1. ボリュームマウントエラー
```bash
# 権限確認
ls -la input/ output/

# 権限修正（必要に応じて）
chmod 755 input/ output/
```

#### 2. ファイルが見つからない
```bash
# inputディレクトリの内容確認
docker-compose run --rm xiaomi-exif-enhancer bash -c "ls -la /app/input"

# ファイルの配置確認
docker-compose run --rm xiaomi-exif-enhancer bash -c "find /app/input -name '*.mp4'"
```

#### 3. メモリ不足
```bash
# Docker Desktop でメモリ制限を増やす、または
# docker-compose.yml でメモリ制限を調整
```

#### 4. OCRモデルのダウンロード遅延
```bash
# 初回起動時はEasyOCRモデルのダウンロードで時間がかかります
# Dockerfileでは事前ダウンロード済みですが、環境によっては追加ダウンロードが発生する場合があります
```

### ログの確認
```bash
# コンテナのログ確認
docker-compose logs xiaomi-exif-enhancer

# リアルタイムログ
docker-compose logs -f xiaomi-exif-enhancer
```

### デバッグモード
```bash
# 詳細ログ付きで実行
docker-compose run --rm xiaomi-exif-enhancer \
  sample.mp4 --debug

# 対話的デバッグ
docker-compose run --rm xiaomi-exif-enhancer bash
```

## 📈 パフォーマンスTips

### 1. ビルド最適化
```bash
# マルチステージビルドの活用（将来の改善）
# BuildKitの使用
DOCKER_BUILDKIT=1 docker build -t xiaomi-video-exif-enhancer .
```

### 2. キャッシュ活用
```bash
# 依存関係の変更がない場合、レイヤーキャッシュを活用
docker-compose build --no-cache  # フルリビルドが必要な場合のみ
```

### 3. 並列処理
```bash
# 複数ファイルの並列処理（将来の機能拡張）
# 現在はバッチ処理で順次処理
```

## 🔄 更新とメンテナンス

### イメージの更新
```bash
# 最新コードでリビルド
docker-compose build --no-cache

# 古いイメージの削除
docker image prune
```

### データのバックアップ
```bash
# 処理済みファイルのバックアップ
cp -r output/ backup-$(date +%Y%m%d)/
```

## 🆘 サポート

問題が発生した場合：

1. **ログの確認**: `docker-compose logs`
2. **デバッグモード**: `--debug` オプションを追加
3. **対話的確認**: `docker-compose run --rm xiaomi-exif-enhancer bash`
4. **Issue報告**: GitHubのIssueで報告

---

**Docker環境での実行により、複雑な環境構築なしにXiaomi Video EXIF Enhancerをすぐに利用できます！**
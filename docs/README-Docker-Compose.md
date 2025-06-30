# Docker Compose での大量ファイル処理

## 🚀 クイックスタート

### 1. 基本準備
```bash
# 入力・出力ディレクトリを確認
ls -la input/    # 動画ファイルがあることを確認
ls -la output/   # 出力ディレクトリを確認

# Docker イメージをビルド
./run_batch.sh build
```

### 2. おすすめ処理コマンド

```bash
# 小バッチ処理（推奨・初回テスト用）
./run_batch.sh small

# 中バッチ処理（通常使用）
./run_batch.sh medium

# 場所付きバッチ処理
./run_batch.sh location "リビング"

# 継続処理（エラーファイルをスキップ）
./run_batch.sh continue
```

## 📋 利用可能なコマンド

| コマンド | バッチサイズ | 説明 | 推奨用途 |
|---------|--------------|------|----------|
| `small` | 20ファイル | 小バッチ処理 | 初回テスト・確認用 |
| `medium` | 50ファイル | 中バッチ処理 | 通常の処理 |
| `large` | 100ファイル | 大バッチ処理 | 大量ファイル処理 |
| `single` | 1ファイル | 単一ファイル処理 | テスト・デバッグ用 |
| `location` | 30ファイル | 場所付き処理 | 場所情報を追加 |
| `continue` | 25ファイル | 継続処理 | エラー後の再開 |

## 🔧 Docker Compose コマンド（直接実行）

### 基本バッチ処理
```bash
# 小バッチ処理
docker-compose -f docker-compose.safe.yml --profile small-batch up

# 中バッチ処理  
docker-compose -f docker-compose.safe.yml --profile medium-batch up

# 大バッチ処理
docker-compose -f docker-compose.safe.yml --profile large-batch up
```

### カスタムコマンド
```bash
# カスタムバッチサイズで実行
docker-compose -f docker-compose.safe.yml run --rm xiaomi-exif-enhancer \
  --batch /app/input \
  --batch-size 30 \
  --disable-parallel \
  --location "寝室" \
  --debug

# 単一ファイル処理
docker-compose -f docker-compose.safe.yml run --rm xiaomi-exif-enhancer \
  /app/input/VIDEO_1750580208742.mp4 \
  --output /app/output/custom_output.mp4 \
  --location "玄関" \
  --debug
```

### サービス管理
```bash
# サービス停止
docker-compose -f docker-compose.safe.yml down

# ログ確認
docker-compose -f docker-compose.safe.yml logs xiaomi-small-batch

# クリーンアップ
./run_batch.sh clean
```

## ⚙️ 設定のカスタマイズ

### メモリ制限の調整
`docker-compose.safe.yml`の`deploy.resources`セクションを編集：

```yaml
deploy:
  resources:
    limits:
      memory: 6G  # メモリ上限を増加
      cpus: '4.0'  # CPU上限を増加
```

### 環境変数の設定
```yaml
environment:
  - FORCE_CPU_MODE=1      # GPU無効化
  - TZ=Asia/Tokyo         # タイムゾーン
  - PYTHONUNBUFFERED=1    # Python出力のバッファリング無効
```

## 📊 処理時間の目安

| ファイル数 | 処理時間（概算） | メモリ使用量 |
|-----------|------------------|--------------|
| 20ファイル | 30-40分 | 2-3GB |
| 50ファイル | 1.5-2時間 | 3-4GB |
| 100ファイル | 3-4時間 | 4-6GB |

## 🔍 トラブルシューティング

### メモリ不足エラー
```bash
# より小さなバッチサイズで実行
./run_batch.sh small

# または手動でバッチサイズを指定
docker-compose -f docker-compose.safe.yml run --rm xiaomi-exif-enhancer \
  --batch /app/input --batch-size 10 --disable-parallel
```

### 処理の中断・再開
```bash
# 処理を中断
Ctrl + C

# 失敗ファイルを確認
ls -la output/failed/

# 継続処理で再開
./run_batch.sh continue
```

### ログの確認
```bash
# リアルタイムログ確認
docker-compose -f docker-compose.safe.yml --profile small-batch up

# 過去のログ確認
docker logs xiaomi-small-batch
```

## 📁 ディレクトリ構造

```
.
├── input/                    # 入力動画ファイル
│   ├── VIDEO_*.mp4
├── output/                   # 出力ファイル
│   ├── *_enhanced.mp4       # 処理済みファイル
│   └── failed/              # 失敗ファイル
├── docker-compose.safe.yml   # 安全な設定
├── run_batch.sh             # 実行スクリプト
└── README-Docker-Compose.md # このファイル
```

## 💡 ベストプラクティス

1. **初回は小バッチでテスト**: `./run_batch.sh small`
2. **メモリ監視**: `docker stats`でリソース使用量を確認
3. **定期的なクリーンアップ**: `./run_batch.sh clean`
4. **バックアップ**: 重要なファイルは事前にバックアップ
5. **段階的処理**: 大量ファイルは複数回に分けて処理
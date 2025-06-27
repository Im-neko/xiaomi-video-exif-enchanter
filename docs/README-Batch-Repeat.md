# 🔄 繰り返しバッチ処理ガイド

大量ファイル（2000+ファイル）を安全・効率的に処理するための自動繰り返し機能です。

## 🚀 クイックスタート

### 1. 基本的な繰り返し処理
```bash
# 最も簡単な方法（推奨）
./run_batch.sh repeat

# または詳細制御
./run_batch_repeat.sh
```

### 2. カスタム設定での実行
```bash
# 30ファイルずつ処理
./run_batch_repeat.sh 30

# 25ファイルずつ、場所付きで処理
./run_batch_repeat.sh 25 "リビング"

# 40ファイルずつ、最大50回繰り返し
./run_batch_repeat.sh 40 "寝室" 50
```

## 📋 コマンド一覧

### 基本コマンド
| コマンド | 説明 | 使用例 |
|---------|------|--------|
| `./run_batch_repeat.sh` | デフォルト設定で実行 | 50ファイルずつ処理 |
| `./run_batch_repeat.sh 30` | バッチサイズ指定 | 30ファイルずつ処理 |
| `./run_batch_repeat.sh 25 "リビング"` | 場所付き | 25ファイルずつ、場所情報付き |

### 管理コマンド
| コマンド | 説明 |
|---------|------|
| `./run_batch_repeat.sh status` | 進行状況を確認 |
| `./run_batch_repeat.sh resume` | 中断された処理を再開 |
| `./run_batch_repeat.sh reset` | 進行状況をリセット |
| `./run_batch_repeat.sh clean` | 一時ファイルをクリーンアップ |

## 🔧 使用シナリオ例

### シナリオ1: 2370ファイルを安全に処理
```bash
# ステップ1: 小さいバッチでテスト
./run_batch_repeat.sh 20

# 問題なければより大きなバッチで継続
./run_batch_repeat.sh resume    # 前回の続きから
# または
./run_batch_repeat.sh 50        # 新しい設定で開始
```

### シナリオ2: 夜間バッチ処理
```bash
# 大きなバッチサイズで長時間実行
nohup ./run_batch_repeat.sh 100 "リビング" 30 > batch.log 2>&1 &

# 翌日、進行状況を確認
./run_batch_repeat.sh status
```

### シナリオ3: エラー後の復旧
```bash
# 進行状況確認
./run_batch_repeat.sh status

# 継続実行
./run_batch_repeat.sh resume

# または完全リセット
./run_batch_repeat.sh reset
./run_batch_repeat.sh 30
```

## 📊 進行状況の表示例

```bash
$ ./run_batch_repeat.sh status
📊 現在の進行状況:
  反復回数: 15
  処理済み: 750 ファイル
  失敗: 25 ファイル  
  残り: 1595 ファイル
  バッチサイズ: 50
  場所: "リビング"
  最終更新: 2025-06-26 23:45:32
  進行率: 32%
  [████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 32%
```

## ⚙️ 設定のカスタマイズ

### デフォルト値の変更
`run_batch_repeat.sh`内の以下の値を編集：
```bash
DEFAULT_BATCH_SIZE=50      # デフォルトバッチサイズ
DEFAULT_MAX_ITERATIONS=100 # デフォルト最大繰り返し回数
```

### Docker Composeでの直接実行
```bash
# 小サイズ繰り返し（20ファイルずつ）
docker-compose -f docker-compose.safe.yml --profile repeat-small up

# 中サイズ繰り返し（50ファイルずつ）
docker-compose -f docker-compose.safe.yml --profile repeat-medium up

# 大サイズ繰り返し（100ファイルずつ）
docker-compose -f docker-compose.safe.yml --profile repeat-large up
```

## 🛡️ 安全機能

### 自動バックアップと復旧
- **進行状況の自動保存**: `.batch_progress`ファイル
- **処理済みファイル追跡**: `.processed_files`ファイル
- **中断・再開機能**: いつでも安全に中断・再開可能

### エラーハンドリング
- **失敗ファイルのスキップ**: 無限ループを防止
- **メモリ不足対策**: 小さなバッチサイズの自動調整
- **プロセス異常終了対応**: 自動的に次のバッチに進行

### リソース管理
- **バッチ間の休憩**: 10秒の待機時間でシステム負荷軽減
- **一時ファイルの自動削除**: ディスク容量の節約
- **メモリ使用量制限**: Docker Composeでのリソース制限

## 📈 パフォーマンス目安

| ファイル数 | バッチサイズ | 推定時間 | 推奨設定 |
|-----------|--------------|----------|----------|
| 100-500 | 20-30 | 2-4時間 | 小〜中バッチ |
| 500-1000 | 30-50 | 4-8時間 | 中バッチ |
| 1000-2000 | 40-60 | 8-16時間 | 中〜大バッチ |
| 2000+ | 50-100 | 16-24時間 | 大バッチ + 夜間実行 |

## 🔍 トラブルシューティング

### よくある問題と解決方法

#### 1. 処理が途中で止まる
```bash
# 進行状況を確認
./run_batch_repeat.sh status

# 継続実行
./run_batch_repeat.sh resume
```

#### 2. メモリ不足エラー
```bash
# より小さなバッチサイズで再開
./run_batch_repeat.sh reset
./run_batch_repeat.sh 20
```

#### 3. ディスク容量不足
```bash
# 一時ファイルをクリーンアップ
./run_batch_repeat.sh clean

# 出力ディレクトリの確認
du -sh output/
```

#### 4. Docker関連エラー
```bash
# Dockerの状態確認
docker ps -a

# コンテナの再起動
docker-compose -f docker-compose.safe.yml down
docker-compose -f docker-compose.safe.yml build
```

## 💡 ベストプラクティス

1. **段階的実行**
   - 最初は小バッチ（20ファイル）でテスト
   - 問題なければバッチサイズを増加

2. **進行状況の定期確認**
   - 長時間実行時は定期的に`status`コマンドで確認
   - ログファイルの監視

3. **リソース監視**
   - `docker stats`でメモリ・CPU使用量を監視
   - システム全体の負荷を確認

4. **バックアップ**
   - 重要なファイルは事前にバックアップ
   - 進行状況ファイル（`.batch_progress`）の保護

5. **夜間実行**
   - 大量ファイルは夜間の無人実行を推奨
   - `nohup`コマンドでバックグラウンド実行
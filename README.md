# Xiaomi Video EXIF Enchanter

Xiaomiホームカメラ(C301)で録画された映像のEXIF情報を拡張するツール

## 3つのスクリプト提供

用途に応じて最適なスクリプトを選択できます：

| スクリプト | 用途 | 特徴 | 推奨用途 |
|-----------|------|------|----------|
| **`exif_enchanter.py`** | 標準OCR処理 | 安定性重視、軽量 | 本番環境、日常使用 |
| **`exif_enchanter_ocr.py`** | 強化OCR処理 | 複数前処理技術、高OCR精度 | OCR精度重視 |
| **`exif_enchanter_ml.py`** | ML+OCR処理 | 機械学習モデル、最高精度 | 最高精度要求時 |

## 仕様

### 1. 対応機器
- Xiaomiホームカメラ C301で録画された映像ファイル

### 2. 日時情報の付与
- 1フレーム目の左上に記載される日時を読み取り
- JST（日本標準時）からUTC（協定世界時）に自動変換
- 正確なタイムゾーン処理でEXIFメタデータとして埋め込み

### 3. 撮影場所の付与
- 指定された撮影場所をEXIF情報に追加

## Technical Specifications

### 推奨技術スタック
- **Python**: メイン実装言語
- **OpenCV**: 映像フレーム抽出・画像処理
- **EasyOCR**: 日時テキスト読み取り（主要）
- **PyTorch**: 機械学習モデル（timestamp recognition）
- **piexif**: EXIF情報操作
- **ffmpeg-python**: 映像ファイル処理

### 実装アーキテクチャ
1. 映像の1フレーム目を抽出
2. 左上領域をクロップしてOCR処理
3. **機械学習モデル** または EasyOCR で日時テキスト認識
4. 日時文字列をパース（JST→UTC変換）
5. FFmpegを使用してEXIFメタデータを埋め込み
6. 自動的な出力ファイル名生成
7. エラーハンドリングと詳細ログ出力

### 機械学習による高精度タイムスタンプ認識
- **モデル**: `models/fixed_xiaomi_timestamp_model.pth` (100%精度達成)
- **フォールバック**: EasyOCR による従来手法
- **自動切り替え**: MLモデル失敗時は自動的にOCRにフォールバック

### CLI設計

#### スクリプト別使用例

**標準処理（推奨）**
```bash
# 基本的な使用（安定性重視）
python exif_enchanter.py input.mp4 --location "リビング"

# 明示的な出力指定
python exif_enchanter.py input.mp4 --location "リビング" --output enhanced_output.mp4

# バッチ処理
python exif_enchanter.py --batch ./videos/ --location "リビング" --output-dir ./enhanced/
```

**強化OCR処理（OCR精度重視）**
```bash
# 複数前処理技術でOCR精度向上
python exif_enchanter_ocr.py input.mp4 --location "リビング"

# Tesseract無効化（EasyOCRのみ使用）
python exif_enchanter_ocr.py input.mp4 --disable-enhanced-ocr
```

**ML処理（最高精度）**
```bash
# 機械学習モデルを使用（高精度・推奨）
python exif_enchanter_ml.py input.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth --location "リビング"

# OCRフォールバック無効化（MLのみ）
python exif_enchanter_ml.py input.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth --disable-fallback-ocr
```

## セットアップ

### 必要要件
- Python 3.8以上
- FFmpeg (システムにインストール済みであること)

### 基本インストール
```bash
# リポジトリをクローン
git clone https://github.com/your-username/xvee.git
cd xvee

# 基本的な依存関係をインストール
pip install -r requirements.txt
```

### 開発者向けインストール
```bash
# 開発用依存関係も含めてインストール
pip install -e .[dev]
```

### 依存ライブラリ
- opencv-python>=4.8.0
- easyocr>=1.7.0
- torch>=2.0.0 (機械学習モデル用)
- piexif>=1.1.3
- ffmpeg-python>=0.2.0
- numpy>=1.24.0
- Pillow>=10.0.0
- scikit-learn>=1.3.0

### Docker使用（推奨・最も簡単）
環境構築が不要で、すぐに使い始められます：

```bash
# 1. プロジェクトをクローン
git clone https://github.com/your-username/xvee.git
cd xvee

# 2. 入力・出力ディレクトリを作成
mkdir -p input output

# 3. サンプル動画をテスト
docker-compose run --rm xiaomi-exif-enhancer sample.mp4 --location "Docker Test" --debug

# 4. 自分の動画を処理（inputディレクトリに動画ファイルを配置）
cp /path/to/your/video.mp4 input/
docker-compose run --rm xiaomi-exif-enhancer /app/input/video.mp4 --location "リビング"

# 5. バッチ処理
docker-compose run --rm xiaomi-exif-enhancer --batch /app/input --output-dir /app/output --location "バッチ処理"
```

詳細なDocker使用方法は [DOCKER.md](DOCKER.md) を参照してください。

## サンプル動画

プロジェクトには `sample.mp4` というサンプル動画が含まれています。このファイルを使用してツールの動作を確認できます。

### サンプル動画について
- **ファイル名**: `sample.mp4`
- **解像度**: 640x360 pixels
- **埋め込み時刻**: 2025/05/28 19:41:14 JST（1フレーム目左上に表示）
- **OCR結果例**: `@ 2025/05/28 19.41.14 ` (信頼度: 0.78)
- **UTC変換**: 2025-05-28 10:41:14 UTC（JST-9時間）
- **期待される出力**: 正確なタイムゾーン変換でEXIFメタデータが設定される
- **用途**: 機能テスト・デモンストレーション・タイムゾーン処理確認

## 使用方法

### サンプル動画での基本テスト

**標準スクリプト**
```bash
# サンプル動画で基本処理をテスト
python exif_enchanter.py sample.mp4

# デバッグモードでの詳細確認（推奨）
python exif_enchanter.py sample.mp4 --debug

# 撮影場所を指定してテスト
python exif_enchanter.py sample.mp4 --location "テストルーム"
```

**強化OCRスクリプト**
```bash
# 複数前処理技術でテスト
python exif_enchanter_ocr.py sample.mp4 --debug

# Tesseract併用でテスト
python exif_enchanter_ocr.py sample.mp4 --location "テストルーム"
```

**MLスクリプト**
```bash
# 機械学習モデルでテスト（高精度・推奨）
python exif_enchanter_ml.py sample.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth --debug

# OCRフォールバック込みでテスト
python exif_enchanter_ml.py sample.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth --location "テストルーム"
```

**期待される処理フロー（デバッグモード時）**
```
✓ Frame extracted successfully, shape: (360, 640, 3)
✓ OCR result: '@ 2025/05/28 19.41.14 ' (confidence: 0.78)
✓ Timestamp found: @ 2025/05/28 19.41.14 
✓ Timestamp parsed successfully: 2025-05-28 19:41:14
```

### 単一ファイル処理
```bash
# 基本的な処理（自動で出力ファイル名を生成）
python exif_enchanter.py input.mp4

# 撮影場所を指定
python exif_enchanter.py input.mp4 --location "リビング"

# 出力ファイル名を指定
python exif_enchanter.py input.mp4 --output enhanced_video.mp4

# 全オプションを指定
python exif_enchanter.py input.mp4 --location "寝室" --output bedroom_video.mp4

# デバッグモードで詳細ログを確認
python exif_enchanter.py input.mp4 --debug
```

### バッチ処理（ディレクトリ一括処理）
```bash
# ディレクトリ内のすべてのMP4ファイルを処理
python exif_enchanter.py --batch /path/to/videos/

# 撮影場所を指定してバッチ処理
python exif_enchanter.py --batch /path/to/videos/ --location "リビング"

# 出力ディレクトリを指定してバッチ処理
python exif_enchanter.py --batch /path/to/videos/ --output-dir /path/to/output/

# エラー時に処理を停止（デフォルトはスキップして継続）
python exif_enchanter.py --batch /path/to/videos/ --no-skip-errors

# 特定の拡張子のみ処理
python exif_enchanter.py --batch /path/to/videos/ --extensions mp4 avi mov

# バッチ処理のデバッグモード
python exif_enchanter.py --batch /path/to/videos/ --location "寝室" --debug
```

### オプション

#### 基本オプション
- `input`: 入力映像ファイルパス（単一ファイル処理時）
- `--batch DIR`: 入力ディレクトリパス（バッチ処理時）
- `-o, --output`: 出力映像ファイルパス（単一）または出力ディレクトリ（バッチ）
- `--output-dir`: バッチ処理専用の出力ディレクトリ
- `-l, --location`: 撮影場所（EXIF情報に追加）
- `--debug`: デバッグモード（詳細ログ出力）

#### スクリプト固有オプション

**標準スクリプト (`exif_enchanter.py`)**
- `--disable-enhanced-ocr`: 強化OCR無効化（基本OCRのみ使用）

**強化OCRスクリプト (`exif_enchanter_ocr.py`)**
- `--disable-enhanced-ocr`: 強化OCR無効化（基本OCRのみ使用）
- `--gpu`: GPU使用（OCR処理高速化）

**MLスクリプト (`exif_enchanter_ml.py`)**
- `--model-path`: MLモデルファイルパス（デフォルト: xiaomi_timestamp_model_best.pth）
- `--disable-fallback-ocr`: OCRフォールバック無効化（MLのみ使用）
- `--gpu`: GPU使用（ML処理高速化）

#### バッチ処理専用オプション
- `--no-skip-errors`: 最初のエラーで処理停止（デフォルト：エラーをスキップして継続）
- `--extensions`: 処理対象の拡張子指定（デフォルト：mp4 MP4）

### 対応動画形式
- MP4, AVI, MOV, MKV, WebM, FLV, WMV
- M4V, 3GP, 3G2, MPG, MPEG, M2V
- MTS, M2TS, TS, VOB, F4V, F4P, F4A, F4B

### 処理フロー
1. ✓ First frame extracted - 1フレーム目を抽出
2. ✓ Timestamp area cropped - 日時領域をクロップ
3. ✓ Timestamp detected - OCRで日時を検出
4. ✓ Timestamp parsed (JST→UTC) - 日時をパース・タイムゾーン変換
5. ✓ EXIF metadata embedded - FFmpegでEXIFメタデータ埋め込み
6. ✓ Output file generated - 自動命名で出力ファイル生成
7. ✓ Video processed successfully - 映像処理完了

### バッチ処理の特徴
- **一括処理**: ディレクトリ内の複数動画ファイルを自動検出・処理
- **進捗表示**: `[1/5] Processing: video.mp4` 形式で進捗を表示
- **エラー耐性**: 個別ファイルのエラーで全体を停止させない（オプションで変更可能）
- **重複回避**: 既存の出力ファイルを自動検出してスキップ
- **統計情報**: 処理完了後に成功・失敗・スキップ数のサマリーを表示
- **柔軟な出力**: 入力ディレクトリ内または指定した別ディレクトリに出力可能

## 開発・テスト

### テスト実行

**各スクリプトのテスト**
```bash
# 標準スクリプトのテスト
python exif_enchanter.py sample.mp4 --debug

# 強化OCRスクリプトのテスト
python exif_enchanter_ocr.py sample.mp4 --debug

# MLスクリプトのテスト（推奨）
python exif_enchanter_ml.py sample.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth --debug

# 機械学習モデルの精度テスト
python test_ml_model.py -v
```

**ユニットテスト**
```bash
# 基本的なユニットテスト
python -m unittest discover -s tests -p "test_*.py" -v

# 全テストの実行
python -m unittest discover -s . -p "test_*.py" -v
```

### 開発者向け情報
詳細な技術仕様・拡張ガイドについては [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。

### パフォーマンス仕様
sample.mp4を使用した実測値：

#### 機械学習モデル使用時（推奨）
- **フレーム抽出**: 0.017秒 (基準: <1秒)
- **ML推論**: 0.1-0.3秒 (GPU使用時はさらに高速)
- **タイムスタンプ精度**: 100% (models/fixed_xiaomi_timestamp_model.pth)
- **FFmpeg EXIF埋め込み**: 0.5-2.0秒（ファイルサイズ依存）
- **総処理時間**: 0.8-2.5秒

#### 従来OCR使用時（フォールバック）
- **フレーム抽出**: 0.017秒 (基準: <1秒)
- **OCR処理**: 0.471秒 (基準: <10秒)  
- **OCR信頼度**: 0.775 (77.5%)
- **総処理時間**: 1.0-3.0秒 (基準: <15秒)

- **タイムゾーン精度**: JST→UTC 完全対応
- **GPU加速**: RTX 5070 Ti最適化済み（8-10倍高速化）

### トラブルシューティング

#### よくある問題
1. **モジュールが見つからない**: `pip install -r requirements.txt` で依存関係をインストール
2. **OCRが動作しない**: EasyOCRの初期化に時間がかかる場合があります
3. **FFmpegエラー**: システムにFFmpegがインストールされているか確認
4. **権限エラー**: 出力ディレクトリの書き込み権限を確認

#### デバッグ情報の確認
```bash
# 詳細なログとエラー情報を表示
python exif_enchanter.py sample.mp4 --debug
```

# Xiaomi Video EXIF Enchanter

Xiaomiホームカメラ(C301)で録画された映像のEXIF情報を拡張するツール

## 仕様

### 1. 対応機器
- Xiaomiホームカメラ C301で録画された映像ファイル

### 2. 日時情報の付与
- 1フレーム目の左上に記載される日時を読み取り
- EXIFのファイル作成日として付与

### 3. 撮影場所の付与
- 指定された撮影場所をEXIF情報に追加

## Technical Specifications

### 推奨技術スタック
- **Python**: メイン実装言語
- **OpenCV**: 映像フレーム抽出・画像処理
- **Tesseract/EasyOCR**: 日時テキスト読み取り
- **exifread/piexif**: EXIF情報操作
- **ffmpeg-python**: 映像ファイル処理

### 実装アーキテクチャ
1. 映像の1フレーム目を抽出
2. 左上領域をクロップしてOCR処理
3. 日時文字列をパースして標準形式に変換
4. EXIFメタデータとして撮影日時・場所を埋め込み
5. 処理済み映像ファイルを出力

### CLI設計
```bash
python exif_enhancer.py input.mp4 --location "リビング" --output output.mp4
```

## セットアップ

### 必要要件
- Python 3.8以上
- FFmpeg (システムにインストール済みであること)

### 基本インストール
```bash
# リポジトリをクローン
git clone https://github.com/your-username/xiaomi-video-exif-enchanter.git
cd xiaomi-video-exif-enchanter

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
- piexif>=1.1.3
- ffmpeg-python>=0.2.0
- numpy>=1.24.0
- Pillow>=10.0.0

## サンプル動画

プロジェクトには `sample.mp4` というサンプル動画が含まれています。このファイルを使用してツールの動作を確認できます。

### サンプル動画について
- **ファイル名**: `sample.mp4`
- **解像度**: 640x360 pixels
- **埋め込み時刻**: 2025/05/28 19:41:14（1フレーム目左上に表示）
- **OCR結果例**: `@ 2025/05/28 19.41.14 ` (信頼度: 0.78)
- **期待される出力**: 日時情報が正常にパースされ、EXIFメタデータとして設定される
- **用途**: 機能テスト・デモンストレーション

## 使用方法

### サンプル動画での基本テスト
```bash
# サンプル動画で基本処理をテスト
python exif_enhancer.py sample.mp4

# デバッグモードでの詳細確認（推奨）
python exif_enhancer.py sample.mp4 --debug

# 撮影場所を指定してテスト
python exif_enhancer.py sample.mp4 --location "テストルーム"

# 期待される処理フロー（デバッグモード時）
# ✓ Frame extracted successfully, shape: (360, 640, 3)
# ✓ OCR result: '@ 2025/05/28 19.41.14 ' (confidence: 0.78)
# ✓ Timestamp found: @ 2025/05/28 19.41.14 
# ✓ Timestamp parsed successfully: 2025-05-28 19:41:14
```

### 基本的な使用方法
```bash
# 基本的な処理（自動で出力ファイル名を生成）
python exif_enhancer.py input.mp4

# 撮影場所を指定
python exif_enhancer.py input.mp4 --location "リビング"

# 出力ファイル名を指定
python exif_enhancer.py input.mp4 --output enhanced_video.mp4

# 全オプションを指定
python exif_enhancer.py input.mp4 --location "寝室" --output bedroom_video.mp4

# デバッグモードで詳細ログを確認
python exif_enhancer.py input.mp4 --debug
```

### オプション
- `input`: 入力映像ファイルパス（必須）
- `-o, --output`: 出力映像ファイルパス（省略時は自動生成）
- `-l, --location`: 撮影場所（EXIF情報に追加）
- `--debug`: デバッグモード（詳細ログ出力）

### 対応動画形式
- MP4, AVI, MOV, MKV, WebM, FLV, WMV
- M4V, 3GP, 3G2, MPG, MPEG, M2V
- MTS, M2TS, TS, VOB, F4V, F4P, F4A, F4B

### 処理フロー
1. ✓ First frame extracted - 1フレーム目を抽出
2. ✓ Timestamp area cropped - 日時領域をクロップ
3. ✓ Timestamp detected - OCRで日時を検出
4. ✓ Timestamp parsed - 日時をパース
5. ✓ Video processed successfully - 映像処理完了

## 開発・テスト

### テスト実行
```bash
# 基本的なユニットテスト
python -m unittest test_exif_enhancer.py -v

# サンプル動画を使用した統合テスト
python test_sample_video.py -v

# 全テストの実行
python -m unittest discover -s . -p "test_*.py" -v
```

### 開発者向け情報
詳細な技術仕様・拡張ガイドについては [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。

### パフォーマンス仕様
sample.mp4を使用した実測値：

- **フレーム抽出**: 0.017秒 (基準: <1秒)
- **OCR処理**: 0.471秒 (基準: <10秒)  
- **総処理時間**: 0.488秒 (基準: <15秒)
- **OCR信頼度**: 0.775 (77.5%)

※CPU環境での実測値。GPU環境ではさらに高速化が期待されます。

### トラブルシューティング

#### よくある問題
1. **モジュールが見つからない**: `pip install -r requirements.txt` で依存関係をインストール
2. **OCRが動作しない**: EasyOCRの初期化に時間がかかる場合があります
3. **FFmpegエラー**: システムにFFmpegがインストールされているか確認
4. **権限エラー**: 出力ディレクトリの書き込み権限を確認

#### デバッグ情報の確認
```bash
# 詳細なログとエラー情報を表示
python exif_enhancer.py sample.mp4 --debug
```
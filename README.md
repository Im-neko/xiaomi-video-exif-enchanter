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

### インストール
```bash
# リポジトリをクローン
git clone https://github.com/your-username/xiaomi-video-exif-enchanter.git
cd xiaomi-video-exif-enchanter

# 依存関係をインストール
pip install -r requirements.txt
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
- **用途**: 機能テスト・デモンストレーション

## 使用方法

### サンプル動画での基本テスト
```bash
# サンプル動画で基本処理をテスト
python exif_enhancer.py sample.mp4

# デバッグモードでの詳細確認
python exif_enhancer.py sample.mp4 --debug

# 撮影場所を指定してテスト
python exif_enhancer.py sample.mp4 --location "テストルーム"
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

### 単体テストの実行
```bash
# 全テストを実行
python -m unittest test_exif_enhancer.py

# 詳細出力でテスト実行
python -m unittest -v test_exif_enhancer.py
```

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
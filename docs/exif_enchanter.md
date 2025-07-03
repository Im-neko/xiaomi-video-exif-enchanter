# exif_enchanter.py - 標準OCRスクリプト

## 概要

`exif_enchanter.py`は、安定性と実用性を重視した標準的なOCR処理スクリプトです。本番環境や日常的な使用に最適化されており、軽量で信頼性の高い処理を提供します。

## 特徴

### ✅ 安定性重視
- 実績のあるEasyOCRエンジンを使用
- シンプルな処理フローで予期しないエラーを最小限に
- 機械学習依存関係なしで軽量

### ✅ Enhanced OCR対応
- 複数の画像前処理技術（拡大、コントラスト調整、余白追加）
- 複数バリエーションでのOCR実行
- 最適な結果の自動選択

### ✅ 実用的設計
- 自動出力ファイル名生成
- バッチ処理対応
- 詳細なエラーハンドリング

## 使用方法

### 基本的な使用法

```bash
# 単一ファイル処理
python exif_enchanter.py sample.mp4

# 撮影場所を指定
python exif_enchanter.py sample.mp4 --location "リビング"

# 出力ファイル名を指定
python exif_enchanter.py sample.mp4 --output enhanced_video.mp4

# デバッグモードで詳細確認
python exif_enchanter.py sample.mp4 --debug
```

### バッチ処理

```bash
# ディレクトリ内の全ファイルを処理
python exif_enchanter.py --batch /path/to/videos/

# 撮影場所を指定してバッチ処理
python exif_enchanter.py --batch /path/to/videos/ --location "リビング"

# 出力ディレクトリを指定
python exif_enchanter.py --batch /path/to/videos/ --output-dir /path/to/output/
```

## オプション

### 基本オプション
- `input`: 入力映像ファイルパス
- `-o, --output`: 出力映像ファイルパス
- `-l, --location`: 撮影場所（EXIF情報に追加）
- `-d, --debug`: デバッグモード（詳細ログ出力）

### バッチ処理オプション
- `--batch`: バッチ処理モード
- `--max-workers`: 並列処理数
- `--use-threading`: マルチプロセシングの代わりにスレッドを使用
- `--batch-size`: バッチサイズ
- `--skip-errors`: エラー時に処理を継続（デフォルト：有効）

### OCR設定オプション
- `--languages`: OCR言語（デフォルト：['en']）
- `--gpu`: GPU使用（OCR処理高速化）
- `--confidence`: OCR信頼度閾値（デフォルト：0.5）
- `--disable-enhanced-ocr`: 強化OCR無効化（基本OCRのみ使用）

## 処理フロー

1. **フレーム抽出**: 動画の1フレーム目を取得
2. **タイムスタンプ領域クロップ**: 左上角の日時領域を切り出し
3. **Enhanced OCR処理**: 
   - 複数画像バリエーション生成（拡大、コントラスト調整等）
   - 各バリエーションでOCR実行
   - 最適な結果を自動選択
4. **タイムスタンプ解析**: JST→UTC変換
5. **EXIF埋め込み**: FFmpegでメタデータ追加

## パフォーマンス

### 標準的な処理時間（sample.mp4）
- **フレーム抽出**: 0.017秒
- **OCR処理**: 0.471秒（Enhanced OCR使用時）
- **EXIF埋め込み**: 0.5-2.0秒
- **総処理時間**: 1.0-3.0秒

### OCR精度
- **基本OCR**: 70-80%
- **Enhanced OCR**: 85-95%
- **信頼度**: EasyOCRの信頼度スコア活用

## エラーハンドリング

### 自動エラー回復
- フレーム抽出失敗時の再試行
- OCR失敗時の別バリエーション試行
- タイムスタンプパース失敗時の異なるパターン適用

### エラー種別
- `FRAME_EXTRACTION_FAILED`: フレーム抽出エラー
- `OCR_FAILED`: OCR処理エラー
- `TIMESTAMP_PARSE_FAILED`: タイムスタンプ解析エラー
- `FFMPEG_FAILED`: EXIF埋め込みエラー

### 失敗ファイルの管理
- `failed/`ディレクトリに自動移動
- エラー理由をテキストファイルに記録
- クロップ画像も保存（デバッグ用）

## 適用場面

### ✅ 推奨用途
- 日常的なビデオ処理
- 本番環境での安定運用
- 大量ファイルのバッチ処理
- リソース制約のある環境

### ⚠️ 制限事項
- 極めて低品質な動画では精度が低下
- 特殊なタイムスタンプフォーマットは非対応
- ML処理と比較して精度は劣る

## トラブルシューティング

### よくある問題

**OCRが認識しない**
```bash
# デバッグモードで詳細確認
python exif_enchanter.py sample.mp4 --debug

# GPU使用で高速化
python exif_enchanter.py sample.mp4 --gpu

# 信頼度閾値を下げる
python exif_enchanter.py sample.mp4 --confidence 0.3
```

**処理が遅い**
```bash
# Enhanced OCRを無効化
python exif_enchanter.py sample.mp4 --disable-enhanced-ocr

# 並列処理数を調整
python exif_enchanter.py --batch /path/to/videos/ --max-workers 2
```

**メモリ不足**
```bash
# スレッド使用でメモリ使用量削減
python exif_enchanter.py --batch /path/to/videos/ --use-threading

# バッチサイズを小さく
python exif_enchanter.py --batch /path/to/videos/ --batch-size 5
```

## 他スクリプトとの比較

| 項目 | exif_enchanter.py | exif_enchanter_ocr.py |
|------|-------------------|-----------------------|
| 安定性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 処理速度 | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| OCR精度 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| リソース使用量 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 依存関係 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 困難ケース対応 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**推奨場面**: 日常使用、本番環境、安定性重視
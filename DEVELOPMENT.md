# 開発者向けガイド

## 概要

Xiaomi Video EXIF Enhancerの開発・拡張に関する技術情報を記載したドキュメントです。

## アーキテクチャ

### 技術スタック
- **Python 3.8以上**: メイン実装言語
- **OpenCV**: 映像フレーム抽出・画像処理
- **EasyOCR**: 日時テキスト読み取り（英語・日本語対応）
- **piexif**: EXIF情報操作
- **ffmpeg-python**: 映像ファイル処理

### 主要コンポーネント
```
exif_enhancer.py
├── XiaomiVideoEXIFEnhancer     # メインクラス
├── extract_first_frame()       # フレーム抽出
├── crop_timestamp_area()       # タイムスタンプ領域切り出し
├── extract_timestamp()         # OCR処理
├── parse_timestamp()          # 日時パース
└── add_exif_data()           # EXIF埋め込み
```

## 主要機能

### 1. OCR処理と信頼度管理
- **信頼度閾値**: デフォルト0.6、実測0.775達成
- **複数言語対応**: 英語・日本語で高精度検出
- **パフォーマンス**: フレーム抽出<1秒、OCR処理<10秒

### 2. Xiaomiカメラ特有の対応
- **タイムスタンプ形式**: `@ 2025/05/28 19.41.14` (JST)
- **タイムゾーン処理**: JST（UTC+9）→UTC自動変換
- **正規表現パターン**: ドット区切り・@記号に対応
- **クロップ最適化**: 解像度に応じた適応的クロップ比率
- **FFmpeg統合**: 実際のEXIFメタデータ埋め込み完了

### 3. タイムゾーン対応とエラーハンドリング
```python
# JST→UTC自動変換（標準機能）
enhancer = XiaomiVideoEXIFEnhancer()

# デバッグモードでの詳細ログ
enhancer = XiaomiVideoEXIFEnhancer(debug=True)

# 包括的エラーハンドリング
try:
    result = enhancer.process_video(video_path)
except VideoProcessingError as e:
    logger.error(f"処理エラー: {e}")
```

## 開発環境セットアップ

### 基本インストール
```bash
# プロジェクトクローン
git clone https://github.com/your-username/xiaomi-video-exif-enchanter.git
cd xiaomi-video-exif-enchanter

# 依存関係インストール
pip install -e .[dev]
```

### テスト実行
```bash
# 基本テスト
python -m unittest test_exif_enhancer.py -v

# サンプル動画統合テスト
python test_sample_video.py -v

# OCR精度・パフォーマンステスト
python test_ocr_accuracy.py -v

# バッチ処理テスト（新規）
python test_batch_processing.py -v

# FFmpeg統合テスト（新規）
python test_ffmpeg_fix.py -v

# タイムゾーン変換テスト（新規）
python test_creation_time_embedding.py -v

# 全テストスイート実行
python -m unittest discover -s . -p "test_*.py" -v
```

### 新機能のデバッグ
```bash
# タイムゾーン変換の確認
python exif_enhancer.py sample.mp4 --debug

# バッチ処理のテスト
mkdir test_batch && cp sample.mp4 test_batch/
python exif_enhancer.py --batch test_batch --debug

# FFmpegメタデータ確認
ffprobe -v quiet -show_entries format_tags=creation_time output_sample.mp4
```

## 主要な技術的課題と解決策

### 1. 正規表現パターンの最適化
**課題**: Xiaomiカメラ特有のタイムスタンプ形式
**解決**: 複数パターン対応
```python
TIMESTAMP_PATTERNS = [
    r'@?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:.](\d{2})[:.](\d{2})',
    r'@?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})',
    r'@?\s*(\d{4})(\d{2})(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})',
]
```

### 2. OCR精度の向上
**課題**: EasyOCRの信頼度とクロップ領域の最適化
**解決**: 
- 適応的クロップ比率（SD: 0.3, HD: 0.25, FHD: 0.2, 4K: 0.15）
- 二段階信頼度システム：メイン0.6、フォールバック0.3
- フォールバック機能により低信頼度でも形式合致時に処理
- 実測で`町 2025/05/28 19.41.14`（信頼度0.311）の解析に成功

### 3. タイムゾーン処理の実装
**課題**: JST表示のタイムスタンプをUTCとして正確に記録
**解決**:
- `datetime.timezone`を使用したJST（UTC+9）の明示的定義
- `astimezone(timezone.utc)`によるUTC変換
- FFmpegの`-metadata creation_time`での正確な埋め込み
- 夏時間やうるう秒に影響されない堅牢な実装

### 4. Python 3.13 互換性
**課題**: 最新Python環境での依存関係エラー
**解決**: バージョン制約緩和 + 個別インストール対応

### 5. 自動出力パス生成
**課題**: ユーザーが毎回出力ファイル名を指定する手間
**解決**:
- `output_path_generator.py`による自動命名システム
- 既存ファイル重複回避（`_1`, `_2`などの連番付与）
- 入力ファイル名ベースの直感的な命名規則
- バッチ処理での大量ファイル対応

## 拡張ポイント

### 1. 他機種対応
- 新しいタイムスタンプ形式の追加
- 異なるクロップ領域の対応
- カメラ固有の処理ロジック
- 他メーカーのタイムゾーン設定対応

### 2. 処理性能向上
- 並列処理の導入（バッチ処理で部分実装済み）
- メモリ効率の改善
- キャッシュ機能の実装
- GPU加速OCRの最適化

### 3. 機能拡張
- ✅ バッチ処理対応（完了）
- GUI版の開発
- 複数言語OCR対応の拡張
- メタデータ編集機能の追加

## 最新の技術的成果（2025年実装済み）

### ✅ 完了済み機能
1. **FFmpeg統合**: 実際のEXIFメタデータ埋め込み処理完了
2. **タイムゾーン処理**: JST⇒UTC完全対応
3. **バッチ処理**: 複数ファイル一括処理機能実装
4. **自動出力管理**: 重複回避・自動命名システム
5. **包括的エラーハンドリング**: 堅牢な処理継続機能
6. **Docker完全対応**: 環境構築不要の実行環境

### 🔄 進行中の改善
1. **他機種対応**: Xiaomi以外のカメラ形式への拡張
2. **GUI版の開発**: 非技術者向けインターフェース
3. **パフォーマンス最適化**: 並列処理・GPU活用
4. **メタデータ拡張**: GPS情報・撮影設定の追加

### 🎯 将来計画
1. **クラウド対応**: オンライン処理サービス化
2. **AI強化**: 高精度タイムスタンプ認識
3. **マルチフォーマット**: 動画以外のメディア対応
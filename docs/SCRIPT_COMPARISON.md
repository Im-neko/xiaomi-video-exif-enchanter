# スクリプト比較ガイド

## 概要

Xiaomi Video EXIF Enchanterは3つの専用スクリプトを提供し、用途に応じて最適な処理方式を選択できます。

## 比較表

| 項目 | exif_enchanter.py | exif_enchanter_ocr.py | exif_enchanter_ml.py |
|------|-------------------|----------------------|---------------------|
| **用途** | 標準OCR処理 | 強化OCR処理 | ML+OCR処理 |
| **精度** | ⭐⭐⭐ (70-80%) | ⭐⭐⭐⭐ (85-95%) | ⭐⭐⭐⭐⭐ (99-100%) |
| **処理速度** | ⭐⭐⭐⭐ (1-3秒) | ⭐⭐⭐ (3-8秒) | ⭐⭐⭐⭐ (0.8-6秒) |
| **安定性** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **リソース使用量** | ⭐⭐⭐⭐⭐ (低) | ⭐⭐⭐⭐ (中) | ⭐⭐ (高) |
| **依存関係** | ⭐⭐⭐⭐⭐ (軽量) | ⭐⭐⭐⭐ (中程度) | ⭐⭐ (重い) |
| **GPU対応** | ✅ | ✅ | ✅✅ |
| **デバッグ機能** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

## 詳細比較

### exif_enchanter.py（標準版）

#### ✅ 適用場面
- 日常的なビデオ処理
- 本番環境での安定運用
- リソース制約のある環境
- 機械学習環境が不要

#### 🔧 技術仕様
- **OCRエンジン**: EasyOCR
- **前処理**: 基本的な拡大・コントラスト調整
- **処理時間**: 1-3秒/ファイル
- **メモリ使用量**: 低（200-500MB）
- **依存関係**: OpenCV, EasyOCR, piexif, ffmpeg-python

#### 📊 パフォーマンス
```
フレーム抽出: 0.017秒
OCR処理:     0.471秒
EXIF埋め込み: 0.5-2.0秒
総処理時間:   1.0-3.0秒
```

---

### exif_enchanter_ocr.py（強化OCR版）

#### ✅ 適用場面
- OCR精度を最大化したい場合
- 低品質・ノイズの多い動画
- 複雑なタイムスタンプフォーマット
- 詳細な前処理分析が必要

#### 🔧 技術仕様
- **OCRエンジン**: EasyOCR + Tesseract
- **前処理**: 7種類の画像バリエーション
  - オリジナル、2倍拡大、3倍拡大
  - コントラスト強化、余白追加
  - 組み合わせ処理
- **処理時間**: 3-8秒/ファイル
- **メモリ使用量**: 中（500MB-1GB）

#### 📊 前処理技術詳細
```python
variants = [
    "original",               # オリジナル画像
    "enlarged_2x",           # 2倍拡大
    "enlarged_3x",           # 3倍拡大  
    "contrast_enhanced",     # コントラスト強化
    "enlarged_2x_contrast",  # 拡大+コントラスト
    "padded_uniform_20",     # 余白追加
    "padded_contrast"        # 余白+コントラスト
]
```

#### 📈 精度向上効果
- **基本OCR**: 70-80%
- **Enhanced OCR**: 85-95%
- **+ Tesseract**: 90-98%

---

### exif_enchanter_ml.py（ML版）

#### ✅ 適用場面
- 最高精度が要求される業務用途
- GPU環境での高速処理
- AI/ML技術活用プロジェクト
- 大量ファイルの自動処理

#### 🔧 技術仕様
- **MLモデル**: CRNN-CTC + アテンション
- **モデルサイズ**: 35MB（8.9M パラメータ）
- **文字セット**: 15文字 `['<BLANK>', ' ', '.', '/', '0-9', ':']`
- **フォールバック**: OCR自動切り替え
- **処理時間**: 0.8-6秒/ファイル（GPU/CPU依存）

#### 🧠 MLアーキテクチャ
```python
class XiaomiTimestampCRNN:
    Conv Block 1: 64 filters    # 特徴抽出
    Conv Block 2: 128 filters   # パターン認識
    Conv Block 3: 256 filters   # 高レベル特徴
    Conv Block 4: 512 filters   # 最終特徴
    
    LSTM 1: 256 units (bi-dir)  # シーケンス処理
    LSTM 2: 256 units (bi-dir)  # 文脈理解
    
    Attention: 8 heads          # 重要部分集中
    CTC Loss: 15 classes        # 文字認識
```

#### 🚀 GPU最適化
- **RTX 5070 Ti**: 3-10倍高速化
- **CUDA 12.8**: 最新GPU対応
- **AMP**: 自動混合精度
- **メモリ効率**: 1.8GB VRAM

## 選択指針

### 🎯 用途別推奨

#### 日常使用・本番環境
```bash
# 推奨: exif_enchanter.py
python exif_enchanter.py sample.mp4 --location "リビング"
```
- ✅ 安定性最優先
- ✅ 軽量で高速
- ✅ 依存関係最小

#### OCR精度重視
```bash
# 推奨: exif_enchanter_ocr.py  
python exif_enchanter_ocr.py sample.mp4 --debug
```
- ✅ 複雑なケースに対応
- ✅ 詳細なデバッグ機能
- ✅ 複数エンジン利用

#### 最高精度要求
```bash
# 推奨: exif_enchanter_ml.py
python exif_enchanter_ml.py sample.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth --gpu
```
- ✅ 100%に近い精度
- ✅ AI技術活用
- ✅ GPU高速化

### 🏗️ 環境別推奨

#### リソース制約環境
- **推奨**: `exif_enchanter.py`
- **理由**: 最小依存関係、低メモリ使用量

#### 高性能サーバー環境
- **推奨**: `exif_enchanter_ml.py`
- **理由**: GPU活用、最高精度

#### 開発・テスト環境
- **推奨**: `exif_enchanter_ocr.py`
- **理由**: 詳細デバッグ、柔軟性

## 移行ガイド

### 標準版 → 強化OCR版
```bash
# 現在
python exif_enchanter.py sample.mp4

# 移行後（OCR精度向上）
python exif_enchanter_ocr.py sample.mp4
```

### 標準版 → ML版
```bash
# 現在
python exif_enchanter.py sample.mp4

# 移行後（最高精度）
python exif_enchanter_ml.py sample.mp4 --model-path models/fixed_xiaomi_timestamp_model.pth
```

### パラメータ互換性
```bash
# 共通パラメータ（全スクリプトで利用可能）
--debug                    # デバッグモード
--location "場所"          # 撮影場所
--batch /path/to/videos/   # バッチ処理
--output output.mp4        # 出力ファイル
--max-workers 4           # 並列処理数
```

## パフォーマンス実測値

### 処理時間比較（sample.mp4）
| スクリプト | GPU使用 | CPU使用 | 精度 |
|-----------|---------|---------|------|
| exif_enchanter.py | 1.0秒 | 1.2秒 | 75% |
| exif_enchanter_ocr.py | 3.0秒 | 5.0秒 | 92% |
| exif_enchanter_ml.py | 0.8秒 | 3.5秒 | 100% |

### バッチ処理性能（100ファイル）
| スクリプト | 総処理時間 | スループット | 成功率 |
|-----------|-----------|-------------|--------|
| exif_enchanter.py | 2分30秒 | 40 files/min | 85% |
| exif_enchanter_ocr.py | 8分20秒 | 12 files/min | 95% |
| exif_enchanter_ml.py | 2分45秒 | 36 files/min | 99% |

## まとめ

### 🎯 推奨フローチャート
```
動画処理が必要
    ↓
精度要求は？
    ↓
[標準] → exif_enchanter.py       # 日常使用
[高精度] → exif_enchanter_ocr.py  # OCR精度重視
[最高精度] → exif_enchanter_ml.py # ML活用

GPU環境あり？
    ↓
[Yes] → exif_enchanter_ml.py     # GPU加速
[No] → 用途に応じて選択

困難なケース？
    ↓
[Yes] → exif_enchanter_ocr.py    # 複数前処理
[No] → exif_enchanter.py         # 標準処理
```

各スクリプトは特定の用途に最適化されており、目的に応じて適切に選択することで最高の結果を得られます。
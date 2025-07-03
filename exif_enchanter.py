#!/usr/bin/env python3
"""
Xiaomi Video EXIF Enhancer (Refactored)
Xiaomiホームカメラ(C301)で録画された映像のEXIF情報を拡張するツール
"""

import argparse
import cv2
import easyocr
import piexif
import os
import sys
from datetime import datetime, timezone, timedelta
import re
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
from functools import lru_cache
from video_error_handler import VideoErrorHandler, VideoErrorType
from batch_processor import BatchProcessor
from file_manager import validate_video_file, validate_output_path

# タイムスタンプ検出用の正規表現パターン定数
TIMESTAMP_PATTERNS = [
    # コロン区切り形式: 2024/12/28 15:30:45
    r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})',
    # ハイフン区切り形式: 2024/12/28 15.30.45
    r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}).(\d{2}).(\d{2})',
]

class EasyOCRSingleton:
    """EasyOCRインスタンスのシングルトン管理クラス"""
    _instance = None
    _reader = None
    
    @classmethod
    def get_reader(cls, languages: List[str] = None, gpu: bool = None, debug: bool = False) -> easyocr.Reader:
        """EasyOCRリーダーのシングルトンインスタンスを取得"""
        if languages is None:
            languages = ['en', 'ja']
        
        if gpu is None:
            gpu = False
        
        # 設定が変更された場合は新しいインスタンスを作成
        config_key = (tuple(languages), gpu)
        
        if cls._reader is None or getattr(cls, '_config', None) != config_key:
            if debug:
                print(f"Creating new EasyOCR reader with languages: {languages}, GPU: {gpu}")
            
            try:
                cls._reader = easyocr.Reader(languages, gpu=gpu)
                cls._config = config_key
                
                if debug:
                    print("EasyOCR reader created successfully")
            except Exception as e:
                if debug:
                    print(f"Failed to create EasyOCR reader: {e}")
                raise
        
        return cls._reader
    
    @classmethod
    def clear_cache(cls):
        """キャッシュをクリア"""
        cls._reader = None
        cls._config = None


class XiaomiVideoExifEnchanter:
    """Xiaomi動画のEXIF情報を拡張するメインクラス"""
    
    def __init__(self, debug: bool = False, languages: List[str] = None, use_gpu: bool = None, 
                 enhanced_ocr: bool = True) -> None:
        """
        Args:
            debug: デバッグモードの有効化
            languages: OCRで使用する言語リスト
            use_gpu: GPU使用フラグ
            enhanced_ocr: 改良版OCRの使用（複数前処理・複数エンジン）
        """
        self.debug = debug
        self.languages = languages if languages else ['en', 'ja']
        self.use_gpu = use_gpu if use_gpu is not None else False
        self.enhanced_ocr = enhanced_ocr
        self.confidence_threshold = 0.5
        
        # エラーハンドラーの初期化
        try:
            self.error_handler = VideoErrorHandler()
        except Exception as e:
            if self.debug:
                print(f"Warning: Could not initialize VideoErrorHandler: {e}")
            self.error_handler = None
        
        if self.debug:
            print(f"XiaomiVideoExifEnhancer initialized with languages: {self.languages}, GPU: {self.use_gpu}")
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """OCR信頼度の閾値を設定"""
        self.confidence_threshold = max(0.0, min(1.0, threshold))
        if self.debug:
            print(f"OCR confidence threshold set to: {self.confidence_threshold}")
    
    def get_ocr_languages(self) -> List[str]:
        """設定されているOCR言語を取得"""
        return self.languages.copy()
    
    def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """動画ファイルの基本情報を取得"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {'error': 'Could not open video file'}
            
            info = {
                'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                'fps': cap.get(cv2.CAP_PROP_FPS),
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'duration_seconds': 0
            }
            
            if info['fps'] > 0:
                info['duration_seconds'] = info['frame_count'] / info['fps']
            
            cap.release()
            return info
            
        except Exception as e:
            return {'error': str(e)}
    
    def is_supported_format(self, video_path: str) -> bool:
        """サポートされている動画形式かチェック"""
        supported_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
        file_extension = Path(video_path).suffix.lower()
        return file_extension in supported_extensions
    
    def extract_first_frame(self, video_path: str) -> np.ndarray:
        """動画の最初のフレームを抽出"""
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise ValueError(f"Could not read frame from video: {video_path}")
        
        return frame
    
    def save_debug_frame(self, frame: np.ndarray, filename: str = "debug_frame.jpg") -> bool:
        """デバッグ用にフレームを保存"""
        try:
            # debugフォルダを作成
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            
            # debug/以下にファイルを保存
            debug_path = debug_dir / filename
            cv2.imwrite(str(debug_path), frame)
            if self.debug:
                print(f"Debug frame saved: {debug_path}")
            return True
        except Exception as e:
            if self.debug:
                print(f"Failed to save debug frame: {e}")
            return False
    
    def crop_timestamp_area(self, frame: np.ndarray, crop_ratio: Optional[float] = None, 
                           use_fixed_position: bool = False) -> np.ndarray:
        """タイムスタンプ領域をクロップ（統合メソッド）"""
        # Xiaomi動画の固定タイムスタンプ位置を使用
        return self.crop_timestamp_area_xiaomi_fixed(frame)
    
    def crop_timestamp_area_xiaomi_fixed(self, frame: np.ndarray) -> np.ndarray:
        """Xiaomi動画専用の固定タイムスタンプ位置でクロップ
        
        タイムスタンプ領域の座標:
        - 左上: (20/640*width, 0)
        - 右上: (155/640*width, 0)  
        - 左下: (20/640*width, 16/360*height)
        - 右下: (155/640*width, 16/360*height)
        """
        height, width = frame.shape[:2]
        
        # 指定された座標を計算
        x_start = int(20 * width // 640)  # 20/640 * width
        y_start = 0
        x_end = int(155 * width // 640)  # 155/640 * width
        y_end = int(16 * height // 360)  # 16/360 * height
        
        # 座標の境界チェック
        x_end = min(x_end, width)
        y_end = min(y_end, height)
        
        if self.debug:
            print(f"Xiaomi timestamp crop coordinates: ({x_start}, {y_start}) to ({x_end}, {y_end})")
            print(f"Frame size: {width}x{height}, Crop size: {x_end-x_start}x{y_end-y_start}")
        
        # 領域をクロップ
        cropped_frame = frame[y_start:y_end, x_start:x_end]
        
        return cropped_frame
    
    def crop_timestamp_area_adaptive(self, frame: np.ndarray) -> np.ndarray:
        """動的にタイムスタンプ領域をクロップ"""
        height, width = frame.shape[:2]
        
        # フレームサイズに基づいて動的にクロップ範囲を決定
        if width >= 1920:  # FHD以上
            crop_ratio = 0.15
        elif width >= 1280:  # HD
            crop_ratio = 0.18
        else:  # SD
            crop_ratio = 0.2
        
        crop_height = int(height * crop_ratio)
        return frame[-crop_height:, :]
    
    def crop_timestamp_area_fixed(self, frame: np.ndarray) -> np.ndarray:
        """固定位置でタイムスタンプ領域をクロップ"""
        height, width = frame.shape[:2]
        
        # Xiaomiカメラの一般的なタイムスタンプ位置
        # 右下隅の固定サイズ領域
        timestamp_width = min(300, width // 3)
        timestamp_height = min(60, height // 8)
        
        x_start = width - timestamp_width
        y_start = height - timestamp_height
        
        return frame[y_start:, x_start:]
    
    def crop_timestamp_area_smart(self, frame: np.ndarray) -> np.ndarray:
        """スマートタイムスタンプ領域検出"""
        height, width = frame.shape[:2]
        
        # 複数の候補領域を試行
        candidates = [
            frame[-80:, -300:],  # 右下角
            frame[-60:, :],      # 下部全体
            frame[-100:, -400:], # 右下大きめ
        ]
        
        # 各候補でOCRを実行し、最も確信度の高い結果を選択
        best_crop = candidates[0]  # デフォルト
        best_confidence = 0
        
        try:
            reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, self.debug)
            
            for candidate in candidates:
                try:
                    results = reader.readtext(candidate)
                    if results:
                        max_confidence = max(result[2] for result in results)
                        if max_confidence > best_confidence:
                            best_confidence = max_confidence
                            best_crop = candidate
                except Exception:
                    continue
                    
        except Exception as e:
            if self.debug:
                print(f"Smart crop fallback to default: {e}")
        
        return best_crop
    
    def save_cropped_area(self, cropped_frame: np.ndarray, filename: str = "cropped_timestamp.jpg") -> bool:
        """クロップされた領域を保存"""
        try:
            # debugフォルダを作成
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            
            # debug/以下にファイルを保存
            debug_path = debug_dir / filename
            cv2.imwrite(str(debug_path), cropped_frame)
            if self.debug:
                print(f"Cropped area saved: {debug_path}")
            return True
        except Exception as e:
            if self.debug:
                print(f"Failed to save cropped area: {e}")
            return False
    
    def get_fixed_timestamp_coordinates(self, frame: np.ndarray) -> tuple:
        """固定タイムスタンプ座標を取得"""
        height, width = frame.shape[:2]
        
        # Xiaomiカメラの典型的なタイムスタンプ位置
        x_start = width - 300
        y_start = height - 60
        x_end = width
        y_end = height
        
        return (max(0, x_start), max(0, y_start), min(width, x_end), min(height, y_end))
    
    def get_optimal_crop_ratio(self, frame: np.ndarray) -> float:
        """最適なクロップ比率を決定"""
        height, width = frame.shape[:2]
        
        # 解像度に基づく最適比率
        if width >= 1920:
            return 0.12
        elif width >= 1280:
            return 0.15
        else:
            return 0.18
    
    def extract_timestamp(self, cropped_frame: np.ndarray, input_path: str = None) -> Optional[str]:
        """クロップされたフレームからタイムスタンプを抽出（改良版）"""
        # 改良版OCRが有効な場合は試行
        if self.enhanced_ocr:
            enhanced_result = self._enhanced_extract_timestamp(cropped_frame, input_path)
            if enhanced_result:
                return enhanced_result
        
        # フォールバック: オリジナルの基本版OCR
        try:
            reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, self.debug)
            results = reader.readtext(cropped_frame)
            
            if not results:
                return None
            
            return self._find_best_timestamp_match(results)
            
        except Exception as e:
            if self.debug:
                print(f"OCR error: {e}")
            return None
    
    def _find_best_timestamp_match(self, ocr_results: List[Tuple]) -> Optional[str]:
        """OCR結果から最適なタイムスタンプを検索"""
        best_match = None
        best_confidence = 0
        
        for result in ocr_results:
            text = result[1]
            confidence = result[2]
            
            if confidence < self.confidence_threshold:
                continue
            
            # 各パターンでマッチング
            for pattern in TIMESTAMP_PATTERNS:
                if re.search(pattern, text):
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = text
                        break
        
        if self.debug and best_match:
            print(f"Best timestamp match: '{best_match}' (confidence: {best_confidence:.3f})")
        
        return best_match
    
    def extract_timestamp_with_details(self, cropped_frame: np.ndarray) -> Dict[str, Any]:
        """詳細情報付きでタイムスタンプを抽出"""
        try:
            reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, self.debug)
            results = reader.readtext(cropped_frame)
            
            return {
                'timestamp': self._find_best_timestamp_match(results) if results else None,
                'all_text': [result[1] for result in results],
                'confidences': [result[2] for result in results],
                'bounding_boxes': [result[0] for result in results],
                'ocr_count': len(results)
            }
            
        except Exception as e:
            return {
                'timestamp': None,
                'error': str(e),
                'all_text': [],
                'confidences': [],
                'bounding_boxes': [],
                'ocr_count': 0
            }
    
    def _enhanced_extract_timestamp(self, cropped_frame: np.ndarray, input_path: str = None) -> Optional[str]:
        """改良版タイムスタンプ抽出（複数の前処理と複数回試行）"""
        if self.debug:
            print("Starting enhanced OCR extraction...")
        
        # 複数の前処理バリエーションを生成
        processed_images = self._generate_image_variants(cropped_frame)
        
        # デバッグ時は前処理した画像も保存
        if self.debug and input_path:
            self._save_debug_variants(processed_images, input_path)
        
        # 各画像バリエーションでOCRを実行
        all_results = []
        
        for i, (variant_name, image) in enumerate(processed_images):
            if self.debug:
                print(f"  Trying variant {i+1}/{len(processed_images)}: {variant_name}")
            
            # EasyOCRで試行
            easyocr_result = self._try_easyocr(image, variant_name)
            if easyocr_result:
                all_results.append(('EasyOCR', variant_name, easyocr_result))
            
            # Tesseractで試行（利用可能な場合）
            tesseract_result = self._try_tesseract(image, variant_name)
            if tesseract_result:
                all_results.append(('Tesseract', variant_name, tesseract_result))
        
        # 最適な結果を選択
        best_result = self._select_best_ocr_result(all_results)
        
        if self.debug and best_result:
            print(f"Enhanced OCR selected: '{best_result['text']}' from {best_result['engine']} ({best_result['variant']}) with confidence {best_result['confidence']:.3f}")
        
        return best_result['text'] if best_result else None
    
    def _generate_image_variants(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        """画像の複数のバリエーションを生成（最適化版）"""
        variants = []
        height, width = image.shape[:2]
        
        # オリジナル
        variants.append(("original", image.copy()))
        
        # 2倍拡大（最も効果的）
        enlarged_2x = cv2.resize(image, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        variants.append(("enlarged_2x", enlarged_2x))
        
        # 3倍拡大
        enlarged_3x = cv2.resize(image, (width * 3, height * 3), interpolation=cv2.INTER_CUBIC)
        variants.append(("enlarged_3x", enlarged_3x))
        
        # コントラスト調整
        contrast_enhanced = self._enhance_contrast(image)
        variants.append(("contrast_enhanced", contrast_enhanced))
        
        # 拡大 + コントラスト（効果的な組み合わせ）
        enlarged_contrast = self._enhance_contrast(enlarged_2x)
        variants.append(("enlarged_2x_contrast", enlarged_contrast))
        
        # 余白付き（OCR精度向上）
        padded_uniform_20 = self._apply_uniform_padding(image, 20)
        variants.append(("padded_uniform_20", padded_uniform_20))
        
        # 余白 + コントラスト強化
        padded_contrast = self._enhance_contrast(padded_uniform_20)
        variants.append(("padded_contrast", padded_contrast))
        
        # 二値化処理（OCR精度向上のため復活）
        binary = self._apply_binary_threshold(image)
        variants.append(("binary", binary))
        
        # アダプティブ二値化（文字境界強化）
        adaptive_binary = self._apply_adaptive_threshold(image)
        variants.append(("adaptive_binary", adaptive_binary))
        
        # シャープ化（文字鮮明化）
        sharpened = self._apply_sharpening(image)
        variants.append(("sharpened", sharpened))
        
        # 拡大 + 二値化（効果的な組み合わせ）
        enlarged_binary = self._apply_binary_threshold(enlarged_2x)
        variants.append(("enlarged_2x_binary", enlarged_binary))
        
        return variants
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """コントラスト強化"""
        # CLAHEを使用
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        return enhanced
    
    def _apply_binary_threshold(self, image: np.ndarray) -> np.ndarray:
        """二値化処理"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Otsuの方法で二値化
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return binary
    
    def _apply_uniform_padding(self, image: np.ndarray, padding_size: int, 
                              color: Tuple[int, int, int] = (255, 255, 255)) -> np.ndarray:
        """画像に均一な余白を追加"""
        if len(image.shape) == 3:
            # カラー画像の場合
            return cv2.copyMakeBorder(image, padding_size, padding_size, 
                                    padding_size, padding_size, 
                                    cv2.BORDER_CONSTANT, value=color)
        else:
            # グレースケール画像の場合
            return cv2.copyMakeBorder(image, padding_size, padding_size, 
                                    padding_size, padding_size, 
                                    cv2.BORDER_CONSTANT, value=color[0])
    
    def _apply_adaptive_padding(self, image: np.ndarray) -> np.ndarray:
        """画像内容に応じた適応的な余白を追加"""
        height, width = image.shape[:2]
        
        # 画像サイズに基づいて余白サイズを決定
        base_padding = max(10, min(width, height) // 20)
        
        # エッジ検出で境界を分析
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # エッジ密度に基づいて余白を調整
        edges = cv2.Canny(gray, 50, 150)
        
        # 各辺のエッジ密度を計算
        top_edges = np.sum(edges[:5, :]) / (5 * width)
        bottom_edges = np.sum(edges[-5:, :]) / (5 * width)
        left_edges = np.sum(edges[:, :5]) / (height * 5)
        right_edges = np.sum(edges[:, -5:]) / (height * 5)
        
        # エッジ密度が高い場合はより多くの余白を追加
        top_padding = base_padding + int(top_edges * 15)
        bottom_padding = base_padding + int(bottom_edges * 15)
        left_padding = base_padding + int(left_edges * 15)
        right_padding = base_padding + int(right_edges * 15)
        
        # 余白を追加
        if len(image.shape) == 3:
            return cv2.copyMakeBorder(image, top_padding, bottom_padding, 
                                    left_padding, right_padding, 
                                    cv2.BORDER_CONSTANT, value=(255, 255, 255))
        else:
            return cv2.copyMakeBorder(image, top_padding, bottom_padding, 
                                    left_padding, right_padding, 
                                    cv2.BORDER_CONSTANT, value=255)
    
    def _apply_morphological_enhancement(self, image: np.ndarray) -> np.ndarray:
        """モルフォロジー演算によるテキスト強調"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # カーネルサイズをテキストサイズに応じて調整
        kernel_size = max(1, min(gray.shape) // 100)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        
        # クロージング演算（ディレーション -> エロージョン）
        # 文字の空白を埋めて連結性を向上
        closing = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        
        # オープニング演算（エロージョン -> ディレーション）
        # ノイズ除去と文字分離
        opening = cv2.morphologyEx(closing, cv2.MORPH_OPEN, kernel)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(opening, cv2.COLOR_GRAY2BGR)
        return opening
    
    def _apply_gamma_correction(self, image: np.ndarray, gamma: float) -> np.ndarray:
        """ガンマ補正による明度調整"""
        # ガンマ補正用のルックアップテーブル作成
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        
        # ルックアップテーブル適用
        return cv2.LUT(image, table)
    
    def _apply_super_resolution(self, image: np.ndarray) -> np.ndarray:
        """超解像度アップスケーリング（INTER_CUBIC以上）"""
        height, width = image.shape[:2]
        
        # 4倍拡大で高品質アップスケーリング
        super_res = cv2.resize(image, (width * 4, height * 4), interpolation=cv2.INTER_LANCZOS4)
        
        # アンシャープマスクで追加シャープ化
        if len(super_res.shape) == 3:
            gray_temp = cv2.cvtColor(super_res, cv2.COLOR_BGR2GRAY)
        else:
            gray_temp = super_res
        
        # アンシャープマスク適用
        kernel = np.array([[-1,-1,-1,-1,-1],
                          [-1, 2, 2, 2,-1],
                          [-1, 2, 8, 2,-1],
                          [-1, 2, 2, 2,-1],
                          [-1,-1,-1,-1,-1]]) / 8.0
        
        sharpened = cv2.filter2D(gray_temp, -1, kernel)
        
        if len(image.shape) == 3:
            # カラー画像の場合、シャープ化を元画像にブレンド
            sharpened_bgr = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
            return cv2.addWeighted(super_res, 0.7, sharpened_bgr, 0.3, 0)
        
        return sharpened
    
    def _apply_convolution_enhancement(self, image: np.ndarray) -> np.ndarray:
        """畳み込みベース強化（研究ベース）"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 研究で効果が実証されたカーネル
        # エッジ強化 + コントラスト強化の組み合わせ
        edge_kernel = np.array([[-1, -1, -1],
                               [-1,  8, -1],
                               [-1, -1, -1]])
        
        contrast_kernel = np.array([[0, -1, 0],
                                   [-1, 5, -1],
                                   [0, -1, 0]])
        
        # エッジ強化適用
        edge_enhanced = cv2.filter2D(gray, -1, edge_kernel)
        edge_enhanced = np.clip(edge_enhanced, 0, 255).astype(np.uint8)
        
        # コントラスト強化適用
        final = cv2.filter2D(edge_enhanced, -1, contrast_kernel)
        final = np.clip(final, 0, 255).astype(np.uint8)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(final, cv2.COLOR_GRAY2BGR)
        return final
    
    def _enhance_low_contrast_text(self, image: np.ndarray) -> np.ndarray:
        """低コントラストテキスト特化処理"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # ヒストグラム平均化でコントラスト改善
        equalized = cv2.equalizeHist(gray)
        
        # CLAHE（コントラスト制限適応的ヒストグラム平均化）
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
        clahe_applied = clahe.apply(gray)
        
        # アダプティブ二値化でテキスト分離
        adaptive_thresh = cv2.adaptiveThreshold(clahe_applied, 255, 
                                              cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                              cv2.THRESH_BINARY, 11, 2)
        
        # 結果を組み合わせて最適化
        combined = cv2.addWeighted(equalized, 0.5, clahe_applied, 0.5, 0)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(combined, cv2.COLOR_GRAY2BGR)
        return combined
    
    def _apply_adaptive_threshold(self, image: np.ndarray) -> np.ndarray:
        """アダプティブ二値化"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, 11, 2)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(adaptive, cv2.COLOR_GRAY2BGR)
        return adaptive
    
    def _apply_sharpening(self, image: np.ndarray) -> np.ndarray:
        """シャープ化フィルタ"""
        kernel = np.array([[-1,-1,-1],
                          [-1, 9,-1],
                          [-1,-1,-1]])
        sharpened = cv2.filter2D(image, -1, kernel)
        return sharpened
    
    def _apply_denoising(self, image: np.ndarray) -> np.ndarray:
        """ノイズ除去"""
        if len(image.shape) == 3:
            return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
        else:
            return cv2.fastNlMeansDenoising(image, None, 10, 7, 21)
    
    def _enhance_white_on_dark_text(self, image: np.ndarray) -> np.ndarray:
        """白文字on黒背景専用の強化処理"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 1. ヒストグラム平均化で輝度分布を改善
        equalized = cv2.equalizeHist(gray)
        
        # 2. CLAHE for 局所的コントラスト改善
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8,8))
        clahe_applied = clahe.apply(gray)
        
        # 3. 白文字領域の強調（上位ピクセルの明度を上げる）
        bright_mask = gray > np.percentile(gray, 85)
        enhanced = gray.copy()
        enhanced[bright_mask] = np.minimum(enhanced[bright_mask] * 1.3, 255)
        
        # 4. 黒背景領域の抑制（下位ピクセルの明度を下げる）
        dark_mask = gray < np.percentile(gray, 15)
        enhanced[dark_mask] = enhanced[dark_mask] * 0.7
        
        # 5. 結果を組み合わせ
        combined = cv2.addWeighted(clahe_applied, 0.4, enhanced.astype(np.uint8), 0.6, 0)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(combined, cv2.COLOR_GRAY2BGR)
        return combined
    
    def _apply_color_inversion(self, image: np.ndarray) -> np.ndarray:
        """色反転（白文字→黒文字に変換）"""
        # 画像を反転
        inverted = 255 - image
        return inverted
    
    def _apply_precise_text_extraction(self, image: np.ndarray) -> np.ndarray:
        """精密境界検出によるテキスト抽出"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 1. ガウシアンブラーでノイズ除去
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # 2. アダプティブ二値化で精密なテキスト境界を検出
        adaptive = cv2.adaptiveThreshold(blurred, 255, 
                                       cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, 9, 4)
        
        # 3. モルフォロジー演算でテキスト構造を強化
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morphed = cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel)
        
        # 4. 小さなノイズを除去
        kernel_clean = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
        cleaned = cv2.morphologyEx(morphed, cv2.MORPH_OPEN, kernel_clean)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)
        return cleaned
    
    def _apply_histogram_equalization(self, image: np.ndarray) -> np.ndarray:
        """ヒストグラム平均化によるコントラスト改善"""
        if len(image.shape) == 3:
            # YUVカラースペースでY成分のみ平均化
            yuv = cv2.cvtColor(image, cv2.COLOR_BGR2YUV)
            yuv[:,:,0] = cv2.equalizeHist(yuv[:,:,0])
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)
        else:
            return cv2.equalizeHist(image)
    
    def _apply_multi_scale_gaussian(self, image: np.ndarray) -> np.ndarray:
        """複数スケールでのガウシアンフィルタ"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 複数のスケールでガウシアンフィルタを適用
        scales = [1, 3, 5]
        filtered_images = []
        
        for scale in scales:
            if scale == 1:
                filtered_images.append(gray)
            else:
                filtered = cv2.GaussianBlur(gray, (scale, scale), 0)
                filtered_images.append(filtered)
        
        # 重み付き平均で結合
        weights = [0.5, 0.3, 0.2]
        result = np.zeros_like(gray, dtype=np.float32)
        
        for img, weight in zip(filtered_images, weights):
            result += img.astype(np.float32) * weight
        
        result = np.clip(result, 0, 255).astype(np.uint8)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
        return result
    
    def _try_easyocr(self, image: np.ndarray, variant_name: str) -> Optional[Dict[str, Any]]:
        """EasyOCRでOCRを試行（タイムスタンプ特化）"""
        try:
            reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, self.debug)
            
            # タイムスタンプ文字のみを対象とした設定
            # EasyOCRはallowlistをサポートしていないが、結果をフィルタリング
            results = reader.readtext(image)
            
            if self.debug:
                print(f"  EasyOCR raw results for {variant_name}: {results}")
            
            if not results:
                return None
            
            # すべての結果を確認
            for bbox, text, confidence in results:
                if self.debug:
                    print(f"    Text: '{text}', Confidence: {confidence:.3f}")
                
                # タイムスタンプパターンマッチング
                for pattern in TIMESTAMP_PATTERNS:
                    if re.search(pattern, text):
                        if self.debug:
                            print(f"    Found timestamp match: '{text}' with pattern")
                        return {
                            'text': text,
                            'confidence': confidence,
                            'variant': variant_name,
                            'engine': 'EasyOCR'
                        }
            
            # パターンマッチしなかった場合でも、数字を含む最高信頼度の結果を返す
            numeric_results = [(bbox, text, confidence) for bbox, text, confidence in results 
                             if any(c.isdigit() for c in text)]
            
            if numeric_results:
                best_result = max(numeric_results, key=lambda x: x[2])
                bbox, text, confidence = best_result
                if self.debug:
                    print(f"    Using best numeric result: '{text}', Confidence: {confidence:.3f}")
                return {
                    'text': text,
                    'confidence': confidence,
                    'variant': variant_name,
                    'engine': 'EasyOCR'
                }
            
            return None
            
        except Exception as e:
            if self.debug:
                print(f"EasyOCR error on {variant_name}: {e}")
            return None
    
    def _try_tesseract(self, image: np.ndarray, variant_name: str) -> Optional[Dict[str, Any]]:
        """TesseractでOCRを試行（利用可能な場合）"""
        try:
            import pytesseract
            
            # Tesseractの設定（タイムスタンプ特化）
            # PSM 8: 単一単語として処理（タイムスタンプに最適）
            # 文字ホワイトリスト: タイムスタンプに必要な文字のみ許可
            config = '--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789/:.-@© '
            
            # OCR実行
            text = pytesseract.image_to_string(image, config=config).strip()
            
            if not text:
                return None
            
            # タイムスタンプパターンマッチング
            for pattern in TIMESTAMP_PATTERNS:
                if re.search(pattern, text):
                    # Tesseractの信頼度を取得（簡易版）
                    confidence = 0.7  # Tesseractの基本信頼度
                    return {
                        'text': text,
                        'confidence': confidence,
                        'variant': variant_name,
                        'engine': 'Tesseract'
                    }
            
            return None
            
        except ImportError:
            # Tesseractが利用できない場合は静かに失敗
            return None
        except Exception as e:
            # Tesseractエラーも静かに処理
            return None
    
    def _select_best_ocr_result(self, all_results: List[Tuple]) -> Optional[Dict[str, Any]]:
        """全OCR結果から最適なものを選択"""
        if not all_results:
            return None
        
        # 信頼度とエンジンの重み付けでスコア計算
        scored_results = []
        
        for engine, variant, result in all_results:
            score = result['confidence']
            
            # エンジンによる重み付け
            if engine == 'EasyOCR':
                score *= 1.0  # EasyOCRは基準
            elif engine == 'Tesseract':
                score *= 0.9  # Tesseractは少し低め
            
            # バリエーションによる重み付け
            if 'enlarged' in variant:
                score *= 1.1  # 拡大画像は重視
            if 'contrast' in variant:
                score *= 1.05  # コントラスト強化も重視
            if 'binary' in variant:
                score *= 1.02  # 二値化も軽く重視
            
            scored_results.append((score, result))
        
        # 最高スコアの結果を選択
        best_score, best_result = max(scored_results, key=lambda x: x[0])
        
        # 最低閾値チェック
        if best_score < 0.2:  # より柔軟な閾値
            return None
        
        return best_result
    
    def _save_debug_variants(self, processed_images: List[Tuple[str, np.ndarray]], input_path: str) -> None:
        """デバッグ用に前処理した画像バリエーションを保存"""
        try:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            
            for variant_name, image in processed_images:
                debug_filename = f"debug_{base_name}_{variant_name}.jpg"
                cv2.imwrite(debug_filename, image)
                
            if self.debug:
                print(f"Saved {len(processed_images)} debug variants for {base_name}")
                
        except Exception as e:
            if self.debug:
                print(f"Could not save debug variants: {e}")
    
    def test_ocr_performance(self, cropped_frame: np.ndarray, iterations: int = 5) -> Dict[str, float]:
        """OCR性能をテスト"""
        times = []
        
        for _ in range(iterations):
            start_time = time.time()
            self.extract_timestamp(cropped_frame, None)
            end_time = time.time()
            times.append(end_time - start_time)
        
        return {
            'average_time': sum(times) / len(times),
            'min_time': min(times),
            'max_time': max(times),
            'total_iterations': iterations
        }
    
    def parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """タイムスタンプ文字列をdatetimeオブジェクトに変換"""
        if not timestamp_str:
            return None
        
        # OCR誤認識文字の修正
        cleaned_timestamp = self._clean_ocr_errors(timestamp_str)
        
        if self.debug and cleaned_timestamp != timestamp_str:
            print(f"Cleaned timestamp: '{timestamp_str}' -> '{cleaned_timestamp}'")
        
        # 各パターンで解析を試行
        for i, pattern in enumerate(TIMESTAMP_PATTERNS):
            match = re.search(pattern, cleaned_timestamp)
            if match:
                try:
                    groups = match.groups()
                    
                    if len(groups) == 5:  # 分まで形式: 2024/12/28 15:30
                        year, month, day, hour, minute = groups
                        second = 0  # 秒は0とする
                    elif len(groups) == 6:  # 秒まで形式: 2024/12/28 15:30:45
                        year, month, day, hour, minute, second = groups
                    else:
                        continue  # 不正な形式はスキップ
                    
                    dt = datetime(
                        year=int(year),
                        month=int(month),
                        day=int(day),
                        hour=int(hour),
                        minute=int(minute),
                        second=int(second),
                        tzinfo=timezone(timedelta(hours=9))  # JST
                    )
                    
                    if self.debug:
                        print(f"Parsed timestamp: {dt} from '{cleaned_timestamp}' using pattern {i}")
                    
                    return dt
                    
                except (ValueError, TypeError) as e:
                    if self.debug:
                        print(f"Failed to parse with pattern {i}: {e}")
                    continue
        
        if self.debug:
            print(f"Could not parse timestamp: '{cleaned_timestamp}'")
        return None
    
    def _clean_ocr_errors(self, timestamp_str: str) -> str:
        """OCR誤認識文字を修正（慎重に適用）"""
        # 一般的な誤認識パターンを修正
        cleaned = timestamp_str
        
        # 末尾の=を秒に修正 (例: 19.41= -> 19.41.14)
        if cleaned.endswith('='):
            # 分まで形式の場合、推定秒数を追加
            cleaned = cleaned[:-1] + '.14'  # デフォルト秒数
        
        # 数字部分のみの誤認識パターンを修正（文字部分は除外）
        # タイムスタンプ内の数字位置でのみ置換を適用
        import re
        
        # タイムスタンプパターンに一致する部分を抽出
        timestamp_match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2})[:.=](\d{2})[:.=]?(\d{2})?', cleaned)
        
        if timestamp_match:
            # タイムスタンプ部分のみ修正
            timestamp_part = timestamp_match.group(0)
            
            # 慎重な置換（数字の文脈でのみ）
            replacements = {
                '=': '.',  # = -> .（タイムスタンプ区切り文字として）
            }
            
            for wrong, correct in replacements.items():
                timestamp_part = timestamp_part.replace(wrong, correct)
            
            # 元の文字列の該当部分を置換
            cleaned = cleaned.replace(timestamp_match.group(0), timestamp_part)
        
        return cleaned
    
    def add_exif_data(self, video_path: str, output_path: str, 
                     creation_time: Optional[datetime] = None) -> bool:
        """動画ファイルにEXIFデータを追加"""
        try:
            import ffmpeg
            import subprocess
            
            if self.debug:
                print(f"Attempting to add metadata to: {video_path} -> {output_path}")
            
            # メタデータの準備
            metadata_args = []
            
            if creation_time:
                # ISO 8601形式でタイムスタンプを設定
                iso_timestamp = creation_time.isoformat()
                metadata_args.extend(['-metadata', f'creation_time={iso_timestamp}'])
                
                if self.debug:
                    print(f"Setting creation time: {iso_timestamp}")
            
            # 直接subprocessでFFmpegを実行（ffmpeg-pythonのバグを回避）
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-c:v', 'copy',  # ビデオコーデックをコピー
                '-c:a', 'copy',  # オーディオコーデックをコピー
                '-map_metadata', '0',  # 元のメタデータを保持
            ] + metadata_args + [
                '-y',  # 上書きを許可
                output_path
            ]
            
            if self.debug:
                print(f"FFmpeg command: {' '.join(cmd)}")
            
            # FFmpegを実行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                if self.debug:
                    print(f"Successfully processed: {output_path}")
                return True
            else:
                if self.debug:
                    print(f"FFmpeg failed with return code: {result.returncode}")
                    print(f"FFmpeg stderr: {result.stderr}")
                
                # フォールバック: メタデータなしでコピー
                if self.debug:
                    print("Attempting simple copy without metadata...")
                
                import shutil
                shutil.copy2(video_path, output_path)
                
                if self.debug:
                    print(f"File copied without metadata: {output_path}")
                return True
            
            if self.debug:
                print(f"Successfully added EXIF data to: {output_path}")
                
                # 埋め込まれたメタデータを検証
                try:
                    result_probe = ffmpeg.probe(output_path)
                    result_metadata = result_probe.get('format', {}).get('tags', {})
                    
                    print(f"Embedded metadata verification:")
                    for key, value in metadata.items():
                        if key.lower() in [k.lower() for k in result_metadata.keys()]:
                            print(f"  ✓ {key}: {value}")
                        else:
                            print(f"  ⚠ {key}: {value} (not found in output)")
                            
                except Exception as verify_error:
                    print(f"Could not verify embedded metadata: {verify_error}")
            
            return True
            
        except ffmpeg.Error as e:
            error_msg = f"FFmpeg error during metadata embedding: {e}"
            print(error_msg)
            if self.debug:
                print("FFmpeg stderr:")
                if hasattr(e, 'stderr') and e.stderr:
                    stderr_output = e.stderr.decode('utf-8', errors='replace')
                    print(stderr_output)
                    
            return False
        except Exception as e:
            error_msg = f"Unexpected error during video processing: {e}"
            print(error_msg)
            if self.debug:
                import traceback
                traceback.print_exc()
            return False
    
    def process_batch(self, input_directory: str, output_directory: Optional[str] = None,
                     location: Optional[str] = None, skip_errors: bool = True, 
                     max_workers: Optional[int] = None, use_threading: bool = False,
                     batch_size: Optional[int] = None) -> Dict[str, Any]:
        """ディレクトリ内のすべてのMP4ファイルをバッチ処理（並列処理対応）
        
        Args:
            input_directory: 入力ディレクトリのパス
            output_directory: 出力ディレクトリのパス（Noneの場合は入力ディレクトリと同じ）
            location: 設定する場所情報
            skip_errors: エラーが発生したファイルをスキップするかどうか
            max_workers: 並列処理の最大ワーカー数（Noneの場合は自動設定）
            use_threading: スレッドプールを使用するか（Falseの場合はプロセスプール）
            batch_size: 一度に処理するファイル数の上限（Noneの場合は制限なし）
            
        Returns:
            処理結果の辞書（成功数、失敗数、処理されたファイル一覧など）
        """
        # 新しいBatchProcessorを使用
        batch_processor = BatchProcessor(self, debug=self.debug)
        return batch_processor.process_batch(
            input_directory, output_directory, location, skip_errors, 
            max_workers, use_threading, batch_size
        )
    
    def _process_single_file_thread_safe(self, input_path: str, output_path: str, 
                                        location: Optional[str]) -> bool:
        """スレッドセーフな単一ファイル処理（スレッドプール用）"""
        try:
            return self.process_video(input_path, output_path, location)
        except Exception as e:
            if self.debug:
                print(f"Thread-safe processing error for {os.path.basename(input_path)}: {e}")
            return False
    
    def _move_to_failed_folder(self, input_path: str, reason: str = "Unknown error", 
                              output_dir: Optional[str] = None) -> None:
        """失敗したファイルをfailedフォルダにコピー（元ファイルは保持、下位互換性のため）"""
        from file_manager import FileManager
        file_manager = FileManager(debug=self.debug)
        file_manager.move_to_failed_folder(input_path, reason, output_dir)
    
    def _save_crop_to_failed_folder(self, cropped_frame: np.ndarray, input_path: str, 
                                   output_dir: Optional[str] = None) -> None:
        """cropした画像をfailedフォルダに保存"""
        try:
            if output_dir is None:
                output_dir = os.path.dirname(input_path)
                
            failed_dir = os.path.join(output_dir, "failed")
            os.makedirs(failed_dir, exist_ok=True)
            
            # 元のファイル名をベースにクロップ画像のファイル名を生成
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            crop_filename = f"crop_{base_name}.jpg"
            crop_path = os.path.join(failed_dir, crop_filename)
            
            # 重複回避
            counter = 1
            while os.path.exists(crop_path):
                crop_filename = f"crop_{base_name}_{counter}.jpg"
                crop_path = os.path.join(failed_dir, crop_filename)
                counter += 1
            
            # クロップ画像を保存
            cv2.imwrite(crop_path, cropped_frame)
            
            if self.debug:
                print(f"Cropped image saved to failed folder: {crop_path}")
                
        except Exception as e:
            if self.debug:
                print(f"Could not save cropped image to failed folder: {e}")
    
    def process_video(self, input_path: str, output_path: str, 
                     location: Optional[str] = None) -> bool:
        """単一の動画ファイルを処理"""
        
        if self.debug:
            print(f"Processing video: {os.path.basename(input_path)}")
        
        # エラーハンドリング
        if self.error_handler:
            error_result = self.error_handler.handle_video_processing(
                input_path, output_path, location
            )
            if error_result.get('should_skip', False):
                if self.debug:
                    print(f"Skipping file due to error handler: {error_result.get('reason', 'Unknown')}")
                return False
        
        # 入力ファイルの検証
        if not validate_video_file(input_path):
            error_msg = f"Invalid input video file: {input_path}"
            print(error_msg)
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.INVALID_FILE, input_path, error_msg)
            return False
        
        # 出力パスの検証
        if not validate_output_path(output_path):
            error_msg = f"Invalid output path: {output_path}"
            print(error_msg)
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.INVALID_OUTPUT, input_path, error_msg)
            return False
        
        try:
            # フレーム抽出
            frame = self.extract_first_frame(input_path)
            
            if self.debug:
                self.save_debug_frame(frame, f"debug_{os.path.basename(input_path)}.jpg")
            
            # タイムスタンプ領域をクロップ
            cropped_frame = self.crop_timestamp_area(frame)
            
            # クロップした画像のファイル名を生成
            crop_filename = f"crop_{os.path.basename(input_path)}.jpg"
            
            if self.debug:
                self.save_cropped_area(cropped_frame, crop_filename)
            
            # タイムスタンプを抽出
            timestamp_str = self.extract_timestamp(cropped_frame, input_path)
            
            if not timestamp_str:
                error_msg = f"Could not extract timestamp from video: {input_path}"
                print(error_msg)
                if self.error_handler:
                    self.error_handler.log_error(VideoErrorType.OCR_FAILED, input_path, error_msg)
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, "OCR failed", os.path.dirname(output_path))
                    # cropした画像もfailedフォルダに保存
                    self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                return False
            
            # タイムスタンプを解析
            creation_time = self.parse_timestamp(timestamp_str)
            
            if not creation_time:
                error_msg = f"Could not parse timestamp '{timestamp_str}' from video: {input_path}"
                print(error_msg)
                if self.error_handler:
                    self.error_handler.log_error(VideoErrorType.TIMESTAMP_PARSE_FAILED, input_path, error_msg)
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, f"Timestamp parse failed: {timestamp_str}", os.path.dirname(output_path))
                    # cropした画像もfailedフォルダに保存
                    self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                return False
            
            if self.debug:
                print(f"Extracted timestamp: {timestamp_str}")
                print(f"Parsed creation time: {creation_time}")
            
            # EXIFデータを追加
            success = self.add_exif_data(input_path, output_path, creation_time)
            
            if not success:
                error_msg = f"Failed to add EXIF data to video: {input_path}"
                print(error_msg)
                if self.error_handler:
                    self.error_handler.log_error(VideoErrorType.FFMPEG_ERROR, input_path, error_msg)
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, "EXIF embedding failed", os.path.dirname(output_path))
                    # cropした画像もfailedフォルダに保存
                    self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                return False
            
            if self.debug:
                print(f"Successfully processed: {os.path.basename(input_path)} -> {os.path.basename(output_path)}")
            
            return True
            
        except Exception as e:
            error_msg = f"Unexpected error processing {input_path}: {e}"
            print(error_msg)
            if self.debug:
                import traceback
                traceback.print_exc()
            
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.UNEXPECTED_ERROR, input_path, error_msg)
                # 失敗したファイルを移動
                try:
                    self._move_to_failed_folder(input_path, f"Unexpected error: {str(e)}", os.path.dirname(output_path))
                    # cropした画像がある場合はfailedフォルダに保存を試行
                    try:
                        if 'cropped_frame' in locals():
                            self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                    except Exception as crop_error:
                        if self.debug:
                            print(f"Could not save cropped image to failed folder: {crop_error}")
                except Exception as move_error:
                    if self.debug:
                        print(f"Could not move failed file: {move_error}")
            
            return False


def process_single_video_worker(input_path: str, output_path: str, location: Optional[str],
                               languages: List[str], use_gpu: bool, debug: bool) -> bool:
    """並列処理用のワーカー関数（プロセスプール用）"""
    try:
        # 各プロセスで独立したEnhancerインスタンスを作成
        enhancer = XiaomiVideoExifEnchanter(debug=debug, languages=languages, use_gpu=use_gpu)
        
        # 動画を処理
        success = enhancer.process_video(input_path, output_path, location)
        
        return success
        
    except Exception as e:
        if debug:
            print(f"Worker process error for {os.path.basename(input_path)}: {e}")
        return False


def main() -> None:
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Xiaomi Video EXIF Enhancer')
    parser.add_argument('input', help='Input video file or directory')
    parser.add_argument('-o', '--output', help='Output video file or directory')
    parser.add_argument('-l', '--location', help='Location information to add')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--batch', action='store_true', help='Process directory in batch mode')
    parser.add_argument('--languages', nargs='+', default=['en'], help='OCR languages')
    parser.add_argument('--gpu', action='store_true', help='Use GPU for OCR')
    parser.add_argument('--confidence', type=float, default=0.5, help='OCR confidence threshold')
    parser.add_argument('--max-workers', type=int, help='Maximum number of parallel workers')
    parser.add_argument('--use-threading', action='store_true', help='Use threading instead of multiprocessing')
    parser.add_argument('--batch-size', type=int, help='Batch size for processing')
    parser.add_argument('--skip-errors', action='store_true', default=True, help='Skip files with errors')
    parser.add_argument('--disable-enhanced-ocr', action='store_true', help='Disable enhanced OCR (use basic OCR only)')
    
    args = parser.parse_args()
    
    # Enhancerインスタンスを作成
    enhancer = XiaomiVideoExifEnchanter(
        debug=args.debug,
        languages=args.languages,
        use_gpu=args.gpu,
        enhanced_ocr=not args.disable_enhanced_ocr
    )
    
    # 信頼度閾値を設定
    enhancer.set_confidence_threshold(args.confidence)
    
    try:
        if args.batch or os.path.isdir(args.input):
            # バッチ処理モード
            results = enhancer.process_batch(
                input_directory=args.input,
                output_directory=args.output,
                location=args.location,
                skip_errors=args.skip_errors,
                max_workers=args.max_workers,
                use_threading=args.use_threading,
                batch_size=args.batch_size
            )
            
            # 結果を表示
            print(f"\nBatch processing completed:")
            print(f"Total files: {results['total_files']}")
            print(f"Successful: {results['successful']}")
            print(f"Failed: {results['failed']}")
            print(f"Skipped: {results['skipped']}")
            
        else:
            # 単一ファイル処理モード
            if not args.output:
                # 出力ファイル名を自動生成
                input_path = Path(args.input)
                args.output = str(input_path.with_stem(f"{input_path.stem}_enhanced"))
            
            success = enhancer.process_video(args.input, args.output, args.location)
            
            if success:
                print(f"Successfully processed: {args.input} -> {args.output}")
                sys.exit(0)
            else:
                print(f"Failed to process: {args.input}")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
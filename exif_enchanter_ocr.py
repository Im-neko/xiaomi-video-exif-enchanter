#!/usr/bin/env python3
"""
Xiaomi Video EXIF Enhancer - OCR Only Version
Xiaomiホームカメラ(C301)で録画された映像のEXIF情報を拡張するツール（OCR専用版）
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
import threading
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
    """EasyOCRインスタンスのシングルトン管理クラス（プロセス安全版）"""
    _instance = None
    _reader = None
    _process_id = None
    _lock = threading.Lock()
    
    @classmethod
    def get_reader(cls, languages: List[str] = None, gpu: bool = None, debug: bool = False) -> easyocr.Reader:
        """EasyOCRリーダーのシングルトンインスタンスを取得（プロセス安全）"""
        import os
        current_process_id = os.getpid()
        
        if languages is None:
            languages = ['en', 'ja']
        
        if gpu is None:
            gpu = False
        
        # 設定が変更された場合、または異なるプロセスの場合は新しいインスタンスを作成
        config_key = (tuple(languages), gpu)
        
        with cls._lock:
            if (cls._reader is None or 
                getattr(cls, '_config', None) != config_key or 
                cls._process_id != current_process_id):
                
                if debug:
                    print(f"Creating new EasyOCR reader with languages: {languages}, GPU: {gpu}, PID: {current_process_id}")
                
                try:
                    cls._reader = easyocr.Reader(languages, gpu=gpu)
                    cls._config = config_key
                    cls._process_id = current_process_id
                    
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
        cls._process_id = None


class XiaomiVideoExifEnchanterOCR:
    """Xiaomi動画のEXIF情報を拡張するメインクラス（OCR専用版）"""
    
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
        self.early_exit_threshold = 0.9  # 早期終了の信頼度閾値
        
        # エラーハンドラーの初期化
        try:
            self.error_handler = VideoErrorHandler()
        except Exception as e:
            if self.debug:
                print(f"Warning: Could not initialize VideoErrorHandler: {e}")
            self.error_handler = None
        
        if self.debug:
            print(f"XiaomiVideoExifEnchanter (OCR) initialized with languages: {self.languages}, GPU: {self.use_gpu}")
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """OCR信頼度の閾値を設定"""
        self.confidence_threshold = max(0.0, min(1.0, threshold))
        if self.debug:
            print(f"OCR confidence threshold set to: {self.confidence_threshold}")
    
    def set_early_exit_threshold(self, threshold: float) -> None:
        """早期終了の信頼度閾値を設定"""
        self.early_exit_threshold = max(0.0, min(1.0, threshold))
        if self.debug:
            print(f"OCR early exit threshold set to: {self.early_exit_threshold}")
    
    def extract_first_frame(self, video_path: str) -> Optional[np.ndarray]:
        """動画の最初のフレームを抽出"""
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            if self.debug:
                print(f"Error: Could not open video file: {video_path}")
            return None
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            if self.debug:
                print(f"Error: Could not read frame from video: {video_path}")
            return None
        
        return frame
    
    def save_debug_frame(self, frame: np.ndarray, filename: str) -> None:
        """デバッグ用にフレームを保存"""
        if self.debug:
            # debugフォルダを作成
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            
            # debug/以下にファイルを保存
            debug_path = debug_dir / filename
            cv2.imwrite(str(debug_path), frame)
            print(f"Debug frame saved: {debug_path}")
    
    def crop_timestamp_area(self, frame: np.ndarray) -> np.ndarray:
        """フレームからタイムスタンプ領域をクロップ（Xiaomi C301専用）"""
        height, width = frame.shape[:2]
        
        # Xiaomi C301カメラの典型的なタイムスタンプ位置を複数試行
        crop_configs = [
            # 左上角の標準的な位置
            {
                'x_start_ratio': 0.03,
                'y_start_ratio': 0.0,
                'x_end_ratio': 0.25,
                'y_end_ratio': 0.05
            },
            # より広めの範囲
            {
                'x_start_ratio': 0.02,
                'y_start_ratio': 0.0,
                'x_end_ratio': 0.3,
                'y_end_ratio': 0.08
            }
        ]
        
        # 最初の設定を使用
        config = crop_configs[0]
        
        x_start = int(width * config['x_start_ratio'])
        y_start = int(height * config['y_start_ratio'])
        x_end = int(width * config['x_end_ratio'])
        y_end = int(height * config['y_end_ratio'])
        
        # 境界チェック
        x_start = max(0, x_start)
        y_start = max(0, y_start)
        x_end = min(width, x_end)
        y_end = min(height, y_end)
        
        cropped = frame[y_start:y_end, x_start:x_end]
        
        if self.debug:
            print(f"Xiaomi timestamp crop coordinates: ({x_start}, {y_start}) to ({x_end}, {y_end})")
            print(f"Frame size: {width}x{height}, Crop size: {x_end-x_start}x{y_end-y_start}")
        
        return cropped
    
    def save_cropped_area(self, cropped_frame: np.ndarray, filename: str) -> None:
        """クロップした領域を保存"""
        if self.debug:
            # debugフォルダを作成
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            
            # debug/以下にファイルを保存
            debug_path = debug_dir / filename
            cv2.imwrite(str(debug_path), cropped_frame)
            print(f"Cropped area saved: {debug_path}")
    
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
        """クロップされたフレームからタイムスタンプを抽出（OCR専用版）"""
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
        best_confidence = 0.0
        
        for bbox, text, confidence in ocr_results:
            if confidence < self.confidence_threshold:
                continue
            
            # タイムスタンプパターンマッチング
            for pattern in TIMESTAMP_PATTERNS:
                if re.search(pattern, text):
                    if confidence > best_confidence:
                        best_match = text
                        best_confidence = confidence
                    break
        
        return best_match
    
    def _enhanced_extract_timestamp(self, cropped_frame: np.ndarray, input_path: str = None) -> Optional[str]:
        """改良版タイムスタンプ抽出（複数前処理・複数エンジン）"""
        if self.debug:
            print("Starting enhanced OCR extraction...")
        
        all_results = []
        
        # 複数の画像バリエーションを生成
        variants = self._generate_image_variants(cropped_frame)
        
        # デバッグ用: バリエーション画像を保存
        if self.debug and input_path:
            # debugフォルダを作成
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            for i, (variant_name, variant_image) in enumerate(variants):
                debug_filename = f"debug_variant_{base_name}_{i}_{variant_name}.jpg"
                debug_path = debug_dir / debug_filename
                cv2.imwrite(str(debug_path), variant_image)
            print(f"Saved {len(variants)} debug variants for {base_name} in debug/")
        
        # 各バリエーションでOCRを実行（2024年最適化版）
        for i, (variant_name, variant_image) in enumerate(variants):
            if self.debug:
                print(f"  Trying variant {i+1}/{len(variants)}: {variant_name}")
            
            # EasyOCRで試行（優先）- 複数結果を収集
            easyocr_results = self._try_easyocr_multiple(variant_image, variant_name)
            for result in easyocr_results:
                all_results.append(('EasyOCR', variant_name, result))
                
                # 早期終了チェック: 高信頼度の完全タイムスタンプが見つかった場合
                if (result.get('confidence', 0) >= self.early_exit_threshold and 
                    self._is_complete_timestamp(result.get('text', ''))):
                    if self.debug:
                        print(f"  Early exit: High confidence complete timestamp found (confidence: {result['confidence']:.3f})")
                    # 現在の結果で最適解を選択して返す
                    best_result = self._select_best_ocr_result(all_results)
                    if best_result and self.debug:
                        print(f"Enhanced OCR selected (early exit): '{best_result['text']}' from {best_result['engine']} ({best_result['variant']}) with confidence {best_result['confidence']:.3f}")
                    return best_result['text'] if best_result else None
            
            # 組み合わせ早期終了チェック: 高信頼度の日付+時刻が組み合わさった場合
            if self._can_combine_early_exit(all_results):
                if self.debug:
                    print(f"  Early exit: High confidence date+time combination found")
                best_result = self._select_best_ocr_result(all_results)
                if best_result and self.debug:
                    print(f"Enhanced OCR selected (early exit combination): '{best_result['text']}' from {best_result['engine']} ({best_result['variant']}) with confidence {best_result['confidence']:.3f}")
                return best_result['text'] if best_result else None
            
            # Tesseractで試行（フォールバック）
            tesseract_result = self._try_tesseract(variant_image, variant_name)
            if tesseract_result:
                all_results.append(('Tesseract', variant_name, tesseract_result))
                
                # 早期終了チェック（Tesseract結果でも）
                if (tesseract_result.get('confidence', 0) >= self.early_exit_threshold and 
                    self._is_complete_timestamp(tesseract_result.get('text', ''))):
                    if self.debug:
                        print(f"  Early exit: High confidence Tesseract result found (confidence: {tesseract_result['confidence']:.3f})")
                    best_result = self._select_best_ocr_result(all_results)
                    if best_result and self.debug:
                        print(f"Enhanced OCR selected (early exit): '{best_result['text']}' from {best_result['engine']} ({best_result['variant']}) with confidence {best_result['confidence']:.3f}")
                    return best_result['text'] if best_result else None
        
        # 最適な結果を選択
        best_result = self._select_best_ocr_result(all_results)
        
        if self.debug and best_result:
            print(f"Enhanced OCR selected: '{best_result['text']}' from {best_result['engine']} ({best_result['variant']}) with confidence {best_result['confidence']:.3f}")
        
        return best_result['text'] if best_result else None
    
    def _process_single_file_thread_safe(self, input_path: str, output_path: str, 
                                        location: Optional[str]) -> bool:
        """スレッドセーフな単一ファイル処理（スレッドプール用）"""
        try:
            return self.process_video(input_path, output_path, location)
        except Exception as e:
            if self.debug:
                print(f"Thread-safe processing error for {os.path.basename(input_path)}: {e}")
            return False
    
    def _generate_image_variants(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        """画像の複数のバリエーションを生成（研究ベース最適化版）"""
        variants = []
        height, width = image.shape[:2]
        
        # オリジナル
        variants.append(("original", image.copy()))
        
        # 2024年研究で最も効果的な前処理技術
        
        # 1. 超解像拡大（最も効果的 - 2-4倍が最適）
        enlarged_2x = cv2.resize(image, (width * 2, height * 2), interpolation=cv2.INTER_LANCZOS4)
        variants.append(("enlarged_2x_lanczos", enlarged_2x))
        
        enlarged_3x = cv2.resize(image, (width * 3, height * 3), interpolation=cv2.INTER_LANCZOS4)
        variants.append(("enlarged_3x_lanczos", enlarged_3x))
        
        # 2. CLAHE（コントラスト制限適応ヒストグラム平均化）
        contrast_enhanced = self._enhance_contrast_clahe(image)
        variants.append(("clahe_enhanced", contrast_enhanced))
        
        # 3. 拡大 + CLAHE（効果的な組み合わせ）
        enlarged_clahe = self._enhance_contrast_clahe(enlarged_2x)
        variants.append(("enlarged_2x_clahe", enlarged_clahe))
        
        # 4. アダプティブ二値化（2024年研究で効果実証）
        adaptive_binary = self._apply_adaptive_threshold_advanced(image)
        variants.append(("adaptive_binary_advanced", adaptive_binary))
        
        # 5. 拡大 + アダプティブ二値化
        enlarged_adaptive = self._apply_adaptive_threshold_advanced(enlarged_2x)
        variants.append(("enlarged_2x_adaptive", enlarged_adaptive))
        
        # 6. Otsu二値化（グローバル閾値）
        otsu_binary = self._apply_otsu_threshold(image)
        variants.append(("otsu_binary", otsu_binary))
        
        # 7. ガンマ補正（低コントラスト画像に効果的）
        gamma_corrected = self._apply_gamma_correction_optimized(image, 1.5)
        variants.append(("gamma_1_5", gamma_corrected))
        
        # 8. ノイズ除去 + 拡大
        denoised = self._apply_denoising_nlmeans(image)
        denoised_enlarged = cv2.resize(denoised, (width * 2, height * 2), interpolation=cv2.INTER_LANCZOS4)
        variants.append(("denoised_enlarged", denoised_enlarged))
        
        # 9. 余白付き（OCR精度向上 - 研究で効果実証）
        padded_20 = self._apply_uniform_padding(image, 20)
        variants.append(("padded_20", padded_20))
        
        # 10. モルフォロジー演算（文字構造強化）
        morphed = self._apply_morphological_enhancement(image)
        variants.append(("morphological", morphed))
        
        # 11. 最適組み合わせ（研究で最高性能）
        optimal = self._apply_optimal_combination(image)
        variants.append(("optimal_combination", optimal))
        
        # 12. 超高解像度（4x INTER_CUBIC）- 2024年最新研究
        enlarged_4x = cv2.resize(image, (width * 4, height * 4), interpolation=cv2.INTER_CUBIC)
        variants.append(("enlarged_4x_cubic", enlarged_4x))
        
        # 13. シャープニングフィルタ
        sharpened = self._apply_sharpening_filter(image)
        variants.append(("sharpened", sharpened))
        
        # 14. エッジ強調 + 拡大
        edge_enhanced = self._apply_edge_enhancement(image)
        edge_enlarged = cv2.resize(edge_enhanced, (width * 2, height * 2), interpolation=cv2.INTER_LANCZOS4)
        variants.append(("edge_enhanced_2x", edge_enlarged))
        
        # 15. 文字特化二値化（研究ベース最適化）
        text_optimized = self._apply_text_optimized_binarization(image)
        variants.append(("text_optimized", text_optimized))
        
        # 16. 拡大 + 文字特化二値化（最高精度組み合わせ）
        enlarged_text_opt = self._apply_text_optimized_binarization(enlarged_2x)
        variants.append(("enlarged_2x_text_opt", enlarged_text_opt))
        
        # 2024年ベストプラクティス追加技術
        
        # 17. 超解像処理（段階的拡大）
        super_res_4x = self._apply_super_resolution(image, 4)
        variants.append(("super_resolution_4x", super_res_4x))
        
        # 18. コントラスト拡張（動的レンジ最適化）
        contrast_stretched = self._apply_contrast_stretching(image)
        variants.append(("contrast_stretch", contrast_stretched))
        
        # 19. バイラテラルフィルタ（エッジ保持ノイズ除去）
        bilateral_filtered = self._apply_bilateral_filtering(image)
        variants.append(("bilateral_denoise", bilateral_filtered))
        
        # 20. 強化2値化（複数手法組み合わせ）
        enhanced_binary = self._apply_enhanced_binarization(image)
        variants.append(("enhanced_binary", enhanced_binary))
        
        # 21. 回転補正（skew correction）
        rotation_corrected = self._apply_rotation_correction(image)
        variants.append(("rotation_corrected", rotation_corrected))
        
        # 22. 最適組み合わせ（3x拡大 + CLAHE + 余白）
        clahe_3x_padded = self._apply_uniform_padding(self._enhance_contrast_clahe(enlarged_3x), 25)
        variants.append(("clahe_3x_padded", clahe_3x_padded))
        
        return variants
    
    def _enhance_contrast_clahe(self, image: np.ndarray) -> np.ndarray:
        """CLAHE（コントラスト制限適応ヒストグラム平均化）による最適化"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 2024年研究に基づく最適パラメータ
        # clipLimit=4.0, tileGridSize=(8,8)が最も効果的
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        return enhanced
    
    def _apply_adaptive_threshold_advanced(self, image: np.ndarray) -> np.ndarray:
        """高度なアダプティブ二値化（2024年研究ベース）"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # ガウシアンブラーで前処理
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # アダプティブ二値化（最適パラメータ）
        adaptive = cv2.adaptiveThreshold(
            blurred, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 
            blockSize=15,  # 研究で最適とされる値
            C=4  # 調整パラメータ
        )
        
        if len(image.shape) == 3:
            return cv2.cvtColor(adaptive, cv2.COLOR_GRAY2BGR)
        return adaptive
    
    def _apply_otsu_threshold(self, image: np.ndarray) -> np.ndarray:
        """Otsu法による自動二値化"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # ガウシアンブラーで前処理
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Otsu二値化
        _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR)
        return otsu
    
    def _apply_gamma_correction_optimized(self, image: np.ndarray, gamma: float) -> np.ndarray:
        """最適化されたガンマ補正"""
        # より高速なルックアップテーブルベースの実装
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        
        return cv2.LUT(image, table)
    
    def _apply_denoising_nlmeans(self, image: np.ndarray) -> np.ndarray:
        """Non-local Meansノイズ除去（最適化版）"""
        if len(image.shape) == 3:
            # カラー画像用の最適パラメータ
            return cv2.fastNlMeansDenoisingColored(image, None, h=8, hColor=8, templateWindowSize=7, searchWindowSize=21)
        else:
            # グレースケール画像用の最適パラメータ
            return cv2.fastNlMeansDenoising(image, None, h=8, templateWindowSize=7, searchWindowSize=21)
    
    def _apply_morphological_enhancement(self, image: np.ndarray) -> np.ndarray:
        """モルフォロジー演算による文字構造強化"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 最適なカーネルサイズ（画像サイズに基づく）
        kernel_size = max(1, min(gray.shape) // 50)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        
        # クロージング（文字の穴を埋める）
        closing = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        
        # オープニング（ノイズ除去）
        opening = cv2.morphologyEx(closing, cv2.MORPH_OPEN, kernel)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(opening, cv2.COLOR_GRAY2BGR)
        return opening
    
    def _apply_optimal_combination(self, image: np.ndarray) -> np.ndarray:
        """研究で最も効果的だった前処理の組み合わせ"""
        height, width = image.shape[:2]
        
        # ステップ1: 2倍拡大（LANCZOS4）
        enlarged = cv2.resize(image, (width * 2, height * 2), interpolation=cv2.INTER_LANCZOS4)
        
        # ステップ2: ノイズ除去
        denoised = self._apply_denoising_nlmeans(enlarged)
        
        # ステップ3: CLAHE適用
        clahe_applied = self._enhance_contrast_clahe(denoised)
        
        # ステップ4: 余白追加
        padded = self._apply_uniform_padding(clahe_applied, 15)
        
        return padded
    
    def _apply_uniform_padding(self, image: np.ndarray, padding: int) -> np.ndarray:
        """画像に均一な余白を追加"""
        if len(image.shape) == 3:
            color = [255, 255, 255]  # 白い余白
        else:
            color = 255
        
        padded = cv2.copyMakeBorder(image, padding, padding, padding, padding, 
                                  cv2.BORDER_CONSTANT, value=color)
        return padded
    
    def _apply_sharpening_filter(self, image: np.ndarray) -> np.ndarray:
        """シャープニングフィルタで文字エッジを強調（2024年研究ベース）"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # ガウシアンブラーでベース画像作成
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # アンシャープマスキング
        sharpened = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)
        
        # さらに高周波成分を強調
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]], dtype=np.float32)
        sharpened = cv2.filter2D(sharpened, -1, kernel)
        
        # 値の範囲を[0,255]に制限
        sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)
        return sharpened
    
    def _apply_edge_enhancement(self, image: np.ndarray) -> np.ndarray:
        """エッジ強調による文字境界明確化"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # Sobelフィルタでエッジ検出
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        # 正規化
        gradient_magnitude = np.uint8(255 * gradient_magnitude / np.max(gradient_magnitude))
        
        # 元画像とエッジを合成
        enhanced = cv2.addWeighted(gray, 0.7, gradient_magnitude, 0.3, 0)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        return enhanced
    
    def _apply_text_optimized_binarization(self, image: np.ndarray) -> np.ndarray:
        """文字認識特化の最適化二値化（2024年最新研究）"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # ステップ1: ガウシアンブラーでノイズ除去
        denoised = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # ステップ2: トップハット変換（白文字強調）
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1))
        tophat = cv2.morphologyEx(denoised, cv2.MORPH_TOPHAT, kernel)
        
        # ステップ3: ブラックハット変換（黒文字強調）
        blackhat = cv2.morphologyEx(denoised, cv2.MORPH_BLACKHAT, kernel)
        
        # ステップ4: 合成
        enhanced = cv2.add(denoised, tophat)
        enhanced = cv2.subtract(enhanced, blackhat)
        
        # ステップ5: アダプティブ二値化（最適パラメータ）
        binary = cv2.adaptiveThreshold(
            enhanced, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,  # 文字サイズに最適化
            C=2            # 閾値調整
        )
        
        # ステップ6: クロージング演算で文字を完全化
        closing_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, closing_kernel)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return binary
    
    def _try_easyocr_multiple(self, image: np.ndarray, variant_name: str) -> List[Dict[str, Any]]:
        """EasyOCRで複数のOCR結果を取得（統合型）"""
        results = []
        
        try:
            reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, self.debug)
            
            # バリエーション別最適パラメータ選択（2024年研究ベース）
            if "enlarged" in variant_name or "4x" in variant_name or "super_resolution" in variant_name:
                # 高解像度画像用パラメータ
                width_ths = 0.2
                height_ths = 0.2
                beam_width = 15
                text_threshold = 0.5
                low_text = 0.2
                link_threshold = 0.2
                canvas_size = 4096
                mag_ratio = 2.0
            elif "binary" in variant_name or "text_opt" in variant_name or "enhanced_binary" in variant_name:
                # 2値化画像用パラメータ
                width_ths = 0.6
                height_ths = 0.6
                beam_width = 12
                text_threshold = 0.6
                low_text = 0.3
                link_threshold = 0.3
                canvas_size = 2560
                mag_ratio = 1.5
            elif "contrast" in variant_name or "clahe" in variant_name:
                # コントラスト強化画像用パラメータ
                width_ths = 0.3
                height_ths = 0.3
                beam_width = 10
                text_threshold = 0.6
                low_text = 0.25
                link_threshold = 0.25
                canvas_size = 3072
                mag_ratio = 1.8
            else:
                # 標準パラメータ
                width_ths = 0.4
                height_ths = 0.4
                beam_width = 8
                text_threshold = 0.7
                low_text = 0.4
                link_threshold = 0.4
                canvas_size = 2560
                mag_ratio = 1.5
            
            ocr_results = reader.readtext(
                image,
                width_ths=width_ths,
                height_ths=height_ths,
                decoder='beamsearch',
                beamWidth=beam_width,
                batch_size=1,
                workers=0,
                allowlist='0123456789/:. @',
                blocklist=None,
                detail=1,
                paragraph=False,
                text_threshold=text_threshold,
                low_text=low_text,
                link_threshold=link_threshold,
                canvas_size=canvas_size,
                mag_ratio=mag_ratio,
                contrast_ths=0.1,
                adjust_contrast=0.5,
                rotation_info=[0]  # 2024年推奨: 回転を最小限に
            )
            
            if self.debug:
                print(f"  EasyOCR raw results for {variant_name}: {ocr_results}")
            
            if not ocr_results:
                return results
            
            # すべての結果を処理
            for bbox, text, confidence in ocr_results:
                if text and len(text.strip()) > 3:  # 最小文字数チェック
                    results.append({
                        'text': text,
                        'confidence': confidence,
                        'bbox': bbox,
                        'variant': variant_name,
                        'engine': 'EasyOCR'
                    })
                    
                    if self.debug:
                        print(f"    Text: '{text}', Confidence: {confidence:.3f}")
            
            return results
            
        except Exception as e:
            if self.debug:
                print(f"  EasyOCR error for {variant_name}: {e}")
            return results
    
    def _try_easyocr(self, image: np.ndarray, variant_name: str) -> Optional[Dict[str, Any]]:
        """EasyOCRでOCRを試行（タイムスタンプ特化・2024年最適化版）"""
        try:
            reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, self.debug)
            
            # 2024年最新研究に基づく超高精度OCRパラメータ
            # タイムスタンプ認識特化の最適化設定
            
            # バリエーション別最適パラメータ選択
            if "enlarged" in variant_name or "4x" in variant_name:
                # 高解像度画像用：より厳密な検出
                width_ths = 0.3
                height_ths = 0.3
                beam_width = 10
            elif "binary" in variant_name or "text_opt" in variant_name:
                # 二値化画像用：より寛容な検出
                width_ths = 0.5
                height_ths = 0.5
                beam_width = 8
            else:
                # 標準設定
                width_ths = 0.4
                height_ths = 0.4
                beam_width = 5
            
            results = reader.readtext(
                image,
                width_ths=width_ths,     # バリエーション別最適化
                height_ths=height_ths,   # バリエーション別最適化
                decoder='beamsearch',    # 最高精度モード
                beamWidth=beam_width,    # 動的ビーム幅
                batch_size=1,            # 安定性重視
                workers=0,               # 並列処理無効
                allowlist='0123456789/:. ',  # タイムスタンプ文字のみ許可
                blocklist=None,          # ブロックリストなし
                detail=1,                # 詳細情報必須
                paragraph=False,         # 段落検出オフ
                text_threshold=0.6,      # 文字検出閾値（厳密）
                low_text=0.3,           # 低信頼度文字の閾値
                link_threshold=0.3,      # 文字結合閾値
                canvas_size=2560,        # キャンバスサイズ拡大
                mag_ratio=1.5           # 拡大比率
            )
            
            if self.debug:
                print(f"  EasyOCR raw results for {variant_name}: {results}")
            
            if not results:
                return None
            
            # 結果を信頼度順にソート
            results = sorted(results, key=lambda x: x[2], reverse=True)
            
            # すべての結果を確認（信頼度順）
            best_timestamp_match = None
            best_numeric_match = None
            
            for bbox, text, confidence in results:
                if self.debug:
                    print(f"    Text: '{text}', Confidence: {confidence:.3f}")
                
                # タイムスタンプパターンマッチング（最優先）
                for pattern in TIMESTAMP_PATTERNS:
                    if re.search(pattern, text):
                        if self.debug:
                            print(f"    Found timestamp match: '{text}' with pattern")
                        return {
                            'text': text,
                            'confidence': confidence,
                            'bbox': bbox,
                            'variant': variant_name,
                            'engine': 'EasyOCR'
                        }
                
                # 数値を多く含む文字列の評価（フォールバック用）
                digit_count = sum(c.isdigit() for c in text)
                slash_count = text.count('/')
                colon_count = text.count(':')
                dot_count = text.count('.')
                space_count = text.count(' ')
                total_chars = len(text.replace(' ', ''))
                digit_ratio = digit_count / total_chars if total_chars > 0 else 0
                
                # タイムスタンプらしい特徴をスコア化
                timestamp_score = 0
                if digit_ratio >= 0.6:  # 数字比率60%以上
                    timestamp_score += 0.3
                if slash_count >= 2:  # スラッシュ2個以上（日付区切り）
                    timestamp_score += 0.2
                if colon_count >= 1 or dot_count >= 2:  # 時刻区切り
                    timestamp_score += 0.2
                if space_count == 1:  # 日付と時刻の間のスペース
                    timestamp_score += 0.1
                if len(text) >= 8:  # 最小タイムスタンプ長
                    timestamp_score += 0.1
                
                # 総合スコアによる評価
                total_score = confidence * timestamp_score
                
                if (timestamp_score >= 0.5 and confidence >= self.confidence_threshold and 
                    (best_numeric_match is None or total_score > best_numeric_match[3])):
                    best_numeric_match = (text, confidence, bbox, total_score)
            
            # 数値マッチがある場合はそれを返す
            if best_numeric_match:
                text, confidence, bbox, score = best_numeric_match
                if self.debug:
                    print(f"    Using best numeric result: '{text}', Confidence: {confidence:.3f}, Score: {score:.3f}")
                return {
                    'text': text,
                    'confidence': confidence,
                    'bbox': bbox,
                    'variant': variant_name,
                    'engine': 'EasyOCR'
                }
            
            return None
            
        except Exception as e:
            if self.debug:
                print(f"  EasyOCR error for {variant_name}: {e}")
            return None
    
    def _try_tesseract(self, image: np.ndarray, variant_name: str) -> Optional[Dict[str, Any]]:
        """TesseractでOCRを試行（2024年最適化版）"""
        try:
            import pytesseract
            
            # 2024年研究に基づく複数のTesseract設定を試行
            configs = [
                # 設定1: タイムスタンプ特化（最も厳格）
                '--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789/:.-@ ',
                # 設定2: 単語レベル検出
                '--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789/:.-@ ',
                # 設定3: より寛容な設定
                '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789/:.-@© ',
                # 設定4: 最も寛容（デフォルト文字セット）
                '--oem 3 --psm 8'
            ]
            
            best_result = None
            best_score = 0
            
            for i, config in enumerate(configs):
                try:
                    # OCR実行
                    result = pytesseract.image_to_string(image, config=config).strip()
                    
                    if self.debug:
                        print(f"  Tesseract config {i+1} result for {variant_name}: '{result}'")
                    
                    if not result:
                        continue
                    
                    # タイムスタンプ評価スコア計算
                    score = self._calculate_timestamp_score(result)
                    
                    # 信頼度計算（Tesseract固有）
                    confidence = 0.7  # ベース信頼度
                    
                    # より厳格な設定ほど信頼度を上げる
                    if i == 0:  # 最も厳格
                        confidence = 0.85
                    elif i == 1:
                        confidence = 0.80
                    elif i == 2:
                        confidence = 0.75
                    
                    total_score = score * confidence
                    
                    if total_score > best_score:
                        best_score = total_score
                        best_result = {
                            'text': result,
                            'confidence': confidence,
                            'bbox': None,
                            'score': score
                        }
                    
                    # タイムスタンプパターンに完全マッチした場合は即座に返す
                    for pattern in TIMESTAMP_PATTERNS:
                        if re.search(pattern, result):
                            if self.debug:
                                print(f"    Found perfect timestamp match: '{result}' with config {i+1}")
                            return {
                                'text': result,
                                'confidence': confidence,
                                'bbox': None,
                                'variant': variant_name,
                                'engine': 'Tesseract'
                            }
                            
                except Exception as config_error:
                    if self.debug:
                        print(f"  Tesseract config {i+1} failed: {config_error}")
                    continue
            
            # 最良の結果があり、最小スコアを満たす場合は返す
            if best_result and best_score >= 0.3:
                if self.debug:
                    print(f"    Using best Tesseract result: '{best_result['text']}', Score: {best_score:.3f}")
                return best_result
            
            return None
            
        except ImportError:
            # Tesseractが利用できない場合は静かに失敗
            return None
        except Exception as e:
            if self.debug:
                print(f"  Tesseract error for {variant_name}: {e}")
            return None
    
    def _calculate_timestamp_score(self, text: str) -> float:
        """テキストがタイムスタンプである可能性をスコア化"""
        if not text:
            return 0.0
        
        score = 0.0
        
        # 数字の比率
        digit_count = sum(c.isdigit() for c in text)
        total_chars = len(text.replace(' ', ''))
        if total_chars > 0:
            digit_ratio = digit_count / total_chars
            score += min(digit_ratio * 0.4, 0.4)  # 最大0.4ポイント
        
        # 特定文字の存在
        if '/' in text:
            score += 0.15 * min(text.count('/'), 2)  # スラッシュ最大2個で0.3ポイント
        if ':' in text:
            score += 0.1 * min(text.count(':'), 2)   # コロン最大2個で0.2ポイント
        if '.' in text:
            score += 0.05 * min(text.count('.'), 2)  # ドット最大2個で0.1ポイント
        
        # 長さ評価
        if 8 <= len(text) <= 25:  # 適切なタイムスタンプ長
            score += 0.1
        
        # パターンマッチング
        for pattern in TIMESTAMP_PATTERNS:
            if re.search(pattern, text):
                score += 0.5  # 完全パターンマッチで大幅加点
                break
        
        return min(score, 1.0)  # 最大1.0
    
    def _calculate_variant_weight(self, variant: str) -> float:
        """バリエーション重み付けを計算"""
        weight = 1.0
        
        if 'enlarged_4x' in variant:
            weight *= 1.25  # 4x拡大は最高効果
        elif 'enlarged_3x' in variant:
            weight *= 1.20  # 3x拡大も非常に効果的
        elif 'enlarged_2x' in variant:
            weight *= 1.15  # 2x拡大は基本的に効果的
        
        if 'cubic' in variant:
            weight *= 1.12  # CUBIC補間は高品質
        elif 'lanczos' in variant:
            weight *= 1.08  # LANCZOS4補間も高品質
        
        if 'text_opt' in variant:
            weight *= 1.18  # 文字特化処理は極めて効果的
        elif 'clahe' in variant:
            weight *= 1.10  # CLAHE は効果的
        elif 'adaptive' in variant:
            weight *= 1.05  # アダプティブ処理も効果的
        
        if 'optimal' in variant:
            weight *= 1.20  # 最適組み合わせは最高重み
        elif 'sharpened' in variant:
            weight *= 1.08  # シャープニングは効果的
        elif 'edge' in variant:
            weight *= 1.06  # エッジ強調も効果的
        
        if 'denoised' in variant:
            weight *= 1.03  # ノイズ除去も効果的
        if 'padded' in variant:
            weight *= 1.02  # パディングは小さいが効果的
        if 'otsu' in variant:
            weight *= 1.02  # Otsu二値化も軽く重視
        
        return weight
    
    def _is_complete_timestamp(self, text: str) -> bool:
        """完全なタイムスタンプ（日付+時刻）かチェック"""
        if not text:
            return False
        
        # 基本的なタイムスタンプパターンマッチ
        for pattern in TIMESTAMP_PATTERNS:
            if re.search(pattern, text):
                # 時刻部分があるかチェック
                has_time = (':' in text) or (text.count('.') >= 2)
                if has_time and len(text) >= 15:  # 最小完全タイムスタンプ長
                    return True
        return False
    
    def _can_combine_early_exit(self, all_results: List[Tuple]) -> bool:
        """高信頼度の日付+時刻の組み合わせで早期終了可能かチェック"""
        if len(all_results) < 2:
            return False
        
        date_candidates = []
        time_candidates = []
        
        for engine, variant, result in all_results:
            text = result.get('text', '').strip()
            confidence = result.get('confidence', 0)
            
            # 高信頼度の結果のみ考慮
            if confidence >= self.early_exit_threshold * 0.8:  # 少し低めの閾値
                if self._is_date_only(text):
                    date_candidates.append((text, confidence))
                elif self._is_time_only(text):
                    time_candidates.append((text, confidence))
        
        # 高信頼度の日付と時刻の組み合わせがあるかチェック
        if date_candidates and time_candidates:
            best_date = max(date_candidates, key=lambda x: x[1])
            best_time = max(time_candidates, key=lambda x: x[1])
            
            # 両方とも十分な信頼度がある場合
            if (best_date[1] >= self.early_exit_threshold * 0.9 and 
                best_time[1] >= self.early_exit_threshold * 0.8):
                return True
        
        return False
    
    def _is_date_only(self, text: str) -> bool:
        """日付のみかチェック"""
        if not text:
            return False
        
        # 日付パターン: YYYY/MM/DD または YYYY-MM-DD
        date_patterns = [
            r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}$',
            r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}\s*$'
        ]
        
        return any(re.match(pattern, text.strip()) for pattern in date_patterns)
    
    def _is_time_only(self, text: str) -> bool:
        """時刻のみかチェック"""
        if not text:
            return False
        
        # 時刻パターン: HH:MM:SS, HH.MM.SS, HHMMSS など
        time_patterns = [
            r'^\d{1,2}[:\.]\d{1,2}[:\.]\d{1,2}$',
            r'^\d{1,2}[:\.]\d{1,2}$',
            r'^\d{6,8}$'  # HHMMSS または HHMMSSS
        ]
        
        return any(re.match(pattern, text.strip()) for pattern in time_patterns)
    
    def _combine_date_and_time(self, date_parts: List[Dict], time_parts: List[Dict]) -> Optional[Dict[str, Any]]:
        """日付部分と時刻部分を組み合わせて完全なタイムスタンプを構築"""
        if not date_parts or not time_parts:
            return None
        
        # 最高スコアの日付と時刻を選択
        best_date = max(date_parts, key=lambda x: x['total_score'])
        best_time = max(time_parts, key=lambda x: x['total_score'])
        
        date_text = best_date['text'].strip()
        time_text = best_time['text'].strip()
        
        # 時刻の正規化
        normalized_time = self._normalize_time_format(time_text)
        
        if normalized_time:
            # 統合されたタイムスタンプを作成
            combined_text = f"{date_text} {normalized_time}"
            
            # 平均信頼度を計算
            avg_confidence = (best_date['base_score'] + best_time['base_score']) / 2
            avg_score = (best_date['total_score'] + best_time['total_score']) / 2
            
            return {
                'text': combined_text,
                'confidence': avg_confidence,
                'total_score': avg_score,
                'source': f"Combined: {best_date['engine']}({best_date['variant']}) + {best_time['engine']}({best_time['variant']})",
                'engine': 'Combined',
                'variant': 'date_time_fusion'
            }
        
        return None
    
    def _normalize_time_format(self, time_text: str) -> Optional[str]:
        """時刻フォーマットを正規化"""
        if not time_text:
            return None
        
        # ドットをコロンに変換
        normalized = time_text.replace('.', ':')
        
        # 数字のみの場合（HHMMSS形式）をパース
        if re.match(r'^\d{6,8}$', time_text):
            if len(time_text) == 6:  # HHMMSS
                return f"{time_text[:2]}:{time_text[2:4]}:{time_text[4:6]}"
            elif len(time_text) == 8:  # HHMMSSMM
                return f"{time_text[:2]}:{time_text[2:4]}:{time_text[4:6]}"
        
        # 既存の区切り文字がある場合
        if ':' in normalized or '.' in time_text:
            return normalized
        
        return None
    
    def _estimate_time_from_date(self, date_result: Dict) -> Optional[Dict[str, Any]]:
        """日付のみの結果から、同一バリエーションで時刻を推定"""
        # この機能は将来の拡張として、現在はNoneを返す
        # 実装する場合: 同じバリエーションの他の結果から時刻らしい文字列を探す
        return None
    
    def _select_best_ocr_result(self, results: List[Tuple]) -> Optional[Dict[str, Any]]:
        """OCR結果から最適なものを選択（統合型アルゴリズム + 合意信頼度）"""
        if not results:
            return None
        
        if self.debug:
            print(f"  Evaluating {len(results)} OCR results...")
        
        # 1. 同一テキストの結果をグループ化し、信頼度を合意スコアで強化
        text_groups = {}
        for engine, variant, result in results:
            text = result['text'].strip()
            confidence = result.get('confidence', 0)
            
            # 基本スコア計算
            base_score = confidence
            timestamp_score = self._calculate_timestamp_score(text)
            
            # バリエーション重み付け
            variant_weight = self._calculate_variant_weight(variant)
            
            # 総合スコア計算
            total_score = base_score * timestamp_score * variant_weight
            
            scored_result = {
                'result': result,
                'total_score': total_score,
                'base_score': base_score,
                'timestamp_score': timestamp_score,
                'engine': engine,
                'variant': variant,
                'variant_weight': variant_weight,
                'text': text,
                'original_confidence': confidence
            }
            
            # 同一テキストでグループ化
            if text not in text_groups:
                text_groups[text] = []
            text_groups[text].append(scored_result)
        
        # 2. 各グループの合意信頼度を計算
        enhanced_results = []
        for text, group in text_groups.items():
            if len(group) == 1:
                # 単一結果の場合はそのまま
                enhanced_results.append(group[0])
            else:
                # 複数結果の場合は合意スコアで強化
                best_in_group = max(group, key=lambda x: x['total_score'])
                
                # 合意ボーナス計算
                consensus_count = len(group)
                confidence_sum = sum(r['original_confidence'] for r in group)
                avg_confidence = confidence_sum / consensus_count
                
                # 合意ボーナス: 複数手法で同じ結果が得られた場合の信頼度向上
                consensus_bonus = min(0.3 * (consensus_count - 1), 0.6)  # 最大0.6の加算
                consistency_bonus = 0.1 if consensus_count >= 3 else 0.05  # 一貫性ボーナス
                
                # 新しい信頼度 = 平均信頼度 + 合意ボーナス + 一貫性ボーナス
                enhanced_confidence = min(avg_confidence + consensus_bonus + consistency_bonus, 1.0)
                
                # 強化された結果を作成
                enhanced_result = best_in_group.copy()
                enhanced_result['result'] = enhanced_result['result'].copy()
                enhanced_result['result']['confidence'] = enhanced_confidence
                enhanced_result['consensus_count'] = consensus_count
                enhanced_result['consensus_bonus'] = consensus_bonus
                enhanced_result['base_score'] = enhanced_confidence
                enhanced_result['total_score'] = enhanced_confidence * enhanced_result['timestamp_score'] * enhanced_result['variant_weight']
                
                enhanced_results.append(enhanced_result)
                
                if self.debug:
                    print(f"    Consensus enhancement for '{text}': {consensus_count} variants, "
                          f"confidence {avg_confidence:.3f} -> {enhanced_confidence:.3f} "
                          f"(bonus: +{consensus_bonus + consistency_bonus:.3f})")
        
        # 3. 結果を分類：完全タイムスタンプ、日付のみ、時刻のみ、その他
        complete_timestamps = []
        date_parts = []
        time_parts = []
        other_results = []
        
        for scored_result in enhanced_results:
            text = scored_result['text']
            
            if self.debug:
                consensus_info = ""
                if 'consensus_count' in scored_result:
                    consensus_info = f" (consensus: {scored_result['consensus_count']} variants)"
                print(f"    {scored_result['engine']}({scored_result['variant']}): '{text}' -> Score: {scored_result['total_score']:.3f}{consensus_info}")
            
            # 結果を分類
            if self._is_complete_timestamp(text):
                complete_timestamps.append(scored_result)
            elif self._is_date_only(text):
                date_parts.append(scored_result)
            elif self._is_time_only(text):
                time_parts.append(scored_result)
            else:
                other_results.append(scored_result)
        
        # 4. 完全なタイムスタンプがある場合は最高スコアを選択
        if complete_timestamps:
            best = max(complete_timestamps, key=lambda x: x['total_score'])
            if self.debug:
                print(f"  Selected complete timestamp: {best['engine']}({best['variant']}) with score {best['total_score']:.3f}")
            return best['result']
        
        # 5. 日付と時刻を統合して完全なタイムスタンプを構築
        if date_parts and time_parts:
            combined_result = self._combine_date_and_time(date_parts, time_parts)
            if combined_result:
                if self.debug:
                    print(f"  Combined timestamp: '{combined_result['text']}' from {combined_result['source']}")
                return combined_result
        
        # 6. 日付のみの場合、時刻を推定
        if date_parts:
            best_date = max(date_parts, key=lambda x: x['total_score'])
            estimated_result = self._estimate_time_from_date(best_date)
            if estimated_result:
                if self.debug:
                    print(f"  Estimated timestamp from date: '{estimated_result['text']}'")
                return estimated_result
        
        # 7. フォールバック：最高スコアを選択
        all_results = complete_timestamps + date_parts + time_parts + other_results
        if all_results:
            best = max(all_results, key=lambda x: x['total_score'])
            if best['total_score'] >= 0.1:
                if self.debug:
                    print(f"  Selected fallback: {best['engine']}({best['variant']}) with score {best['total_score']:.3f}")
                return best['result']
        
        if self.debug:
            print("  No suitable OCR result found")
        return None
    
    def parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """タイムスタンプ文字列を解析してdatetimeオブジェクトに変換"""
        if not timestamp_str:
            return None
        
        # 前処理: 余分な文字を除去
        cleaned = re.sub(r'[^\d/:.@\s-]', '', timestamp_str)
        cleaned = cleaned.strip()
        
        if self.debug:
            print(f"Parsing timestamp: '{timestamp_str}' -> '{cleaned}'")
        
        # パターンに基づく解析
        for pattern in TIMESTAMP_PATTERNS:
            match = re.search(pattern, cleaned)
            if match:
                try:
                    year, month, day, hour, minute, second = map(int, match.groups())
                    
                    # 日付の妥当性チェック
                    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                        continue
                    
                    # JST（日本標準時）として解釈
                    jst = timezone(timedelta(hours=9))
                    timestamp = datetime(year, month, day, hour, minute, second, tzinfo=jst)
                    
                    # UTCに変換
                    utc_timestamp = timestamp.astimezone(timezone.utc)
                    
                    if self.debug:
                        print(f"Parsed JST: {timestamp}")
                        print(f"Converted to UTC: {utc_timestamp}")
                    
                    return utc_timestamp
                    
                except ValueError as e:
                    if self.debug:
                        print(f"Invalid date/time values: {e}")
                    continue
        
        if self.debug:
            print(f"Could not parse timestamp: '{timestamp_str}'")
        
        return None
    
    def embed_exif_with_ffmpeg(self, input_path: str, output_path: str, creation_time: datetime, location: str = None) -> bool:
        """FFmpegを使用してEXIFデータを追加"""
        import subprocess
        
        # メタデータ引数を構築
        metadata_args = [
            '-metadata', f'creation_time={creation_time.isoformat()}'
        ]
        
        if location:
            metadata_args.extend(['-metadata', f'location={location}'])
        
        # FFmpegコマンドを実行
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-c', 'copy',
            *metadata_args,
            output_path
        ]
        
        try:
            if self.debug:
                print(f"Running FFmpeg command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if self.debug:
                print("FFmpeg completed successfully")
                if result.stdout:
                    print(f"FFmpeg stdout: {result.stdout}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg failed with return code {e.returncode}"
            if e.stderr:
                error_msg += f": {e.stderr}"
            
            print(error_msg)
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.FFMPEG_FAILED, input_path, error_msg)
            
            return False
        except FileNotFoundError:
            error_msg = "FFmpeg not found. Please install FFmpeg."
            print(error_msg)
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.FFMPEG_FAILED, input_path, error_msg)
            
            return False
    
    def _move_to_failed_folder(self, input_path: str, reason: str, output_dir: str) -> None:
        """失敗したファイルをfailedフォルダにコピー（元ファイルは保持）"""
        try:
            failed_dir = Path(output_dir) / "failed"
            failed_dir.mkdir(exist_ok=True)
            
            # ユニークなファイル名を生成
            input_file = Path(input_path)
            failed_path = failed_dir / input_file.name
            
            counter = 1
            while failed_path.exists():
                stem = input_file.stem
                suffix = input_file.suffix
                failed_path = failed_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            
            # ファイルをコピー（元ファイルは保持）
            import shutil
            shutil.copy2(input_path, failed_path)
            
            # 理由をテキストファイルに記録
            reason_file = failed_path.with_suffix(failed_path.suffix + ".error.txt")
            with open(reason_file, 'w', encoding='utf-8') as f:
                f.write(f"Error: {reason}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            
            if self.debug:
                print(f"Copied failed file to: {failed_path}")
                print(f"Original file preserved: {input_path}")
                print(f"Reason: {reason}")
                
        except Exception as e:
            if self.debug:
                print(f"Failed to copy error file: {e}")
    
    def _save_crop_to_failed_folder(self, cropped_frame: np.ndarray, input_path: str, output_dir: str) -> None:
        """クロップした画像をfailedフォルダに保存"""
        try:
            failed_dir = Path(output_dir) / "failed"
            failed_dir.mkdir(exist_ok=True)
            
            input_file = Path(input_path)
            crop_filename = f"crop_{input_file.stem}.jpg"
            crop_path = failed_dir / crop_filename
            
            cv2.imwrite(str(crop_path), cropped_frame)
            
            if self.debug:
                print(f"Cropped image saved to failed folder: {crop_path}")
                
        except Exception as e:
            if self.debug:
                print(f"Failed to save crop image: {e}")
    
    def process_video(self, input_path: str, output_path: str, location: str = None) -> bool:
        """単一動画ファイルを処理"""
        if self.debug:
            print(f"Processing video: {os.path.basename(input_path)}")
        
        # 入力ファイルの検証
        if not validate_video_file(input_path):
            error_msg = f"Invalid input file: {input_path}"
            print(error_msg)
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.FILE_NOT_FOUND, input_path, error_msg)
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
            success = self.embed_exif_with_ffmpeg(input_path, output_path, creation_time, location)
            
            if success:
                if self.debug:
                    print(f"Successfully processed: {os.path.basename(input_path)} -> {os.path.basename(output_path)}")
                return True
            else:
                if self.error_handler:
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, "FFmpeg failed", os.path.dirname(output_path))
                    # cropした画像もfailedフォルダに保存
                    self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                return False
                
        except Exception as e:
            error_msg = f"Unexpected error processing {input_path}: {str(e)}"
            print(error_msg)
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.UNKNOWN_ERROR, input_path, error_msg)
                # 失敗したファイルを移動
                self._move_to_failed_folder(input_path, f"Unexpected error: {str(e)}", os.path.dirname(output_path))
            return False
    
    def _apply_super_resolution(self, image: np.ndarray, scale: int) -> np.ndarray:
        """超解像拡大（EDSR風の高度な拡大）"""
        height, width = image.shape[:2]
        
        # 段階的拡大でアーティファクトを減少
        if scale == 4:
            # 2倍 → 2倍の段階的拡大
            step1 = cv2.resize(image, (width * 2, height * 2), interpolation=cv2.INTER_LANCZOS4)
            result = cv2.resize(step1, (width * 4, height * 4), interpolation=cv2.INTER_LANCZOS4)
        else:
            result = cv2.resize(image, (width * scale, height * scale), interpolation=cv2.INTER_LANCZOS4)
        
        # ガウシアンノイズ除去
        result = cv2.GaussianBlur(result, (3, 3), 0.5)
        
        return result
    
    def _apply_contrast_stretching(self, image: np.ndarray) -> np.ndarray:
        """コントラスト拡張（動的レンジ最適化）"""
        if len(image.shape) == 3:
            # カラー画像の場合、LAB色空間で処理
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l_channel = lab[:, :, 0]
            
            # L チャンネルのコントラスト拡張
            min_val = np.percentile(l_channel, 2)
            max_val = np.percentile(l_channel, 98)
            
            stretched = np.clip((l_channel - min_val) * 255 / (max_val - min_val), 0, 255)
            lab[:, :, 0] = stretched.astype(np.uint8)
            
            return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            # グレースケール画像
            min_val = np.percentile(image, 2)
            max_val = np.percentile(image, 98)
            
            return np.clip((image - min_val) * 255 / (max_val - min_val), 0, 255).astype(np.uint8)
    
    def _apply_bilateral_filtering(self, image: np.ndarray) -> np.ndarray:
        """バイラテラルフィルタ（エッジ保持ノイズ除去）"""
        # パラメータ最適化（2024年研究ベース）
        d = 9  # 近傍サイズ
        sigma_color = 75  # 色の標準偏差
        sigma_space = 75  # 空間の標準偏差
        
        return cv2.bilateralFilter(image, d, sigma_color, sigma_space)
    
    def _apply_enhanced_binarization(self, image: np.ndarray) -> np.ndarray:
        """強化2値化（複数手法の組み合わせ）"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 1. CLAHE前処理
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # 2. ガウシアンブラー
        blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
        
        # 3. 適応的閾値
        binary1 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        
        # 4. Otsu閾値
        _, binary2 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 5. 組み合わせ（論理積）
        combined = cv2.bitwise_and(binary1, binary2)
        
        if len(image.shape) == 3:
            return cv2.cvtColor(combined, cv2.COLOR_GRAY2BGR)
        return combined
    
    def _apply_rotation_correction(self, image: np.ndarray) -> np.ndarray:
        """回転補正（skew correction）"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # エッジ検出
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # ハフ変換で直線検出
        lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
        
        if lines is not None:
            # 最も多い角度を計算
            angles = []
            for line in lines:
                rho, theta = line[0]
                angle = np.degrees(theta) - 90
                if abs(angle) < 45:  # 45度以内の回転のみ補正
                    angles.append(angle)
            
            if angles:
                # 中央値を使用（外れ値に対してロバスト）
                rotation_angle = np.median(angles)
                
                # 回転補正
                if abs(rotation_angle) > 0.5:  # 0.5度以上の場合のみ補正
                    height, width = image.shape[:2]
                    center = (width // 2, height // 2)
                    rotation_matrix = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
                    
                    return cv2.warpAffine(image, rotation_matrix, (width, height),
                                        flags=cv2.INTER_LANCZOS4,
                                        borderMode=cv2.BORDER_CONSTANT,
                                        borderValue=(255, 255, 255) if len(image.shape) == 3 else 255)
        
        return image

    def process_batch(self, input_directory: str, output_directory: str = None, 
                     location: str = None, skip_errors: bool = True, 
                     max_workers: int = None, use_threading: bool = False, 
                     batch_size: int = None) -> Dict[str, Any]:
        """バッチ処理を実行"""
        if self.debug:
            print(f"Starting batch processing from: {input_directory}")
        
        try:
            # BatchProcessorを使用
            processor = BatchProcessor(
                enhancer=self,
                debug=self.debug
            )
            
            return processor.process_batch(
                input_directory=input_directory,
                output_directory=output_directory,
                location=location,
                skip_errors=skip_errors,
                max_workers=max_workers,
                use_threading=use_threading,
                batch_size=batch_size
            )
            
        except Exception as e:
            error_msg = f"Batch processing failed: {str(e)}"
            print(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'processed': 0,
                'failed': 0,
                'total': 0
            }


def worker_process_video(args) -> bool:
    """ワーカープロセス用の動画処理関数"""
    input_path, output_path, location, debug, languages, use_gpu, enhanced_ocr, confidence_threshold, early_exit_threshold = args
    
    try:
        # 各プロセスで新しいenhancerインスタンスを作成
        enhancer = XiaomiVideoExifEnchanterOCR(
            debug=debug,
            languages=languages,
            use_gpu=use_gpu,
            enhanced_ocr=enhanced_ocr
        )
        
        enhancer.set_confidence_threshold(confidence_threshold)
        enhancer.set_early_exit_threshold(early_exit_threshold)
        
        success = enhancer.process_video(input_path, output_path, location)
        
        return success
        
    except Exception as e:
        if debug:
            print(f"Worker process error for {os.path.basename(input_path)}: {e}")
        return False


def main() -> None:
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Xiaomi Video EXIF Enhancer - OCR Only Version')
    parser.add_argument('input', help='Input video file or directory')
    parser.add_argument('-o', '--output', help='Output video file or directory')
    parser.add_argument('-l', '--location', help='Location information to add')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--batch', action='store_true', help='Process directory in batch mode')
    parser.add_argument('--languages', nargs='+', default=['en'], help='OCR languages')
    parser.add_argument('--gpu', action='store_true', help='Use GPU for OCR')
    parser.add_argument('--confidence', type=float, default=0.5, help='OCR confidence threshold')
    parser.add_argument('--early-exit-threshold', type=float, default=0.9, help='Early exit confidence threshold (stop processing when high confidence result found)')
    parser.add_argument('--max-workers', type=int, help='Maximum number of parallel workers')
    parser.add_argument('--use-threading', action='store_true', help='Use threading instead of multiprocessing')
    parser.add_argument('--batch-size', type=int, help='Batch size for processing')
    parser.add_argument('--skip-errors', action='store_true', default=True, help='Skip files with errors')
    parser.add_argument('--disable-enhanced-ocr', action='store_true', help='Disable enhanced OCR (use basic OCR only)')
    
    args = parser.parse_args()
    
    # Enhancerインスタンスを作成
    enhancer = XiaomiVideoExifEnchanterOCR(
        debug=args.debug,
        languages=args.languages,
        use_gpu=args.gpu,
        enhanced_ocr=not args.disable_enhanced_ocr
    )
    
    # 信頼度閾値を設定
    enhancer.set_confidence_threshold(args.confidence)
    enhancer.set_early_exit_threshold(args.early_exit_threshold)
    
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
            
            print(f"\nBatch processing completed:")
            print(f"  Total files: {results.get('total', 0)}")
            print(f"  Processed successfully: {results.get('processed', 0)}")
            print(f"  Failed: {results.get('failed', 0)}")
            
            if results.get('failed', 0) > 0:
                print(f"  Failed files copied to: {results.get('failed_directory', 'failed/')}")
            
            # 統計情報の表示
            if 'statistics' in results:
                stats = results['statistics']
                print(f"\nProcessing statistics:")
                print(f"  Average time per file: {stats.get('avg_time_per_file', 0):.2f}s")
                print(f"  Total processing time: {stats.get('total_time', 0):.2f}s")
            
        else:
            # 単一ファイル処理モード
            if not args.output:
                # 出力ファイル名を自動生成
                input_path = Path(args.input)
                output_filename = f"{input_path.stem}_enhanced{input_path.suffix}"
                args.output = str(input_path.parent / output_filename)
            
            success = enhancer.process_video(args.input, args.output, args.location)
            
            if success:
                print(f"Successfully processed: {args.input} -> {args.output}")
            else:
                print(f"Failed to process: {args.input}")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
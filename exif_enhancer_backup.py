#!/usr/bin/env python3
"""
Xiaomi Video EXIF Enhancer
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
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing
from tqdm import tqdm
from functools import lru_cache
from video_error_handler import VideoErrorHandler, VideoErrorType
from output_path_generator import OutputPathGenerator


# タイムスタンプ検出用の正規表現パターン定数
TIMESTAMP_PATTERNS = [
    # @記号付きドット区切り形式: @ 2025/05/28 19.41.14
    r'@?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:.](\d{2})[:.](\d{2})',
    # @記号付きコロン区切り形式: @ 2025/05/28 19:41:14
    r'@?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})',
    # 数字のみ形式: 20250528 19:41:14
    r'@?\s*(\d{4})(\d{2})(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})',
]

# デフォルト設定
DEFAULT_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_CROP_RATIO = 0.25
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}


class EasyOCRSingleton:
    """EasyOCRのシングルトンクラス - 初期化オーバーヘッドを削減"""
    _instances = {}
    _lock = multiprocessing.Lock()
    
    @classmethod
    def get_reader(cls, languages: List[str] = None, gpu: bool = None, debug: bool = False) -> easyocr.Reader:
        """EasyOCRリーダーのシングルトンインスタンスを取得
        
        Args:
            languages: OCR言語リスト
            gpu: GPU使用フラグ（自動検出）
            debug: デバッグモード
            
        Returns:
            EasyOCRリーダーインスタンス
        """
        if languages is None:
            languages = ['en', 'ja']
        
        # 環境変数でのCPUモード強制チェック
        force_cpu = os.environ.get('FORCE_CPU_MODE', '').lower() in ('1', 'true', 'yes')
        force_gpu = os.environ.get('FORCE_GPU_MODE', '').lower() in ('1', 'true', 'yes')
        
        if force_cpu:
            gpu = False
            if debug:
                print("GPU mode disabled by FORCE_CPU_MODE environment variable")
        elif force_gpu:
            gpu = True
            if debug:
                print("GPU mode forced by FORCE_GPU_MODE environment variable")
        
        # GPU利用可能性の自動検出とRTX 50シリーズ互換性チェック
        elif gpu is None:
            try:
                import torch
                gpu = torch.cuda.is_available()
                
                # RTX 50シリーズの互換性チェック（GPU強制時は警告のみ）
                if gpu and torch.cuda.is_available():
                    device_name = torch.cuda.get_device_name(0)
                    capability = torch.cuda.get_device_capability(0)
                    
                    # CUDA capability sm_120 (RTX 50シリーズ) の場合は警告（強制GPUモード時は継続）
                    if capability[0] >= 12 or "RTX 50" in device_name or "RTX 5070" in device_name:
                        if debug:
                            print(f"⚠️ Detected {device_name} with CUDA capability sm_{capability[0]}{capability[1]}")
                            if not force_gpu:
                                print("RTX 50シリーズはPyTorch安定版で未サポートのため、CPUフォールバックを推奨")
                                gpu = False  # GPU強制でない場合のみCPUモードに強制
                            else:
                                print("FORCE_GPU_MODE=1により強制的にGPUモードで継続します")
                
                if debug and gpu:
                    print("CUDA GPU detected, enabling GPU acceleration for OCR")
                elif debug:
                    print("Using CPU mode for EasyOCR (GPU disabled or incompatible)")
            except ImportError:
                gpu = False
        
        # インスタンスキーの生成
        key = (tuple(sorted(languages)), gpu)
        
        with cls._lock:
            if key not in cls._instances:
                if debug:
                    print(f"Creating new EasyOCR reader instance: languages={languages}, gpu={gpu}")
                
                start_time = time.time()
                try:
                    reader = easyocr.Reader(languages, gpu=gpu)
                    init_time = time.time() - start_time
                    
                    if debug:
                        print(f"EasyOCR reader initialized in {init_time:.2f} seconds")
                    
                    cls._instances[key] = reader
                except Exception as e:
                    if debug:
                        print(f"Failed to initialize EasyOCR reader with GPU={gpu}: {e}")
                    
                    # GPU初期化に失敗した場合、CPUフォールバックを試行
                    if gpu:
                        if debug:
                            print("Falling back to CPU mode...")
                        try:
                            reader = easyocr.Reader(languages, gpu=False)
                            init_time = time.time() - start_time
                            
                            if debug:
                                print(f"EasyOCR reader initialized in CPU mode in {init_time:.2f} seconds")
                            
                            # CPUモードでキャッシュ
                            cpu_key = (tuple(sorted(languages)), False)
                            cls._instances[cpu_key] = reader
                            return reader
                        except Exception as cpu_error:
                            if debug:
                                print(f"CPU fallback also failed: {cpu_error}")
                            raise RuntimeError(f"Failed to initialize EasyOCR reader: GPU error: {e}, CPU error: {cpu_error}")
                    else:
                        raise RuntimeError(f"Failed to initialize EasyOCR reader: {e}")
            else:
                if debug:
                    print("Reusing existing EasyOCR reader instance")
        
        return cls._instances[key]
    
    @classmethod
    def clear_cache(cls):
        """キャッシュされたリーダーインスタンスをクリア"""
        with cls._lock:
            cls._instances.clear()


class XiaomiVideoEXIFEnhancer:
    """Xiaomiホームカメラ映像のEXIF情報を拡張するクラス"""
    
    def __init__(self, debug: bool = False, languages: List[str] = None, use_gpu: bool = None) -> None:
        """初期化処理
        
        Args:
            debug: デバッグモードの有効/無効
            languages: OCRで使用する言語リスト（デフォルト: ['en', 'ja']）
            use_gpu: GPU使用フラグ（自動検出）
        """
        self.debug = debug
        self.languages = languages or ['en', 'ja']
        self.use_gpu = use_gpu
        self.confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD
        
        # 映像エラーハンドラーを初期化
        self.error_handler = VideoErrorHandler(debug=debug)
        
        # 出力パス生成器を初期化
        self.path_generator = OutputPathGenerator(debug=debug)
        
        # EasyOCRリーダーはシングルトンで取得（初期化オーバーヘッド削減）
        self.reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, debug)
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """OCR信頼度閾値を設定
        
        Args:
            threshold: 信頼度閾値（0.0-1.0）
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"Threshold must be between 0.0 and 1.0, got {threshold}")
        self.confidence_threshold = threshold
        if self.debug:
            print(f"Confidence threshold set to {threshold}")
    
    def get_ocr_languages(self) -> List[str]:
        """使用中のOCR言語リストを取得
        
        Returns:
            言語コードのリスト
        """
        return self.languages.copy()
    
    def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """映像ファイルの基本情報を取得
        
        Args:
            video_path: 映像ファイルのパス
            
        Returns:
            映像の基本情報（フレーム数、FPS、解像度など）
            
        Raises:
            ValueError: 映像の読み込みに失敗した場合
        """
        if self.debug:
            print(f"Getting video info for: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        
        try:
            if not cap.isOpened():
                raise ValueError(f"Cannot open video file: {video_path}")
            
            # 基本的な映像情報を取得
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            
            # FourCCをテキストに変換
            fourcc_str = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
            
            video_info = {
                'frame_count': frame_count,
                'fps': fps,
                'width': width,
                'height': height,
                'resolution': f"{width}x{height}",
                'fourcc': fourcc_str,
                'duration_seconds': frame_count / fps if fps > 0 else 0,
                'file_size_bytes': os.path.getsize(video_path) if os.path.exists(video_path) else 0
            }
            
            if self.debug:
                print(f"Video info: {video_info}")
            
            return video_info
        finally:
            cap.release()
    
    def is_supported_format(self, video_path: str) -> bool:
        """サポートされている映像形式かどうかを確認
        
        Args:
            video_path: 映像ファイルのパス
            
        Returns:
            サポートされている場合True
        """
        file_extension = Path(video_path).suffix.lower()
        return file_extension in SUPPORTED_VIDEO_EXTENSIONS
    
    def extract_first_frame(self, video_path: str) -> np.ndarray:
        """映像の1フレーム目を抽出（改良されたエラーハンドリング付き）
        
        Args:
            video_path: 映像ファイルのパス
            
        Returns:
            抽出されたフレーム
            
        Raises:
            ValueError: 映像の読み込みに失敗した場合
            FileNotFoundError: ファイルが存在しない場合
            PermissionError: アクセス権限がない場合
        """
        if self.debug:
            print(f"Extracting first frame from: {video_path}")
        
        # 映像ファイルの詳細検証
        try:
            # エラーハンドラーで詳細分析
            is_valid = self.error_handler.validate_video_file(video_path, raise_on_error=True)
        except (FileNotFoundError, PermissionError, ValueError, RuntimeError) as e:
            # ユーザーフレンドリーなエラーレポート生成
            error_report = self.error_handler.create_error_report(video_path)
            
            if self.debug:
                print("\n" + "="*50)
                print("VIDEO FILE ERROR DETECTED")
                print("="*50)
                print(error_report['user_message'])
                print("\n回復のための提案:")
                for i, suggestion in enumerate(error_report['recovery_suggestions'], 1):
                    print(f"  {i}. {suggestion}")
                print("="*50)
            else:
                # 非デバッグモードでも重要な情報は表示
                print(f"\n❌ 映像ファイルエラー: {Path(video_path).name}")
                print(error_report['user_message'])
            
            # 元の例外を再発生
            raise
        
        cap = cv2.VideoCapture(video_path)
        
        try:
            if not cap.isOpened():
                error_msg = f"Cannot open video file: {video_path}"
                if self.debug:
                    print(f"OpenCV error: {error_msg}")
                raise ValueError(error_msg)
            
            ret, frame = cap.read()
            if not ret or frame is None:
                error_msg = f"Failed to read first frame from: {video_path}"
                if self.debug:
                    print(f"Frame reading error: {error_msg}")
                raise ValueError(error_msg)
            
            if self.debug:
                print(f"Frame extracted successfully, shape: {frame.shape}")
                print(f"Frame dtype: {frame.dtype}, min: {frame.min()}, max: {frame.max()}")
            
            # フレーム形式の確認とバリデーション
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                error_msg = f"Invalid frame format: expected 3-channel color image, got shape {frame.shape}"
                if self.debug:
                    print(f"Frame format error: {error_msg}")
                raise ValueError(error_msg)
            
            return frame
        finally:
            cap.release()
    
    def save_debug_frame(self, frame: np.ndarray, filename: str = "debug_frame.jpg") -> bool:
        """デバッグ用にフレームを保存
        
        Args:
            frame: 保存するフレーム
            filename: 保存ファイル名
            
        Returns:
            保存成功時True
        """
        try:
            import cv2
            success = cv2.imwrite(filename, frame)
            if self.debug and success:
                print(f"Debug frame saved as: {filename}")
            return success
        except Exception as e:
            if self.debug:
                print(f"Failed to save debug frame: {e}")
            return False
    
    def crop_timestamp_area(self, frame: np.ndarray, crop_ratio: Optional[float] = None, use_fixed_position: bool = False) -> np.ndarray:
        """左上の日時領域をクロップ（固定位置優先または適応的比率）
        
        Args:
            frame: 入力フレーム
            crop_ratio: クロップ比率（0.1-1.0、Noneの場合は適応的に決定）
            use_fixed_position: 固定位置クロップを使用するかどうか
            
        Returns:
            クロップされた画像
            
        Raises:
            ValueError: 無効なフレーム形式または比率の場合
        """
        if len(frame.shape) != 3:
            raise ValueError(f"Invalid frame format: expected 3D array, got shape {frame.shape}")
        
        height, width = frame.shape[:2]
        
        if use_fixed_position:
            # 固定位置でのクロップ（Xiaomi C301 カメラ用）
            crop_coords = self.get_fixed_timestamp_coordinates(frame)
            x1, y1, x2, y2 = crop_coords
            
            if self.debug:
                print(f"Using fixed position crop: {width}x{height} -> coordinates({x1},{y1},{x2},{y2})")
            
            cropped = frame[y1:y2, x1:x2]
        else:
            # 既存の適応的クロップ
            if crop_ratio is None:
                crop_ratio = 0.25  # 従来のデフォルト値で後方互換性を保持
                if self.debug:
                    print(f"Using default crop ratio: {crop_ratio}")
            
            if not 0.1 <= crop_ratio <= 1.0:
                raise ValueError(f"Invalid crop_ratio: {crop_ratio}, must be between 0.1 and 1.0")
            
            crop_height = int(height * crop_ratio)
            crop_width = int(width * crop_ratio)
            
            if self.debug:
                print(f"Cropping timestamp area: {width}x{height} -> {crop_width}x{crop_height} (ratio: {crop_ratio})")
            
            cropped = frame[0:crop_height, 0:crop_width]
        
        if self.debug:
            print(f"Cropped area shape: {cropped.shape}")
        
        return cropped
    
    def crop_timestamp_area_adaptive(self, frame: np.ndarray) -> np.ndarray:
        """適応的クロップ（解像度に基づく最適化）
        
        Args:
            frame: 入力フレーム
            
        Returns:
            クロップされた画像
        """
        optimal_ratio = self.get_optimal_crop_ratio(frame)
        return self.crop_timestamp_area(frame, crop_ratio=optimal_ratio, use_fixed_position=False)
    
    def crop_timestamp_area_fixed(self, frame: np.ndarray) -> np.ndarray:
        """固定位置クロップ（精度向上版）
        
        Args:
            frame: 入力フレーム
            
        Returns:
            クロップされた画像
        """
        return self.crop_timestamp_area(frame, use_fixed_position=True)
    
    def crop_timestamp_area_smart(self, frame: np.ndarray) -> np.ndarray:
        """スマートクロップ（固定位置と適応的の組み合わせ）
        
        Args:
            frame: 入力フレーム
            
        Returns:
            クロップされた画像
        """
        # まず固定位置でクロップを試行
        cropped_fixed = self.crop_timestamp_area(frame, use_fixed_position=True)
        
        # 固定位置クロップでOCRを実行
        timestamp_fixed = self.extract_timestamp(cropped_fixed)
        
        if timestamp_fixed and len(timestamp_fixed) > 10:  # 有効なタイムスタンプが検出された
            if self.debug:
                print(f"Fixed position cropping successful: {timestamp_fixed}")
            return cropped_fixed
        else:
            # 固定位置で失敗した場合、適応的クロップにフォールバック
            if self.debug:
                print("Fixed position cropping failed, falling back to adaptive cropping")
            return self.crop_timestamp_area_adaptive(frame)
    
    def save_cropped_area(self, cropped_frame: np.ndarray, filename: str = "cropped_timestamp.jpg") -> bool:
        """クロップした日時領域を保存
        
        Args:
            cropped_frame: クロップされたフレーム
            filename: 保存ファイル名
            
        Returns:
            保存成功時True
        """
        try:
            import cv2
            success = cv2.imwrite(filename, cropped_frame)
            if self.debug and success:
                print(f"Cropped timestamp area saved as: {filename}")
            return success
        except Exception as e:
            if self.debug:
                print(f"Failed to save cropped area: {e}")
            return False
    
    def get_fixed_timestamp_coordinates(self, frame: np.ndarray) -> tuple:
        """Xiaomi C301カメラのタイムスタンプ固定位置座標を取得
        
        Args:
            frame: 入力フレーム
            
        Returns:
            タイムスタンプ領域の座標 (x1, y1, x2, y2)
        """
        height, width = frame.shape[:2]
        
        # Xiaomi C301 カメラのタイムスタンプ位置（解像度別）
        if width <= 640:  # SD quality (640x360, 640x480)
            # タイムスタンプ領域をより広く設定（高さも十分に確保）
            x1, y1 = 5, 5
            x2, y2 = min(280, width), min(50, height)
        elif width <= 1280:  # HD quality (1280x720)
            x1, y1 = 10, 10
            x2, y2 = min(420, width), min(70, height)
        elif width <= 1920:  # Full HD (1920x1080)
            x1, y1 = 15, 15
            x2, y2 = min(520, width), min(85, height)
        else:  # 4K and above
            x1, y1 = 25, 25
            x2, y2 = min(700, width), min(110, height)
        
        # フレーム境界内に収まるように調整
        x1 = max(0, min(x1, width - 50))
        y1 = max(0, min(y1, height - 25))
        x2 = max(x1 + 50, min(x2, width))
        y2 = max(y1 + 25, min(y2, height))
        
        return (x1, y1, x2, y2)
    
    def get_optimal_crop_ratio(self, frame: np.ndarray) -> float:
        """映像解像度に基づいて最適なクロップ比率を決定
        
        Args:
            frame: 入力フレーム
            
        Returns:
            最適なクロップ比率
        """
        height, width = frame.shape[:2]
        
        # 解像度に基づく適応的クロップ比率
        if width <= 640:  # SD quality
            return 0.3
        elif width <= 1280:  # HD quality
            return 0.25
        elif width <= 1920:  # Full HD
            return 0.2
        else:  # 4K and above
            return 0.15
    
    def extract_timestamp(self, cropped_frame: np.ndarray) -> Optional[str]:
        """OCRで日時文字列を抽出
        
        Args:
            cropped_frame: クロップされたフレーム
            
        Returns:
            抽出された日時文字列、見つからない場合はNone
        """
        try:
            if self.debug:
                print("Running OCR on cropped frame...")
            
            start_time = time.time()
            results = self.reader.readtext(cropped_frame)
            ocr_time = time.time() - start_time
            
            if self.debug:
                print(f"OCR completed in {ocr_time:.3f} seconds")
                print(f"OCR detected {len(results)} text regions")
            
            return self._find_best_timestamp_match(results)
        except Exception as e:
            if self.debug:
                print(f"OCR processing failed: {e}")
            return None
    
    def _find_best_timestamp_match(self, ocr_results: List[Tuple]) -> Optional[str]:
        """OCR結果から最適なタイムスタンプを選択
        
        Args:
            ocr_results: EasyOCRの結果リスト
            
        Returns:
            最適なタイムスタンプ文字列、見つからない場合はNone
        """
        timestamp_candidates = []
        fallback_candidates = []  # 信頼度が低いが形式が合致するもの
        
        for (bbox, text, conf) in ocr_results:
            if self.debug:
                print(f"OCR result: '{text}' (confidence: {conf:.3f})")
            
            # 複数パターンでマッチを試行
            pattern_matched = False
            for pattern in TIMESTAMP_PATTERNS:
                if re.search(pattern, text):
                    if conf >= self.confidence_threshold:
                        timestamp_candidates.append((text, conf, bbox))
                        if self.debug:
                            print(f"Timestamp candidate: '{text}' (confidence: {conf:.3f})")
                    else:
                        # 信頼度が低いがパターンマッチするものをフォールバック候補に
                        fallback_candidates.append((text, conf, bbox))
                        if self.debug:
                            print(f"Fallback timestamp candidate: '{text}' (confidence: {conf:.3f})")
                    pattern_matched = True
                    break
        
        # 通常の候補がある場合
        if timestamp_candidates:
            best_candidate = max(timestamp_candidates, key=lambda x: x[1])
            best_text, best_conf, best_bbox = best_candidate
            if self.debug:
                print(f"Best timestamp: '{best_text}' (confidence: {best_conf:.3f})")
            return best_text
        
        # フォールバック候補を検討（信頼度0.3以上）
        if fallback_candidates:
            valid_fallbacks = [(text, conf, bbox) for text, conf, bbox in fallback_candidates if conf >= 0.3]
            if valid_fallbacks:
                best_fallback = max(valid_fallbacks, key=lambda x: x[1])
                best_text, best_conf, best_bbox = best_fallback
                if self.debug:
                    print(f"Using fallback timestamp: '{best_text}' (confidence: {best_conf:.3f})")
                return best_text
        
        if self.debug:
            print(f"No valid timestamp found above confidence threshold {self.confidence_threshold}")
            if fallback_candidates:
                print(f"Fallback candidates available but confidence too low")
        
        return None
    
    def extract_timestamp_with_details(self, cropped_frame: np.ndarray) -> Dict[str, Any]:
        """詳細情報付きでタイムスタンプを抽出
        
        Args:
            cropped_frame: クロップされたフレーム
            
        Returns:
            タイムスタンプと詳細情報を含む辞書
        """
        result = {
            'timestamp': None,
            'confidence': 0.0,
            'bbox': None,
            'ocr_time': 0.0,
            'total_detections': 0,
            'valid_candidates': 0,
            'all_results': []
        }
        
        try:
            start_time = time.time()
            ocr_results = self.reader.readtext(cropped_frame)
            result['ocr_time'] = time.time() - start_time
            result['total_detections'] = len(ocr_results)
            
            candidates = []
            
            for (bbox, text, conf) in ocr_results:
                result['all_results'].append({
                    'text': text,
                    'confidence': conf,
                    'bbox': bbox
                })
                
                if conf >= self.confidence_threshold:
                    # 複数パターンでマッチを試行
                    for pattern in TIMESTAMP_PATTERNS:
                        if re.search(pattern, text):
                            candidates.append((text, conf, bbox))
                            break
            
            result['valid_candidates'] = len(candidates)
            
            if candidates:
                best_text, best_conf, best_bbox = max(candidates, key=lambda x: x[1])
                result['timestamp'] = best_text
                result['confidence'] = best_conf
                result['bbox'] = best_bbox
            
        except Exception as e:
            if self.debug:
                print(f"OCR processing failed: {e}")
        
        return result
    
    def test_ocr_performance(self, cropped_frame: np.ndarray, iterations: int = 5) -> Dict[str, float]:
        """OCR性能をテスト
        
        Args:
            cropped_frame: テスト用フレーム
            iterations: テスト回数
            
        Returns:
            性能測定結果
        """
        times = []
        successful_runs = 0
        
        for i in range(iterations):
            try:
                start_time = time.time()
                self.reader.readtext(cropped_frame)
                end_time = time.time()
                times.append(end_time - start_time)
                successful_runs += 1
            except Exception:
                pass
        
        if times:
            return {
                'average_time': sum(times) / len(times),
                'min_time': min(times),
                'max_time': max(times),
                'successful_runs': successful_runs,
                'total_runs': iterations,
                'success_rate': successful_runs / iterations
            }
        else:
            return {
                'average_time': 0.0,
                'min_time': 0.0,
                'max_time': 0.0,
                'successful_runs': 0,
                'total_runs': iterations,
                'success_rate': 0.0
            }
    
    def parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """日時文字列を標準形式に変換
        
        Args:
            timestamp_str: 日時文字列
            
        Returns:
            パースされたdatetimeオブジェクト、失敗した場合はNone
        """
        if not timestamp_str:
            if self.debug:
                print("No timestamp string provided")
            return None
        
        if self.debug:
            print(f"Parsing timestamp: {timestamp_str}")
        
        for i, pattern in enumerate(TIMESTAMP_PATTERNS):
            match = re.search(pattern, timestamp_str)
            if match:
                year, month, day, hour, minute, second = match.groups()
                try:
                    # JST (UTC+9) として作成
                    jst = timezone(timedelta(hours=9))
                    dt = datetime(int(year), int(month), int(day), 
                                int(hour), int(minute), int(second), tzinfo=jst)
                    if self.debug:
                        print(f"Timestamp parsed successfully (JST): {dt}")
                    return dt
                except ValueError as e:
                    if self.debug:
                        print(f"Invalid date values in '{timestamp_str}' (pattern {i+1}): {e}")
                    continue
        
        if self.debug:
            print(f"Failed to parse timestamp: {timestamp_str}")
        return None
    
    def add_exif_data(self, video_path: str, output_path: str, 
                     timestamp: Optional[datetime], location: Optional[str] = None) -> bool:
        """EXIF情報を追加して映像を出力（Issue #9対応強化版）
        
        Args:
            video_path: 入力映像ファイルのパス
            output_path: 出力映像ファイルのパス
            timestamp: 設定するタイムスタンプ
            location: 設定する場所情報
            
        Returns:
            処理成功時True、失敗時False
        """
        try:
            import ffmpeg
        except ImportError:
            error_msg = "Error: ffmpeg-python is not installed"
            print(error_msg)
            if self.debug:
                print("Install with: pip install ffmpeg-python")
            return False
        
        if self.debug:
            print(f"Adding EXIF data to: {video_path}")
            print(f"Output path: {output_path}")
            if timestamp:
                if timestamp.tzinfo is None:
                    jst = timezone(timedelta(hours=9))
                    timestamp_with_tz = timestamp.replace(tzinfo=jst)
                else:
                    timestamp_with_tz = timestamp
                utc_time = timestamp_with_tz.astimezone(timezone.utc)
                print(f"Timestamp: {timestamp} (JST) -> {utc_time.isoformat()} (UTC)")
            if location:
                print(f"Location: {location}")
        
        # メタデータ辞書の構築
        metadata = {}
        
        # Issue #9: 作成日時のEXIF情報への埋め込み
        if timestamp:
            # JST から UTC に変換してISO 8601形式で設定
            if timestamp.tzinfo is None:
                # ナイーブなdatetimeの場合はJSTとして扱う
                jst = timezone(timedelta(hours=9))
                timestamp = timestamp.replace(tzinfo=jst)
            
            # UTC に変換
            utc_timestamp = timestamp.astimezone(timezone.utc)
            creation_time = utc_timestamp.isoformat()
            metadata['creation_time'] = creation_time
            
            # 互換性のため複数のタイムスタンプフィールドを設定
            metadata['date'] = creation_time
            
            if self.debug:
                print(f"Set creation_time metadata: {creation_time}")
        
        # Issue #10: 撮影場所のEXIF情報への埋め込み
        if location:
            # UTF-8エンコーディングの確保
            try:
                encoded_location = location.encode('utf-8').decode('utf-8')
                metadata['location'] = encoded_location
                
                # 場所情報の追加フィールド
                metadata['comment'] = f"撮影場所: {encoded_location}"
                
                if self.debug:
                    print(f"Set location metadata: {encoded_location}")
                    
            except UnicodeEncodeError:
                print(f"Warning: Failed to encode location '{location}' as UTF-8")
                metadata['location'] = "Unknown Location"
        
        # ツール情報の追加
        metadata['encoder'] = 'Xiaomi Video EXIF Enhancer'
        
        if self.debug:
            print(f"Final metadata to embed: {metadata}")
        
        # 既存メタデータの保持チェック
        try:
            # 既存のメタデータを取得して保持
            probe = ffmpeg.probe(video_path)
            existing_metadata = probe.get('format', {}).get('tags', {})
            
            if existing_metadata and self.debug:
                print(f"Found existing metadata: {existing_metadata}")
                # 既存のメタデータを保持（新規データで上書きしない）
                for key, value in existing_metadata.items():
                    if key.lower() not in [k.lower() for k in metadata.keys()]:
                        metadata[key] = value
                        if self.debug:
                            print(f"Preserved existing metadata: {key}={value}")
                            
        except Exception as e:
            if self.debug:
                print(f"Could not read existing metadata: {e}")
        
        # メタデータ埋め込みの実行
        try:
            if self.debug:
                print("Running FFmpeg with metadata embedding...")
            
            # メタデータを正しい形式で構築
            print(f"Metadata to embed: {metadata}")
            
            try:
                # subprocessを使用してFFmpegを直接実行
                import subprocess
                
                cmd = ['ffmpeg', '-i', video_path, '-vcodec', 'copy', '-acodec', 'copy']
                
                # メタデータパラメータを追加
                for key, value in metadata.items():
                    cmd.extend(['-metadata', f'{key}={value}'])
                
                cmd.extend(['-y', output_path])
                
                print(f"FFmpeg command: {' '.join(cmd)}")
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"FFmpeg failed with return code {result.returncode}: {result.stderr}")
                
                if self.debug:
                    print("✓ FFmpeg processing completed successfully")
                    
            except Exception as stream_error:
                print(f"FFmpeg execution error: {stream_error}")
                raise
            
            # 埋め込み結果の検証
            if self.debug:
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
                    print(e.stderr.decode('utf-8', errors='replace'))
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
        """失敗したファイルをfailedフォルダに移動（下位互換性のため）"""
        from file_manager import FileManager
        file_manager = FileManager(debug=self.debug)
        file_manager.move_to_failed_folder(input_path, reason, output_dir)
    
    def _process_batch_sequential(self, video_files: List[str], output_directory: str, 
                                 location: Optional[str], skip_errors: bool,
                                 path_generator, results: Dict[str, Any]) -> Dict[str, Any]:
        """逐次バッチ処理（メモリ効率化版）"""
        
        # プログレス表示の改善とガベージコレクション
        import gc
        import time
        
        start_time = time.time()
        last_gc_time = start_time
        
        # 各ファイルを処理（プログレスバー付き）
        progress_bar = tqdm(video_files, desc="Processing videos", unit="file")
        
        for i, input_file in enumerate(progress_bar, 1):
            file_name = os.path.basename(input_file)
            progress_bar.set_description(f"Processing: {file_name[:30]}")
            
            # デバッグ情報表示
            if self.debug:
                elapsed_time = time.time() - start_time
                if i > 1:
                    avg_time_per_file = elapsed_time / (i - 1)
                    estimated_remaining = avg_time_per_file * (len(video_files) - i + 1)
                    progress_bar.write(f"[{i}/{len(video_files)}] Processing: {file_name}")
                    progress_bar.write(f"  Elapsed: {elapsed_time:.1f}s | Est. remaining: {estimated_remaining:.1f}s")
                else:
                    progress_bar.write(f"[{i}/{len(video_files)}] Processing: {file_name}")
            
            # 定期的なガベージコレクション（100ファイルごと）
            current_time = time.time()
            if current_time - last_gc_time > 300:  # 5分ごと
                if self.debug:
                    print("  Running garbage collection...")
                gc.collect()
                last_gc_time = current_time
            
            try:
                # 出力ファイルパスを生成
                input_dir = os.path.dirname(input_file)
                if path_generator:
                    if output_directory == input_dir:
                        output_file = path_generator.generate_output_path(input_file)
                    else:
                        base_name = Path(input_file).stem
                        output_file = os.path.join(output_directory, f"{base_name}_enhanced.mp4")
                else:
                    # 簡単な命名方式
                    base_name = Path(input_file).stem
                    if output_directory == input_dir:
                        output_file = os.path.join(output_directory, f"{base_name}_enhanced.mp4")
                    else:
                        output_file = os.path.join(output_directory, f"{base_name}.mp4")
                
                # 既存ファイルのスキップチェック（拡張版）
                base_name = Path(input_file).stem
                existing_patterns = [
                    os.path.join(output_directory, f"{base_name}_enhanced.mp4"),
                    os.path.join(output_directory, f"{base_name}_enhanced_001.mp4"),
                    os.path.join(output_directory, f"{base_name}_enhanced_002.mp4"),
                    os.path.join(output_directory, f"{base_name}_enhanced_003.mp4")
                ]
                
                existing_file = None
                for pattern in existing_patterns:
                    if os.path.exists(pattern):
                        existing_file = pattern
                        break
                
                if existing_file:
                    if self.debug:
                        progress_bar.write(f"  ⚠ Output file already exists, skipping: {os.path.basename(existing_file)}")
                    results['skipped_files'].append({
                        'input': input_file,
                        'output': existing_file,
                        'reason': 'Output file already exists'
                    })
                    continue
                
                # ファイルを処理
                success = self.process_video(input_file, output_file, location)
                
                if success:
                    results['successful'] += 1
                    results['processed_files'].append({
                        'input': input_file,
                        'output': output_file,
                        'status': 'success'
                    })
                    if self.debug:
                        progress_bar.write(f"  ✅ Success: {os.path.basename(output_file)}")
                else:
                    results['failed'] += 1
                    results['failed_files'].append({
                        'input': input_file,
                        'output': output_file,
                        'error': 'Processing failed - moved to failed folder'
                    })
                    if self.debug:
                        progress_bar.write(f"  ❌ Failed: {file_name}")
                    
                    # 失敗したファイルは既に failed フォルダに移動されているため、
                    # outputディレクトリには作成されない
                    
                    if not skip_errors:
                        progress_bar.write(f"Stopping batch processing due to error in: {file_name}")
                        break
                        
            except Exception as e:
                results['failed'] += 1
                results['failed_files'].append({
                    'input': input_file,
                    'output': '',
                    'error': str(e)
                })
                progress_bar.write(f"  ❌ Error processing {file_name}: {e}")
                
                # バッチ処理での例外も失敗フォルダに移動
                try:
                    self._move_to_failed_folder(input_file, f"Batch processing error: {str(e)}", output_directory)
                except Exception as move_error:
                    if self.debug:
                        progress_bar.write(f"Could not move failed file in batch processing: {move_error}")
                
                if not skip_errors:
                    progress_bar.write(f"Stopping batch processing due to error in: {file_name}")
                    break
        
        # 処理結果のサマリー
        print(f"\n{'='*60}")
        print(f"BATCH PROCESSING SUMMARY")
        print(f"{'='*60}")
        print(f"Total files found: {results['total_files']}")
        print(f"Successfully processed: {results['successful']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped (already processed): {results['skipped']}")
        
        if results['successful'] > 0:
            print(f"\n✅ Successfully processed files:")
            for item in results['processed_files']:
                print(f"  {os.path.basename(item['input'])} → {os.path.basename(item['output'])}")
        
        if results['failed_files']:
            print(f"\n❌ Failed files:")
            for item in results['failed_files']:
                print(f"  {os.path.basename(item['input'])}: {item['error']}")
        
        if results['skipped_files']:
            print(f"\n⚠ Skipped files:")
            for item in results['skipped_files']:
                print(f"  {os.path.basename(item['input'])}: {item['reason']}")
        
        print(f"{'='*60}")
        
        return results
    
    def _filter_unprocessed_files(self, video_files: List[str], output_directory: str) -> List[str]:
        """処理済みファイルを除外して、未処理のファイルのみを返す
        
        Args:
            video_files: 入力ファイルのリスト
            output_directory: 出力ディレクトリのパス
            
        Returns:
            未処理のファイルのリスト
        """
        unprocessed_files = []
        
        for input_file in video_files:
            base_name = Path(input_file).stem
            
            # 複数の出力ファイル名パターンをチェック
            output_patterns = [
                os.path.join(output_directory, f"{base_name}_enhanced.mp4"),
                os.path.join(output_directory, f"{base_name}_processed.mp4"), 
                os.path.join(output_directory, f"{base_name}_modified.mp4"),
                os.path.join(output_directory, f"{base_name}.mp4"),
                os.path.join(output_directory, "failed", f"{base_name}.mp4"),
                os.path.join(output_directory, "failed", f"{base_name}_1.mp4"),
                os.path.join(output_directory, "failed", f"{base_name}_2.mp4"),
                os.path.join(output_directory, "failed", f"{base_name}_3.mp4")
            ]
            
            # いずれかのパターンで処理済みファイルが存在するかチェック
            already_processed = any(os.path.exists(pattern) for pattern in output_patterns)
            
            if not already_processed:
                unprocessed_files.append(input_file)
            elif self.debug:
                print(f"Skipping already processed file: {os.path.basename(input_file)}")
        
        return unprocessed_files
    
    def _process_batch_parallel(self, video_files: List[str], output_directory: str,
                               location: Optional[str], skip_errors: bool,
                               max_workers: int, use_threading: bool,
                               path_generator, results: Dict[str, Any]) -> Dict[str, Any]:
        """並列バッチ処理"""
        if self.debug:
            print(f"Starting parallel batch processing with {max_workers} workers")
        
        # 実行器の選択
        executor_class = ThreadPoolExecutor if use_threading else ProcessPoolExecutor
        
        try:
            with executor_class(max_workers=max_workers) as executor:
                # 処理タスクを作成
                future_to_file = {}
                
                # プログレスバー用の設定
                progress_bar = tqdm(total=len(video_files), desc="Submitting tasks", unit="task")
                
                for input_file in video_files:
                    progress_bar.set_description(f"Submitting: {os.path.basename(input_file)[:20]}")
                    # 出力ファイルパスを生成
                    try:
                        if path_generator:
                            if output_directory == os.path.dirname(input_file):
                                output_file = path_generator.generate_output_path(input_file)
                            else:
                                base_name = Path(input_file).stem
                                output_file = os.path.join(output_directory, f"{base_name}_enhanced.mp4")
                        else:
                            base_name = Path(input_file).stem
                            if output_directory == os.path.dirname(input_file):
                                output_file = os.path.join(output_directory, f"{base_name}_enhanced.mp4")
                            else:
                                output_file = os.path.join(output_directory, f"{base_name}.mp4")
                    
                        # 既存ファイルのスキップチェック（拡張版）
                        base_name = Path(input_file).stem
                        existing_patterns = [
                            os.path.join(output_directory, f"{base_name}_enhanced.mp4"),
                            os.path.join(output_directory, f"{base_name}_enhanced_001.mp4"),
                            os.path.join(output_directory, f"{base_name}_enhanced_002.mp4"),
                            os.path.join(output_directory, f"{base_name}_enhanced_003.mp4")
                        ]
                        
                        existing_file = None
                        for pattern in existing_patterns:
                            if os.path.exists(pattern):
                                existing_file = pattern
                                break
                        
                        if existing_file:
                            results['skipped_files'].append({
                                'input': input_file,
                                'output': existing_file,
                                'reason': 'Output file already exists'
                            })
                            continue
                        
                        # 並列処理タスクを投入
                        if use_threading:
                            # スレッドプール: 同一プロセス内でのOCRリーダー共有
                            future = executor.submit(self._process_single_file_thread_safe, 
                                                    input_file, output_file, location)
                        else:
                            # プロセスプール: 各プロセスで独立したリーダー初期化
                            future = executor.submit(process_single_video_worker, 
                                                    input_file, output_file, location, 
                                                    self.languages, self.use_gpu, self.debug)
                        
                        future_to_file[future] = (input_file, output_file)
                        progress_bar.update(1)
                        
                    except Exception as e:
                        results['failed'] += 1
                        results['failed_files'].append({
                            'input': input_file,
                            'output': '',
                            'error': f'Path generation error: {str(e)}'
                        })
                        progress_bar.update(1)
                
                progress_bar.close()
                
                # 結果を収集
                completed = 0
                total_tasks = len(future_to_file)
                
                # 処理用のプログレスバー
                processing_bar = tqdm(total=total_tasks, desc="Processing videos", unit="file")
                
                for future in as_completed(future_to_file):
                    input_file, output_file = future_to_file[future]
                    file_name = os.path.basename(input_file)
                    completed += 1
                    
                    processing_bar.set_description(f"Completed: {file_name[:25]}")
                    processing_bar.update(1)
                    
                    try:
                        success = future.result()
                        
                        if success:
                            results['successful'] += 1
                            results['processed_files'].append({
                                'input': input_file,
                                'output': output_file,
                                'status': 'success'
                            })
                            if self.debug:
                                processing_bar.write(f"[{completed}/{total_tasks}] ✅ Success: {file_name}")
                        else:
                            results['failed'] += 1
                            results['failed_files'].append({
                                'input': input_file,
                                'output': output_file,
                                'error': 'Processing failed - moved to failed folder'
                            })
                            if self.debug:
                                processing_bar.write(f"[{completed}/{total_tasks}] ❌ Failed: {file_name}")
                            
                            if not skip_errors:
                                # 残りのタスクをキャンセル
                                for remaining_future in future_to_file:
                                    if not remaining_future.done():
                                        remaining_future.cancel()
                                break
                                
                    except Exception as e:
                        results['failed'] += 1
                        results['failed_files'].append({
                            'input': input_file,
                            'output': output_file,
                            'error': str(e)
                        })
                        processing_bar.write(f"[{completed}/{total_tasks}] ❌ Error: {file_name} - {e}")
                        
                        if not skip_errors:
                            break
                
                processing_bar.close()
                            
        except Exception as e:
            print(f"❌ Parallel processing error: {e}")
            # フォールバックとして逐次処理を試行
            print("Falling back to sequential processing...")
            return self._process_batch_sequential(
                video_files, output_directory, location, skip_errors, 
                path_generator, results
            )
        
        # 処理結果のサマリー（既存のコードと同じ）
        print(f"\n{'='*60}")
        print(f"PARALLEL BATCH PROCESSING SUMMARY")
        print(f"{'='*60}")
        print(f"Total files found: {results['total_files']}")
        print(f"Successfully processed: {results['successful']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped (already processed): {results['skipped']}")
        
        if results['successful'] > 0:
            print(f"\n✅ Successfully processed files:")
            for item in results['processed_files']:
                print(f"  {os.path.basename(item['input'])} → {os.path.basename(item['output'])}")
        
        if results['failed_files']:
            print(f"\n❌ Failed files:")
            for item in results['failed_files']:
                print(f"  {os.path.basename(item['input'])}: {item['error']}")
        
        if results['skipped_files']:
            print(f"\n⚠ Skipped files:")
            for item in results['skipped_files']:
                print(f"  {os.path.basename(item['input'])}: {item['reason']}")
        
        print(f"{'='*60}")
        
        return results
    
    def _process_single_file_thread_safe(self, input_path: str, output_path: str, 
                                        location: Optional[str] = None) -> bool:
        """スレッドセーフな単一ファイル処理（OCRリーダー共有）"""
        try:
            return self.process_video(input_path, output_path, location)
        except Exception as e:
            if self.debug:
                print(f"Thread processing error for {input_path}: {e}")
            return False
    
    def _move_to_failed_folder(self, input_path: str, reason: str = "Unknown error", output_dir: Optional[str] = None) -> None:
        """ファイルを失敗フォルダにコピー
        
        Args:
            input_path: コピーするファイルのパス
            reason: 失敗理由
            output_dir: 出力ディレクトリ（指定されない場合は入力ファイルと同じディレクトリを使用）
        """
        try:
            import shutil
            
            # 失敗フォルダのパスを生成
            if output_dir and os.path.exists(output_dir):
                # 出力ディレクトリが指定されている場合はそこにfailedフォルダを作成
                failed_dir = os.path.join(output_dir, "failed")
            else:
                # 出力ディレクトリが指定されていない場合は入力ファイルと同じディレクトリ
                input_dir = os.path.dirname(input_path)
                failed_dir = os.path.join(input_dir, "failed")
            
            # 失敗フォルダが存在しない場合は作成
            os.makedirs(failed_dir, exist_ok=True)
            
            # ファイル名を取得
            filename = os.path.basename(input_path)
            failed_path = os.path.join(failed_dir, filename)
            
            # 同名ファイルが既にある場合は番号を付ける
            counter = 1
            base_name, ext = os.path.splitext(filename)
            while os.path.exists(failed_path):
                failed_path = os.path.join(failed_dir, f"{base_name}_{counter}{ext}")
                counter += 1
            
            # ファイルをコピー（移動ではなく）
            shutil.copy2(input_path, failed_path)
            
            if self.debug:
                print(f"Copied failed file to: {failed_path}")
                print(f"Reason: {reason}")
            else:
                print(f"❌ Copied to failed folder: {filename} (Reason: {reason})")
                
        except Exception as e:
            if self.debug:
                print(f"Failed to copy file to failed folder: {e}")
            else:
                print(f"⚠ Could not copy file to failed folder: {e}")
    
    def process_video(self, input_path: str, output_path: str, 
                     location: Optional[str] = None) -> bool:
        """メイン処理
        
        Args:
            input_path: 入力映像ファイルのパス
            output_path: 出力映像ファイルのパス
            location: 設定する場所情報
            
        Returns:
            処理成功時True、失敗時False
        """
        print(f"Processing: {input_path}")
        
        try:
            # 1フレーム目を抽出
            frame = self.extract_first_frame(input_path)
            print("✓ First frame extracted")
            
            # 日時領域をクロップ
            cropped = self.crop_timestamp_area(frame)
            print("✓ Timestamp area cropped")
            
            # OCRで日時を抽出
            timestamp_str = self.extract_timestamp(cropped)
            if timestamp_str:
                print(f"✓ Timestamp detected: {timestamp_str}")
            else:
                print("⚠ No timestamp detected")
            
            # 日時をパース
            timestamp = self.parse_timestamp(timestamp_str)
            if timestamp:
                print(f"✓ Timestamp parsed: {timestamp}")
            else:
                print("⚠ Failed to parse timestamp")
                # 完全なタイムスタンプが得られない場合は失敗として処理
                output_dir = os.path.dirname(output_path) if output_path else None
                self._move_to_failed_folder(input_path, "Incomplete timestamp information", output_dir)
                return False
            
            # EXIF情報を追加して出力
            success = self.add_exif_data(input_path, output_path, timestamp, location)
            
            if success:
                print(f"✓ Video processed successfully: {output_path}")
            else:
                print("✗ Failed to process video")
                # EXIF処理に失敗した場合も失敗フォルダに移動
                output_dir = os.path.dirname(output_path) if output_path else None
                self._move_to_failed_folder(input_path, "EXIF processing failed", output_dir)
            
            return success
            
        except Exception as e:
            print(f"✗ Error during video processing: {e}")
            # 例外が発生した場合も失敗フォルダに移動
            output_dir = os.path.dirname(output_path) if output_path else None
            self._move_to_failed_folder(input_path, f"Processing error: {str(e)}", output_dir)
            return False


def process_single_video_worker(input_path: str, output_path: str, location: Optional[str],
                               languages: List[str], use_gpu: bool, debug: bool) -> bool:
    """並列処理用のワーカー関数（プロセスプール用）
    
    Args:
        input_path: 入力映像ファイルのパス
        output_path: 出力映像ファイルのパス
        location: 設定する場所情報
        languages: OCR言語リスト
        use_gpu: GPU使用フラグ
        debug: デバッグモード
        
    Returns:
        処理成功時True
    """
    try:
        # 各ワーカープロセスで独立したEnhancerインスタンスを作成
        enhancer = XiaomiVideoEXIFEnhancer(debug=debug, languages=languages, use_gpu=use_gpu)
        return enhancer.process_video(input_path, output_path, location)
    except Exception as e:
        if debug:
            print(f"Worker process error for {input_path}: {e}")
        return False


def validate_video_file(file_path: str) -> bool:
    """動画ファイルの妥当性チェック
    
    Args:
        file_path: チェックするファイルパス
        
    Returns:
        有効な動画ファイルの場合True
    """
    if not os.path.exists(file_path):
        return False
    
    # ファイルサイズをチェック（空ファイルでないか）
    if os.path.getsize(file_path) == 0:
        return False
    
    # 拡張子をチェック
    valid_extensions = {
        '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', 
        '.m4v', '.3gp', '.3g2', '.mpg', '.mpeg', '.m2v', '.mts', 
        '.m2ts', '.ts', '.vob', '.f4v', '.f4p', '.f4a', '.f4b'
    }
    
    file_extension = Path(file_path).suffix.lower()
    return file_extension in valid_extensions


def validate_output_path(output_path: str) -> bool:
    """出力パスの妥当性チェック
    
    Args:
        output_path: チェックする出力パス
        
    Returns:
        有効な出力パスの場合True
    """
    output_dir = Path(output_path).parent
    
    # 出力ディレクトリが書き込み可能かチェック
    if output_dir.exists() and not os.access(output_dir, os.W_OK):
        return False
    
    # 既存ファイルが存在する場合、上書き可能かチェック
    if os.path.exists(output_path) and not os.access(output_path, os.W_OK):
        return False
    
    return True


def main() -> None:
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='Xiaomi Video EXIF Enhancer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single file processing:
    %(prog)s input.mp4
    %(prog)s input.mp4 --location "リビング"
    %(prog)s input.mp4 --output enhanced.mp4 --location "寝室"
  
  Batch processing:
    %(prog)s --batch /path/to/videos/
    %(prog)s --batch /path/to/videos/ --output-dir /path/to/output/
    %(prog)s --batch /path/to/videos/ --location "リビング" --no-skip-errors
        """
    )
    
    # 入力方式の選択
    parser.add_argument('input', nargs='?', help='Input video file path (for single file processing)')
    parser.add_argument('--batch', metavar='DIR', help='Input directory path (for batch processing)')
    
    # 出力オプション
    parser.add_argument('-o', '--output', help='Output video file path (single file) or output directory (batch)')
    parser.add_argument('--output-dir', help='Output directory for batch processing (alternative to --output)')
    
    # 処理オプション
    parser.add_argument('-l', '--location', help='Location to add to EXIF')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    # バッチ処理専用オプション
    parser.add_argument('--no-skip-errors', action='store_true', 
                       help='Stop batch processing on first error (default: skip errors and continue)')
    parser.add_argument('--extensions', nargs='*', default=['mp4', 'MP4'], 
                       help='Video file extensions to process in batch mode (default: mp4 MP4)')
    
    # 並列処理オプション
    parser.add_argument('--max-workers', type=int, 
                       help='Maximum number of parallel workers (default: auto-detect)')
    parser.add_argument('--disable-parallel', action='store_true',
                       help='Disable parallel processing (force sequential)')
    parser.add_argument('--use-threading', action='store_true',
                       help='Use threading instead of multiprocessing for parallel execution')
    parser.add_argument('--batch-size', type=int,
                       help='Maximum number of files to process in one batch (prevents memory issues)')
    parser.add_argument('--gpu', action='store_true',
                       help='Enable GPU acceleration for OCR (requires CUDA)')
    
    args = parser.parse_args()
    
    # 入力方式の妥当性チェック
    if args.batch and args.input:
        print("Error: Cannot specify both input file and --batch directory")
        parser.print_help()
        sys.exit(1)
    elif not args.batch and not args.input:
        print("Error: Must specify either input file or --batch directory")
        parser.print_help()
        sys.exit(1)
    
    try:
        # 処理実行
        enhancer = XiaomiVideoEXIFEnhancer(debug=args.debug, use_gpu=args.gpu)
        
        if args.batch:
            # バッチ処理モード
            print(f"Starting batch processing mode")
            print(f"Input directory: {args.batch}")
            
            # 出力ディレクトリの決定
            output_dir = args.output_dir or args.output
            if output_dir:
                print(f"Output directory: {output_dir}")
            else:
                print(f"Output directory: {args.batch} (same as input)")
            
            # バッチ処理設定
            skip_errors = not args.no_skip_errors
            if args.disable_parallel:
                max_workers = 1  # 並列処理を無効化（実質的にシーケンシャル処理）
            else:
                max_workers = args.max_workers
            use_threading = args.use_threading
            
            if args.debug:
                print(f"Skip errors: {skip_errors}")
                print(f"Extensions: {args.extensions}")
                print(f"Location: {args.location or 'Not specified'}")
                if not args.disable_parallel:
                    print(f"Parallel processing: Enabled")
                    print(f"Max workers: {max_workers or 'Auto-detect'}")
                    print(f"Executor type: {'Threading' if use_threading else 'Multiprocessing'}")
                else:
                    print(f"Parallel processing: Disabled")
            
            # バッチ処理を実行
            results = enhancer.process_batch(
                input_directory=args.batch,
                output_directory=output_dir,
                location=args.location,
                skip_errors=skip_errors,
                max_workers=max_workers,
                use_threading=use_threading,
                batch_size=args.batch_size
            )
            
            # 結果に基づいて終了コードを決定
            if results['total_files'] == 0:
                print("No video files found to process")
                sys.exit(1)
            elif results['failed'] > 0 and not skip_errors:
                sys.exit(1)
            elif results['successful'] == 0:
                print("No files were successfully processed")
                sys.exit(1)
            else:
                sys.exit(0)
                
        else:
            # シングルファイル処理モード
            if not args.input:
                print("Error: Input file path is required for single file processing")
                parser.print_help()
                sys.exit(1)
            
            # 入力ファイルの妥当性チェック
            if not validate_video_file(args.input):
                if not os.path.exists(args.input):
                    print(f"Error: Input file not found: {args.input}")
                elif os.path.getsize(args.input) == 0:
                    print(f"Error: Input file is empty: {args.input}")
                else:
                    print(f"Error: Invalid video file format: {args.input}")
                sys.exit(1)
            
            # 出力パス生成器を初期化
            try:
                from output_path_generator import OutputPathGenerator
                path_generator = OutputPathGenerator(debug=args.debug)
                
                # 出力パスの設定・生成
                if not args.output:
                    try:
                        args.output = path_generator.generate_output_path(args.input)
                        if args.debug:
                            print(f"Auto-generated output path: {args.output}")
                    except Exception as e:
                        print(f"Error: Failed to generate output path: {e}")
                        sys.exit(1)
                
                # 出力パスの妥当性チェック
                is_valid, issues = path_generator.validate_output_path(args.output)
                if not is_valid:
                    print("Error: Output path validation failed:")
                    for issue in issues:
                        print(f"  - {issue}")
                    
                    # 代替パスの提案
                    alternatives = path_generator.suggest_alternative_paths(args.input, count=3)
                    if alternatives:
                        print("\n💡 Suggested alternative paths:")
                        for i, alt in enumerate(alternatives, 1):
                            print(f"  {i}. {alt}")
                    sys.exit(1)
                    
            except ImportError:
                # OutputPathGeneratorが利用できない場合
                if not args.output:
                    from pathlib import Path
                    base_name = Path(args.input).stem
                    args.output = f"{base_name}_enhanced.mp4"
                    if args.debug:
                        print(f"Simple auto-generated output path: {args.output}")
            
            # デバッグ情報の出力
            if args.debug:
                print(f"Single file processing mode")
                print(f"Input file: {args.input}")
                print(f"Output file: {args.output}")
                print(f"Location: {args.location or 'Not specified'}")
                print(f"File size: {os.path.getsize(args.input)} bytes")
            
            # シングルファイル処理を実行
            success = enhancer.process_video(args.input, args.output, args.location)
            sys.exit(0 if success else 1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
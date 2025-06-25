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
from datetime import datetime
import re
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
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


class XiaomiVideoEXIFEnhancer:
    """Xiaomiホームカメラ映像のEXIF情報を拡張するクラス"""
    
    def __init__(self, debug: bool = False, languages: List[str] = None) -> None:
        """初期化処理
        
        Args:
            debug: デバッグモードの有効/無効
            languages: OCRで使用する言語リスト（デフォルト: ['en', 'ja']）
        """
        self.debug = debug
        self.languages = languages or ['en', 'ja']
        self.confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD
        
        # 映像エラーハンドラーを初期化
        self.error_handler = VideoErrorHandler(debug=debug)
        
        # 出力パス生成器を初期化
        self.path_generator = OutputPathGenerator(debug=debug)
        
        try:
            if debug:
                print(f"Initializing EasyOCR reader with languages: {self.languages}")
            
            start_time = time.time()
            self.reader = easyocr.Reader(self.languages)
            init_time = time.time() - start_time
            
            if debug:
                print(f"EasyOCR reader initialized successfully in {init_time:.2f} seconds")
        except Exception as e:
            if debug:
                print(f"Failed to initialize EasyOCR reader: {e}")
            raise RuntimeError(f"Failed to initialize EasyOCR reader: {e}")
    
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
    
    def crop_timestamp_area(self, frame: np.ndarray, crop_ratio: Optional[float] = None) -> np.ndarray:
        """左上の日時領域をクロップ（適応的または固定比率）
        
        Args:
            frame: 入力フレーム
            crop_ratio: クロップ比率（0.1-1.0、Noneの場合は適応的に決定）
            
        Returns:
            クロップされた画像
            
        Raises:
            ValueError: 無効なフレーム形式または比率の場合
        """
        if len(frame.shape) != 3:
            raise ValueError(f"Invalid frame format: expected 3D array, got shape {frame.shape}")
        
        # 適応的クロップ比率の決定
        if crop_ratio is None:
            crop_ratio = self.get_optimal_crop_ratio(frame)
            if self.debug:
                print(f"Using adaptive crop ratio: {crop_ratio}")
        
        if not 0.1 <= crop_ratio <= 1.0:
            raise ValueError(f"Invalid crop_ratio: {crop_ratio}, must be between 0.1 and 1.0")
        
        height, width = frame.shape[:2]
        crop_height = int(height * crop_ratio)
        crop_width = int(width * crop_ratio)
        
        if self.debug:
            print(f"Cropping timestamp area: {width}x{height} -> {crop_width}x{crop_height} (ratio: {crop_ratio})")
        
        cropped = frame[0:crop_height, 0:crop_width]
        
        if self.debug:
            print(f"Cropped area shape: {cropped.shape}")
        
        return cropped
    
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
                    dt = datetime(int(year), int(month), int(day), 
                                int(hour), int(minute), int(second))
                    if self.debug:
                        print(f"Timestamp parsed successfully: {dt}")
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
                print(f"Timestamp: {timestamp} -> {timestamp.isoformat() + 'Z'}")
            if location:
                print(f"Location: {location}")
        
        # メタデータ辞書の構築
        metadata = {}
        
        # Issue #9: 作成日時のEXIF情報への埋め込み
        if timestamp:
            # ISO 8601形式でのタイムスタンプ設定
            creation_time = timestamp.isoformat() + 'Z'
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
            
            (
                ffmpeg
                .input(video_path)
                .output(output_path, **{'metadata': metadata})
                .overwrite_output()
                .run(quiet=not self.debug)
            )
            
            if self.debug:
                print("✓ FFmpeg processing completed successfully")
                
                # 埋め込み結果の検証
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
            
            # EXIF情報を追加して出力
            success = self.add_exif_data(input_path, output_path, timestamp, location)
            
            if success:
                print(f"✓ Video processed successfully: {output_path}")
            else:
                print("✗ Failed to process video")
            
            return success
            
        except Exception as e:
            print(f"✗ Error during video processing: {e}")
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
  %(prog)s input.mp4
  %(prog)s input.mp4 --location "リビング"
  %(prog)s input.mp4 --output enhanced.mp4 --location "寝室"
        """
    )
    
    parser.add_argument('input', help='Input video file path')
    parser.add_argument('-o', '--output', help='Output video file path')
    parser.add_argument('-l', '--location', help='Location to add to EXIF')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
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
    
    # デバッグ情報の出力
    if args.debug:
        print(f"Input file: {args.input}")
        print(f"Output file: {args.output}")
        print(f"Location: {args.location or 'Not specified'}")
        print(f"File size: {os.path.getsize(args.input)} bytes")
    
    try:
        # 処理実行
        enhancer = XiaomiVideoEXIFEnhancer(debug=args.debug)
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
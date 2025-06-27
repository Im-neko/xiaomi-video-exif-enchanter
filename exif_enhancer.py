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
    # @記号付きドット区切り形式: @ 2025/05/28 19.41.14
    r'@?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:.](\d{2})[:.](\d{2})',
    # 標準的なドット区切り形式: 2024.12.28 15.30.45
    r'(\d{4})\.(\d{1,2})\.(\d{1,2})\s+(\d{1,2})\.(\d{2})\.(\d{2})',
    # コロン区切り形式: 2024/12/28 15:30:45
    r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})',
    # スペース無し形式: 20241228153045
    r'(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})',
    # ハイフン区切り形式: 2024-12-28 15:30:45
    r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})',
    # 日本語混在形式: 2024年12月28日 15時30分45秒
    r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})時(\d{2})分(\d{2})秒',
    # AM/PM形式: 2024/12/28 3:30:45 PM
    r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)',
    # ISO形式: 2024-12-28T15:30:45
    r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})'
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


class XiaomiVideoExifEnhancer:
    """Xiaomi動画のEXIF情報を拡張するメインクラス"""
    
    def __init__(self, debug: bool = False, languages: List[str] = None, use_gpu: bool = None) -> None:
        """
        Args:
            debug: デバッグモードの有効化
            languages: OCRで使用する言語リスト
            use_gpu: GPU使用フラグ
        """
        self.debug = debug
        self.languages = languages if languages else ['en', 'ja']
        self.use_gpu = use_gpu if use_gpu is not None else False
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
            cv2.imwrite(filename, frame)
            if self.debug:
                print(f"Debug frame saved: {filename}")
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
        - 左上: (0, 0)
        - 右上: (1/4*width, 0)  
        - 左下: (0, 3/68*height)
        - 右下: (1/4*width, 3/68*height)
        """
        height, width = frame.shape[:2]
        
        # 指定された座標を計算
        x_start = 0
        y_start = 0
        x_end = int(width // 4)  # 1/4 * width
        y_end = int(3 * height // 68)  # 3/68 * height
        
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
            cv2.imwrite(filename, cropped_frame)
            if self.debug:
                print(f"Cropped area saved: {filename}")
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
    
    def extract_timestamp(self, cropped_frame: np.ndarray) -> Optional[str]:
        """クロップされたフレームからタイムスタンプを抽出"""
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
    
    def test_ocr_performance(self, cropped_frame: np.ndarray, iterations: int = 5) -> Dict[str, float]:
        """OCR性能をテスト"""
        times = []
        
        for _ in range(iterations):
            start_time = time.time()
            self.extract_timestamp(cropped_frame)
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
        
        # 各パターンで解析を試行
        for i, pattern in enumerate(TIMESTAMP_PATTERNS):
            match = re.search(pattern, timestamp_str)
            if match:
                try:
                    groups = match.groups()
                    
                    if i == 6:  # AM/PM形式
                        year, month, day, hour, minute, second, period = groups
                        hour = int(hour)
                        if period.upper() == 'PM' and hour != 12:
                            hour += 12
                        elif period.upper() == 'AM' and hour == 12:
                            hour = 0
                    else:
                        year, month, day, hour, minute, second = groups[:6]
                        hour = int(hour)
                    
                    dt = datetime(
                        year=int(year),
                        month=int(month),
                        day=int(day),
                        hour=hour,
                        minute=int(minute),
                        second=int(second),
                        tzinfo=timezone(timedelta(hours=9))  # JST
                    )
                    
                    if self.debug:
                        print(f"Parsed timestamp: {dt} from '{timestamp_str}' using pattern {i}")
                    
                    return dt
                    
                except (ValueError, TypeError) as e:
                    if self.debug:
                        print(f"Failed to parse with pattern {i}: {e}")
                    continue
        
        if self.debug:
            print(f"Could not parse timestamp: '{timestamp_str}'")
        return None
    
    def add_exif_data(self, video_path: str, output_path: str, 
                     creation_time: Optional[datetime] = None) -> bool:
        """動画ファイルにEXIFデータを追加"""
        try:
            import ffmpeg
            
            # メタデータの準備
            metadata = {}
            
            if creation_time:
                # ISO 8601形式でタイムスタンプを設定
                iso_timestamp = creation_time.isoformat()
                metadata['creation_time'] = iso_timestamp
                metadata['date'] = creation_time.strftime('%Y-%m-%d %H:%M:%S')
                
                if self.debug:
                    print(f"Setting creation time: {iso_timestamp}")
            
            # 追加のメタデータ
            metadata['comment'] = 'Enhanced by Xiaomi Video EXIF Enhancer'
            metadata['software'] = 'Xiaomi Video EXIF Enhancer'
            
            # FFmpegでメタデータを埋め込み
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(stream, output_path, vcodec='copy', acodec='copy', **metadata)
            
            # 既存ファイルを上書きするオプションを追加
            ffmpeg.run(stream, overwrite_output=True, quiet=not self.debug)
            
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
            
            if self.debug:
                self.save_cropped_area(cropped_frame, f"crop_{os.path.basename(input_path)}.jpg")
            
            # タイムスタンプを抽出
            timestamp_str = self.extract_timestamp(cropped_frame)
            
            if not timestamp_str:
                error_msg = f"Could not extract timestamp from video: {input_path}"
                print(error_msg)
                if self.error_handler:
                    self.error_handler.log_error(VideoErrorType.OCR_FAILED, input_path, error_msg)
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, "OCR failed", os.path.dirname(output_path))
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
                except Exception as move_error:
                    if self.debug:
                        print(f"Could not move failed file: {move_error}")
            
            return False


def process_single_video_worker(input_path: str, output_path: str, location: Optional[str],
                               languages: List[str], use_gpu: bool, debug: bool) -> bool:
    """並列処理用のワーカー関数（プロセスプール用）"""
    try:
        # 各プロセスで独立したEnhancerインスタンスを作成
        enhancer = XiaomiVideoExifEnhancer(debug=debug, languages=languages, use_gpu=use_gpu)
        
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
    parser.add_argument('--languages', nargs='+', default=['en', 'ja'], help='OCR languages')
    parser.add_argument('--gpu', action='store_true', help='Use GPU for OCR')
    parser.add_argument('--confidence', type=float, default=0.5, help='OCR confidence threshold')
    parser.add_argument('--max-workers', type=int, help='Maximum number of parallel workers')
    parser.add_argument('--use-threading', action='store_true', help='Use threading instead of multiprocessing')
    parser.add_argument('--batch-size', type=int, help='Batch size for processing')
    parser.add_argument('--skip-errors', action='store_true', default=True, help='Skip files with errors')
    
    args = parser.parse_args()
    
    # Enhancerインスタンスを作成
    enhancer = XiaomiVideoExifEnhancer(
        debug=args.debug,
        languages=args.languages,
        use_gpu=args.gpu
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
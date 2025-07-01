#!/usr/bin/env python3
"""
Xiaomi Video EXIF Enhancer - ML Model Version
Xiaomiホームカメラ(C301)で録画された映像のEXIF情報を拡張するツール（ML専用版）
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


class XiaomiVideoExifEnchanterML:
    """Xiaomi動画のEXIF情報を拡張するメインクラス（ML専用版）"""
    
    def __init__(self, debug: bool = False, languages: List[str] = None, use_gpu: bool = None, 
                 model_path: str = "xiaomi_timestamp_model_best.pth", fallback_ocr: bool = True) -> None:
        """
        Args:
            debug: デバッグモードの有効化
            languages: OCRで使用する言語リスト（フォールバック用）
            use_gpu: GPU使用フラグ
            model_path: ML モデルファイルのパス
            fallback_ocr: MLモデル失敗時のOCRフォールバック
        """
        self.debug = debug
        self.languages = languages if languages else ['en', 'ja']
        self.use_gpu = use_gpu if use_gpu is not None else False
        self.model_path = model_path
        self.fallback_ocr = fallback_ocr
        self.confidence_threshold = 0.5
        self.ml_trainer = None
        self.ml_model_loaded = False
        
        # エラーハンドラーの初期化
        try:
            self.error_handler = VideoErrorHandler()
        except Exception as e:
            if self.debug:
                print(f"Warning: Could not initialize VideoErrorHandler: {e}")
            self.error_handler = None
        
        if self.debug:
            print(f"XiaomiVideoExifEnchanter (ML) initialized with model: {self.model_path}")
            print(f"Languages: {self.languages}, GPU: {self.use_gpu}, Fallback OCR: {self.fallback_ocr}")
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """OCR信頼度の閾値を設定"""
        self.confidence_threshold = max(0.0, min(1.0, threshold))
        if self.debug:
            print(f"OCR confidence threshold set to: {self.confidence_threshold}")
    
    def _load_ml_model(self):
        """ML モデルを遅延読み込み"""
        if self.ml_trainer is None and not self.ml_model_loaded:
            try:
                from timestamp_ml_trainer import XiaomiTimestampTrainer
                self.ml_trainer = XiaomiTimestampTrainer(debug=self.debug)
                self.ml_trainer.load_model(self.model_path)
                self.ml_model_loaded = True
                if self.debug:
                    print(f"✅ ML model loaded successfully: {self.model_path}")
                return True
            except Exception as e:
                if self.debug:
                    print(f"❌ Failed to load ML model: {e}")
                self.ml_model_loaded = False
                self.ml_trainer = None
                return False
        return self.ml_trainer is not None
    
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
            cv2.imwrite(filename, frame)
            print(f"Debug frame saved: {filename}")
    
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
            cv2.imwrite(filename, cropped_frame)
            print(f"Cropped area saved: {filename}")
    
    def extract_timestamp(self, cropped_frame: np.ndarray, input_path: str = None) -> Optional[str]:
        """クロップされたフレームからタイムスタンプを抽出（ML専用版）"""
        # ML モデルでタイムスタンプ抽出を試行
        ml_result = self._extract_timestamp_with_ml(cropped_frame)
        if ml_result:
            if self.debug:
                print(f"✅ ML model detected timestamp: {ml_result}")
            return ml_result
        
        # MLモデルが失敗した場合のフォールバック
        if self.fallback_ocr:
            if self.debug:
                print("⚠️ ML model failed, falling back to OCR...")
            return self._fallback_ocr_extract(cropped_frame)
        
        if self.debug:
            print("❌ ML model failed and fallback OCR is disabled")
        return None
    
    def _extract_timestamp_with_ml(self, cropped_frame: np.ndarray) -> Optional[str]:
        """ML モデルを使用してタイムスタンプを抽出"""
        try:
            # MLモデルを読み込み
            if not self._load_ml_model():
                return None
            
            if not self.ml_trainer:
                return None
            
            # 前処理: 画像をグレースケールに変換
            if len(cropped_frame.shape) == 3:
                gray_frame = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2GRAY)
            else:
                gray_frame = cropped_frame
            
            # ML モデルで予測
            predicted_text = self.ml_trainer.predict_timestamp(gray_frame)
            
            if self.debug and predicted_text:
                print(f"🤖 ML model prediction: {predicted_text}")
            
            # 予測結果の検証（タイムスタンプパターンに一致するかチェック）
            if predicted_text:
                for pattern in TIMESTAMP_PATTERNS:
                    if re.search(pattern, predicted_text):
                        return predicted_text
                
                # パターンに一致しない場合でも、数値が多く含まれていれば候補として返す
                digit_count = sum(c.isdigit() for c in predicted_text)
                total_chars = len(predicted_text.replace(' ', ''))
                digit_ratio = digit_count / total_chars if total_chars > 0 else 0
                
                if digit_ratio >= 0.7:
                    if self.debug:
                        print(f"🤖 ML model prediction has high digit ratio: {digit_ratio:.2f}")
                    return predicted_text
            
            return None
            
        except Exception as e:
            if self.debug:
                print(f"❌ ML model prediction failed: {e}")
            return None
    
    def _fallback_ocr_extract(self, cropped_frame: np.ndarray) -> Optional[str]:
        """フォールバックOCR抽出（基本的なEasyOCR）"""
        try:
            reader = EasyOCRSingleton.get_reader(self.languages, self.use_gpu, self.debug)
            results = reader.readtext(cropped_frame)
            
            if self.debug:
                print(f"  Fallback OCR results: {results}")
            
            if not results:
                return None
            
            # 最適な結果を選択
            best_match = None
            best_confidence = 0.0
            
            for bbox, text, confidence in results:
                if confidence < self.confidence_threshold:
                    continue
                
                # タイムスタンプパターンマッチング
                for pattern in TIMESTAMP_PATTERNS:
                    if re.search(pattern, text):
                        if confidence > best_confidence:
                            best_match = text
                            best_confidence = confidence
                        break
                
                # パターンに一致しなくても数値が多い場合は候補とする
                if not best_match:
                    digit_count = sum(c.isdigit() for c in text)
                    total_chars = len(text.replace(' ', ''))
                    digit_ratio = digit_count / total_chars if total_chars > 0 else 0
                    
                    if digit_ratio >= 0.7 and confidence > best_confidence:
                        best_match = text
                        best_confidence = confidence
            
            if self.debug and best_match:
                print(f"  Fallback OCR selected: '{best_match}' with confidence {best_confidence:.3f}")
            
            return best_match
            
        except Exception as e:
            if self.debug:
                print(f"Fallback OCR error: {e}")
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
        """失敗したファイルをfailedフォルダに移動"""
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
            
            # ファイルを移動
            import shutil
            shutil.move(input_path, failed_path)
            
            # 理由をテキストファイルに記録
            reason_file = failed_path.with_suffix(failed_path.suffix + ".error.txt")
            with open(reason_file, 'w', encoding='utf-8') as f:
                f.write(f"Error: {reason}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"ML Model: {self.model_path}\n")
                f.write(f"Fallback OCR: {self.fallback_ocr}\n")
            
            if self.debug:
                print(f"Moved failed file to: {failed_path}")
                print(f"Reason: {reason}")
                
        except Exception as e:
            if self.debug:
                print(f"Failed to move error file: {e}")
    
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
            print(f"Processing video with ML model: {os.path.basename(input_path)}")
        
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
                self.save_debug_frame(frame, f"debug_ml_{os.path.basename(input_path)}.jpg")
            
            # タイムスタンプ領域をクロップ
            cropped_frame = self.crop_timestamp_area(frame)
            
            # クロップした画像のファイル名を生成
            crop_filename = f"crop_ml_{os.path.basename(input_path)}.jpg"
            
            if self.debug:
                self.save_cropped_area(cropped_frame, crop_filename)
            
            # タイムスタンプを抽出（ML優先）
            timestamp_str = self.extract_timestamp(cropped_frame, input_path)
            
            if not timestamp_str:
                error_msg = f"Could not extract timestamp from video (ML): {input_path}"
                print(error_msg)
                if self.error_handler:
                    error_type = VideoErrorType.OCR_FAILED if self.fallback_ocr else VideoErrorType.ML_MODEL_FAILED
                    self.error_handler.log_error(error_type, input_path, error_msg)
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, "ML + OCR failed", os.path.dirname(output_path))
                    # cropした画像もfailedフォルダに保存
                    self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                return False
            
            # タイムスタンプを解析
            creation_time = self.parse_timestamp(timestamp_str)
            
            if not creation_time:
                error_msg = f"Could not parse timestamp '{timestamp_str}' from video (ML): {input_path}"
                print(error_msg)
                if self.error_handler:
                    self.error_handler.log_error(VideoErrorType.TIMESTAMP_PARSE_FAILED, input_path, error_msg)
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, f"Timestamp parse failed: {timestamp_str}", os.path.dirname(output_path))
                    # cropした画像もfailedフォルダに保存
                    self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                return False
            
            if self.debug:
                print(f"Extracted timestamp (ML): {timestamp_str}")
                print(f"Parsed creation time: {creation_time}")
            
            # EXIFデータを追加
            success = self.embed_exif_with_ffmpeg(input_path, output_path, creation_time, location)
            
            if success:
                if self.debug:
                    print(f"Successfully processed (ML): {os.path.basename(input_path)} -> {os.path.basename(output_path)}")
                return True
            else:
                if self.error_handler:
                    # 失敗したファイルを移動
                    self._move_to_failed_folder(input_path, "FFmpeg failed", os.path.dirname(output_path))
                    # cropした画像もfailedフォルダに保存
                    self._save_crop_to_failed_folder(cropped_frame, input_path, os.path.dirname(output_path))
                return False
                
        except Exception as e:
            error_msg = f"Unexpected error processing {input_path} (ML): {str(e)}"
            print(error_msg)
            if self.error_handler:
                self.error_handler.log_error(VideoErrorType.UNKNOWN_ERROR, input_path, error_msg)
                # 失敗したファイルを移動
                self._move_to_failed_folder(input_path, f"Unexpected error: {str(e)}", os.path.dirname(output_path))
            return False
    
    def process_batch(self, input_directory: str, output_directory: str = None, 
                     location: str = None, skip_errors: bool = True, 
                     max_workers: int = None, use_threading: bool = False, 
                     batch_size: int = None) -> Dict[str, Any]:
        """バッチ処理を実行"""
        if self.debug:
            print(f"Starting ML batch processing from: {input_directory}")
        
        try:
            # BatchProcessorを使用
            processor = BatchProcessor(
                enhancer=self,
                debug=self.debug,
                max_workers=max_workers,
                use_threading=use_threading,
                batch_size=batch_size
            )
            
            return processor.process_directory(
                input_directory=input_directory,
                output_directory=output_directory,
                location=location,
                skip_errors=skip_errors
            )
            
        except Exception as e:
            error_msg = f"ML batch processing failed: {str(e)}"
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
    input_path, output_path, location, debug, languages, use_gpu, model_path, fallback_ocr, confidence_threshold = args
    
    try:
        # 各プロセスで新しいenhancerインスタンスを作成
        enhancer = XiaomiVideoExifEnchanterML(
            debug=debug,
            languages=languages,
            use_gpu=use_gpu,
            model_path=model_path,
            fallback_ocr=fallback_ocr
        )
        
        enhancer.set_confidence_threshold(confidence_threshold)
        
        success = enhancer.process_video(input_path, output_path, location)
        
        return success
        
    except Exception as e:
        if debug:
            print(f"Worker process error for {os.path.basename(input_path)}: {e}")
        return False


def main() -> None:
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Xiaomi Video EXIF Enhancer - ML Model Version')
    parser.add_argument('input', help='Input video file or directory')
    parser.add_argument('-o', '--output', help='Output video file or directory')
    parser.add_argument('-l', '--location', help='Location information to add')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--batch', action='store_true', help='Process directory in batch mode')
    parser.add_argument('--languages', nargs='+', default=['en'], help='OCR languages (for fallback)')
    parser.add_argument('--gpu', action='store_true', help='Use GPU for processing')
    parser.add_argument('--confidence', type=float, default=0.5, help='OCR confidence threshold (for fallback)')
    parser.add_argument('--model-path', type=str, default='xiaomi_timestamp_model_best.pth', help='Path to ML model file')
    parser.add_argument('--disable-fallback-ocr', action='store_true', help='Disable OCR fallback when ML fails')
    parser.add_argument('--max-workers', type=int, help='Maximum number of parallel workers')
    parser.add_argument('--use-threading', action='store_true', help='Use threading instead of multiprocessing')
    parser.add_argument('--batch-size', type=int, help='Batch size for processing')
    parser.add_argument('--skip-errors', action='store_true', default=True, help='Skip files with errors')
    
    args = parser.parse_args()
    
    # MLモデルファイルの存在確認
    if not os.path.exists(args.model_path):
        print(f"Error: ML model file not found: {args.model_path}")
        print("Available model files:")
        for model_file in Path(".").glob("*.pth"):
            print(f"  - {model_file}")
        sys.exit(1)
    
    # Enhancerインスタンスを作成
    enhancer = XiaomiVideoExifEnchanterML(
        debug=args.debug,
        languages=args.languages,
        use_gpu=args.gpu,
        model_path=args.model_path,
        fallback_ocr=not args.disable_fallback_ocr
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
            
            print(f"\nML Batch processing completed:")
            print(f"  Total files: {results.get('total', 0)}")
            print(f"  Processed successfully: {results.get('processed', 0)}")
            print(f"  Failed: {results.get('failed', 0)}")
            print(f"  ML Model: {args.model_path}")
            print(f"  Fallback OCR: {not args.disable_fallback_ocr}")
            
            if results.get('failed', 0) > 0:
                print(f"  Failed files moved to: {results.get('failed_directory', 'failed/')}")
            
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
                output_filename = f"{input_path.stem}_ml_enhanced{input_path.suffix}"
                args.output = str(input_path.parent / output_filename)
            
            success = enhancer.process_video(args.input, args.output, args.location)
            
            if success:
                print(f"Successfully processed (ML): {args.input} -> {args.output}")
                print(f"ML Model: {args.model_path}")
            else:
                print(f"Failed to process (ML): {args.input}")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\nML processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected ML processing error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
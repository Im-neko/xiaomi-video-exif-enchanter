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
from pathlib import Path
from typing import Optional, Tuple
import numpy as np


class XiaomiVideoEXIFEnhancer:
    """Xiaomiホームカメラ映像のEXIF情報を拡張するクラス"""
    
    def __init__(self, debug: bool = False) -> None:
        """初期化処理
        
        Args:
            debug: デバッグモードの有効/無効
        """
        self.debug = debug
        try:
            if debug:
                print("Initializing EasyOCR reader...")
            self.reader = easyocr.Reader(['en'])
            if debug:
                print("EasyOCR reader initialized successfully")
        except Exception as e:
            if debug:
                print(f"Failed to initialize EasyOCR reader: {e}")
            raise RuntimeError(f"Failed to initialize EasyOCR reader: {e}")
    
    def extract_first_frame(self, video_path: str) -> np.ndarray:
        """映像の1フレーム目を抽出
        
        Args:
            video_path: 映像ファイルのパス
            
        Returns:
            抽出されたフレーム
            
        Raises:
            ValueError: 映像の読み込みに失敗した場合
        """
        if self.debug:
            print(f"Extracting first frame from: {video_path}")
        cap = cv2.VideoCapture(video_path)
        
        try:
            ret, frame = cap.read()
            if not ret:
                if self.debug:
                    print(f"Failed to read video: {video_path}")
                raise ValueError(f"Failed to read video: {video_path}")
            
            if self.debug:
                print(f"Frame extracted successfully, shape: {frame.shape}")
            return frame
        finally:
            cap.release()
    
    def crop_timestamp_area(self, frame: np.ndarray) -> np.ndarray:
        """左上の日時領域をクロップ
        
        Args:
            frame: 入力フレーム
            
        Returns:
            クロップされた画像
        """
        height, width = frame.shape[:2]
        crop_height = height // 4
        crop_width = width // 4
        cropped = frame[0:crop_height, 0:crop_width]
        return cropped
    
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
            results = self.reader.readtext(cropped_frame)
            timestamp_pattern = r'\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}[:.]\d{2}[:.]\d{2}'
            
            if self.debug:
                print(f"OCR detected {len(results)} text regions")
            
            for (bbox, text, conf) in results:
                if self.debug:
                    print(f"OCR result: '{text}' (confidence: {conf:.2f})")
                if conf > 0.5:
                    if re.search(timestamp_pattern, text):
                        if self.debug:
                            print(f"Timestamp found: {text}")
                        return text
            
            if self.debug:
                print("No valid timestamp found in OCR results")
            return None
        except Exception as e:
            if self.debug:
                print(f"OCR processing failed: {e}")
            return None
    
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
        
        patterns = [
            r'@?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})[:.](\d{2})[:.](\d{2})',
            r'@?\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})',
            r'@?\s*(\d{4})(\d{2})(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})',
        ]
        
        for i, pattern in enumerate(patterns):
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
        """EXIF情報を追加して映像を出力
        
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
            print("Error: ffmpeg-python is not installed")
            return False
        
        metadata = {}
        if timestamp:
            metadata['creation_time'] = timestamp.isoformat() + 'Z'
        if location:
            metadata['location'] = location
        
        try:
            (
                ffmpeg
                .input(video_path)
                .output(output_path, **{'metadata': metadata})
                .overwrite_output()
                .run(quiet=True)
            )
            return True
        except ffmpeg.Error as e:
            print(f"FFmpeg error: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during video processing: {e}")
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
    
    # 出力パスの設定
    if not args.output:
        input_path = Path(args.input)
        args.output = str(input_path.with_stem(f"{input_path.stem}_enhanced"))
    
    # 出力パスの妥当性チェック
    if not validate_output_path(args.output):
        print(f"Error: Cannot write to output path: {args.output}")
        sys.exit(1)
    
    # 出力ディレクトリの存在確認・作成
    output_dir = Path(args.output).parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error: Cannot create output directory: {e}")
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
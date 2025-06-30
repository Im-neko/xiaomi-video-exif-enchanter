#!/usr/bin/env python3
"""
File Manager
ファイル操作とパス生成を統一管理するモジュール
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
import glob


class FileManager:
    """ファイル操作とパス管理の統一クラス"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        
    def get_video_files(self, input_directory: str, pattern: str = "*.mp4") -> List[str]:
        """指定ディレクトリから動画ファイルを取得"""
        search_pattern = os.path.join(input_directory, pattern)
        video_files = glob.glob(search_pattern)
        video_files.sort()  # ファイル名順にソート
        
        if self.debug:
            print(f"Found {len(video_files)} video files in {input_directory}")
            
        return video_files
        
    def filter_unprocessed_files(self, video_files: List[str], output_directory: str) -> List[str]:
        """処理済みファイルを除外して、未処理のファイルのみを返す"""
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
        
    def generate_output_path(self, input_file: str, output_directory: str, 
                           path_generator=None) -> str:
        """出力ファイルパスを生成"""
        try:
            if path_generator:
                if output_directory == os.path.dirname(input_file):
                    return path_generator.generate_output_path(input_file)
                else:
                    base_name = Path(input_file).stem
                    return os.path.join(output_directory, f"{base_name}_enhanced.mp4")
            else:
                base_name = Path(input_file).stem
                if output_directory == os.path.dirname(input_file):
                    return os.path.join(output_directory, f"{base_name}_enhanced.mp4")
                else:
                    return os.path.join(output_directory, f"{base_name}.mp4")
        except Exception as e:
            # フォールバック
            base_name = Path(input_file).stem
            return os.path.join(output_directory, f"{base_name}_enhanced.mp4")
            
    def check_existing_files(self, input_file: str, output_directory: str) -> Optional[str]:
        """既存ファイルの存在をチェック"""
        base_name = Path(input_file).stem
        existing_patterns = [
            os.path.join(output_directory, f"{base_name}_enhanced.mp4"),
            os.path.join(output_directory, f"{base_name}_enhanced_001.mp4"),
            os.path.join(output_directory, f"{base_name}_enhanced_002.mp4"),
            os.path.join(output_directory, f"{base_name}_enhanced_003.mp4")
        ]
        
        for pattern in existing_patterns:
            if os.path.exists(pattern):
                return pattern
        return None
        
    def create_output_directory(self, output_directory: str) -> None:
        """出力ディレクトリを作成"""
        os.makedirs(output_directory, exist_ok=True)
        
        # failed フォルダも作成
        failed_dir = os.path.join(output_directory, "failed")
        os.makedirs(failed_dir, exist_ok=True)
        
    def move_to_failed_folder(self, input_path: str, reason: str = "Unknown error", 
                            output_dir: Optional[str] = None) -> None:
        """失敗したファイルをfailedフォルダに移動"""
        try:
            if output_dir is None:
                output_dir = os.path.dirname(input_path)
                
            failed_dir = os.path.join(output_dir, "failed")
            os.makedirs(failed_dir, exist_ok=True)
            
            # 移動先のファイル名を決定（重複回避）
            base_name = os.path.basename(input_path)
            destination = os.path.join(failed_dir, base_name)
            
            counter = 1
            original_destination = destination
            while os.path.exists(destination):
                name_part, ext = os.path.splitext(base_name)
                destination = os.path.join(failed_dir, f"{name_part}_{counter}{ext}")
                counter += 1
                
            # ファイルを移動
            shutil.move(input_path, destination)
            
            if self.debug:
                print(f"Moved failed file to: {destination}")
                print(f"Reason: {reason}")
                
        except Exception as e:
            if self.debug:
                print(f"Could not move failed file: {e}")
                
    def limit_batch_size(self, unprocessed_files: List[str], batch_size: Optional[int], 
                        max_workers: Optional[int]) -> List[str]:
        """バッチサイズの制限を適用"""
        # 明示的なバッチサイズ制限
        if batch_size is not None and len(unprocessed_files) > batch_size:
            if self.debug:
                print(f"Limiting batch size from {len(unprocessed_files)} to {batch_size} unprocessed files")
            video_files = unprocessed_files[:batch_size]
            print(f"⚠ Processing next {batch_size} unprocessed files out of {len(unprocessed_files)} remaining")
            return video_files
            
        # 自動制限: 1000ファイル以上の場合は警告を表示して制限（並列処理無効時は制限しない）
        elif len(unprocessed_files) > 1000 and max_workers != 1:
            default_limit = 500
            if self.debug:
                print(f"Auto-limiting large batch from {len(unprocessed_files)} to {default_limit} files")
            video_files = unprocessed_files[:default_limit]
            print(f"⚠ Auto-limited to next {default_limit} unprocessed files to prevent memory issues")
            print(f"  Run the command multiple times or use --batch-size to process more files")
            return video_files
        else:
            return unprocessed_files


def validate_video_file(file_path: str) -> bool:
    """動画ファイルの妥当性をチェック"""
    if not os.path.exists(file_path):
        return False
        
    if not file_path.lower().endswith('.mp4'):
        return False
        
    # ファイルサイズチェック（空ファイルでないか）
    if os.path.getsize(file_path) == 0:
        return False
        
    return True


def validate_output_path(output_path: str) -> bool:
    """出力パスの妥当性をチェック"""
    try:
        # ディレクトリが存在するかチェック
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            
        # 書き込み権限をチェック
        return os.access(output_dir, os.W_OK)
    except Exception:
        return False


def create_results_dict(total_files: int, skipped_count: int = 0) -> Dict[str, Any]:
    """処理結果を格納する辞書を作成"""
    return {
        'total_files': total_files,
        'successful': 0,
        'failed': 0,
        'skipped': skipped_count,
        'processed_files': [],
        'failed_files': [],
        'skipped_files': []
    }
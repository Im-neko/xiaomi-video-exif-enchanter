#!/usr/bin/env python3
"""
安全なバッチ処理スクリプト
大量ファイル処理用の設定で実行
"""

import subprocess
import sys
import os
from pathlib import Path

def run_safe_batch_processing(input_dir: str, batch_size: int = 100, location: str = None):
    """
    安全な設定でバッチ処理を実行
    
    Args:
        input_dir: 入力ディレクトリ
        batch_size: バッチサイズ
        location: 場所情報
    """
    
    # 基本コマンド
    cmd = [
        'python3', 'exif_enhancer.py',
        '--batch', input_dir,
        '--batch-size', str(batch_size),
        '--disable-parallel',  # 安全のため並列処理を無効化
        '--debug'
    ]
    
    # 場所情報が指定された場合は追加
    if location:
        cmd.extend(['--location', location])
    
    print(f"Running command: {' '.join(cmd)}")
    print(f"Processing directory: {input_dir}")
    print(f"Batch size: {batch_size}")
    print(f"Location: {location or 'Not specified'}")
    print("-" * 60)
    
    try:
        # バッチ処理を実行
        result = subprocess.run(cmd, check=True)
        print("\n✅ Batch processing completed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Batch processing failed with exit code: {e.returncode}")
        return False
    except KeyboardInterrupt:
        print("\n⚠ Processing cancelled by user")
        return False
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 batch_process_safe.py <input_directory> [batch_size] [location]")
        print("Example: python3 batch_process_safe.py input/ 50 'リビング'")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    location = sys.argv[3] if len(sys.argv) > 3 else None
    
    # 入力ディレクトリの確認
    if not os.path.exists(input_dir):
        print(f"❌ Error: Input directory not found: {input_dir}")
        sys.exit(1)
    
    if not os.path.isdir(input_dir):
        print(f"❌ Error: Not a directory: {input_dir}")
        sys.exit(1)
    
    # ファイル数の確認
    import glob
    video_files = []
    for ext in ['*.mp4', '*.MP4', '*.avi', '*.AVI', '*.mov', '*.MOV']:
        video_files.extend(glob.glob(os.path.join(input_dir, ext)))
    
    print(f"Found {len(video_files)} video files in {input_dir}")
    
    if len(video_files) == 0:
        print("❌ No video files found to process")
        sys.exit(1)
    
    if len(video_files) > batch_size:
        print(f"⚠ Processing will be limited to first {batch_size} files")
        print(f"  Run multiple times to process all {len(video_files)} files")
    
    # 処理実行
    success = run_safe_batch_processing(input_dir, batch_size, location)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
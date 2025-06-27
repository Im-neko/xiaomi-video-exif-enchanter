#!/usr/bin/env python3
"""
Xiaomi固定位置クロップのテストスクリプト
"""

import cv2
import numpy as np
import os
import sys
from pathlib import Path

def test_xiaomi_crop():
    """Xiaomi固定位置クロップをテスト"""
    
    # テスト用にサンプル動画から最初のフレームを抽出
    sample_video = "input/VIDEO_1750580208742.mp4"
    
    if not os.path.exists(sample_video):
        print(f"Sample video not found: {sample_video}")
        # 利用可能な動画ファイルを探す
        input_dir = "input"
        if os.path.exists(input_dir):
            video_files = [f for f in os.listdir(input_dir) if f.endswith('.mp4')]
            if video_files:
                sample_video = os.path.join(input_dir, video_files[0])
                print(f"Using alternative video: {sample_video}")
            else:
                print("No video files found in input directory")
                return False
        else:
            print("Input directory not found")
            return False
    
    try:
        # 動画からフレームを抽出
        cap = cv2.VideoCapture(sample_video)
        if not cap.isOpened():
            print(f"Could not open video: {sample_video}")
            return False
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            print("Could not read frame from video")
            return False
        
        print(f"Original frame size: {frame.shape[1]}x{frame.shape[0]} (WxH)")
        
        # Xiaomi固定位置でクロップ
        height, width = frame.shape[:2]
        
        # 指定された座標を計算
        x_start = 0
        y_start = 0
        x_end = int(width // 4)  # 1/4 * width
        y_end = int(3 * height // 68)  # 3/68 * height
        
        # 座標の境界チェック
        x_end = min(x_end, width)
        y_end = min(y_end, height)
        
        print(f"Crop coordinates: ({x_start}, {y_start}) to ({x_end}, {y_end})")
        print(f"Crop size: {x_end-x_start}x{y_end-y_start}")
        
        # 領域をクロップ
        cropped_frame = frame[y_start:y_end, x_start:x_end]
        
        # デバッグ用に画像を保存
        cv2.imwrite("test_original_frame.jpg", frame)
        cv2.imwrite("test_xiaomi_cropped.jpg", cropped_frame)
        
        print("✅ Xiaomi crop test completed successfully!")
        print("📁 Saved files:")
        print("  - test_original_frame.jpg (original frame)")
        print("  - test_xiaomi_cropped.jpg (cropped timestamp area)")
        
        # クロップされた領域の情報を表示
        print(f"📊 Cropped area stats:")
        print(f"  - Size: {cropped_frame.shape[1]}x{cropped_frame.shape[0]}")
        print(f"  - Position: Top-left corner of frame")
        print(f"  - Coverage: {(x_end-x_start)/width*100:.1f}% width, {(y_end-y_start)/height*100:.1f}% height")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during crop test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_basic_imports():
    """基本的なインポートをテスト"""
    try:
        print("Testing basic imports...")
        
        # 基本的なインポート
        import cv2
        print("✅ OpenCV imported successfully")
        
        import numpy as np
        print("✅ NumPy imported successfully")
        
        # ファイル管理モジュール
        from file_manager import FileManager, validate_video_file
        print("✅ FileManager imported successfully")
        
        # 進行状況管理は tqdm なしでテスト
        try:
            from progress_manager import ProgressManager
            print("⚠ ProgressManager requires tqdm (not installed)")
        except ImportError as e:
            print(f"⚠ ProgressManager import failed: {e}")
        
        # メインクラスのテスト（tqdm関連を除く）
        print("Testing XiaomiVideoExifEnhancer class...")
        
        # tqdm を一時的に無効化してテスト
        sys.modules['tqdm'] = type(sys)('mock_tqdm')
        sys.modules['tqdm'].tqdm = lambda x, **kwargs: x
        
        try:
            from exif_enhancer import XiaomiVideoExifEnhancer
            enhancer = XiaomiVideoExifEnhancer(debug=True)
            print("✅ XiaomiVideoExifEnhancer created successfully")
            
            # OCR言語設定のテスト
            languages = enhancer.get_ocr_languages()
            print(f"✅ OCR languages: {languages}")
            
            return True
        except Exception as e:
            print(f"❌ XiaomiVideoExifEnhancer error: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Testing Xiaomi Video EXIF Enhancer (Refactored)")
    print("=" * 60)
    
    # 基本的なインポートテスト
    import_success = test_basic_imports()
    
    print("\n" + "=" * 60)
    
    # クロップ機能のテスト
    if import_success:
        crop_success = test_xiaomi_crop()
        
        if crop_success:
            print("\n✅ All tests passed!")
            print("📋 Next steps:")
            print("  1. Install tqdm: pip install tqdm")
            print("  2. Test with actual video processing")
        else:
            print("\n⚠ Crop test failed")
    else:
        print("\n❌ Import test failed - cannot proceed with crop test")
    
    print("\n" + "=" * 60)
#!/usr/bin/env python3
"""
シンプルなXiaomi固定位置クロップテスト
"""

import cv2
import numpy as np
import os

def test_xiaomi_crop_simple():
    """シンプルなクロップテスト"""
    
    # 利用可能な動画ファイルを探す
    input_dir = "input"
    sample_video = None
    
    if os.path.exists(input_dir):
        video_files = [f for f in os.listdir(input_dir) if f.endswith('.mp4')]
        if video_files:
            sample_video = os.path.join(input_dir, video_files[0])
            print(f"Using video: {sample_video}")
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
        
        print(f"✅ Original frame size: {frame.shape[1]}x{frame.shape[0]} (WxH)")
        
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
        
        print(f"✅ Crop coordinates: ({x_start}, {y_start}) to ({x_end}, {y_end})")
        print(f"✅ Crop size: {x_end-x_start}x{y_end-y_start}")
        
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
        
        # クロップ領域の妥当性チェック
        if cropped_frame.shape[0] > 0 and cropped_frame.shape[1] > 0:
            print("✅ Cropped frame has valid dimensions")
        else:
            print("❌ Cropped frame has invalid dimensions")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error during crop test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Simple Xiaomi Crop Test")
    print("=" * 40)
    
    success = test_xiaomi_crop_simple()
    
    if success:
        print("\n✅ Crop test passed!")
        print("🔍 Check the generated images to verify timestamp area")
    else:
        print("\n❌ Crop test failed!")
    
    print("=" * 40)
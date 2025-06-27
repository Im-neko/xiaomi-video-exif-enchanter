#!/usr/bin/env python3
"""
低信頼度でのOCRテストスクリプト
"""

import sys
import os
sys.path.append('/app')

from exif_enhancer import XiaomiVideoEXIFEnhancer

def test_low_confidence_processing():
    """低信頼度設定でのテスト"""
    
    # 信頼度を下げた設定でEnhancerを初期化
    enhancer = XiaomiVideoEXIFEnhancer(debug=True, use_gpu=False)
    enhancer.set_confidence_threshold(0.3)  # 信頼度を下げる
    
    input_file = '/app/input/VIDEO_1750580208742.mp4'
    output_file = '/app/output/test_low_confidence.mp4'
    
    print(f"Testing with confidence threshold: {enhancer.confidence_threshold}")
    
    try:
        # フレーム抽出とOCRテスト
        frame = enhancer.extract_first_frame(input_file)
        print(f"Frame extracted: {frame.shape}")
        
        cropped = enhancer.crop_timestamp_area(frame)
        print(f"Cropped area: {cropped.shape}")
        
        # OCRで詳細結果を取得
        ocr_details = enhancer.extract_timestamp_with_details(cropped)
        print("\nOCR詳細結果:")
        print(f"  検出されたテキスト数: {ocr_details['total_detections']}")
        print(f"  有効候補数: {ocr_details['valid_candidates']}")
        print(f"  OCR処理時間: {ocr_details['ocr_time']:.3f}秒")
        
        for i, result in enumerate(ocr_details['all_results']):
            print(f"  結果{i+1}: '{result['text']}' (信頼度: {result['confidence']:.3f})")
        
        if ocr_details['timestamp']:
            print(f"\n✅ 選択されたタイムスタンプ: {ocr_details['timestamp']}")
            print(f"信頼度: {ocr_details['confidence']:.3f}")
            
            # タイムスタンプをパース
            parsed_time = enhancer.parse_timestamp(ocr_details['timestamp'])
            if parsed_time:
                print(f"パース結果: {parsed_time}")
                
                # 完全な処理を実行
                success = enhancer.process_video(input_file, output_file)
                print(f"\n処理結果: {'成功' if success else '失敗'}")
                return success
            else:
                print("タイムスタンプのパースに失敗")
        else:
            print("❌ タイムスタンプが検出されませんでした")
            
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        
    return False

if __name__ == '__main__':
    success = test_low_confidence_processing()
    sys.exit(0 if success else 1)
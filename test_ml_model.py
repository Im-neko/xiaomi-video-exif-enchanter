#!/usr/bin/env python3
"""
Xiaomi Timestamp ML Model Tester
学習済みモデルの実際のテストとOCRとの比較
"""

import os
import cv2
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import subprocess
import random

# Import from the trainer
from timestamp_ml_trainer import XiaomiTimestampTrainer, XiaomiTimestampDataExtractor

class ModelTester:
    """学習済みモデルのテスト用クラス"""
    
    def __init__(self, model_path: str, output_dir: str, debug: bool = True):
        self.model_path = model_path
        self.output_dir = Path(output_dir)
        self.debug = debug
        
        # Load trained CRNN-CTC model
        self.trainer = XiaomiTimestampTrainer(debug=debug)
        self.trainer.load_model(model_path)
        
        # Data extractor for getting test samples
        self.extractor = XiaomiTimestampDataExtractor(output_dir, debug=debug)
        
        if self.debug:
            print(f"✅ Model loaded from: {model_path}")
    
    def extract_timestamp_ocr(self, video_path: str) -> str:
        """既存のOCR実装を使用してタイムスタンプを抽出"""
        try:
            # 既存のexif_enchanter実装を使用
            from exif_enchanter import XiaomiVideoExifEnchanter
            
            enchanter = XiaomiVideoExifEnchanter(debug=False, enhanced_ocr=True)
            
            # 動画の最初のフレームを抽出
            frame = enchanter.extract_first_frame(video_path)
            
            # タイムスタンプ領域をクロップ
            cropped = enchanter.crop_timestamp_area(frame)
            
            # タイムスタンプを抽出
            timestamp = enchanter.extract_timestamp(cropped)
            
            if timestamp and timestamp != "OCR_FAILED":
                return timestamp
            else:
                return "OCR_FAILED"
                
        except Exception as e:
            if self.debug:
                print(f"OCR extraction failed: {e}")
            return "OCR_ERROR"
    
    def test_single_video(self, video_path: Path) -> Dict:
        """単一の動画ファイルでテスト"""
        result = {
            'video_path': str(video_path),
            'actual_timestamp': None,
            'ml_predicted': None,
            'ocr_predicted': None,
            'ml_success': False,
            'ocr_success': False
        }
        
        try:
            # 実際のタイムスタンプを取得
            actual = self.extractor.extract_timestamp_from_filename(video_path)
            if not actual:
                return result
            result['actual_timestamp'] = actual
            
            # フレームからタイムスタンプ領域を抽出
            timestamp_image = self.extractor.extract_frame_timestamp_region(video_path)
            if timestamp_image is None:
                return result
            
            # MLモデルで予測
            try:
                ml_prediction = self.trainer.predict_timestamp(timestamp_image)
                result['ml_predicted'] = ml_prediction
                result['ml_success'] = self.is_timestamp_similar(actual, ml_prediction)
            except Exception as e:
                if self.debug:
                    print(f"ML prediction failed: {e}")
                result['ml_predicted'] = "ML_ERROR"
            
            # OCRで予測（動画ファイルを直接使用）
            try:
                ocr_prediction = self.extract_timestamp_ocr(str(video_path))
                result['ocr_predicted'] = ocr_prediction
                result['ocr_success'] = self.is_timestamp_similar(actual, ocr_prediction)
            except Exception as e:
                if self.debug:
                    print(f"OCR prediction failed: {e}")
                result['ocr_predicted'] = "OCR_ERROR"
            
        except Exception as e:
            if self.debug:
                print(f"Test failed for {video_path}: {e}")
        
        return result
    
    def is_timestamp_similar(self, actual: str, predicted: str, tolerance_minutes: int = 5) -> bool:
        """タイムスタンプが類似しているかチェック（数分の誤差を許容）"""
        try:
            if not actual or not predicted or "ERROR" in predicted or "FAILED" in predicted:
                return False
            
            # 日時形式を統一
            actual_dt = datetime.strptime(actual, '%Y/%m/%d %H:%M:%S')
            
            # 予測結果から数字のみ抽出して日時として解釈を試行
            import re
            numbers = re.findall(r'\d+', predicted)
            if len(numbers) >= 6:
                try:
                    pred_dt = datetime(
                        int(numbers[0]),  # year
                        int(numbers[1]),  # month
                        int(numbers[2]),  # day
                        int(numbers[3]),  # hour
                        int(numbers[4]),  # minute
                        int(numbers[5])   # second
                    )
                    
                    # 時差を計算
                    diff_seconds = abs((actual_dt - pred_dt).total_seconds())
                    return diff_seconds <= tolerance_minutes * 60
                except:
                    pass
            
            # 直接文字列比較も試す
            return actual.replace('/', '').replace(':', '').replace(' ', '') == predicted.replace('/', '').replace(':', '').replace(' ', '')
            
        except Exception as e:
            if self.debug:
                print(f"Timestamp comparison failed: {e}")
            return False
    
    def run_comprehensive_test(self, num_samples: int = 50) -> Dict:
        """包括的なテストを実行"""
        print(f"🧪 Running comprehensive test with {num_samples} samples...")
        
        # テスト用の動画ファイルをランダムに選択
        video_files = list(self.output_dir.glob("*.mp4"))
        if len(video_files) == 0:
            print("❌ No video files found for testing")
            return {}
        
        test_files = random.sample(video_files, min(num_samples, len(video_files)))
        
        results = []
        ml_successes = 0
        ocr_successes = 0
        total_valid_tests = 0
        
        print(f"Testing {len(test_files)} files...")
        
        for i, video_file in enumerate(test_files):
            if self.debug and i % 10 == 0:
                print(f"Progress: {i}/{len(test_files)}")
            
            result = self.test_single_video(video_file)
            
            if result['actual_timestamp']:
                results.append(result)
                total_valid_tests += 1
                
                if result['ml_success']:
                    ml_successes += 1
                if result['ocr_success']:
                    ocr_successes += 1
                
                if self.debug and i < 10:  # Show first 10 detailed results
                    print(f"\n--- Test {i+1} ---")
                    print(f"File: {Path(result['video_path']).name}")
                    print(f"Actual:  {result['actual_timestamp']}")
                    print(f"ML:      {result['ml_predicted']} ({'✅' if result['ml_success'] else '❌'})")
                    print(f"OCR:     {result['ocr_predicted']} ({'✅' if result['ocr_success'] else '❌'})")
        
        # 結果の集計
        ml_accuracy = (ml_successes / total_valid_tests * 100) if total_valid_tests > 0 else 0
        ocr_accuracy = (ocr_successes / total_valid_tests * 100) if total_valid_tests > 0 else 0
        
        summary = {
            'total_tests': total_valid_tests,
            'ml_successes': ml_successes,
            'ocr_successes': ocr_successes,
            'ml_accuracy': ml_accuracy,
            'ocr_accuracy': ocr_accuracy,
            'detailed_results': results
        }
        
        return summary
    
    def print_test_summary(self, summary: Dict):
        """テスト結果のサマリーを表示"""
        print("\n" + "="*60)
        print("🎯 TEST RESULTS SUMMARY")
        print("="*60)
        print(f"Total valid tests: {summary['total_tests']}")
        print(f"ML Model accuracy: {summary['ml_accuracy']:.1f}% ({summary['ml_successes']}/{summary['total_tests']})")
        print(f"OCR accuracy:      {summary['ocr_accuracy']:.1f}% ({summary['ocr_successes']}/{summary['total_tests']})")
        
        improvement = summary['ml_accuracy'] - summary['ocr_accuracy']
        if improvement > 0:
            print(f"🚀 ML Model is {improvement:.1f}% better than OCR!")
        elif improvement < 0:
            print(f"📉 OCR is {abs(improvement):.1f}% better than ML Model")
        else:
            print("🤝 ML Model and OCR have similar accuracy")
        
        print("="*60)
    
    def save_test_results(self, summary: Dict, filename: str = "test_results.json"):
        """テスト結果をJSONファイルに保存"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"📊 Test results saved to: {filename}")

def run_ocr_only_test(output_dir: str):
    """OCRのみのテストを実行"""
    print("🔍 Running OCR-only accuracy test...")
    
    # Data extractor for getting test samples
    extractor = XiaomiTimestampDataExtractor(output_dir, debug=True)
    
    # テスト用の動画ファイルをランダムに選択
    import random
    from pathlib import Path
    
    video_files = list(Path(output_dir).glob("*.mp4"))
    if len(video_files) == 0:
        print("❌ No video files found for testing")
        return
    
    test_files = random.sample(video_files, min(20, len(video_files)))
    
    ocr_successes = 0
    total_valid_tests = 0
    
    print(f"Testing {len(test_files)} files with OCR...")
    
    for i, video_file in enumerate(test_files):
        print(f"Progress: {i+1}/{len(test_files)}")
        
        # 実際のタイムスタンプを取得
        actual = extractor.extract_timestamp_from_filename(video_file)
        if not actual:
            continue
        
        # OCRで予測
        try:
            from exif_enchanter import XiaomiVideoExifEnchanter
            enchanter = XiaomiVideoExifEnchanter(debug=False, enhanced_ocr=True)
            
            # 動画の最初のフレームを抽出
            frame = enchanter.extract_first_frame(str(video_file))
            cropped = enchanter.crop_timestamp_area(frame)
            timestamp = enchanter.extract_timestamp(cropped)
            
            if timestamp and timestamp != "OCR_FAILED":
                ocr_prediction = timestamp
                # 類似性をチェック（簡単な比較）
                if actual.replace('/', '').replace(':', '').replace(' ', '') == ocr_prediction.replace('/', '').replace(':', '').replace(' ', ''):
                    ocr_successes += 1
                    print(f"✅ {Path(video_file).name}: {actual} == {ocr_prediction}")
                else:
                    print(f"❌ {Path(video_file).name}: {actual} != {ocr_prediction}")
            else:
                print(f"❌ {Path(video_file).name}: OCR failed")
                
            total_valid_tests += 1
                
        except Exception as e:
            print(f"❌ Error processing {video_file}: {e}")
    
    # 結果の集計
    ocr_accuracy = (ocr_successes / total_valid_tests * 100) if total_valid_tests > 0 else 0
    
    print("\n" + "="*60)
    print("🎯 OCR-ONLY TEST RESULTS")
    print("="*60)
    print(f"Total valid tests: {total_valid_tests}")
    print(f"OCR accuracy: {ocr_accuracy:.1f}% ({ocr_successes}/{total_valid_tests})")
    print("="*60)

def main():
    """メイン実行関数"""
    model_path = "models/fixed_xiaomi_timestamp_model.pth"
    output_dir = "/mnt/c/Users/micro/apps/xiaomi-video-exif-enchanter/output"
    
    print("🚀 Xiaomi Timestamp ML Model Testing Started")
    
    # モデルファイルの存在確認
    if not os.path.exists(model_path):
        print(f"❌ Model file not found: {model_path}")
        print("Please run timestamp_ml_trainer.py first to create the model.")
        return
    
    # テスター初期化を試行
    try:
        tester = ModelTester(model_path, output_dir, debug=True)
    except RuntimeError as e:
        if "state_dict" in str(e):
            print(f"❌ Model architecture mismatch: {model_path}")
            print("The saved model was trained with a different architecture.")
            print("Please run timestamp_ml_trainer.py to retrain with current architecture.")
            print("Running OCR-only comparison test instead...")
            run_ocr_only_test(output_dir)
            return
        else:
            raise e
    
    # 包括的テスト実行
    summary = tester.run_comprehensive_test(num_samples=30)
    
    if summary:
        # 結果表示
        tester.print_test_summary(summary)
        
        # 結果保存
        tester.save_test_results(summary)
    else:
        print("❌ No test results generated")
    
    print("🎉 Testing completed!")

if __name__ == "__main__":
    main()
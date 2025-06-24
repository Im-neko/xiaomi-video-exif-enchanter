#!/usr/bin/env python3
"""
Xiaomiカメラ映像の実際の統合テストファイル
Issue #16: 実際のXiaomiカメラ映像でのテストを実装
"""

import unittest
import cv2
import numpy as np
import os
import time
from datetime import datetime
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestXiaomiCameraIntegration(unittest.TestCase):
    """実際のXiaomiカメラ映像を使用した統合テスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.sample_video = "sample.mp4"
        self.expected_timestamp = datetime(2025, 5, 28, 19, 41, 14)
        self.expected_frame_shape = (360, 640, 3)
        
        # sample.mp4の存在確認
        if not os.path.exists(self.sample_video):
            self.skipTest(f"Sample video {self.sample_video} not found")
    
    def test_sample_video_properties(self):
        """サンプル動画のプロパティ確認"""
        # ファイル存在確認
        self.assertTrue(os.path.exists(self.sample_video))
        
        # ファイルサイズ確認
        file_size = os.path.getsize(self.sample_video)
        self.assertEqual(file_size, 428364, "Expected file size: 428,364 bytes")
        
        # OpenCVでの読み込み確認
        cap = cv2.VideoCapture(self.sample_video)
        self.assertTrue(cap.isOpened(), "Video should be readable by OpenCV")
        
        # 解像度確認
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.assertEqual((height, width), (360, 640), "Expected resolution: 640x360")
        
        cap.release()
    
    def test_frame_extraction_with_real_video(self):
        """実際の動画からのフレーム抽出テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # フレーム抽出実行
        start_time = time.time()
        frame = enhancer.extract_first_frame(self.sample_video)
        extraction_time = time.time() - start_time
        
        # フレーム検証
        self.assertIsNotNone(frame, "Frame should be extracted")
        self.assertEqual(frame.shape, self.expected_frame_shape, "Frame shape should match expected")
        self.assertEqual(frame.dtype, np.uint8, "Frame should be uint8")
        
        # パフォーマンス検証
        self.assertLess(extraction_time, 1.0, "Frame extraction should be < 1 second")
        
        print(f"Frame extraction time: {extraction_time:.3f}s")
    
    def test_timestamp_area_cropping(self):
        """タイムスタンプ領域のクロッピングテスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # フレーム抽出とクロップ
        frame = enhancer.extract_first_frame(self.sample_video)
        cropped = enhancer.crop_timestamp_area(frame)
        
        # クロップ結果検証
        self.assertIsNotNone(cropped, "Cropped area should not be None")
        
        # 適応的クロップ比率（640x360の場合は0.3）
        expected_height = int(360 * 0.3)  # 108
        expected_width = int(640 * 0.3)   # 192
        expected_shape = (expected_height, expected_width, 3)
        
        self.assertEqual(cropped.shape, expected_shape, 
                        f"Cropped shape should be {expected_shape}")
        
        print(f"Cropped area shape: {cropped.shape}")
    
    def test_ocr_processing_accuracy(self):
        """OCR処理精度テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        
        # フレーム抽出とクロップ
        frame = enhancer.extract_first_frame(self.sample_video)
        cropped = enhancer.crop_timestamp_area(frame)
        
        # 詳細OCR情報を取得
        ocr_details = enhancer.extract_timestamp_with_details(cropped)
        
        # OCR結果検証
        self.assertGreater(ocr_details['total_detections'], 0, 
                          "OCR should detect at least one text region")
        
        # 信頼度が低い場合の対応確認
        if ocr_details['timestamp'] is None:
            print(f"OCR detected text but confidence too low:")
            for result in ocr_details['all_results']:
                print(f"  Text: '{result['text']}' (confidence: {result['confidence']:.3f})")
            
            # 信頼度を下げて再テスト
            enhancer.set_confidence_threshold(0.3)
            timestamp_low_threshold = enhancer.extract_timestamp(cropped)
            
            if timestamp_low_threshold:
                print(f"With lower threshold: {timestamp_low_threshold}")
        
        # パフォーマンス検証
        self.assertLess(ocr_details['ocr_time'], 10.0, 
                       "OCR processing should be < 10 seconds")
        
        print(f"OCR time: {ocr_details['ocr_time']:.3f}s")
        print(f"Total detections: {ocr_details['total_detections']}")
        print(f"Valid candidates: {ocr_details['valid_candidates']}")
    
    def test_ocr_consistency_multiple_runs(self):
        """OCR処理の一貫性テスト（複数回実行）"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # フレーム抽出とクロップ
        frame = enhancer.extract_first_frame(self.sample_video)
        cropped = enhancer.crop_timestamp_area(frame)
        
        # 5回連続でOCR実行
        results = []
        times = []
        
        for i in range(5):
            start_time = time.time()
            result = enhancer.extract_timestamp_with_details(cropped)
            end_time = time.time()
            
            results.append(result)
            times.append(end_time - start_time)
        
        # 一貫性検証
        detection_counts = [r['total_detections'] for r in results]
        unique_counts = set(detection_counts)
        self.assertLessEqual(len(unique_counts), 2, 
                           "Detection count should be consistent across runs")
        
        # パフォーマンス検証
        avg_time = sum(times) / len(times)
        self.assertLess(avg_time, 5.0, "Average OCR time should be < 5 seconds")
        
        print(f"OCR consistency test:")
        print(f"  Average time: {avg_time:.3f}s")
        print(f"  Detection counts: {detection_counts}")
        print(f"  Time range: {min(times):.3f}s - {max(times):.3f}s")
    
    def test_performance_benchmarks(self):
        """パフォーマンスベンチマークテスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # 全体処理のベンチマーク
        benchmarks = {}
        
        # 1. フレーム抽出
        start_time = time.time()
        frame = enhancer.extract_first_frame(self.sample_video)
        benchmarks['frame_extraction'] = time.time() - start_time
        
        # 2. クロップ処理
        start_time = time.time()
        cropped = enhancer.crop_timestamp_area(frame)
        benchmarks['cropping'] = time.time() - start_time
        
        # 3. OCR処理（3回平均）
        ocr_times = []
        for _ in range(3):
            start_time = time.time()
            enhancer.extract_timestamp(cropped)
            ocr_times.append(time.time() - start_time)
        benchmarks['ocr_processing'] = sum(ocr_times) / len(ocr_times)
        
        # 4. 全体処理時間
        benchmarks['total_processing'] = (benchmarks['frame_extraction'] + 
                                        benchmarks['cropping'] + 
                                        benchmarks['ocr_processing'])
        
        # ベンチマーク結果の検証
        self.assertLess(benchmarks['frame_extraction'], 1.0, 
                       "Frame extraction should be < 1s")
        self.assertLess(benchmarks['cropping'], 0.1, 
                       "Cropping should be < 0.1s")
        self.assertLess(benchmarks['ocr_processing'], 10.0, 
                       "OCR processing should be < 10s")
        self.assertLess(benchmarks['total_processing'], 15.0, 
                       "Total processing should be < 15s")
        
        # 結果出力
        print(f"\nPerformance Benchmarks:")
        for operation, time_taken in benchmarks.items():
            print(f"  {operation}: {time_taken:.3f}s")
    
    def test_timestamp_parsing_robustness(self):
        """タイムスタンプパース機能の堅牢性テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # 様々なタイムスタンプ形式のテストケース
        test_cases = [
            "@ 2025/05/28 19.41.14",  # 実際のOCR結果形式
            "2025/05/28 19:41:14",    # 標準形式
            "2025-05-28 19:41:14",    # ハイフン区切り
            "@ 2025-05-28 19.41.14",  # ハイフン + ドット
            "町 2025/05/28 19.41.14", # OCRノイズ付き
        ]
        
        successful_parses = 0
        
        for test_case in test_cases:
            result = enhancer.parse_timestamp(test_case)
            if result is not None:
                successful_parses += 1
                print(f"Parsed '{test_case}' -> {result}")
            else:
                print(f"Failed to parse '{test_case}'")
        
        # 少なくとも50%のケースで成功すべき
        success_rate = successful_parses / len(test_cases)
        self.assertGreaterEqual(success_rate, 0.5, 
                               f"At least 50% of test cases should parse successfully")
        
        print(f"Parse success rate: {success_rate:.1%}")
    
    def test_error_handling_robustness(self):
        """エラーハンドリングの堅牢性テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # 1. 存在しないファイルのテスト
        with self.assertRaises(FileNotFoundError):
            enhancer.extract_first_frame("nonexistent.mp4")
        
        # 2. 無効なフレームでのクロップテスト
        invalid_frame = np.array([])
        with self.assertRaises(ValueError):
            enhancer.crop_timestamp_area(invalid_frame)
        
        # 3. 空のタイムスタンプのパーステスト
        result = enhancer.parse_timestamp("")
        self.assertIsNone(result, "Empty string should return None")
        
        result = enhancer.parse_timestamp(None)
        self.assertIsNone(result, "None should return None")
        
        # 4. 無効なタイムスタンプのパーステスト
        invalid_timestamps = [
            "invalid timestamp",
            "2025/13/40 25:99:99",  # 無効な日時
            "abc/def/ghi hh:mm:ss",  # 非数値
        ]
        
        for invalid_ts in invalid_timestamps:
            result = enhancer.parse_timestamp(invalid_ts)
            self.assertIsNone(result, f"Invalid timestamp '{invalid_ts}' should return None")
        
        print("Error handling robustness tests passed")


class TestXiaomiCameraMemoryUsage(unittest.TestCase):
    """メモリ使用量テスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.sample_video = "sample.mp4"
        if not os.path.exists(self.sample_video):
            self.skipTest(f"Sample video {self.sample_video} not found")
    
    def test_memory_efficiency(self):
        """メモリ効率テスト"""
        try:
            import psutil
            import gc
        except ImportError:
            self.skipTest("psutil not available for memory testing")
        
        # メモリ使用量測定開始
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 複数回処理実行
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        for i in range(10):
            frame = enhancer.extract_first_frame(self.sample_video)
            cropped = enhancer.crop_timestamp_area(frame)
            enhancer.extract_timestamp(cropped)
            
            # 明示的にガベージコレクション
            del frame, cropped
            gc.collect()
        
        # 最終メモリ使用量
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # メモリリークがないことを確認（増加量が100MB未満）
        self.assertLess(memory_increase, 100, 
                       f"Memory increase should be < 100MB, got {memory_increase:.1f}MB")
        
        print(f"Memory usage: {initial_memory:.1f}MB -> {final_memory:.1f}MB "
              f"(+{memory_increase:.1f}MB)")


if __name__ == '__main__':
    # テスト実行時の詳細出力
    unittest.main(verbosity=2, buffer=True)
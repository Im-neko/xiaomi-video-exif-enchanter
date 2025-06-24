#!/usr/bin/env python3
"""
OCR Accuracy Analysis for Sample Video
sample.mp4のOCR精度と信頼度を詳細に分析するテスト
"""

import unittest
import os
from datetime import datetime
import cv2
import numpy as np
from unittest.mock import patch
import time

from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestOCRAccuracyAnalysis(unittest.TestCase):
    """OCR精度の詳細分析テスト"""
    
    SAMPLE_VIDEO_PATH = "sample.mp4"
    EXPECTED_TIMESTAMP_STR = "@ 2025/05/28 19.41.14"
    EXPECTED_DATETIME = datetime(2025, 5, 28, 19, 41, 14)
    MIN_CONFIDENCE_THRESHOLD = 0.5
    EXPECTED_CONFIDENCE_RANGE = (0.75, 1.0)  # 期待される信頼度範囲
    
    @classmethod
    def setUpClass(cls):
        """テストクラス開始前の準備"""
        if not os.path.exists(cls.SAMPLE_VIDEO_PATH):
            raise unittest.SkipTest(f"Sample video not found: {cls.SAMPLE_VIDEO_PATH}")
    
    def setUp(self):
        """各テスト前の準備"""
        try:
            self.enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        except Exception as e:
            self.skipTest(f"Failed to initialize EasyOCR: {e}")
    
    def test_ocr_confidence_threshold(self):
        """
OCR信頼度が闾値を超えることをテスト"""
        frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # OCR結果の詳細を取得
        results = self.enhancer.reader.readtext(cropped)
        
        # 少なくとも1つのテキスト領域が検出されることを確認
        self.assertGreater(len(results), 0, "At least one text region should be detected")
        
        # 最高信頼度の結果を取得
        best_result = max(results, key=lambda x: x[2])
        bbox, text, confidence = best_result
        
        print(f"\nOCR Analysis:")
        print(f"  Detected text: '{text}'")
        print(f"  Confidence: {confidence:.3f}")
        print(f"  Bounding box: {bbox}")
        
        # 信頼度の確認
        self.assertGreaterEqual(confidence, self.MIN_CONFIDENCE_THRESHOLD,
                               f"Confidence {confidence:.3f} should be >= {self.MIN_CONFIDENCE_THRESHOLD}")
        
        # 期待される範囲内か確認
        self.assertGreaterEqual(confidence, self.EXPECTED_CONFIDENCE_RANGE[0],
                               f"Confidence {confidence:.3f} should be >= {self.EXPECTED_CONFIDENCE_RANGE[0]}")
        
        # タイムスタンプらしいテキストが検出されているか確認
        self.assertIn("2025", text, "Text should contain year")
        self.assertIn("05", text, "Text should contain month")
        self.assertIn("28", text, "Text should contain day")
    
    def test_ocr_text_accuracy(self):
        """
OCRテキストの精度をテスト"""
        frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = self.enhancer.crop_timestamp_area(frame)
        timestamp_str = self.enhancer.extract_timestamp(cropped)
        
        self.assertIsNotNone(timestamp_str, "Timestamp should be detected")
        
        # 数字の精度チェック
        expected_numbers = ['2025', '05', '28', '19', '41', '14']
        
        for number in expected_numbers:
            self.assertIn(number, timestamp_str,
                         f"'{number}' should be correctly detected in '{timestamp_str}'")
        
        # 区切り文字の精度チェック
        self.assertTrue('/' in timestamp_str or '-' in timestamp_str,
                       "Date separator should be detected")
        self.assertTrue('.' in timestamp_str or ':' in timestamp_str,
                       "Time separator should be detected")
    
    def test_timestamp_parsing_accuracy(self):
        """タイムスタンプパーシングの精度テスト"""
        frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = self.enhancer.crop_timestamp_area(frame)
        timestamp_str = self.enhancer.extract_timestamp(cropped)
        parsed_datetime = self.enhancer.parse_timestamp(timestamp_str)
        
        self.assertIsNotNone(parsed_datetime, "Timestamp should be parsed successfully")
        self.assertEqual(parsed_datetime, self.EXPECTED_DATETIME,
                        f"Parsed datetime {parsed_datetime} should match expected {self.EXPECTED_DATETIME}")
        
        # 各コンポーネントの精度確認
        self.assertEqual(parsed_datetime.year, 2025, "Year should be 2025")
        self.assertEqual(parsed_datetime.month, 5, "Month should be 5")
        self.assertEqual(parsed_datetime.day, 28, "Day should be 28")
        self.assertEqual(parsed_datetime.hour, 19, "Hour should be 19")
        self.assertEqual(parsed_datetime.minute, 41, "Minute should be 41")
        self.assertEqual(parsed_datetime.second, 14, "Second should be 14")
    
    def test_ocr_consistency_multiple_runs(self):
        """複数回のOCR実行での一貫性テスト"""
        frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        results = []
        confidences = []
        
        # 5回連続でOCRを実行
        for i in range(5):
            ocr_results = self.enhancer.reader.readtext(cropped)
            if ocr_results:
                best_result = max(ocr_results, key=lambda x: x[2])
                _, text, confidence = best_result
                results.append(text)
                confidences.append(confidence)
        
        print(f"\nConsistency Analysis (5 runs):")
        for i, (text, conf) in enumerate(zip(results, confidences)):
            print(f"  Run {i+1}: '{text}' (confidence: {conf:.3f})")
        
        # 結果の一貫性確認
        unique_results = set(results)
        self.assertLessEqual(len(unique_results), 2,
                            f"Should have at most 2 unique results, got {len(unique_results)}: {unique_results}")
        
        # 信頼度の安定性確認
        avg_confidence = sum(confidences) / len(confidences)
        confidence_variance = sum((c - avg_confidence) ** 2 for c in confidences) / len(confidences)
        
        print(f"  Average confidence: {avg_confidence:.3f}")
        print(f"  Confidence variance: {confidence_variance:.6f}")
        
        self.assertGreaterEqual(avg_confidence, self.MIN_CONFIDENCE_THRESHOLD,
                               f"Average confidence should be >= {self.MIN_CONFIDENCE_THRESHOLD}")
        self.assertLess(confidence_variance, 0.01,
                       f"Confidence variance should be < 0.01, got {confidence_variance:.6f}")
    
    def test_cropping_area_optimization(self):
        """クロップ領域の最適化テスト"""
        frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        height, width = frame.shape[:2]
        
        # 異なるクロップサイズでテスト
        crop_ratios = [
            (1/4, 1/4),  # デフォルト
            (1/3, 1/3),  # 少し大きめ
            (1/5, 1/5),  # 少し小さめ
            (1/4, 1/3),  # 縦長
            (1/3, 1/4),  # 横長
        ]
        
        best_confidence = 0
        best_ratio = None
        best_text = None
        
        print(f"\nCrop Area Optimization:")
        
        for h_ratio, w_ratio in crop_ratios:
            crop_h = int(height * h_ratio)
            crop_w = int(width * w_ratio)
            cropped = frame[0:crop_h, 0:crop_w]
            
            try:
                ocr_results = self.enhancer.reader.readtext(cropped)
                if ocr_results:
                    best_result = max(ocr_results, key=lambda x: x[2])
                    _, text, confidence = best_result
                    
                    print(f"  {h_ratio:.2f}x{w_ratio:.2f} ({crop_h}x{crop_w}): '{text}' (conf: {confidence:.3f})")
                    
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_ratio = (h_ratio, w_ratio)
                        best_text = text
                else:
                    print(f"  {h_ratio:.2f}x{w_ratio:.2f} ({crop_h}x{crop_w}): No text detected")
            
            except Exception as e:
                print(f"  {h_ratio:.2f}x{w_ratio:.2f} ({crop_h}x{crop_w}): Error - {e}")
        
        print(f"  Best ratio: {best_ratio} with confidence {best_confidence:.3f}")
        
        # デフォルトの1/4が合理的であることを確認
        self.assertIsNotNone(best_ratio, "Should find at least one working crop ratio")
        self.assertGreaterEqual(best_confidence, self.MIN_CONFIDENCE_THRESHOLD,
                               "Best confidence should meet minimum threshold")
    
    def test_image_preprocessing_effects(self):
        """画像前処理がOCR精度に与える影響のテスト"""
        frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        preprocessing_methods = [
            ("original", lambda img: img),
            ("grayscale", lambda img: cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)),
            ("gaussian_blur", lambda img: cv2.GaussianBlur(img, (3, 3), 0)),
            ("contrast_enhanced", lambda img: cv2.convertScaleAbs(img, alpha=1.2, beta=10)),
            ("histogram_eq", lambda img: cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))),
        ]
        
        print(f"\nImage Preprocessing Effects:")
        
        for method_name, preprocess_func in preprocessing_methods:
            try:
                processed_img = preprocess_func(cropped.copy())
                
                # グレースケール画像は3チャンネルに変換
                if len(processed_img.shape) == 2:
                    processed_img = cv2.cvtColor(processed_img, cv2.COLOR_GRAY2BGR)
                
                ocr_results = self.enhancer.reader.readtext(processed_img)
                
                if ocr_results:
                    best_result = max(ocr_results, key=lambda x: x[2])
                    _, text, confidence = best_result
                    print(f"  {method_name:15}: '{text}' (conf: {confidence:.3f})")
                else:
                    print(f"  {method_name:15}: No text detected")
                    
            except Exception as e:
                print(f"  {method_name:15}: Error - {e}")
        
        # オリジナル画像で十分な精度が得られることを確認
        original_results = self.enhancer.reader.readtext(cropped)
        if original_results:
            original_confidence = max(original_results, key=lambda x: x[2])[2]
            self.assertGreaterEqual(original_confidence, self.MIN_CONFIDENCE_THRESHOLD,
                                   "Original image should have sufficient confidence")


class TestOCRPerformanceMetrics(unittest.TestCase):
    """OCRパフォーマンスメトリクスのテスト"""
    
    SAMPLE_VIDEO_PATH = "sample.mp4"
    
    def setUp(self):
        """テスト準備"""
        if not os.path.exists(self.SAMPLE_VIDEO_PATH):
            self.skipTest(f"Sample video not found: {self.SAMPLE_VIDEO_PATH}")
        
        try:
            self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)  # パフォーマンス測定ではデバッグ無効
        except Exception as e:
            self.skipTest(f"Failed to initialize EasyOCR: {e}")
    
    def test_ocr_processing_time(self):
        """
OCR処理時間のパフォーマンステスト"""
        frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # OCR処理時間を測定
        start_time = time.time()
        results = self.enhancer.reader.readtext(cropped)
        end_time = time.time()
        
        ocr_time = end_time - start_time
        
        print(f"\nOCR Performance Metrics:")
        print(f"  OCR processing time: {ocr_time:.3f} seconds")
        print(f"  Detected regions: {len(results)}")
        
        if results:
            best_result = max(results, key=lambda x: x[2])
            _, text, confidence = best_result
            print(f"  Best result: '{text}' (confidence: {confidence:.3f})")
        
        # OCR処理は通常10秒以内に完了すべき（初回はモデルロードで遅い可能性）
        self.assertLess(ocr_time, 10.0,
                       f"OCR processing should complete within 10 seconds, took {ocr_time:.3f}s")
        
        # 何らかのテキストが検出されることを確認
        self.assertGreater(len(results), 0, "At least one text region should be detected")
    
    def test_memory_usage_stability(self):
        """メモリ使用量の安定性テスト"""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # 10回連続でOCR処理を実行
        for i in range(10):
            frame = self.enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
            cropped = self.enhancer.crop_timestamp_area(frame)
            results = self.enhancer.reader.readtext(cropped)
            
            # 明示的なガベージコレクション
            del frame, cropped, results
            gc.collect()
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        print(f"\nMemory Usage Analysis:")
        print(f"  Initial memory: {initial_memory:.1f} MB")
        print(f"  Final memory: {final_memory:.1f} MB")
        print(f"  Memory increase: {memory_increase:.1f} MB")
        
        # メモリリークが異常でないことを確認（100MB以下の増加）
        self.assertLess(memory_increase, 100,
                       f"Memory increase should be < 100MB, got {memory_increase:.1f}MB")


if __name__ == '__main__':
    # テストの実行
    unittest.main(verbosity=2)

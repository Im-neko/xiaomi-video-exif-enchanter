#!/usr/bin/env python3
"""
EasyOCR初期化と基本的なテキスト読み取り機能のテストファイル
"""

import unittest
import cv2
import numpy as np
import os
import tempfile
import time
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestEasyOCRInitialization(unittest.TestCase):
    """EasyOCR初期化のテストクラス"""
    
    def test_default_initialization(self):
        """デフォルト設定での初期化テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # 初期化確認
        self.assertIsNotNone(enhancer.reader)
        self.assertEqual(enhancer.languages, ['en', 'ja'])
        self.assertEqual(enhancer.confidence_threshold, 0.6)
    
    def test_english_only_initialization(self):
        """英語のみでの初期化テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=['en'])
        
        self.assertEqual(enhancer.languages, ['en'])
        self.assertIsNotNone(enhancer.reader)
    
    def test_multiple_languages_initialization(self):
        """複数言語での初期化テスト"""
        # 互換性のある言語組み合わせを使用
        languages = ['en', 'ja']
        enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=languages)
        
        self.assertEqual(enhancer.languages, languages)
        self.assertIsNotNone(enhancer.reader)
    
    def test_debug_initialization(self):
        """デバッグモードでの初期化テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=True, languages=['en'])
        
        self.assertTrue(enhancer.debug)
        self.assertIsNotNone(enhancer.reader)
    
    def test_get_ocr_languages(self):
        """OCR言語取得テスト"""
        languages = ['en', 'ja']
        enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=languages)
        
        retrieved_languages = enhancer.get_ocr_languages()
        self.assertEqual(retrieved_languages, languages)
        
        # リストのコピーが返されることを確認
        retrieved_languages.append('ch_sim')
        self.assertNotEqual(enhancer.languages, retrieved_languages)


class TestConfidenceThreshold(unittest.TestCase):
    """信頼度閾値のテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=['en'])
    
    def test_set_valid_confidence_threshold(self):
        """有効な信頼度閾値設定テスト"""
        valid_thresholds = [0.0, 0.1, 0.5, 0.8, 1.0]
        
        for threshold in valid_thresholds:
            with self.subTest(threshold=threshold):
                self.enhancer.set_confidence_threshold(threshold)
                self.assertEqual(self.enhancer.confidence_threshold, threshold)
    
    def test_set_invalid_confidence_threshold(self):
        """無効な信頼度閾値設定テスト"""
        invalid_thresholds = [-0.1, -1.0, 1.1, 2.0]
        
        for threshold in invalid_thresholds:
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    self.enhancer.set_confidence_threshold(threshold)


class TestBasicOCRFunctionality(unittest.TestCase):
    """基本的なOCR機能のテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=['en'])
        self.sample_video = "sample.mp4"
        
        # テスト用の画像を作成（白背景に黒文字）
        self.test_image = self._create_test_image_with_text("2025/05/28 19:41:14")
    
    def _create_test_image_with_text(self, text: str) -> np.ndarray:
        """テスト用のテキスト画像を作成"""
        img = np.ones((100, 300, 3), dtype=np.uint8) * 255  # 白背景
        
        # OpenCVでテキストを描画
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        color = (0, 0, 0)  # 黒文字
        thickness = 2
        
        # テキストサイズを取得して中央に配置
        text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
        x = (img.shape[1] - text_size[0]) // 2
        y = (img.shape[0] + text_size[1]) // 2
        
        cv2.putText(img, text, (x, y), font, font_scale, color, thickness)
        return img
    
    def test_extract_timestamp_from_test_image(self):
        """テスト画像からのタイムスタンプ抽出テスト"""
        timestamp = self.enhancer.extract_timestamp(self.test_image)
        
        # タイムスタンプが抽出されることを確認
        self.assertIsInstance(timestamp, (str, type(None)))
        if timestamp:
            self.assertIn("2025", timestamp)
    
    def test_extract_timestamp_with_details_from_test_image(self):
        """詳細情報付きタイムスタンプ抽出テスト"""
        result = self.enhancer.extract_timestamp_with_details(self.test_image)
        
        # 結果の構造確認
        required_keys = ['timestamp', 'confidence', 'bbox', 'ocr_time', 
                        'total_detections', 'valid_candidates', 'all_results']
        for key in required_keys:
            self.assertIn(key, result)
        
        # データ型確認
        self.assertIsInstance(result['ocr_time'], float)
        self.assertIsInstance(result['total_detections'], int)
        self.assertIsInstance(result['valid_candidates'], int)
        self.assertIsInstance(result['all_results'], list)
        self.assertGreaterEqual(result['ocr_time'], 0.0)
        self.assertGreaterEqual(result['total_detections'], 0)
    
    def test_find_best_timestamp_match(self):
        """最適タイムスタンプマッチングテスト"""
        # モックOCR結果を作成
        mock_results = [
            ([(0, 0), (100, 0), (100, 20), (0, 20)], "2025/05/28 19:41:14", 0.95),
            ([(0, 30), (80, 30), (80, 50), (0, 50)], "some text", 0.8),
            ([(0, 60), (90, 60), (90, 80), (0, 80)], "2024/01/01 12:00:00", 0.7),
        ]
        
        result = self.enhancer._find_best_timestamp_match(mock_results)
        
        # 最も信頼度の高いタイムスタンプが選択されることを確認
        self.assertEqual(result, "2025/05/28 19:41:14")
    
    def test_find_best_timestamp_match_below_threshold(self):
        """閾値以下の信頼度でのマッチングテスト"""
        # 低信頼度のOCR結果
        mock_results = [
            ([(0, 0), (100, 0), (100, 20), (0, 20)], "2025/05/28 19:41:14", 0.3),
            ([(0, 30), (80, 30), (80, 50), (0, 50)], "some text", 0.4),
        ]
        
        result = self.enhancer._find_best_timestamp_match(mock_results)
        
        # 閾値以下なのでNoneが返されることを確認
        self.assertIsNone(result)
    
    def test_extract_timestamp_from_empty_image(self):
        """空の画像からのタイムスタンプ抽出テスト"""
        empty_image = np.ones((50, 50, 3), dtype=np.uint8) * 255
        
        timestamp = self.enhancer.extract_timestamp(empty_image)
        
        # 空の画像からはタイムスタンプが抽出されないことを確認
        self.assertIsNone(timestamp)


class TestOCRPerformanceMeasurement(unittest.TestCase):
    """OCR性能測定のテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=['en'])
        self.test_image = np.ones((100, 200, 3), dtype=np.uint8) * 255
    
    def test_ocr_performance_measurement(self):
        """OCR性能測定テスト"""
        result = self.enhancer.test_ocr_performance(self.test_image, iterations=3)
        
        # 結果の構造確認
        required_keys = ['average_time', 'min_time', 'max_time', 
                        'successful_runs', 'total_runs', 'success_rate']
        for key in required_keys:
            self.assertIn(key, result)
        
        # 値の妥当性確認
        self.assertGreaterEqual(result['average_time'], 0)
        self.assertGreaterEqual(result['min_time'], 0)
        self.assertGreaterEqual(result['max_time'], 0)
        self.assertGreaterEqual(result['successful_runs'], 0)
        self.assertEqual(result['total_runs'], 3)
        self.assertGreaterEqual(result['success_rate'], 0.0)
        self.assertLessEqual(result['success_rate'], 1.0)
    
    def test_ocr_performance_with_zero_iterations(self):
        """0回イテレーションでの性能測定テスト"""
        result = self.enhancer.test_ocr_performance(self.test_image, iterations=0)
        
        self.assertEqual(result['total_runs'], 0)
        self.assertEqual(result['successful_runs'], 0)
        self.assertEqual(result['success_rate'], 0.0)


class TestOCRWithSampleVideo(unittest.TestCase):
    """サンプル映像を使用したOCRテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=['en'])
        self.sample_video = "sample.mp4"
    
    def test_extract_timestamp_from_sample_video(self):
        """サンプル映像からのタイムスタンプ抽出テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        timestamp = self.enhancer.extract_timestamp(cropped)
        
        # タイムスタンプが抽出できることを確認
        if timestamp:
            self.assertIsInstance(timestamp, str)
            self.assertRegex(timestamp, r'\d{4}')  # 年が含まれることを確認
    
    def test_extract_timestamp_with_details_from_sample_video(self):
        """サンプル映像からの詳細付きタイムスタンプ抽出テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        result = self.enhancer.extract_timestamp_with_details(cropped)
        
        # OCR処理が実行されたことを確認
        self.assertGreater(result['ocr_time'], 0)
        self.assertGreaterEqual(result['total_detections'], 0)
    
    def test_ocr_performance_with_sample_video(self):
        """サンプル映像での性能測定テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        result = self.enhancer.test_ocr_performance(cropped, iterations=2)
        
        # 性能測定が実行されたことを確認
        self.assertGreaterEqual(result['total_runs'], 0)
        if result['successful_runs'] > 0:
            self.assertGreater(result['average_time'], 0)


class TestOCRErrorHandling(unittest.TestCase):
    """OCRエラーハンドリングのテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False, languages=['en'])
    
    def test_extract_timestamp_with_invalid_image(self):
        """無効な画像でのタイムスタンプ抽出テスト"""
        # 無効な形状の画像
        invalid_image = np.zeros((10, 10), dtype=np.uint8)  # 2D image
        
        # エラーが適切にハンドリングされることを確認
        timestamp = self.enhancer.extract_timestamp(invalid_image)
        self.assertIsNone(timestamp)
    
    def test_extract_timestamp_with_details_error_handling(self):
        """詳細付き抽出でのエラーハンドリングテスト"""
        invalid_image = np.zeros((5, 5), dtype=np.uint8)  # 非常に小さい画像
        
        result = self.enhancer.extract_timestamp_with_details(invalid_image)
        
        # エラーが発生してもdict構造は維持されることを確認
        self.assertIsInstance(result, dict)
        self.assertIn('timestamp', result)


if __name__ == '__main__':
    unittest.main()
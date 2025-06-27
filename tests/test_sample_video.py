#!/usr/bin/env python3
"""
Sample Video Integration Tests
sample.mp4の実際の時刻情報(2025/05/28 19:41:14)を使用した統合テスト
"""

import unittest
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import tempfile
import cv2
import numpy as np

from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestSampleVideoIntegration(unittest.TestCase):
    """sample.mp4を使用した統合テスト"""
    
    SAMPLE_VIDEO_PATH = "sample.mp4"
    EXPECTED_TIMESTAMP = datetime(2025, 5, 28, 19, 41, 14)
    EXPECTED_FRAME_SHAPE = (360, 640, 3)  # height, width, channels
    
    @classmethod
    def setUpClass(cls):
        """テストクラス開始前の準備"""
        # sample.mp4の存在確認
        if not os.path.exists(cls.SAMPLE_VIDEO_PATH):
            raise unittest.SkipTest(f"Sample video not found: {cls.SAMPLE_VIDEO_PATH}")
        
        # ファイルサイズ確認（空でないか）
        if os.path.getsize(cls.SAMPLE_VIDEO_PATH) == 0:
            raise unittest.SkipTest(f"Sample video is empty: {cls.SAMPLE_VIDEO_PATH}")
    
    def setUp(self):
        """各テスト前の準備"""
        # EasyOCRの初期化が重いので、必要な場合のみ初期化
        self.enhancer = None
    
    def _get_enhancer(self):
        """遅延初期化でEnhancerを取得"""
        if self.enhancer is None:
            try:
                self.enhancer = XiaomiVideoEXIFEnhancer(debug=True)
            except Exception as e:
                self.skipTest(f"Failed to initialize EasyOCR: {e}")
        return self.enhancer
    
    def test_sample_video_exists_and_readable(self):
        """サンプル動画の存在と読み込み可能性をテスト"""
        # ファイル存在確認
        self.assertTrue(os.path.exists(self.SAMPLE_VIDEO_PATH), 
                       f"Sample video should exist: {self.SAMPLE_VIDEO_PATH}")
        
        # OpenCVで読み込み可能か確認
        cap = cv2.VideoCapture(self.SAMPLE_VIDEO_PATH)
        try:
            self.assertTrue(cap.isOpened(), "Sample video should be readable by OpenCV")
            
            # フレーム読み込み確認
            ret, frame = cap.read()
            self.assertTrue(ret, "Should be able to read first frame")
            self.assertIsNotNone(frame, "First frame should not be None")
            
            # フレームサイズ確認
            self.assertEqual(frame.shape, self.EXPECTED_FRAME_SHAPE,
                           f"Frame shape should be {self.EXPECTED_FRAME_SHAPE}")
        finally:
            cap.release()
    
    def test_extract_first_frame_from_sample(self):
        """サンプル動画からの1フレーム目抽出テスト"""
        enhancer = self._get_enhancer()
        
        frame = enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        
        # フレーム形状確認
        self.assertEqual(frame.shape, self.EXPECTED_FRAME_SHAPE)
        
        # フレームが空でないことを確認
        self.assertGreater(np.sum(frame), 0, "Frame should not be completely black")
    
    def test_crop_timestamp_area_from_sample(self):
        """サンプル動画からのタイムスタンプ領域クロップテスト"""
        enhancer = self._get_enhancer()
        
        # 1フレーム目を抽出
        frame = enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        
        # タイムスタンプ領域をクロップ
        cropped = enhancer.crop_timestamp_area(frame)
        
        # クロップされたサイズ確認（左上1/4）
        expected_height = self.EXPECTED_FRAME_SHAPE[0] // 4  # 90
        expected_width = self.EXPECTED_FRAME_SHAPE[1] // 4   # 160
        
        self.assertEqual(cropped.shape[0], expected_height)
        self.assertEqual(cropped.shape[1], expected_width)
        self.assertEqual(cropped.shape[2], 3)  # RGB channels
    
    def test_ocr_timestamp_detection_from_sample(self):
        """サンプル動画からのOCRタイムスタンプ検出テスト"""
        enhancer = self._get_enhancer()
        
        # フレーム抽出とクロップ
        frame = enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = enhancer.crop_timestamp_area(frame)
        
        # OCRでタイムスタンプ抽出
        timestamp_str = enhancer.extract_timestamp(cropped)
        
        # タイムスタンプが検出されることを確認
        self.assertIsNotNone(timestamp_str, "Timestamp should be detected from sample video")
        
        # 期待される形式であることを確認
        self.assertIn("2025", timestamp_str, "Should contain year 2025")
        self.assertIn("05", timestamp_str, "Should contain month 05")
        self.assertIn("28", timestamp_str, "Should contain day 28")
        self.assertIn("19", timestamp_str, "Should contain hour 19")
        self.assertIn("41", timestamp_str, "Should contain minute 41")
        self.assertIn("14", timestamp_str, "Should contain second 14")
    
    def test_parse_sample_timestamp(self):
        """サンプル動画のタイムスタンプパースをテスト"""
        enhancer = self._get_enhancer()
        
        # 実際のOCR結果をシミュレート
        test_timestamp_strings = [
            "@ 2025/05/28 19.41.14 ",  # 実際のOCR結果
            "2025/05/28 19.41.14",     # @記号なし
            "@ 2025-05-28 19.41.14",   # ハイフン区切り
        ]
        
        for timestamp_str in test_timestamp_strings:
            with self.subTest(timestamp_str=timestamp_str):
                parsed = enhancer.parse_timestamp(timestamp_str)
                
                self.assertIsNotNone(parsed, f"Should parse: {timestamp_str}")
                self.assertEqual(parsed, self.EXPECTED_TIMESTAMP,
                               f"Parsed timestamp should match expected: {timestamp_str}")
    
    def test_full_pipeline_with_sample_video(self):
        """サンプル動画を使用した完全なパイプラインテスト"""
        enhancer = self._get_enhancer()
        
        # 完全なパイプラインを実行
        frame = enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        cropped = enhancer.crop_timestamp_area(frame)
        timestamp_str = enhancer.extract_timestamp(cropped)
        parsed_timestamp = enhancer.parse_timestamp(timestamp_str)
        
        # 各段階での結果を確認
        self.assertEqual(frame.shape, self.EXPECTED_FRAME_SHAPE)
        self.assertIsNotNone(timestamp_str)
        self.assertIsNotNone(parsed_timestamp)
        self.assertEqual(parsed_timestamp, self.EXPECTED_TIMESTAMP)
    
    @patch('os.path.exists')
    def test_process_video_with_sample_mock_ffmpeg(self, mock_exists):
        """FFmpegをモックしてサンプル動画の処理をテスト"""
        # FFmpegの存在をモック
        mock_exists.side_effect = lambda path: (
            path == self.SAMPLE_VIDEO_PATH or 
            path == 'sample_enhanced.mp4' or
            'ffmpeg' in path
        )
        
        enhancer = self._get_enhancer()
        
        # 一時的な出力ファイル名
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            output_path = tmp.name
        
        try:
            # FFmpegをモックして処理実行（実際のFFmpeg処理はスキップ）
            with patch.object(enhancer, 'add_exif_data', return_value=True):
                success = enhancer.process_video(
                    self.SAMPLE_VIDEO_PATH, 
                    output_path, 
                    "テストルーム"
                )
                
                # 処理の成功を確認
                self.assertTrue(success, "Video processing should succeed")
        
        finally:
            # 一時ファイルクリーンアップ
            if os.path.exists(output_path):
                os.unlink(output_path)


class TestSampleVideoTimestampRegex(unittest.TestCase):
    """サンプル動画のタイムスタンプ形式に特化した正規表現テスト"""
    
    def setUp(self):
        """テスト準備"""
        # EasyOCRをモックして高速化
        with patch('easyocr.Reader'):
            self.enhancer = XiaomiVideoEXIFEnhancer()
    
    def test_sample_timestamp_formats(self):
        """サンプル動画で実際に検出される形式のテスト"""
        test_cases = [
            # 実際のOCR結果パターン
            ("@ 2025/05/28 19.41.14 ", datetime(2025, 5, 28, 19, 41, 14)),
            ("@ 2025/05/28 19.41.14", datetime(2025, 5, 28, 19, 41, 14)),
            ("@2025/05/28 19.41.14 ", datetime(2025, 5, 28, 19, 41, 14)),
            
            # バリエーション
            ("2025/05/28 19.41.14", datetime(2025, 5, 28, 19, 41, 14)),
            (" @ 2025/05/28 19.41.14 ", datetime(2025, 5, 28, 19, 41, 14)),
            
            # 他の区切り文字
            ("@ 2025-05-28 19.41.14", datetime(2025, 5, 28, 19, 41, 14)),
            ("@ 2025/05/28 19:41:14", datetime(2025, 5, 28, 19, 41, 14)),
        ]
        
        for timestamp_str, expected in test_cases:
            with self.subTest(timestamp_str=timestamp_str):
                result = self.enhancer.parse_timestamp(timestamp_str)
                self.assertEqual(result, expected, 
                               f"Failed to parse: '{timestamp_str}'")
    
    def test_invalid_sample_timestamp_formats(self):
        """無効なタイムスタンプ形式のテスト"""
        invalid_cases = [
            "@ 2025/05/28",  # 時刻部分なし
            "19.41.14",      # 日付部分なし
            "@ 2025/13/28 19.41.14",  # 無効な月
            "@ 2025/05/32 19.41.14",  # 無効な日
            "@ 2025/05/28 25.41.14",  # 無効な時
            "@ 2025/05/28 19.61.14",  # 無効な分
            "@ 2025/05/28 19.41.61",  # 無効な秒
            "random text",             # 全く無関係
            "",                        # 空文字
            None,                      # None
        ]
        
        for timestamp_str in invalid_cases:
            with self.subTest(timestamp_str=timestamp_str):
                result = self.enhancer.parse_timestamp(timestamp_str)
                self.assertIsNone(result, 
                                f"Should not parse invalid: '{timestamp_str}'")


class TestSampleVideoPerformance(unittest.TestCase):
    """サンプル動画を使用したパフォーマンステスト"""
    
    SAMPLE_VIDEO_PATH = "sample.mp4"
    
    def setUp(self):
        """テスト準備"""
        if not os.path.exists(self.SAMPLE_VIDEO_PATH):
            self.skipTest(f"Sample video not found: {self.SAMPLE_VIDEO_PATH}")
    
    def test_frame_extraction_performance(self):
        """フレーム抽出のパフォーマンステスト"""
        import time
        
        with patch('easyocr.Reader'):
            enhancer = XiaomiVideoEXIFEnhancer()
        
        start_time = time.time()
        frame = enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        end_time = time.time()
        
        extraction_time = end_time - start_time
        
        # フレーム抽出は1秒以内に完了すべき
        self.assertLess(extraction_time, 1.0, 
                       f"Frame extraction took {extraction_time:.2f}s, should be < 1.0s")
        
        # 結果の妥当性確認
        self.assertEqual(frame.shape, (360, 640, 3))
    
    def test_crop_operation_performance(self):
        """クロップ操作のパフォーマンステスト"""
        import time
        
        with patch('easyocr.Reader'):
            enhancer = XiaomiVideoEXIFEnhancer()
        
        frame = enhancer.extract_first_frame(self.SAMPLE_VIDEO_PATH)
        
        start_time = time.time()
        cropped = enhancer.crop_timestamp_area(frame)
        end_time = time.time()
        
        crop_time = end_time - start_time
        
        # クロップ操作は0.1秒以内に完了すべき
        self.assertLess(crop_time, 0.1, 
                       f"Crop operation took {crop_time:.3f}s, should be < 0.1s")
        
        # 結果の妥当性確認
        self.assertEqual(cropped.shape, (90, 160, 3))


if __name__ == '__main__':
    # テストの実行順序を制御
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 基本的な統合テストを最初に実行
    suite.addTests(loader.loadTestsFromTestCase(TestSampleVideoIntegration))
    
    # 正規表現テスト
    suite.addTests(loader.loadTestsFromTestCase(TestSampleVideoTimestampRegex))
    
    # パフォーマンステスト（最後に実行）
    suite.addTests(loader.loadTestsFromTestCase(TestSampleVideoPerformance))
    
    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 結果サマリー
    print(f"\n{'='*50}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    print(f"{'='*50}")

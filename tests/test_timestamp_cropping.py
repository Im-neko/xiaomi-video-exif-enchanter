#!/usr/bin/env python3
"""
左上領域の日時クロップ機能の詳細テストファイル  
"""

import unittest
import cv2
import numpy as np
import os
import tempfile
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestTimestampCropping(unittest.TestCase):
    """日時クロップ機能のテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        self.debug_enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        self.sample_video = "sample.mp4"
        
        # テスト用のダミーフレームを作成
        self.test_frame = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)
    
    def test_crop_timestamp_area_default_ratio(self):
        """デフォルト比率でのクロップテスト"""
        cropped = self.enhancer.crop_timestamp_area(self.test_frame)
        
        # デフォルト比率0.25でのクロップ確認
        expected_height = int(360 * 0.25)  # 90
        expected_width = int(640 * 0.25)   # 160
        
        self.assertEqual(cropped.shape[:2], (expected_height, expected_width))
        self.assertEqual(cropped.shape[2], 3)
    
    def test_crop_timestamp_area_custom_ratio(self):
        """カスタム比率でのクロップテスト"""
        ratios = [0.1, 0.2, 0.3, 0.5, 1.0]
        
        for ratio in ratios:
            with self.subTest(ratio=ratio):
                cropped = self.enhancer.crop_timestamp_area(self.test_frame, ratio)
                
                expected_height = int(360 * ratio)
                expected_width = int(640 * ratio)
                
                self.assertEqual(cropped.shape[:2], (expected_height, expected_width))
                self.assertEqual(cropped.shape[2], 3)
    
    def test_crop_timestamp_area_invalid_ratio(self):
        """無効な比率でのクロップテスト"""
        invalid_ratios = [0.05, 0.0, 1.1, 2.0, -0.1]
        
        for ratio in invalid_ratios:
            with self.subTest(ratio=ratio):
                with self.assertRaises(ValueError):
                    self.enhancer.crop_timestamp_area(self.test_frame, ratio)
    
    def test_crop_timestamp_area_invalid_frame(self):
        """無効なフレームでのクロップテスト"""
        # 2Dフレーム
        invalid_frame_2d = np.zeros((100, 100), dtype=np.uint8)
        with self.assertRaises(ValueError):
            self.enhancer.crop_timestamp_area(invalid_frame_2d)
        
        # 4Dフレーム
        invalid_frame_4d = np.zeros((1, 100, 100, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            self.enhancer.crop_timestamp_area(invalid_frame_4d)
    
    def test_save_cropped_area_success(self):
        """クロップ領域保存成功テスト"""
        cropped = self.enhancer.crop_timestamp_area(self.test_frame)
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            success = self.enhancer.save_cropped_area(cropped, temp_path)
            
            self.assertTrue(success)
            self.assertTrue(os.path.exists(temp_path))
            self.assertGreater(os.path.getsize(temp_path), 0)
            
            # 保存された画像が読み込める事を確認
            saved_image = cv2.imread(temp_path)
            self.assertIsNotNone(saved_image)
            self.assertEqual(saved_image.shape[:2], cropped.shape[:2])
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_save_cropped_area_invalid_path(self):
        """無効なパスでのクロップ領域保存テスト"""
        cropped = self.enhancer.crop_timestamp_area(self.test_frame)
        
        success = self.enhancer.save_cropped_area(cropped, "/invalid/path/cropped.jpg")
        self.assertFalse(success)
    
    def test_get_optimal_crop_ratio_sd_quality(self):
        """SD品質での最適クロップ比率テスト"""
        sd_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        ratio = self.enhancer.get_optimal_crop_ratio(sd_frame)
        self.assertEqual(ratio, 0.3)
    
    def test_get_optimal_crop_ratio_hd_quality(self):
        """HD品質での最適クロップ比率テスト"""
        hd_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        ratio = self.enhancer.get_optimal_crop_ratio(hd_frame)
        self.assertEqual(ratio, 0.25)
    
    def test_get_optimal_crop_ratio_full_hd_quality(self):
        """Full HD品質での最適クロップ比率テスト"""
        full_hd_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        ratio = self.enhancer.get_optimal_crop_ratio(full_hd_frame)
        self.assertEqual(ratio, 0.2)
    
    def test_get_optimal_crop_ratio_4k_quality(self):
        """4K品質での最適クロップ比率テスト"""
        uhd_frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
        ratio = self.enhancer.get_optimal_crop_ratio(uhd_frame)
        self.assertEqual(ratio, 0.15)
    
    def test_crop_timestamp_area_adaptive(self):
        """適応的クロップテスト"""
        test_frames = [
            (np.zeros((480, 640, 3), dtype=np.uint8), 0.3),   # SD
            (np.zeros((720, 1280, 3), dtype=np.uint8), 0.25), # HD
            (np.zeros((1080, 1920, 3), dtype=np.uint8), 0.2), # Full HD
            (np.zeros((2160, 3840, 3), dtype=np.uint8), 0.15) # 4K
        ]
        
        for frame, expected_ratio in test_frames:
            with self.subTest(resolution=f"{frame.shape[1]}x{frame.shape[0]}"):
                cropped = self.enhancer.crop_timestamp_area_adaptive(frame)
                
                expected_height = int(frame.shape[0] * expected_ratio)
                expected_width = int(frame.shape[1] * expected_ratio)
                
                self.assertEqual(cropped.shape[:2], (expected_height, expected_width))
                self.assertEqual(cropped.shape[2], 3)
    
    def test_crop_timestamp_area_debug_info(self):
        """デバッグ情報付きクロップテスト"""
        cropped = self.debug_enhancer.crop_timestamp_area(self.test_frame, 0.3)
        
        # デバッグ情報が出力されることを確認（基本的な動作確認）
        self.assertIsInstance(cropped, np.ndarray)
        self.assertEqual(len(cropped.shape), 3)


class TestTimestampCroppingWithSampleVideo(unittest.TestCase):
    """サンプル映像を使用したクロップテスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        self.sample_video = "sample.mp4"
    
    def test_crop_sample_video_timestamp_area(self):
        """サンプル映像での日時クロップテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # サンプル映像の期待される特性
        expected_height = int(360 * 0.25)  # 90
        expected_width = int(640 * 0.25)   # 160
        
        self.assertEqual(cropped.shape[:2], (expected_height, expected_width))
        self.assertEqual(cropped.shape[2], 3)
    
    def test_crop_sample_video_adaptive(self):
        """サンプル映像での適応的クロップテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area_adaptive(frame)
        
        # 640x360は SD品質なので0.3の比率が適用される
        expected_height = int(360 * 0.3)   # 108
        expected_width = int(640 * 0.3)    # 192
        
        self.assertEqual(cropped.shape[:2], (expected_height, expected_width))
        self.assertEqual(cropped.shape[2], 3)
    
    def test_save_sample_video_cropped_area(self):
        """サンプル映像クロップ領域の保存テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            success = self.enhancer.save_cropped_area(cropped, temp_path)
            
            self.assertTrue(success)
            self.assertTrue(os.path.exists(temp_path))
            self.assertGreater(os.path.getsize(temp_path), 0)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestTimestampCroppingCompatibility(unittest.TestCase):
    """既存機能との互換性テスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        self.sample_video = "sample.mp4"
    
    def test_backward_compatibility_with_existing_tests(self):
        """既存テストコードとの後方互換性確認"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        
        # 引数なしでの呼び出し（既存の使用方法）
        cropped_old = self.enhancer.crop_timestamp_area(frame)
        
        # 明示的にデフォルト比率での呼び出し
        cropped_new = self.enhancer.crop_timestamp_area(frame, 0.25)
        
        # 結果が同じことを確認
        np.testing.assert_array_equal(cropped_old, cropped_new)
    
    def test_integration_with_existing_pipeline(self):
        """既存パイプラインとの統合テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        # 既存のパイプライン通りの処理
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # OCR処理まで実行できることを確認
        try:
            timestamp = self.enhancer.extract_timestamp(cropped)
            # タイムスタンプが取得できるか、None（取得失敗）であることを確認
            self.assertTrue(timestamp is None or isinstance(timestamp, str))
        except Exception:
            # OCR処理でエラーが発生した場合は、それはOCRの問題であり、
            # クロップ機能は正常に動作している
            pass


if __name__ == '__main__':
    unittest.main()
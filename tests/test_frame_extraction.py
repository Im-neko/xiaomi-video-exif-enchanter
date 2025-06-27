#!/usr/bin/env python3
"""
1フレーム目抽出機能の詳細テストファイル
"""

import unittest
import cv2
import numpy as np
import os
import tempfile
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestFrameExtraction(unittest.TestCase):
    """フレーム抽出機能のテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        self.debug_enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        self.sample_video = "sample.mp4"
    
    def test_extract_first_frame_format_validation(self):
        """フレーム抽出時の形式バリデーションテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        
        # フレーム形式の確認
        self.assertIsInstance(frame, np.ndarray)
        self.assertEqual(len(frame.shape), 3, "Frame should be 3-dimensional")
        self.assertEqual(frame.shape[2], 3, "Frame should have 3 color channels")
        self.assertGreater(frame.shape[0], 0, "Frame height should be positive")
        self.assertGreater(frame.shape[1], 0, "Frame width should be positive")
        
        # データ型の確認
        self.assertEqual(frame.dtype, np.uint8, "Frame should be uint8 type")
        
        # 値の範囲確認
        self.assertGreaterEqual(frame.min(), 0, "Frame values should be non-negative")
        self.assertLessEqual(frame.max(), 255, "Frame values should be <= 255")
    
    def test_extract_first_frame_debug_info(self):
        """デバッグ情報付きフレーム抽出テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        # デバッグモードでフレーム抽出
        frame = self.debug_enhancer.extract_first_frame(self.sample_video)
        
        # 基本的な確認
        self.assertIsInstance(frame, np.ndarray)
        self.assertEqual(len(frame.shape), 3)
        self.assertEqual(frame.shape[2], 3)
    
    def test_save_debug_frame_success(self):
        """デバッグフレーム保存成功テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # フレーム保存
            success = self.enhancer.save_debug_frame(frame, temp_path)
            
            self.assertTrue(success, "Frame save should succeed")
            self.assertTrue(os.path.exists(temp_path), "Saved file should exist")
            self.assertGreater(os.path.getsize(temp_path), 0, "Saved file should not be empty")
            
            # 保存されたファイルが読み込める事を確認
            saved_frame = cv2.imread(temp_path)
            self.assertIsNotNone(saved_frame, "Saved frame should be readable")
            self.assertEqual(len(saved_frame.shape), 3)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_save_debug_frame_invalid_path(self):
        """無効なパスでのデバッグフレーム保存テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        
        # 無効なパスでの保存試行
        success = self.enhancer.save_debug_frame(frame, "/invalid/path/debug.jpg")
        self.assertFalse(success, "Frame save should fail with invalid path")
    
    def test_crop_timestamp_area_format_validation(self):
        """タイムスタンプ領域クロップの形式バリデーションテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # クロップされた画像の形式確認
        self.assertIsInstance(cropped, np.ndarray)
        self.assertEqual(len(cropped.shape), 3)
        self.assertEqual(cropped.shape[2], 3)
        
        # サイズが適切に縮小されていることを確認
        self.assertLess(cropped.shape[0], frame.shape[0])
        self.assertLess(cropped.shape[1], frame.shape[1])
        self.assertEqual(cropped.shape[0], frame.shape[0] // 4)
        self.assertEqual(cropped.shape[1], frame.shape[1] // 4)
    
    def test_crop_timestamp_area_invalid_frame(self):
        """無効なフレームでのクロップテスト"""
        # 2Dフレーム（グレースケール）での失敗テスト
        invalid_frame = np.zeros((100, 100), dtype=np.uint8)
        
        with self.assertRaises(ValueError):
            self.enhancer.crop_timestamp_area(invalid_frame)
    
    def test_crop_timestamp_area_debug_info(self):
        """デバッグ情報付きクロップテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.debug_enhancer.extract_first_frame(self.sample_video)
        cropped = self.debug_enhancer.crop_timestamp_area(frame)
        
        # 基本的な確認
        self.assertIsInstance(cropped, np.ndarray)
        self.assertEqual(len(cropped.shape), 3)
    
    def test_frame_ocr_compatibility(self):
        """フレームがOCR処理に適した形式かテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # OCR処理に適した形式の確認
        self.assertEqual(cropped.dtype, np.uint8)
        self.assertGreaterEqual(cropped.min(), 0)
        self.assertLessEqual(cropped.max(), 255)
        
        # 十分なサイズがあることを確認
        self.assertGreater(cropped.shape[0], 10)
        self.assertGreater(cropped.shape[1], 10)


class TestFrameExtractionErrorHandling(unittest.TestCase):
    """フレーム抽出エラーハンドリングのテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
    
    def test_extract_frame_empty_video(self):
        """空の映像ファイルでのフレーム抽出テスト"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            with self.assertRaises(ValueError):
                self.enhancer.extract_first_frame(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_extract_frame_corrupted_video(self):
        """破損した映像ファイルでのフレーム抽出テスト"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_file.write(b"corrupted video data")
            temp_path = temp_file.name
        
        try:
            with self.assertRaises(ValueError):
                self.enhancer.extract_first_frame(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_extract_frame_nonexistent_file(self):
        """存在しないファイルでのフレーム抽出テスト"""
        with self.assertRaises(FileNotFoundError):
            self.enhancer.extract_first_frame("nonexistent_video.mp4")
    
    def test_extract_frame_unsupported_format(self):
        """非サポート形式でのフレーム抽出テスト"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
            temp_file.write(b"not a video file")
            temp_path = temp_file.name
        
        try:
            with self.assertRaises(ValueError):
                self.enhancer.extract_first_frame(temp_path)
        finally:
            os.unlink(temp_path)


class TestFrameExtractionWithSampleVideo(unittest.TestCase):
    """サンプル映像を使用したフレーム抽出テスト"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        self.sample_video = "sample.mp4"
    
    def test_sample_video_frame_extraction(self):
        """サンプル映像でのフレーム抽出テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        
        # サンプル映像の期待される特性
        self.assertEqual(frame.shape[:2], (360, 640))  # Height, Width
        self.assertEqual(frame.shape[2], 3)  # Color channels
        self.assertEqual(frame.dtype, np.uint8)
    
    def test_sample_video_timestamp_area_crop(self):
        """サンプル映像でのタイムスタンプ領域クロップテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # クロップされた領域のサイズ確認
        expected_height = 360 // 4  # 90
        expected_width = 640 // 4   # 160
        
        self.assertEqual(cropped.shape[:2], (expected_height, expected_width))
        self.assertEqual(cropped.shape[2], 3)


if __name__ == '__main__':
    unittest.main()
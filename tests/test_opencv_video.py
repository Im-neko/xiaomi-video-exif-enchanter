#!/usr/bin/env python3
"""
OpenCV映像読み込み機能のテストファイル
"""

import unittest
import cv2
import numpy as np
import os
import tempfile
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestOpenCVVideoReading(unittest.TestCase):
    """OpenCV映像読み込み機能のテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        self.sample_video = "sample.mp4"
    
    def test_get_video_info_success(self):
        """映像情報取得の成功テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        info = self.enhancer.get_video_info(self.sample_video)
        
        # 基本的な情報が含まれていることを確認
        required_keys = ['frame_count', 'fps', 'width', 'height', 
                        'resolution', 'fourcc', 'duration_seconds', 'file_size_bytes']
        for key in required_keys:
            self.assertIn(key, info)
        
        # 値が妥当であることを確認
        self.assertGreater(info['frame_count'], 0)
        self.assertGreater(info['fps'], 0)
        self.assertGreater(info['width'], 0)
        self.assertGreater(info['height'], 0)
        self.assertGreater(info['file_size_bytes'], 0)
        self.assertEqual(info['resolution'], f"{info['width']}x{info['height']}")
    
    def test_get_video_info_file_not_found(self):
        """存在しないファイルの映像情報取得テスト"""
        with self.assertRaises(ValueError):
            self.enhancer.get_video_info("nonexistent.mp4")
    
    def test_is_supported_format_mp4(self):
        """MP4形式のサポート確認テスト"""
        self.assertTrue(self.enhancer.is_supported_format("test.mp4"))
    
    def test_is_supported_format_avi(self):
        """AVI形式のサポート確認テスト"""
        self.assertTrue(self.enhancer.is_supported_format("test.avi"))
    
    def test_is_supported_format_mov(self):
        """MOV形式のサポート確認テスト"""
        self.assertTrue(self.enhancer.is_supported_format("test.mov"))
    
    def test_is_supported_format_mkv(self):
        """MKV形式のサポート確認テスト"""
        self.assertTrue(self.enhancer.is_supported_format("test.mkv"))
    
    def test_is_supported_format_unsupported(self):
        """非サポート形式の確認テスト"""
        self.assertFalse(self.enhancer.is_supported_format("test.txt"))
        self.assertFalse(self.enhancer.is_supported_format("test.jpg"))
        self.assertFalse(self.enhancer.is_supported_format("test.unknown"))
    
    def test_is_supported_format_case_insensitive(self):
        """大文字小文字を区別しない形式確認テスト"""
        self.assertTrue(self.enhancer.is_supported_format("test.MP4"))
        self.assertTrue(self.enhancer.is_supported_format("test.Avi"))
        self.assertTrue(self.enhancer.is_supported_format("test.MOV"))
    
    def test_extract_first_frame_enhanced_validation(self):
        """強化されたフレーム抽出バリデーションテスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        frame = self.enhancer.extract_first_frame(self.sample_video)
        
        # フレームが正常に抽出されたことを確認
        self.assertIsInstance(frame, np.ndarray)
        self.assertEqual(len(frame.shape), 3)  # H, W, C
        self.assertGreater(frame.shape[0], 0)  # Height
        self.assertGreater(frame.shape[1], 0)  # Width
        self.assertEqual(frame.shape[2], 3)    # RGB/BGR channels
    
    def test_extract_first_frame_file_not_found(self):
        """存在しないファイルのフレーム抽出テスト"""
        with self.assertRaises(FileNotFoundError):
            self.enhancer.extract_first_frame("nonexistent.mp4")
    
    def test_extract_first_frame_unsupported_format(self):
        """非サポート形式のフレーム抽出テスト"""
        # 一時的なテキストファイルを作成
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
            temp_file.write(b"not a video file")
            temp_path = temp_file.name
        
        try:
            with self.assertRaises(ValueError):
                self.enhancer.extract_first_frame(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_video_info_with_sample_video(self):
        """サンプル映像での映像情報取得テスト"""
        if not os.path.exists(self.sample_video):
            self.skipTest("Sample video not found")
        
        info = self.enhancer.get_video_info(self.sample_video)
        
        # サンプル映像の期待される特性を確認
        self.assertEqual(info['resolution'], "640x360")
        self.assertGreater(info['fps'], 15.0)  # FPSは15以上であることを確認
        self.assertLess(info['fps'], 25.0)     # FPSは25未満であることを確認
        self.assertGreater(info['duration_seconds'], 0)


class TestVideoReadingErrorHandling(unittest.TestCase):
    """映像読み込みエラーハンドリングのテストクラス"""
    
    def setUp(self):
        """テスト前の準備"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
    
    def test_corrupted_video_handling(self):
        """破損した映像ファイルのハンドリングテスト"""
        # 破損したファイルを模擬（実際には空のmp4ファイル）
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_file.write(b"corrupted video data")
            temp_path = temp_file.name
        
        try:
            with self.assertRaises(ValueError):
                self.enhancer.get_video_info(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_empty_video_file(self):
        """空の映像ファイルのハンドリングテスト"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            with self.assertRaises(ValueError):
                self.enhancer.extract_first_frame(temp_path)
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
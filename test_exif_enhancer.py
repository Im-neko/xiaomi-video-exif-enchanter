#!/usr/bin/env python3
"""
Xiaomi Video EXIF Enhancer のユニットテスト
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from datetime import datetime
import cv2
import os
import tempfile
from pathlib import Path

from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestXiaomiVideoEXIFEnhancer(unittest.TestCase):
    """XiaomiVideoEXIFEnhancer のテストクラス"""
    
    def setUp(self):
        """Each test 前のセットアップ"""
        with patch('easyocr.Reader'):
            self.enhancer = XiaomiVideoEXIFEnhancer()
    
    def test_crop_timestamp_area(self):
        """タイムスタンプ領域のクロップテスト"""
        # 800x600 のダミーフレームを作成
        frame = np.zeros((600, 800, 3), dtype=np.uint8)
        
        cropped = self.enhancer.crop_timestamp_area(frame)
        
        # 左上 1/4 のサイズでクロップされることを確認
        expected_height = 600 // 4  # 150
        expected_width = 800 // 4   # 200
        
        self.assertEqual(cropped.shape[0], expected_height)
        self.assertEqual(cropped.shape[1], expected_width)
        self.assertEqual(cropped.shape[2], 3)  # RGB channels
    
    def test_parse_timestamp_valid_formats(self):
        """有効なタイムスタンプ形式のテスト"""
        # ハイフン区切り形式
        result = self.enhancer.parse_timestamp("2024-03-15 14:30:25")
        expected = datetime(2024, 3, 15, 14, 30, 25)
        self.assertEqual(result, expected)
        
        # スラッシュ区切り形式
        result = self.enhancer.parse_timestamp("2024/03/15 14:30:25")
        expected = datetime(2024, 3, 15, 14, 30, 25)
        self.assertEqual(result, expected)
        
        # 区切りなし形式
        result = self.enhancer.parse_timestamp("20240315 14:30:25")
        expected = datetime(2024, 3, 15, 14, 30, 25)
        self.assertEqual(result, expected)
    
    def test_parse_timestamp_invalid_formats(self):
        """無効なタイムスタンプ形式のテスト"""
        # None の場合
        result = self.enhancer.parse_timestamp(None)
        self.assertIsNone(result)
        
        # 空文字列の場合
        result = self.enhancer.parse_timestamp("")
        self.assertIsNone(result)
        
        # 無効な日付の場合
        result = self.enhancer.parse_timestamp("2024-13-35 25:70:80")
        self.assertIsNone(result)
        
        # フォーマットが合わない場合
        result = self.enhancer.parse_timestamp("invalid timestamp")
        self.assertIsNone(result)
    
    @patch('cv2.VideoCapture')
    def test_extract_first_frame_success(self, mock_video_capture):
        """フレーム抽出成功テスト"""
        # Mock の設定
        mock_cap = Mock()
        mock_video_capture.return_value = mock_cap
        
        # ダミーフレームを作成
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, dummy_frame)
        
        result = self.enhancer.extract_first_frame("dummy_path.mp4")
        
        # 結果の確認
        np.testing.assert_array_equal(result, dummy_frame)
        mock_cap.release.assert_called_once()
    
    @patch('cv2.VideoCapture')
    def test_extract_first_frame_failure(self, mock_video_capture):
        """フレーム抽出失敗テスト"""
        mock_cap = Mock()
        mock_video_capture.return_value = mock_cap
        mock_cap.read.return_value = (False, None)
        
        with self.assertRaises(ValueError) as context:
            self.enhancer.extract_first_frame("dummy_path.mp4")
        
        self.assertIn("Failed to read video", str(context.exception))
        mock_cap.release.assert_called_once()
    
    def test_extract_timestamp_with_mock_ocr(self):
        """OCR をモックしたタイムスタンプ抽出テスト"""
        # Mock OCR results
        mock_results = [
            ([(0, 0), (100, 0), (100, 30), (0, 30)], "2024-03-15 14:30:25", 0.8),
            ([(0, 40), (100, 40), (100, 70), (0, 70)], "some other text", 0.9)
        ]
        
        self.enhancer.reader.readtext.return_value = mock_results
        
        dummy_frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = self.enhancer.extract_timestamp(dummy_frame)
        
        self.assertEqual(result, "2024-03-15 14:30:25")
    
    def test_extract_timestamp_no_valid_timestamp(self):
        """有効なタイムスタンプがない場合のテスト"""
        mock_results = [
            ([(0, 0), (100, 0), (100, 30), (0, 30)], "some random text", 0.8),
            ([(0, 40), (100, 40), (100, 70), (0, 70)], "more text", 0.9)
        ]
        
        self.enhancer.reader.readtext.return_value = mock_results
        
        dummy_frame = np.zeros((100, 200, 3), dtype=np.uint8)
        result = self.enhancer.extract_timestamp(dummy_frame)
        
        self.assertIsNone(result)
    
    @patch('ffmpeg.run')
    @patch('ffmpeg.output')
    @patch('ffmpeg.input')
    def test_add_exif_data_success(self, mock_input, mock_output, mock_run):
        """EXIFデータ追加成功テスト"""
        # Mock の設定
        mock_stream = Mock()
        mock_input.return_value = mock_stream
        mock_output.return_value = mock_stream
        mock_stream.overwrite_output.return_value = mock_stream
        
        timestamp = datetime(2024, 3, 15, 14, 30, 25)
        location = "リビング"
        
        result = self.enhancer.add_exif_data(
            "input.mp4", "output.mp4", timestamp, location
        )
        
        self.assertTrue(result)
        mock_run.assert_called_once()
    
    @patch('ffmpeg.run')
    @patch('ffmpeg.output')
    @patch('ffmpeg.input')
    def test_add_exif_data_ffmpeg_error(self, mock_input, mock_output, mock_run):
        """FFmpeg エラーのテスト"""
        import ffmpeg
        
        mock_stream = Mock()
        mock_input.return_value = mock_stream
        mock_output.return_value = mock_stream
        mock_stream.overwrite_output.return_value = mock_stream
        mock_run.side_effect = ffmpeg.Error("FFmpeg error", "", "")
        
        timestamp = datetime(2024, 3, 15, 14, 30, 25)
        
        result = self.enhancer.add_exif_data(
            "input.mp4", "output.mp4", timestamp
        )
        
        self.assertFalse(result)
    
    @patch.object(XiaomiVideoEXIFEnhancer, 'add_exif_data')
    @patch.object(XiaomiVideoEXIFEnhancer, 'parse_timestamp')
    @patch.object(XiaomiVideoEXIFEnhancer, 'extract_timestamp')
    @patch.object(XiaomiVideoEXIFEnhancer, 'crop_timestamp_area')
    @patch.object(XiaomiVideoEXIFEnhancer, 'extract_first_frame')
    def test_process_video_success(self, mock_extract_frame, mock_crop, 
                                  mock_extract_ts, mock_parse_ts, mock_add_exif):
        """動画処理成功テスト"""
        # Mock の設定
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cropped_frame = np.zeros((120, 160, 3), dtype=np.uint8)
        timestamp_str = "2024-03-15 14:30:25"
        timestamp = datetime(2024, 3, 15, 14, 30, 25)
        
        mock_extract_frame.return_value = dummy_frame
        mock_crop.return_value = cropped_frame
        mock_extract_ts.return_value = timestamp_str
        mock_parse_ts.return_value = timestamp
        mock_add_exif.return_value = True
        
        result = self.enhancer.process_video("input.mp4", "output.mp4", "リビング")
        
        self.assertTrue(result)
        mock_extract_frame.assert_called_once_with("input.mp4")
        mock_crop.assert_called_once_with(dummy_frame)
        mock_extract_ts.assert_called_once_with(cropped_frame)
        mock_parse_ts.assert_called_once_with(timestamp_str)
        mock_add_exif.assert_called_once_with("input.mp4", "output.mp4", timestamp, "リビング")


class TestMainFunction(unittest.TestCase):
    """main 関数のテストクラス"""
    
    @patch('sys.argv', ['exif_enhancer.py', 'nonexistent.mp4'])
    @patch('os.path.exists')
    def test_main_file_not_found(self, mock_exists):
        """入力ファイルが存在しない場合のテスト"""
        from exif_enhancer import main
        
        mock_exists.return_value = False
        
        with self.assertRaises(SystemExit) as context:
            main()
        
        self.assertEqual(context.exception.code, 1)
    
    @patch('sys.argv', ['exif_enhancer.py', 'input.mp4'])
    @patch('os.path.exists')
    @patch.object(XiaomiVideoEXIFEnhancer, 'process_video')
    @patch('easyocr.Reader')
    def test_main_success(self, mock_reader, mock_process, mock_exists):
        """正常処理のテスト"""
        from exif_enhancer import main
        
        mock_exists.return_value = True
        mock_process.return_value = True
        
        with self.assertRaises(SystemExit) as context:
            main()
        
        self.assertEqual(context.exception.code, 0)
        mock_process.assert_called_once()


if __name__ == '__main__':
    unittest.main()
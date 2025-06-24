#!/usr/bin/env python3
"""
映像ファイルエラーハンドリングのテストファイル
Issue #14: 映像ファイル読み込みエラーのハンドリング
"""

import unittest
import os
import tempfile
import stat
from pathlib import Path
from exif_enhancer import XiaomiVideoEXIFEnhancer, SUPPORTED_VIDEO_EXTENSIONS
from video_error_handler import VideoErrorHandler, VideoErrorType


class TestVideoErrorHandling(unittest.TestCase):
    """映像ファイルエラーハンドリングのテスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        self.error_handler = VideoErrorHandler(debug=True)
        self.temp_dir = tempfile.mkdtemp()
        
        # テスト用ファイルのパス
        self.empty_file = os.path.join(self.temp_dir, "empty.mp4")
        self.corrupted_file = os.path.join(self.temp_dir, "corrupted.mp4")
        self.unsupported_file = os.path.join(self.temp_dir, "unsupported.xyz")
        
        # テストファイル作成
        self._create_test_files()
    
    def tearDown(self):
        """テスト後処理"""
        # テストファイル削除
        for file_path in [self.empty_file, self.corrupted_file, self.unsupported_file]:
            try:
                os.remove(file_path)
            except FileNotFoundError:
                pass
        
        try:
            os.rmdir(self.temp_dir)
        except OSError:
            pass
    
    def _create_test_files(self):
        """テスト用エラーファイルを作成"""
        # 空ファイル
        with open(self.empty_file, 'w') as f:
            pass
        
        # 破損ファイル（mp4ヘッダーがない）
        with open(self.corrupted_file, 'w') as f:
            f.write("This is not a valid video file")
        
        # サポートされていない拡張子
        with open(self.unsupported_file, 'w') as f:
            f.write("unsupported format")
    
    def test_file_not_found_error(self):
        """存在しないファイルのエラーハンドリングテスト"""
        nonexistent_file = "nonexistent_video.mp4"
        
        with self.assertRaises(FileNotFoundError) as context:
            self.enhancer.extract_first_frame(nonexistent_file)
        
        # エラーレポート確認
        error_report = self.error_handler.create_error_report(nonexistent_file)
        self.assertEqual(error_report['error_type'], 'file_not_found')
        self.assertIn('ファイルが見つかりません', error_report['user_message'])
        self.assertIn('ファイルパスを確認する', error_report['recovery_suggestions'])
    
    def test_empty_file_error(self):
        """空ファイルのエラーハンドリングテスト"""
        with self.assertRaises(ValueError) as context:
            self.enhancer.extract_first_frame(self.empty_file)
        
        # エラーレポート確認
        error_report = self.error_handler.create_error_report(self.empty_file)
        self.assertEqual(error_report['error_type'], 'empty_file')
        self.assertIn('ファイルが空です', error_report['user_message'])
        self.assertEqual(error_report['technical_details']['file_size'], 0)
    
    def test_corrupted_file_error(self):
        """破損ファイルのエラーハンドリングテスト"""
        with self.assertRaises(ValueError) as context:
            self.enhancer.extract_first_frame(self.corrupted_file)
        
        # エラーレポート確認
        error_report = self.error_handler.create_error_report(self.corrupted_file)
        self.assertEqual(error_report['error_type'], 'corrupted_file')
        self.assertIn('破損している可能性があります', error_report['user_message'])
        self.assertIn('元のファイルを再取得する', error_report['recovery_suggestions'])
    
    def test_unsupported_format_error(self):
        """サポートされていない形式のエラーハンドリングテスト"""
        with self.assertRaises(ValueError) as context:
            self.enhancer.extract_first_frame(self.unsupported_file)
        
        # エラーレポート確認
        error_report = self.error_handler.create_error_report(self.unsupported_file)
        self.assertEqual(error_report['error_type'], 'unsupported_format')
        self.assertIn('サポートされていないファイル形式です', error_report['user_message'])
        self.assertIn('.xyz', error_report['user_message'])
    
    def test_valid_file_processing(self):
        """正常ファイルの処理テスト"""
        # sample.mp4が存在する場合のテスト
        sample_file = "sample.mp4"
        if os.path.exists(sample_file):
            try:
                frame = self.enhancer.extract_first_frame(sample_file)
                self.assertIsNotNone(frame)
                self.assertEqual(len(frame.shape), 3)
                self.assertEqual(frame.shape[2], 3)
            except Exception as e:
                self.fail(f"Valid file processing failed: {e}")
    
    def test_error_report_structure(self):
        """エラーレポートの構造テスト"""
        error_report = self.error_handler.create_error_report("nonexistent.mp4")
        
        # 必要なキーの存在確認
        required_keys = [
            'timestamp', 'file_path', 'error_type', 'error_message',
            'user_message', 'recovery_suggestions', 'technical_details', 'system_info'
        ]
        
        for key in required_keys:
            self.assertIn(key, error_report, f"Missing key: {key}")
        
        # 技術詳細の構造確認
        tech_details = error_report['technical_details']
        self.assertIn('file_exists', tech_details)
        self.assertIn('file_size', tech_details)
        self.assertIn('permissions', tech_details)
        
        # システム情報の確認
        sys_info = error_report['system_info']
        self.assertIn('opencv_version', sys_info)
        self.assertIn('python_version', sys_info)
        self.assertIn('platform', sys_info)
    
    def test_error_handler_validate_video_file(self):
        """エラーハンドラーのファイル検証テスト"""
        # 存在しないファイル
        with self.assertRaises(FileNotFoundError):
            self.error_handler.validate_video_file("nonexistent.mp4", raise_on_error=True)
        
        # 空ファイル
        with self.assertRaises(ValueError):
            self.error_handler.validate_video_file(self.empty_file, raise_on_error=True)
        
        # サポートされていない形式
        with self.assertRaises(ValueError):
            self.error_handler.validate_video_file(self.unsupported_file, raise_on_error=True)
        
        # 例外を発生させない場合
        result = self.error_handler.validate_video_file("nonexistent.mp4", raise_on_error=False)
        self.assertFalse(result)
    
    def test_user_friendly_messages(self):
        """ユーザーフレンドリーメッセージのテスト"""
        test_cases = [
            ("nonexistent.mp4", VideoErrorType.FILE_NOT_FOUND, "ファイルが見つかりません"),
            (self.empty_file, VideoErrorType.EMPTY_FILE, "ファイルが空です"),
            (self.corrupted_file, VideoErrorType.CORRUPTED_FILE, "破損している可能性があります"),
            (self.unsupported_file, VideoErrorType.UNSUPPORTED_FORMAT, "サポートされていないファイル形式です")
        ]
        
        for file_path, expected_type, expected_message_part in test_cases:
            error_type, message, details = self.error_handler.analyze_file_error(file_path)
            user_message = self.error_handler.get_user_friendly_message(error_type, details)
            
            self.assertEqual(error_type, expected_type)
            self.assertIn(expected_message_part, user_message)
            self.assertIn("💡", user_message)  # ヒントが含まれていることを確認
    
    def test_recovery_suggestions(self):
        """回復提案のテスト"""
        suggestions_map = {
            VideoErrorType.FILE_NOT_FOUND: "ファイルパスを確認する",
            VideoErrorType.UNSUPPORTED_FORMAT: "サポートされている形式に変換する",
            VideoErrorType.CORRUPTED_FILE: "元のファイルを再取得する",
            VideoErrorType.PERMISSION_DENIED: "ファイルの読み取り権限を付与する"
        }
        
        for error_type, expected_suggestion in suggestions_map.items():
            suggestions = self.error_handler.get_recovery_suggestions(error_type)
            self.assertIsInstance(suggestions, list)
            self.assertGreater(len(suggestions), 0)
            self.assertTrue(any(expected_suggestion in suggestion for suggestion in suggestions))
    
    def test_supported_video_extensions(self):
        """サポートされている映像拡張子のテスト"""
        # 実際のSUPPORTED_VIDEO_EXTENSIONSから取得
        supported_extensions = SUPPORTED_VIDEO_EXTENSIONS
        
        for ext in supported_extensions:
            self.assertTrue(self.enhancer.is_supported_format(f"test{ext}"))
        
        # サポートされていない拡張子
        unsupported_extensions = ['.xyz', '.txt', '.pdf', '.doc']
        for ext in unsupported_extensions:
            self.assertFalse(self.enhancer.is_supported_format(f"test{ext}"))


class TestVideoErrorIntegration(unittest.TestCase):
    """映像エラーハンドリングの統合テスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)  # 非デバッグモードでテスト
    
    def test_error_handling_in_non_debug_mode(self):
        """非デバッグモードでのエラーハンドリング"""
        # 標準出力をキャプチャして、適切なメッセージが表示されることを確認
        import io
        import sys
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            with self.assertRaises(FileNotFoundError):
                self.enhancer.extract_first_frame("nonexistent.mp4")
        finally:
            sys.stdout = sys.__stdout__
        
        output = captured_output.getvalue()
        self.assertIn("映像ファイルエラー", output)
        self.assertIn("ファイルが見つかりません", output)
    
    def test_error_handling_graceful_degradation(self):
        """エラーハンドリングの段階的劣化テスト"""
        # エラーハンドラーが利用できない場合でも基本的な動作は継続することを確認
        enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        
        # error_handlerを一時的に無効化
        original_error_handler = enhancer.error_handler
        enhancer.error_handler = None
        
        with self.assertRaises((FileNotFoundError, AttributeError)):
            enhancer.extract_first_frame("nonexistent.mp4")
        
        # 復元
        enhancer.error_handler = original_error_handler


if __name__ == '__main__':
    # テスト実行時の詳細出力
    unittest.main(verbosity=2, buffer=False)
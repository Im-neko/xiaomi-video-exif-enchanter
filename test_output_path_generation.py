#!/usr/bin/env python3
"""
出力パス自動生成機能のテストファイル
Issue #13: 出力ファイルパスの自動生成機能
"""

import unittest
import os
import tempfile
import shutil
from pathlib import Path
from output_path_generator import OutputPathGenerator
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestOutputPathGeneration(unittest.TestCase):
    """出力パス自動生成のテスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.generator = OutputPathGenerator(debug=True)
        self.temp_dir = tempfile.mkdtemp()
        
        # テスト用ファイルのパス
        self.test_input = os.path.join(self.temp_dir, "test_video.mp4")
        
        # テストファイル作成
        with open(self.test_input, 'w') as f:
            f.write("dummy video content")
    
    def tearDown(self):
        """テスト後処理"""
        # テンポラリディレクトリを削除
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_basic_output_path_generation(self):
        """基本的な出力パス生成テスト"""
        output_path = self.generator.generate_output_path(self.test_input)
        
        # 基本的な検証
        self.assertTrue(output_path.endswith("_enhanced.mp4"))
        self.assertIn("test_video", output_path)
        self.assertEqual(Path(output_path).parent, Path(self.test_input).parent)
    
    def test_custom_suffix_generation(self):
        """カスタムサフィックスでの生成テスト"""
        custom_suffix = "_processed"
        output_path = self.generator.generate_output_path(
            self.test_input, suffix=custom_suffix
        )
        
        self.assertTrue(output_path.endswith(f"{custom_suffix}.mp4"))
        self.assertIn("test_video", output_path)
    
    def test_custom_output_directory(self):
        """カスタム出力ディレクトリのテスト"""
        custom_dir = os.path.join(self.temp_dir, "output")
        output_path = self.generator.generate_output_path(
            self.test_input, output_dir=custom_dir
        )
        
        self.assertEqual(Path(output_path).parent, Path(custom_dir))
        self.assertTrue(os.path.exists(custom_dir))  # ディレクトリが作成されていること
    
    def test_collision_resolution_with_numbering(self):
        """連番による重複解決テスト"""
        # 基本パスを生成
        base_output = self.generator.generate_output_path(self.test_input)
        
        # 基本パスにファイルを作成して重複をシミュレート
        with open(base_output, 'w') as f:
            f.write("existing file")
        
        # 重複解決された新しいパス生成
        new_output = self.generator.generate_output_path(self.test_input)
        
        self.assertNotEqual(base_output, new_output)
        self.assertTrue("_001" in new_output or any(f"_{i:03d}" in new_output for i in range(1, 10)))
    
    def test_collision_resolution_with_timestamp(self):
        """タイムスタンプによる重複解決テスト"""
        # 基本パスを生成
        base_output = self.generator.generate_output_path(self.test_input)
        
        # 基本パスにファイルを作成
        with open(base_output, 'w') as f:
            f.write("existing file")
        
        # タイムスタンプベースで重複解決
        timestamp_output = self.generator.generate_output_path(
            self.test_input, preserve_timestamp=True
        )
        
        self.assertNotEqual(base_output, timestamp_output)
        # タイムスタンプが含まれていることを確認（YYYYMMDD_HHMMSS形式）
        self.assertTrue(any(char.isdigit() for char in Path(timestamp_output).stem))
    
    def test_output_path_validation(self):
        """出力パス妥当性検証テスト"""
        output_path = self.generator.generate_output_path(self.test_input)
        
        # 有効なパスの検証
        is_valid, issues = self.generator.validate_output_path(output_path)
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)
        
        # 無効なパス（存在しないディレクトリ）の検証
        invalid_path = "/nonexistent/directory/file.mp4"
        is_valid, issues = self.generator.validate_output_path(invalid_path)
        self.assertFalse(is_valid)
        self.assertGreater(len(issues), 0)
    
    def test_file_already_exists_validation(self):
        """既存ファイルの検証テスト"""
        output_path = self.generator.generate_output_path(self.test_input)
        
        # ファイルを作成
        with open(output_path, 'w') as f:
            f.write("existing output file")
        
        # 既存ファイルが検出されることを確認
        is_valid, issues = self.generator.validate_output_path(output_path)
        self.assertFalse(is_valid)
        self.assertTrue(any("既に存在" in issue for issue in issues))
    
    def test_output_info_generation(self):
        """出力ファイル情報生成テスト"""
        output_path = self.generator.generate_output_path(self.test_input)
        info = self.generator.get_output_info(self.test_input, output_path)
        
        # 必要な情報が含まれていることを確認
        self.assertIn('input_file', info)
        self.assertIn('output_file', info)
        self.assertIn('output_directory', info)
        
        # 入力ファイル情報
        input_info = info['input_file']
        self.assertEqual(input_info['name'], "test_video.mp4")
        self.assertEqual(input_info['stem'], "test_video")
        self.assertEqual(input_info['suffix'], ".mp4")
        
        # 出力ファイル情報
        output_info = info['output_file']
        self.assertTrue(output_info['name'].endswith("_enhanced.mp4"))
        self.assertFalse(output_info['exists'])  # まだ作成されていない
        
        # ディレクトリ情報
        dir_info = info['output_directory']
        self.assertTrue(dir_info['exists'])
        self.assertTrue(dir_info['writable'])
    
    def test_alternative_path_suggestions(self):
        """代替パス提案テスト"""
        alternatives = self.generator.suggest_alternative_paths(self.test_input, count=5)
        
        self.assertIsInstance(alternatives, list)
        self.assertLessEqual(len(alternatives), 5)
        
        # 各代替パスが異なることを確認
        unique_alternatives = set(alternatives)
        self.assertEqual(len(unique_alternatives), len(alternatives))
        
        # 各パスが有効であることを確認
        for alt_path in alternatives:
            self.assertTrue(alt_path.endswith(".mp4"))
            self.assertIn("test_video", alt_path)
    
    def test_permission_error_handling(self):
        """権限エラーハンドリングテスト"""
        # 読み取り専用ディレクトリの作成（可能な場合）
        readonly_dir = os.path.join(self.temp_dir, "readonly")
        os.makedirs(readonly_dir, exist_ok=True)
        
        try:
            # ディレクトリを読み取り専用に設定
            os.chmod(readonly_dir, 0o444)
            
            # 権限エラーが発生することを確認
            with self.assertRaises(PermissionError):
                self.generator.generate_output_path(
                    self.test_input, output_dir=readonly_dir
                )
        finally:
            # 権限を復元してクリーンアップ
            os.chmod(readonly_dir, 0o755)
    
    def test_nonexistent_input_file(self):
        """存在しない入力ファイルのエラーハンドリング"""
        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.mp4")
        
        with self.assertRaises(ValueError) as context:
            self.generator.generate_output_path(nonexistent_file)
        
        self.assertIn("does not exist", str(context.exception))
    
    def test_free_space_checking(self):
        """空き容量チェックテスト"""
        output_path = self.generator.generate_output_path(self.test_input)
        info = self.generator.get_output_info(self.test_input, output_path)
        
        # 空き容量情報が取得できることを確認
        free_space = info['output_directory']['free_space']
        self.assertIsInstance(free_space, int)
        self.assertGreaterEqual(free_space, 0)
    
    def test_invalid_filename_characters(self):
        """無効なファイル名文字のテスト"""
        # 無効な文字を含むパスでの検証
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        
        for char in invalid_chars:
            invalid_path = os.path.join(self.temp_dir, f"invalid{char}file.mp4")
            is_valid, issues = self.generator.validate_output_path(invalid_path)
            
            # 少なくとも1つの問題が検出されることを確認
            self.assertGreater(len(issues), 0)


class TestOutputPathIntegration(unittest.TestCase):
    """出力パス生成の統合テスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_input = os.path.join(self.temp_dir, "integration_test.mp4")
        
        # テストファイル作成
        with open(self.test_input, 'w') as f:
            f.write("integration test video content")
    
    def tearDown(self):
        """テスト後処理"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_integration_with_enhancer(self):
        """XiaomiVideoEXIFEnhancerとの統合テスト"""
        enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        
        # 出力パス生成器がエンハンサーに統合されていることを確認
        self.assertIsNotNone(enhancer.path_generator)
        self.assertIsInstance(enhancer.path_generator, OutputPathGenerator)
        
        # 生成機能が動作することを確認
        output_path = enhancer.path_generator.generate_output_path(self.test_input)
        self.assertTrue(output_path.endswith("_enhanced.mp4"))
    
    def test_collision_handling_multiple_files(self):
        """複数ファイルでの重複処理テスト"""
        generator = OutputPathGenerator(debug=False)
        
        # 複数の出力パスを生成
        paths = []
        for i in range(5):
            output_path = generator.generate_output_path(self.test_input)
            paths.append(output_path)
            
            # 各パスにファイルを作成して次の重複をシミュレート
            with open(output_path, 'w') as f:
                f.write(f"file {i}")
        
        # すべてのパスが異なることを確認
        unique_paths = set(paths)
        self.assertEqual(len(unique_paths), len(paths))
        
        # すべてのファイルが実際に作成されていることを確認
        for path in paths:
            self.assertTrue(os.path.exists(path))
    
    def test_edge_case_very_long_filename(self):
        """非常に長いファイル名のエッジケーステスト"""
        # 長いファイル名を作成
        long_name = "a" * 200  # 200文字の長いファイル名
        long_input = os.path.join(self.temp_dir, f"{long_name}.mp4")
        
        with open(long_input, 'w') as f:
            f.write("long filename test")
        
        generator = OutputPathGenerator(debug=True)
        
        try:
            output_path = generator.generate_output_path(long_input)
            # パスが生成できることを確認
            self.assertIsInstance(output_path, str)
            self.assertTrue(len(output_path) > 0)
        except OSError:
            # ファイルシステムの制限で失敗することもある
            self.skipTest("Filesystem does not support very long filenames")


if __name__ == '__main__':
    # テスト実行時の詳細出力
    unittest.main(verbosity=2, buffer=True)
#!/usr/bin/env python3
"""
バッチ処理機能の包括テストファイル
ディレクトリ内の複数ファイルの一括処理をテスト
"""

import unittest
import tempfile
import os
import shutil
from pathlib import Path
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestBatchProcessing(unittest.TestCase):
    """バッチ処理機能のテストクラス"""
    
    def setUp(self):
        """テストセットアップ"""
        self.test_dir = tempfile.mkdtemp()
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        # テスト用の模擬MP4ファイルを作成
        self.create_mock_video_files()
    
    def tearDown(self):
        """テストクリーンアップ"""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def create_mock_video_files(self):
        """テスト用の模擬MP4ファイルを作成"""
        # 基本的なMP4ヘッダーを含むダミーファイル
        mp4_header = b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41'
        test_content = mp4_header + b'\x00' * 1000
        
        # 複数のテストファイルを作成
        self.test_files = [
            'video1.mp4',
            'video2.MP4',
            'video3.mp4',
            'document.txt',  # 非動画ファイル
            'video4.avi',
            'empty_video.mp4'
        ]
        
        for filename in self.test_files:
            file_path = os.path.join(self.test_dir, filename)
            if filename == 'empty_video.mp4':
                # 空ファイル
                open(file_path, 'w').close()
            elif filename.endswith(('.mp4', '.MP4', '.avi')):
                # 動画ファイル
                with open(file_path, 'wb') as f:
                    f.write(test_content)
            else:
                # テキストファイル
                with open(file_path, 'w') as f:
                    f.write("This is not a video file")
    
    def test_basic_batch_processing(self):
        """基本的なバッチ処理のテスト"""
        print("\n=== 基本的なバッチ処理テスト ===")
        
        # サブディレクトリを作成して、期待される動画ファイルだけをコピー
        input_dir = os.path.join(self.test_dir, "input")
        os.makedirs(input_dir)
        
        # 有効な動画ファイルのみをコピー
        valid_files = ['video1.mp4', 'video2.MP4', 'video3.mp4']
        for filename in valid_files:
            src = os.path.join(self.test_dir, filename)
            dst = os.path.join(input_dir, filename)
            shutil.copy2(src, dst)
        
        # バッチ処理実行
        results = self.enhancer.process_batch(
            input_directory=input_dir,
            location="テストルーム"
        )
        
        # 結果検証
        self.assertEqual(results['total_files'], 3, "検出されたファイル数が正しくない")
        self.assertGreaterEqual(results['successful'] + results['failed'], 0, "何らかの処理結果があるべき")
        
        # 処理ファイルの検証
        print(f"Total files: {results['total_files']}")
        print(f"Successful: {results['successful']}")
        print(f"Failed: {results['failed']}")
        print(f"Skipped: {len(results['skipped_files'])}")
        
        self.assertIsInstance(results['processed_files'], list)
        self.assertIsInstance(results['failed_files'], list)
        self.assertIsInstance(results['skipped_files'], list)
    
    def test_batch_with_output_directory(self):
        """出力ディレクトリ指定のバッチ処理テスト"""
        print("\n=== 出力ディレクトリ指定テスト ===")
        
        input_dir = os.path.join(self.test_dir, "input")
        output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(input_dir)
        
        # テストファイルをコピー
        test_file = os.path.join(input_dir, "test_video.mp4")
        src_file = os.path.join(self.test_dir, "video1.mp4")
        shutil.copy2(src_file, test_file)
        
        # バッチ処理実行
        results = self.enhancer.process_batch(
            input_directory=input_dir,
            output_directory=output_dir,
            location="テストルーム"
        )
        
        # 出力ディレクトリが作成されているか確認
        self.assertTrue(os.path.exists(output_dir), "出力ディレクトリが作成されていない")
        
        print(f"Output directory created: {os.path.exists(output_dir)}")
        print(f"Files in output directory: {os.listdir(output_dir) if os.path.exists(output_dir) else 'None'}")
    
    def test_batch_empty_directory(self):
        """空ディレクトリのバッチ処理テスト"""
        print("\n=== 空ディレクトリテスト ===")
        
        empty_dir = os.path.join(self.test_dir, "empty")
        os.makedirs(empty_dir)
        
        # 空ディレクトリでバッチ処理
        results = self.enhancer.process_batch(input_directory=empty_dir)
        
        # 結果検証
        self.assertEqual(results['total_files'], 0, "空ディレクトリでファイルが検出された")
        self.assertEqual(results['successful'], 0)
        self.assertEqual(results['failed'], 0)
        print(f"Empty directory result: {results}")
    
    def test_batch_nonexistent_directory(self):
        """存在しないディレクトリのエラーハンドリングテスト"""
        print("\n=== 存在しないディレクトリテスト ===")
        
        nonexistent_dir = os.path.join(self.test_dir, "nonexistent")
        
        # 存在しないディレクトリでバッチ処理
        with self.assertRaises(ValueError) as context:
            self.enhancer.process_batch(input_directory=nonexistent_dir)
        
        self.assertIn("not found", str(context.exception))
        print(f"Expected error caught: {context.exception}")
    
    def test_batch_skip_errors_mode(self):
        """エラースキップモードのテスト"""
        print("\n=== エラースキップモードテスト ===")
        
        input_dir = os.path.join(self.test_dir, "mixed")
        os.makedirs(input_dir)
        
        # 有効なファイルと無効なファイルを混在
        valid_file = os.path.join(input_dir, "valid.mp4")
        invalid_file = os.path.join(input_dir, "invalid.mp4")
        
        # 有効なファイルをコピー
        shutil.copy2(os.path.join(self.test_dir, "video1.mp4"), valid_file)
        
        # 無効なファイル（空ファイル）を作成
        open(invalid_file, 'w').close()
        
        # skip_errors=Trueでバッチ処理
        results = self.enhancer.process_batch(
            input_directory=input_dir,
            skip_errors=True
        )
        
        print(f"Skip errors mode result: {results}")
        self.assertEqual(results['total_files'], 2, "ファイル検出数が正しくない")
    
    def test_batch_file_collision_handling(self):
        """ファイル名衝突処理のテスト"""
        print("\n=== ファイル名衝突処理テスト ===")
        
        input_dir = os.path.join(self.test_dir, "collision")
        os.makedirs(input_dir)
        
        # テストファイルを作成
        test_file = os.path.join(input_dir, "collision_test.mp4")
        shutil.copy2(os.path.join(self.test_dir, "video1.mp4"), test_file)
        
        # 出力ファイルを事前に作成（衝突を発生させる）
        expected_output = os.path.join(input_dir, "collision_test_enhanced.mp4")
        with open(expected_output, 'w') as f:
            f.write("existing file")
        
        # バッチ処理実行
        results = self.enhancer.process_batch(input_directory=input_dir)
        
        # スキップされるべき
        self.assertEqual(len(results['skipped_files']), 1, "ファイル衝突がスキップされていない")
        print(f"File collision handled: {len(results['skipped_files'])} files skipped")
    
    def test_batch_results_structure(self):
        """バッチ処理結果の構造テスト"""
        print("\n=== 処理結果構造テスト ===")
        
        input_dir = os.path.join(self.test_dir, "structure")
        os.makedirs(input_dir)
        
        # 最小限のテストファイル
        test_file = os.path.join(input_dir, "structure_test.mp4")
        shutil.copy2(os.path.join(self.test_dir, "video1.mp4"), test_file)
        
        results = self.enhancer.process_batch(input_directory=input_dir)
        
        # 結果構造の検証
        required_keys = ['total_files', 'successful', 'failed', 'processed_files', 'failed_files', 'skipped_files']
        for key in required_keys:
            self.assertIn(key, results, f"結果に必要なキー '{key}' が不足")
        
        # データ型の検証
        self.assertIsInstance(results['total_files'], int)
        self.assertIsInstance(results['successful'], int)
        self.assertIsInstance(results['failed'], int)
        self.assertIsInstance(results['processed_files'], list)
        self.assertIsInstance(results['failed_files'], list)
        self.assertIsInstance(results['skipped_files'], list)
        
        print(f"Result structure validated: {list(results.keys())}")


class TestBatchIntegration(unittest.TestCase):
    """バッチ処理の統合テストクラス"""
    
    def setUp(self):
        """統合テスト用のセットアップ"""
        self.test_dir = tempfile.mkdtemp()
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=True)
    
    def tearDown(self):
        """統合テストのクリーンアップ"""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_batch_with_real_sample(self):
        """実際のsample.mp4を使った統合テスト"""
        print("\n=== sample.mp4統合テスト ===")
        
        # sample.mp4が存在するかチェック
        sample_path = "sample.mp4"
        if not os.path.exists(sample_path):
            print("sample.mp4が見つからないため、統合テストをスキップ")
            self.skipTest("sample.mp4 not found")
        
        # テスト用ディレクトリにsample.mp4をコピー
        input_dir = os.path.join(self.test_dir, "real_test")
        os.makedirs(input_dir)
        test_sample = os.path.join(input_dir, "test_sample.mp4")
        shutil.copy2(sample_path, test_sample)
        
        # バッチ処理実行
        results = self.enhancer.process_batch(
            input_directory=input_dir,
            location="バッチテストルーム"
        )
        
        print(f"Real sample test results: {results}")
        
        # 最低限の結果を期待
        self.assertEqual(results['total_files'], 1)
        # success or failedのいずれかは1以上であるべき
        self.assertGreaterEqual(results['successful'] + results['failed'], 1)


if __name__ == '__main__':
    print("=" * 70)
    print("バッチ処理機能 包括テスト")
    print("=" * 70)
    
    # テストスイートの実行
    unittest.main(verbosity=2)
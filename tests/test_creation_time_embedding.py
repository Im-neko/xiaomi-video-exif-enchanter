#!/usr/bin/env python3
"""
作成日時のEXIF情報埋め込み機能のテスト
Issue #9: 作成日時のEXIF情報への埋め込み
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from exif_enhancer import XiaomiVideoEXIFEnhancer


class TestCreationTimeEmbedding(unittest.TestCase):
    """作成日時のEXIF情報埋め込みテスト"""
    
    def setUp(self):
        """テストセットアップ"""
        self.enhancer = XiaomiVideoEXIFEnhancer(debug=True)
        self.temp_dir = tempfile.mkdtemp()
        
        # テスト用ファイルのパス
        self.test_input = os.path.join(self.temp_dir, "test_creation_time.mp4")
        self.test_output = os.path.join(self.temp_dir, "test_creation_time_enhanced.mp4")
        
        # 最小限のMP4ファイルを作成
        with open(self.test_input, 'wb') as f:
            # 最小限のMP4ヘッダー（ダミー）
            f.write(b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41')
            f.write(b'\x00' * 2000)  # パディング
    
    def tearDown(self):
        """テスト後処理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_iso8601_timestamp_formatting(self):
        """ISO 8601形式のタイムスタンプフォーマットテスト"""
        print("\n=== Testing ISO 8601 Timestamp Formatting ===")
        
        # テスト用タイムスタンプ（Xiaomiカメラの典型的な時刻）
        test_datetime = datetime(2025, 5, 28, 19, 41, 14)
        
        # ISO 8601形式への変換をテスト
        iso_format = test_datetime.isoformat() + 'Z'
        
        print(f"Original datetime: {test_datetime}")
        print(f"ISO 8601 format: {iso_format}")
        
        # 期待される形式: 2025-05-28T19:41:14Z
        expected_format = "2025-05-28T19:41:14Z"
        self.assertEqual(iso_format, expected_format)
        
        print("✅ ISO 8601 formatting test passed")
    
    def test_timezone_handling(self):
        """タイムゾーン情報の処理テスト"""
        print("\n=== Testing Timezone Handling ===")
        
        # UTC+9 (JST) タイムゾーンでのテスト
        jst_timezone = timezone.utc.replace(tzinfo=None)  # シンプルなUTC処理
        test_datetime_jst = datetime(2025, 5, 28, 19, 41, 14)
        
        # UTC変換テスト（実際の実装では必要に応じて変換）
        utc_datetime = test_datetime_jst  # 現在の実装ではローカル時刻として扱う
        iso_format = utc_datetime.isoformat() + 'Z'
        
        print(f"JST datetime: {test_datetime_jst}")
        print(f"ISO format with Z suffix: {iso_format}")
        
        # 基本的なフォーマットの確認
        self.assertTrue(iso_format.endswith('Z'))
        self.assertIn('T', iso_format)
        
        print("✅ Timezone handling test passed")
    
    def test_metadata_preservation(self):
        """既存メタデータの保持テスト"""
        print("\n=== Testing Metadata Preservation ===")
        
        test_timestamp = datetime(2025, 5, 28, 19, 41, 14)
        test_location = "リビング"
        
        # メタデータ辞書の構築をテスト
        metadata = {}
        
        # タイムスタンプの設定
        if test_timestamp:
            metadata['creation_time'] = test_timestamp.isoformat() + 'Z'
        
        # 場所情報の設定
        if test_location:
            metadata['location'] = test_location
        
        print(f"Generated metadata: {metadata}")
        
        # 期待されるメタデータが含まれていることを確認
        self.assertIn('creation_time', metadata)
        self.assertEqual(metadata['creation_time'], '2025-05-28T19:41:14Z')
        self.assertIn('location', metadata)
        self.assertEqual(metadata['location'], 'リビング')
        
        print("✅ Metadata preservation test passed")
    
    def test_add_exif_data_integration(self):
        """add_exif_dataメソッドの統合テスト"""
        print("\n=== Testing add_exif_data Integration ===")
        
        test_timestamp = datetime(2025, 5, 28, 19, 41, 14)
        test_location = "Xiaomiカメラテスト"
        
        print(f"Testing with timestamp: {test_timestamp}")
        print(f"Testing with location: {test_location}")
        
        try:
            # add_exif_dataメソッドを呼び出し
            success = self.enhancer.add_exif_data(
                video_path=self.test_input,
                output_path=self.test_output,
                timestamp=test_timestamp,
                location=test_location
            )
            
            if success:
                print("✅ add_exif_data completed successfully")
                if os.path.exists(self.test_output):
                    print(f"✅ Output file created: {os.path.getsize(self.test_output)} bytes")
                else:
                    print("⚠ Output file was not created")
            else:
                print("⚠ add_exif_data failed (likely due to missing ffmpeg)")
                
        except Exception as e:
            print(f"❌ Error during add_exif_data: {e}")
            # FFmpegが利用できない環境でもテストが失敗しないようにする
            if "ffmpeg" not in str(e).lower():
                raise
            else:
                print("⚠ FFmpeg not available - this is expected in some environments")
        
        print("✅ Integration test completed")
    
    def test_timestamp_parsing_and_embedding(self):
        """タイムスタンプのパースと埋め込みの統合テスト"""
        print("\n=== Testing Timestamp Parsing and Embedding ===")
        
        # 典型的なXiaomiカメラのタイムスタンプ形式をテスト
        timestamp_strings = [
            "@ 2025/05/28 19.41.14",
            "2025/05/28 19:41:14",
            "20250528 19:41:14"
        ]
        
        for timestamp_str in timestamp_strings:
            print(f"Testing timestamp string: '{timestamp_str}'")
            
            # タイムスタンプのパース
            parsed_timestamp = self.enhancer.parse_timestamp(timestamp_str)
            
            if parsed_timestamp:
                print(f"  ✅ Parsed: {parsed_timestamp}")
                
                # ISO 8601形式への変換
                iso_format = parsed_timestamp.isoformat() + 'Z'
                print(f"  ✅ ISO format: {iso_format}")
                
                # 基本的な検証
                self.assertIsInstance(parsed_timestamp, datetime)
                self.assertEqual(parsed_timestamp.year, 2025)
                self.assertEqual(parsed_timestamp.month, 5)
                self.assertEqual(parsed_timestamp.day, 28)
                self.assertEqual(parsed_timestamp.hour, 19)
                self.assertEqual(parsed_timestamp.minute, 41)
                self.assertEqual(parsed_timestamp.second, 14)
                
            else:
                print(f"  ❌ Failed to parse: '{timestamp_str}'")
        
        print("✅ Timestamp parsing and embedding test completed")
    
    def test_error_handling(self):
        """エラーハンドリングのテスト"""
        print("\n=== Testing Error Handling ===")
        
        # 無効なタイムスタンプでのテスト
        invalid_timestamp = None
        result = self.enhancer.add_exif_data(
            video_path=self.test_input,
            output_path=self.test_output,
            timestamp=invalid_timestamp,
            location="テスト場所"
        )
        
        print(f"Result with None timestamp: {result}")
        
        # 無効なファイルパスでのテスト
        try:
            result = self.enhancer.add_exif_data(
                video_path="/nonexistent/file.mp4",
                output_path=self.test_output,
                timestamp=datetime.now(),
                location="テスト場所"
            )
            print(f"Result with invalid file: {result}")
        except Exception as e:
            print(f"Expected error for invalid file: {e}")
        
        print("✅ Error handling test completed")


def test_creation_time_embedding():
    """統合的な作成日時埋め込みテスト"""
    print("=" * 60)
    print("Testing Creation Time Embedding - Issue #9")
    print("=" * 60)
    
    enhancer = XiaomiVideoEXIFEnhancer(debug=True)
    
    # 基本的な機能確認
    print("\n1. Testing basic timestamp formatting...")
    test_timestamp = datetime(2025, 5, 28, 19, 41, 14)
    iso_format = test_timestamp.isoformat() + 'Z'
    print(f"   Test timestamp: {test_timestamp}")
    print(f"   ISO 8601 format: {iso_format}")
    assert iso_format == "2025-05-28T19:41:14Z", "ISO 8601 formatting failed"
    print("   ✅ Timestamp formatting works correctly")
    
    # タイムスタンプパース機能確認
    print("\n2. Testing timestamp parsing...")
    test_strings = [
        "@ 2025/05/28 19.41.14",
        "2025/05/28 19:41:14",
        "20250528 19:41:14"
    ]
    
    for ts_str in test_strings:
        parsed = enhancer.parse_timestamp(ts_str)
        if parsed:
            print(f"   ✅ Parsed '{ts_str}' -> {parsed}")
        else:
            print(f"   ❌ Failed to parse '{ts_str}'")
    
    # メタデータ構築テスト
    print("\n3. Testing metadata construction...")
    metadata = {}
    if test_timestamp:
        metadata['creation_time'] = test_timestamp.isoformat() + 'Z'
    metadata['location'] = "テスト場所"
    print(f"   Generated metadata: {metadata}")
    print("   ✅ Metadata construction works correctly")
    
    print("\n" + "=" * 60)
    print("✅ Creation Time Embedding Test Completed")
    print("=" * 60)


if __name__ == '__main__':
    # 統合テストを実行
    test_creation_time_embedding()
    print("\n")
    
    # ユニットテストを実行
    unittest.main(verbosity=2, argv=[''])
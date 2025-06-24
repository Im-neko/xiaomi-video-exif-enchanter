#!/usr/bin/env python3
"""
メタデータ統合機能のテスト
Issue #10: 撮影場所のEXIF情報への埋め込み
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from exif_enhancer import XiaomiVideoEXIFEnhancer


def test_metadata_integration():
    """メタデータ統合機能のテスト"""
    print("=" * 60)
    print("Testing Metadata Integration - Issue #10")
    print("=" * 60)
    
    # テスト用の一時ディレクトリとファイル作成
    with tempfile.TemporaryDirectory() as temp_dir:
        # ダミー映像ファイル作成（実際の映像処理はスキップ）
        test_input = os.path.join(temp_dir, "test_xiaomi_video.mp4")
        test_output = os.path.join(temp_dir, "test_xiaomi_video_enhanced.mp4")
        
        # 最小限のMP4ファイルを作成（実際の映像データなし）
        with open(test_input, 'wb') as f:
            # 最小限のMP4ヘッダー（ダミー）
            f.write(b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41')
            f.write(b'\x00' * 1000)  # パディング
        
        try:
            # XiaomiVideoEXIFEnhancerを初期化
            enhancer = XiaomiVideoEXIFEnhancer(debug=True)
            
            print("✓ XiaomiVideoEXIFEnhancer initialized with MetadataManager")
            print(f"✓ Input file created: {Path(test_input).name}")
            
            # テスト用のメタデータ情報
            test_timestamp = datetime(2025, 5, 28, 19, 41, 14)
            test_location = "リビング（テスト用Xiaomiカメラ）"
            additional_metadata = {
                'title': 'Xiaomi テスト映像',
                'description': 'メタデータ統合テスト',
                'genre': 'ホームセキュリティ'
            }
            
            print(f"\nTest metadata:")
            print(f"  Timestamp: {test_timestamp}")
            print(f"  Location: {test_location}")
            print(f"  Additional: {additional_metadata}")
            
            # メタデータ作成をテスト
            metadata = enhancer.metadata_manager.create_metadata_dict(
                timestamp=test_timestamp,
                location=test_location,
                additional_metadata=additional_metadata
            )
            
            print(f"\n✓ Metadata created successfully:")
            print(enhancer.metadata_manager.format_metadata_for_display(metadata))
            
            # メタデータ検証
            is_valid, issues = enhancer.metadata_manager.validate_metadata(metadata)
            print(f"\n✓ Metadata validation: {'Valid' if is_valid else 'Invalid'}")
            if issues:
                for issue in issues:
                    print(f"  - {issue}")
            
            # add_exif_data メソッドの動作確認（FFmpegなしでもメタデータ処理をテスト）
            print(f"\n--- Testing add_exif_data integration ---")
            
            # FFmpegが利用できない場合のテスト
            result = enhancer.add_exif_data(
                video_path=test_input,
                output_path=test_output,
                timestamp=test_timestamp,
                location=test_location,
                additional_metadata=additional_metadata
            )
            
            if result:
                print("✓ add_exif_data completed successfully")
                if os.path.exists(test_output):
                    print(f"✓ Output file created: {Path(test_output).name}")
                    print(f"  File size: {os.path.getsize(test_output)} bytes")
            else:
                print("⚠ add_exif_data failed (likely due to missing ffmpeg or invalid input)")
            
            # UTF-8日本語エンコーディングテスト
            print(f"\n--- UTF-8 Japanese Text Encoding Test ---")
            japanese_locations = [
                "東京都渋谷区",
                "リビング（Xiaomiカメラ）",
                "寝室🏠📹",
                "玄関エントランス・セキュリティカメラ"
            ]
            
            for location in japanese_locations:
                encoded = enhancer.metadata_manager._encode_utf8_string(location)
                print(f"  Original: {location}")
                print(f"  Encoded:  {encoded}")
                print(f"  Bytes:    {len(encoded.encode('utf-8'))}")
                print()
            
            print("=" * 60)
            print("✓ Metadata Integration Test Completed Successfully")
            print("=" * 60)
            
        except Exception as e:
            print(f"✗ Error during test: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return True


if __name__ == '__main__':
    success = test_metadata_integration()
    exit(0 if success else 1)
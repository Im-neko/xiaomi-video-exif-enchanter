#!/usr/bin/env python3
"""
メタデータ管理モジュール
Issue #10: 撮影場所のEXIF情報への埋め込み
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
import logging
import subprocess


class MetadataManager:
    """映像ファイルのメタデータ管理クラス"""
    
    def __init__(self, debug: bool = False):
        """初期化
        
        Args:
            debug: デバッグモードの有効/無効
        """
        self.debug = debug
        self.logger = self._setup_logger()
        
        # サポートされているメタデータキー
        self.SUPPORTED_KEYS = {
            'title': 'タイトル',
            'description': '説明',
            'location': '撮影場所',
            'creation_time': '作成日時',
            'comment': 'コメント',
            'artist': 'アーティスト',
            'album': 'アルバム',
            'genre': 'ジャンル',
            'year': '年',
            'track': 'トラック',
            'encoder': 'エンコーダー'
        }
    
    def _setup_logger(self) -> logging.Logger:
        """ロガーのセットアップ
        
        Returns:
            設定済みロガー
        """
        logger = logging.getLogger('MetadataManager')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        return logger
    
    def create_metadata_dict(self, timestamp: Optional[datetime] = None, 
                           location: Optional[str] = None,
                           additional_metadata: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """メタデータ辞書を作成
        
        Args:
            timestamp: 作成日時
            location: 撮影場所
            additional_metadata: 追加のメタデータ
            
        Returns:
            FFmpeg用のメタデータ辞書
        """
        metadata = {}
        
        # 作成日時の設定
        if timestamp:
            # ISO 8601形式に変換
            creation_time = timestamp.strftime("%Y-%m-%dT%H:%M:%S.000000Z")
            metadata['creation_time'] = creation_time
            
            if self.debug:
                self.logger.debug(f"Set creation_time: {creation_time}")
        
        # 撮影場所の設定
        if location:
            # UTF-8で適切にエンコード
            encoded_location = self._encode_utf8_string(location)
            metadata['location'] = encoded_location
            
            # 追加の場所関連メタデータ
            metadata['comment'] = f"撮影場所: {encoded_location}"
            
            if self.debug:
                self.logger.debug(f"Set location: {encoded_location}")
        
        # 自動生成されるメタデータ
        metadata['encoder'] = 'Xiaomi Video EXIF Enhancer'
        metadata['title'] = 'Enhanced Xiaomi Camera Video'
        
        # 追加のメタデータがある場合
        if additional_metadata:
            for key, value in additional_metadata.items():
                if key in self.SUPPORTED_KEYS:
                    metadata[key] = self._encode_utf8_string(str(value))
                    if self.debug:
                        self.logger.debug(f"Set {key}: {value}")
        
        if self.debug:
            self.logger.debug(f"Created metadata: {metadata}")
        
        return metadata
    
    def _encode_utf8_string(self, text: str) -> str:
        """UTF-8文字列の適切なエンコーディング
        
        Args:
            text: エンコードする文字列
            
        Returns:
            適切にエンコードされた文字列
        """
        if not text:
            return ""
        
        try:
            # 既にUTF-8の場合はそのまま、そうでなければエンコード
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='replace')
            
            # 制御文字を削除
            cleaned_text = ''.join(char for char in text if ord(char) >= 32 or char in '\t\n\r')
            
            # 長すぎる場合は切り詰め（FFmpegの制限対応）
            if len(cleaned_text.encode('utf-8')) > 255:
                # UTF-8で255バイト以下になるよう調整
                while len(cleaned_text.encode('utf-8')) > 255:
                    cleaned_text = cleaned_text[:-1]
                cleaned_text += "..."
            
            return cleaned_text
            
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error encoding string '{text}': {e}")
            # エラーの場合は安全な文字列を返す
            return "Unknown Location"
    
    def validate_metadata(self, metadata: Dict[str, str]) -> Tuple[bool, List[str]]:
        """メタデータの妥当性を検証
        
        Args:
            metadata: 検証するメタデータ辞書
            
        Returns:
            (妥当性, 問題のリスト)
        """
        issues = []
        
        # 各キーと値の検証
        for key, value in metadata.items():
            # キーの検証
            if not isinstance(key, str) or not key:
                issues.append(f"無効なメタデータキー: {key}")
                continue
            
            # 値の検証
            if not isinstance(value, str):
                issues.append(f"メタデータ値は文字列である必要があります: {key}={value}")
                continue
            
            # UTF-8エンコーディング検証
            try:
                value.encode('utf-8')
            except UnicodeEncodeError:
                issues.append(f"UTF-8エンコーディングできない値: {key}={value}")
            
            # 長さ制限の確認
            if len(value.encode('utf-8')) > 255:
                issues.append(f"メタデータ値が長すぎます: {key} ({len(value.encode('utf-8'))} bytes > 255)")
        
        # 必須フィールドの確認
        recommended_fields = ['encoder']
        for field in recommended_fields:
            if field not in metadata:
                issues.append(f"推奨フィールドが不足: {field}")
        
        return len(issues) == 0, issues
    
    def get_existing_metadata(self, video_path: str) -> Dict[str, str]:
        """既存の映像ファイルからメタデータを取得
        
        Args:
            video_path: 映像ファイルのパス
            
        Returns:
            既存のメタデータ辞書
        """
        metadata = {}
        
        try:
            # ffprobeを使用してメタデータを取得
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                video_path
            ]
            
            if self.debug:
                self.logger.debug(f"Running ffprobe: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                probe_data = json.loads(result.stdout)
                
                # formatセクションからメタデータを抽出
                if 'format' in probe_data and 'tags' in probe_data['format']:
                    tags = probe_data['format']['tags']
                    
                    # キーを小文字に正規化
                    for key, value in tags.items():
                        normalized_key = key.lower()
                        if normalized_key in self.SUPPORTED_KEYS:
                            metadata[normalized_key] = str(value)
                
                if self.debug:
                    self.logger.debug(f"Extracted existing metadata: {metadata}")
            
            else:
                if self.debug:
                    self.logger.warning(f"ffprobe failed: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            if self.debug:
                self.logger.error("ffprobe timeout")
        except FileNotFoundError:
            if self.debug:
                self.logger.warning("ffprobe not found")
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error getting metadata: {e}")
        
        return metadata
    
    def merge_metadata(self, existing: Dict[str, str], new: Dict[str, str], 
                      preserve_existing: bool = True) -> Dict[str, str]:
        """既存メタデータと新規メタデータをマージ
        
        Args:
            existing: 既存のメタデータ
            new: 新規のメタデータ
            preserve_existing: 既存の値を保持するかどうか
            
        Returns:
            マージされたメタデータ
        """
        merged = existing.copy() if preserve_existing else {}
        
        for key, value in new.items():
            if preserve_existing and key in existing:
                # 既存の値を保持（ただし特定のキーは上書き）
                overwrite_keys = ['encoder', 'creation_time']
                if key in overwrite_keys:
                    merged[key] = value
                    if self.debug:
                        self.logger.debug(f"Overrode existing {key}: {existing[key]} -> {value}")
            else:
                merged[key] = value
                if self.debug:
                    self.logger.debug(f"Added new {key}: {value}")
        
        return merged
    
    def format_metadata_for_display(self, metadata: Dict[str, str]) -> str:
        """メタデータを表示用にフォーマット
        
        Args:
            metadata: 表示するメタデータ
            
        Returns:
            フォーマットされた文字列
        """
        if not metadata:
            return "メタデータがありません"
        
        lines = ["メタデータ情報:"]
        
        # 重要なフィールドを先に表示
        priority_fields = ['title', 'creation_time', 'location', 'description']
        
        # 優先フィールド
        for field in priority_fields:
            if field in metadata:
                display_name = self.SUPPORTED_KEYS.get(field, field)
                lines.append(f"  {display_name}: {metadata[field]}")
        
        # その他のフィールド
        for key, value in metadata.items():
            if key not in priority_fields:
                display_name = self.SUPPORTED_KEYS.get(key, key)
                lines.append(f"  {display_name}: {value}")
        
        return "\n".join(lines)
    
    def export_metadata_to_file(self, metadata: Dict[str, str], output_path: str) -> bool:
        """メタデータをファイルにエクスポート
        
        Args:
            metadata: エクスポートするメタデータ
            output_path: 出力ファイルパス
            
        Returns:
            成功時True
        """
        try:
            export_data = {
                'metadata': metadata,
                'export_time': datetime.now().isoformat(),
                'version': '1.0',
                'tool': 'Xiaomi Video EXIF Enhancer'
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            if self.debug:
                self.logger.debug(f"Metadata exported to: {output_path}")
            
            return True
            
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error exporting metadata: {e}")
            return False
    
    def import_metadata_from_file(self, input_path: str) -> Optional[Dict[str, str]]:
        """ファイルからメタデータをインポート
        
        Args:
            input_path: 入力ファイルパス
            
        Returns:
            インポートされたメタデータ、失敗時はNone
        """
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'metadata' in data:
                metadata = data['metadata']
                
                # 妥当性を検証
                is_valid, issues = self.validate_metadata(metadata)
                if not is_valid:
                    if self.debug:
                        self.logger.warning(f"Invalid metadata imported: {issues}")
                
                if self.debug:
                    self.logger.debug(f"Metadata imported from: {input_path}")
                
                return metadata
            
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error importing metadata: {e}")
        
        return None


if __name__ == '__main__':
    # テスト実行
    manager = MetadataManager(debug=True)
    
    print("=" * 50)
    print("Testing MetadataManager")
    print("=" * 50)
    
    # メタデータ作成テスト
    test_timestamp = datetime(2025, 5, 28, 19, 41, 14)
    test_location = "リビング（テスト用）"
    
    metadata = manager.create_metadata_dict(
        timestamp=test_timestamp,
        location=test_location,
        additional_metadata={
            'title': 'テスト映像',
            'description': 'Xiaomiカメラテスト映像'
        }
    )
    
    print("Created metadata:")
    print(manager.format_metadata_for_display(metadata))
    
    # メタデータ検証テスト
    is_valid, issues = manager.validate_metadata(metadata)
    print(f"\nValidation: {'✓ Valid' if is_valid else '✗ Invalid'}")
    if issues:
        for issue in issues:
            print(f"  - {issue}")
    
    # UTF-8エンコーディングテスト
    japanese_text = "東京都渋谷区🎌📹"
    encoded_text = manager._encode_utf8_string(japanese_text)
    print(f"\nUTF-8 encoding test:")
    print(f"  Original: {japanese_text}")
    print(f"  Encoded: {encoded_text}")
    print(f"  Byte length: {len(encoded_text.encode('utf-8'))}")
    
    # エクスポート/インポートテスト
    export_file = "test_metadata.json"
    if manager.export_metadata_to_file(metadata, export_file):
        print(f"\n✓ Metadata exported to {export_file}")
        
        imported_metadata = manager.import_metadata_from_file(export_file)
        if imported_metadata:
            print("✓ Metadata imported successfully")
            print("Imported metadata:")
            print(manager.format_metadata_for_display(imported_metadata))
        
        # クリーンアップ
        try:
            os.remove(export_file)
        except FileNotFoundError:
            pass
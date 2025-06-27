#!/usr/bin/env python3
"""
映像ファイル読み込みエラーハンドリング専用モジュール
Issue #14: 映像ファイル読み込みエラーのハンドリング
"""

import os
import cv2
import stat
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import logging


class VideoErrorType(Enum):
    """映像ファイルエラーの種類"""
    FILE_NOT_FOUND = "file_not_found"
    UNSUPPORTED_FORMAT = "unsupported_format"
    CORRUPTED_FILE = "corrupted_file"
    PERMISSION_DENIED = "permission_denied"
    EMPTY_FILE = "empty_file"
    INSUFFICIENT_SPACE = "insufficient_space"
    CODEC_ERROR = "codec_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN_ERROR = "unknown_error"


class VideoErrorHandler:
    """映像ファイルエラーハンドリングクラス"""
    
    def __init__(self, debug: bool = False):
        """初期化
        
        Args:
            debug: デバッグモードの有効/無効
        """
        self.debug = debug
        self.logger = self._setup_logger()
        
        # サポートされている映像形式
        self.SUPPORTED_EXTENSIONS = {
            '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm',
            '.m4v', '.3gp', '.ts', '.mts', '.m2ts', '.ogv', '.divx'
        }
        
        # よくあるエラーパターン
        self.ERROR_PATTERNS = {
            "moov atom not found": VideoErrorType.CORRUPTED_FILE,
            "Invalid data found": VideoErrorType.CORRUPTED_FILE,
            "Permission denied": VideoErrorType.PERMISSION_DENIED,
            "No space left": VideoErrorType.INSUFFICIENT_SPACE,
            "Connection refused": VideoErrorType.NETWORK_ERROR,
            "Codec not supported": VideoErrorType.CODEC_ERROR,
        }
    
    def _setup_logger(self) -> logging.Logger:
        """ロガーのセットアップ
        
        Returns:
            設定済みロガー
        """
        logger = logging.getLogger('VideoErrorHandler')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        return logger
    
    def analyze_file_error(self, video_path: str) -> Tuple[VideoErrorType, str, Dict[str, Any]]:
        """ファイルエラーの詳細分析
        
        Args:
            video_path: 映像ファイルのパス
            
        Returns:
            (エラータイプ, エラーメッセージ, 詳細情報)
        """
        details = {
            'file_path': video_path,
            'file_exists': False,
            'file_size': 0,
            'permissions': None,
            'extension': None,
            'cv2_can_open': False,
            'error_details': None
        }
        
        try:
            # 1. ファイル存在確認
            if not os.path.exists(video_path):
                return (
                    VideoErrorType.FILE_NOT_FOUND,
                    f"ファイルが見つかりません: {video_path}",
                    details
                )
            
            details['file_exists'] = True
            
            # 2. ファイル情報取得
            file_stat = os.stat(video_path)
            details['file_size'] = file_stat.st_size
            details['permissions'] = oct(file_stat.st_mode)
            
            path_obj = Path(video_path)
            details['extension'] = path_obj.suffix.lower()
            
            # 3. ファイルサイズチェック
            if file_stat.st_size == 0:
                return (
                    VideoErrorType.EMPTY_FILE,
                    f"ファイルが空です: {video_path}",
                    details
                )
            
            # 4. 読み取り権限チェック
            if not os.access(video_path, os.R_OK):
                return (
                    VideoErrorType.PERMISSION_DENIED,
                    f"ファイルの読み取り権限がありません: {video_path}",
                    details
                )
            
            # 5. 拡張子チェック
            if details['extension'] not in self.SUPPORTED_EXTENSIONS:
                return (
                    VideoErrorType.UNSUPPORTED_FORMAT,
                    f"サポートされていないファイル形式です: {details['extension']}",
                    details
                )
            
            # 6. OpenCV読み込みテスト
            cap = cv2.VideoCapture(video_path)
            try:
                if not cap.isOpened():
                    details['cv2_can_open'] = False
                    return (
                        VideoErrorType.CORRUPTED_FILE,
                        f"映像ファイルを開けません（破損の可能性）: {video_path}",
                        details
                    )
                
                details['cv2_can_open'] = True
                
                # フレーム読み込みテスト
                ret, frame = cap.read()
                if not ret or frame is None:
                    return (
                        VideoErrorType.CORRUPTED_FILE,
                        f"映像フレームを読み込めません（破損の可能性）: {video_path}",
                        details
                    )
                
                # 正常な場合
                return (
                    VideoErrorType.UNKNOWN_ERROR,  # 実際は正常だが、この関数はエラー分析用
                    "映像ファイルは正常に読み込めます",
                    details
                )
                
            finally:
                cap.release()
                
        except PermissionError as e:
            details['error_details'] = str(e)
            return (
                VideoErrorType.PERMISSION_DENIED,
                f"アクセス権限エラー: {video_path} - {str(e)}",
                details
            )
        except OSError as e:
            details['error_details'] = str(e)
            error_msg = str(e).lower()
            
            # エラーパターンマッチング
            for pattern, error_type in self.ERROR_PATTERNS.items():
                if pattern.lower() in error_msg:
                    return (
                        error_type,
                        f"{error_type.value}: {video_path} - {str(e)}",
                        details
                    )
            
            return (
                VideoErrorType.UNKNOWN_ERROR,
                f"システムエラー: {video_path} - {str(e)}",
                details
            )
        except Exception as e:
            details['error_details'] = str(e)
            return (
                VideoErrorType.UNKNOWN_ERROR,
                f"予期しないエラー: {video_path} - {str(e)}",
                details
            )
    
    def get_user_friendly_message(self, error_type: VideoErrorType, details: Dict[str, Any]) -> str:
        """ユーザーフレンドリーなエラーメッセージを生成
        
        Args:
            error_type: エラータイプ
            details: エラー詳細情報
            
        Returns:
            ユーザー向けエラーメッセージ
        """
        file_path = details.get('file_path', 'unknown')
        file_name = Path(file_path).name
        
        messages = {
            VideoErrorType.FILE_NOT_FOUND: 
                f"❌ ファイルが見つかりません\n"
                f"   ファイル: {file_name}\n"
                f"   パス: {file_path}\n"
                f"   💡 ファイルパスが正しいか確認してください",
                
            VideoErrorType.UNSUPPORTED_FORMAT:
                f"❌ サポートされていないファイル形式です\n"
                f"   ファイル: {file_name}\n"
                f"   形式: {details.get('extension', 'unknown')}\n"
                f"   💡 対応形式: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}",
                
            VideoErrorType.CORRUPTED_FILE:
                f"❌ ファイルが破損している可能性があります\n"
                f"   ファイル: {file_name}\n"
                f"   サイズ: {details.get('file_size', 0):,} bytes\n"
                f"   💡 別の映像ファイルで試すか、ファイルを再取得してください",
                
            VideoErrorType.PERMISSION_DENIED:
                f"❌ ファイルへのアクセス権限がありません\n"
                f"   ファイル: {file_name}\n"
                f"   権限: {details.get('permissions', 'unknown')}\n"
                f"   💡 ファイルの読み取り権限を確認してください",
                
            VideoErrorType.EMPTY_FILE:
                f"❌ ファイルが空です\n"
                f"   ファイル: {file_name}\n"
                f"   サイズ: {details.get('file_size', 0)} bytes\n"
                f"   💡 正しい映像ファイルかどうか確認してください",
                
            VideoErrorType.CODEC_ERROR:
                f"❌ 映像コーデックがサポートされていません\n"
                f"   ファイル: {file_name}\n"
                f"   💡 別の形式に変換するか、コーデックをインストールしてください",
                
            VideoErrorType.NETWORK_ERROR:
                f"❌ ネットワークエラーが発生しました\n"
                f"   ファイル: {file_name}\n"
                f"   💡 ネットワーク接続とURLを確認してください",
                
            VideoErrorType.INSUFFICIENT_SPACE:
                f"❌ ディスク容量が不足しています\n"
                f"   💡 ディスク容量を確保してから再実行してください"
        }
        
        return messages.get(error_type, 
            f"❌ 不明なエラーが発生しました\n"
            f"   ファイル: {file_name}\n"
            f"   詳細: {details.get('error_details', 'No details available')}"
        )
    
    def get_recovery_suggestions(self, error_type: VideoErrorType) -> List[str]:
        """エラー回復のための提案を取得
        
        Args:
            error_type: エラータイプ
            
        Returns:
            回復提案のリスト
        """
        suggestions = {
            VideoErrorType.FILE_NOT_FOUND: [
                "ファイルパスを確認する",
                "ファイル名のスペルを確認する",
                "ファイルが移動または削除されていないか確認する",
                "相対パスではなく絶対パスを使用する"
            ],
            
            VideoErrorType.UNSUPPORTED_FORMAT: [
                "サポートされている形式に変換する",
                "FFmpegを使用して変換する",
                "別の映像ファイルを使用する"
            ],
            
            VideoErrorType.CORRUPTED_FILE: [
                "元のファイルを再取得する",
                "別の映像ファイルで試す",
                "映像修復ツールを使用する",
                "ファイルの整合性を確認する"
            ],
            
            VideoErrorType.PERMISSION_DENIED: [
                "ファイルの読み取り権限を付与する",
                "管理者権限で実行する",
                "ファイルの所有者を確認する"
            ],
            
            VideoErrorType.EMPTY_FILE: [
                "正しいファイルかどうか確認する",
                "ファイルが完全にダウンロードされているか確認する",
                "別のファイルで試す"
            ],
            
            VideoErrorType.CODEC_ERROR: [
                "FFmpegがインストールされているか確認する",
                "必要なコーデックをインストールする",
                "別の形式に変換する"
            ]
        }
        
        return suggestions.get(error_type, [
            "ファイルとシステム環境を確認する",
            "エラーログを確認する",
            "別のファイルで試す"
        ])
    
    def create_error_report(self, video_path: str) -> Dict[str, Any]:
        """詳細なエラーレポートを作成
        
        Args:
            video_path: 映像ファイルのパス
            
        Returns:
            エラーレポート辞書
        """
        error_type, message, details = self.analyze_file_error(video_path)
        
        report = {
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'file_path': video_path,
            'error_type': error_type.value,
            'error_message': message,
            'user_message': self.get_user_friendly_message(error_type, details),
            'recovery_suggestions': self.get_recovery_suggestions(error_type),
            'technical_details': details,
            'system_info': {
                'opencv_version': cv2.__version__,
                'python_version': __import__('sys').version,
                'platform': __import__('platform').platform()
            }
        }
        
        if self.debug:
            self.logger.debug(f"Error report created: {report}")
        
        return report
    
    def validate_video_file(self, video_path: str, raise_on_error: bool = True) -> bool:
        """映像ファイルの妥当性を検証
        
        Args:
            video_path: 映像ファイルのパス
            raise_on_error: エラー時に例外を発生させるかどうか
            
        Returns:
            ファイルが有効な場合True
            
        Raises:
            各種例外（raise_on_errorがTrueの場合）
        """
        error_type, message, details = self.analyze_file_error(video_path)
        
        # 正常な場合（この関数では"正常"もUNKNOWN_ERRORとして返される）
        if error_type == VideoErrorType.UNKNOWN_ERROR and "正常に読み込めます" in message:
            return True
        
        if raise_on_error:
            # エラータイプに応じて適切な例外を発生
            if error_type == VideoErrorType.FILE_NOT_FOUND:
                raise FileNotFoundError(message)
            elif error_type == VideoErrorType.PERMISSION_DENIED:
                raise PermissionError(message)
            elif error_type in [VideoErrorType.CORRUPTED_FILE, VideoErrorType.UNSUPPORTED_FORMAT, 
                              VideoErrorType.EMPTY_FILE, VideoErrorType.CODEC_ERROR]:
                raise ValueError(message)
            else:
                raise RuntimeError(message)
        
        return False
    
    def handle_video_processing(self, input_path: str, output_path: str, 
                               location: Optional[str] = None) -> Dict[str, Any]:
        """動画処理のエラーハンドリング
        
        Args:
            input_path: 入力ファイルのパス
            output_path: 出力ファイルのパス
            location: 場所情報（オプション）
            
        Returns:
            処理結果の辞書（should_skip, reason等）
        """
        try:
            # 入力ファイルの検証
            if not self.validate_video_file(input_path, raise_on_error=False):
                error_type, message, details = self.analyze_file_error(input_path)
                return {
                    'should_skip': True,
                    'reason': f'Invalid input file: {message}',
                    'error_type': error_type.value,
                    'details': details
                }
            
            # 出力パスの検証
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                except OSError as e:
                    return {
                        'should_skip': True,
                        'reason': f'Cannot create output directory: {e}',
                        'error_type': 'directory_creation_failed',
                        'details': {'output_dir': output_dir, 'error': str(e)}
                    }
            
            # 処理を続行
            return {
                'should_skip': False,
                'reason': 'File validation passed',
                'error_type': None,
                'details': {}
            }
            
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error in handle_video_processing: {e}")
            return {
                'should_skip': True,
                'reason': f'Unexpected error: {e}',
                'error_type': 'unexpected_error',
                'details': {'exception': str(e)}
            }
    
    def log_error(self, error_type: VideoErrorType, file_path: str, message: str):
        """エラーをログに記録
        
        Args:
            error_type: エラータイプ
            file_path: ファイルパス
            message: エラーメッセージ
        """
        log_message = f"[{error_type.value}] {os.path.basename(file_path)}: {message}"
        
        if self.debug:
            self.logger.error(log_message)
        else:
            # デバッグモードでない場合は標準エラー出力に表示
            print(f"ERROR: {log_message}")


def create_test_error_files():
    """テスト用のエラーファイルを作成"""
    # 空ファイル
    with open('test_empty.mp4', 'w') as f:
        pass
    
    # 不正な内容のファイル
    with open('test_corrupted.mp4', 'w') as f:
        f.write("This is not a video file")
    
    # サポートされていない拡張子
    with open('test_unsupported.xyz', 'w') as f:
        f.write("unsupported format")


if __name__ == '__main__':
    # テスト実行
    handler = VideoErrorHandler(debug=True)
    
    # テストファイル作成
    create_test_error_files()
    
    test_files = [
        'sample.mp4',  # 正常なファイル
        'nonexistent.mp4',  # 存在しないファイル
        'test_empty.mp4',  # 空ファイル
        'test_corrupted.mp4',  # 破損ファイル
        'test_unsupported.xyz'  # サポートされていない形式
    ]
    
    for test_file in test_files:
        print(f"\n{'='*50}")
        print(f"Testing: {test_file}")
        print('='*50)
        
        report = handler.create_error_report(test_file)
        print(f"Error Type: {report['error_type']}")
        print(f"Message: {report['error_message']}")
        print("\nUser Message:")
        print(report['user_message'])
        print("\nRecovery Suggestions:")
        for i, suggestion in enumerate(report['recovery_suggestions'], 1):
            print(f"  {i}. {suggestion}")
    
    # テストファイル削除
    for test_file in ['test_empty.mp4', 'test_corrupted.mp4', 'test_unsupported.xyz']:
        try:
            os.remove(test_file)
        except FileNotFoundError:
            pass
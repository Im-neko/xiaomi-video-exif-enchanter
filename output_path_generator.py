#!/usr/bin/env python3
"""
出力ファイルパス自動生成モジュール
Issue #13: 出力ファイルパスの自動生成機能
"""

import os
import stat
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import logging
from datetime import datetime


class OutputPathGenerator:
    """出力ファイルパス自動生成クラス"""
    
    def __init__(self, debug: bool = False):
        """初期化
        
        Args:
            debug: デバッグモードの有効/無効
        """
        self.debug = debug
        self.logger = self._setup_logger()
        
        # デフォルト設定
        self.DEFAULT_SUFFIX = "_enhanced"
        self.TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
        self.MAX_COLLISION_ATTEMPTS = 999
    
    def _setup_logger(self) -> logging.Logger:
        """ロガーのセットアップ
        
        Returns:
            設定済みロガー
        """
        logger = logging.getLogger('OutputPathGenerator')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        return logger
    
    def generate_output_path(self, input_path: str, output_dir: Optional[str] = None, 
                           suffix: Optional[str] = None, 
                           preserve_timestamp: bool = False) -> str:
        """出力ファイルパスを自動生成
        
        Args:
            input_path: 入力ファイルのパス
            output_dir: 出力ディレクトリ（指定しない場合は入力ファイルと同じディレクトリ、Dockerコンテナ内では/app/output）
            suffix: ファイル名に追加するサフィックス（デフォルト: _enhanced）
            preserve_timestamp: 既存ファイルがある場合にタイムスタンプを追加するか
            
        Returns:
            生成された出力ファイルパス
            
        Raises:
            ValueError: 無効な入力パスの場合
            PermissionError: 出力ディレクトリへの書き込み権限がない場合
        """
        if self.debug:
            self.logger.debug(f"Generating output path for: {input_path}")
        
        # 入力パスの検証
        input_path_obj = Path(input_path)
        if not input_path_obj.exists():
            raise ValueError(f"Input file does not exist: {input_path}")
        
        # 基本的な出力パス情報
        stem = input_path_obj.stem  # 拡張子なしのファイル名
        extension = input_path_obj.suffix  # 拡張子
        
        # 出力ディレクトリの決定
        if output_dir is None:
            # Dockerコンテナ内の場合は/app/outputをデフォルトとする
            if self._is_docker_container() and str(input_path_obj.parent) == '/app/input':
                output_dir = '/app/output'
                if self.debug:
                    self.logger.debug("Docker container detected: using /app/output as default output directory")
            else:
                output_dir = str(input_path_obj.parent)
        
        # 出力ディレクトリの検証と作成
        self._ensure_output_directory(output_dir)
        
        # サフィックスの決定
        if suffix is None:
            suffix = self.DEFAULT_SUFFIX
        
        # 基本的な出力ファイル名生成
        base_output_name = f"{stem}{suffix}{extension}"
        potential_output_path = os.path.join(output_dir, base_output_name)
        
        if self.debug:
            self.logger.debug(f"Base output path: {potential_output_path}")
        
        # 重複チェックと解決
        final_output_path = self._resolve_path_collision(
            potential_output_path, preserve_timestamp
        )
        
        if self.debug:
            self.logger.debug(f"Final output path: {final_output_path}")
        
        return final_output_path
    
    def _ensure_output_directory(self, output_dir: str) -> None:
        """出力ディレクトリの存在確認と権限チェック
        
        Args:
            output_dir: 出力ディレクトリのパス
            
        Raises:
            PermissionError: ディレクトリの作成や書き込み権限がない場合
            OSError: ディレクトリ作成に失敗した場合
        """
        output_path = Path(output_dir)
        
        # ディレクトリが存在しない場合は作成
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
                if self.debug:
                    self.logger.debug(f"Created output directory: {output_dir}")
            except OSError as e:
                raise OSError(f"Failed to create output directory: {output_dir} - {e}")
        
        # 書き込み権限の確認
        if not os.access(output_dir, os.W_OK):
            raise PermissionError(f"No write permission for output directory: {output_dir}")
        
        if self.debug:
            self.logger.debug(f"Output directory verified: {output_dir}")
    
    def _resolve_path_collision(self, base_path: str, preserve_timestamp: bool) -> str:
        """ファイルパスの重複解決
        
        Args:
            base_path: 基本となる出力パス
            preserve_timestamp: タイムスタンプを使用するかどうか
            
        Returns:
            重複のない出力パス
        """
        if not os.path.exists(base_path):
            return base_path
        
        if self.debug:
            self.logger.debug(f"Path collision detected: {base_path}")
        
        path_obj = Path(base_path)
        stem = path_obj.stem
        extension = path_obj.suffix
        directory = path_obj.parent
        
        if preserve_timestamp:
            # タイムスタンプベースの解決
            timestamp = datetime.now().strftime(self.TIMESTAMP_FORMAT)
            new_path = directory / f"{stem}_{timestamp}{extension}"
            
            # それでも重複する場合は連番を追加
            counter = 1
            while new_path.exists() and counter <= self.MAX_COLLISION_ATTEMPTS:
                new_path = directory / f"{stem}_{timestamp}_{counter:03d}{extension}"
                counter += 1
        else:
            # 連番ベースの解決
            counter = 1
            new_path = directory / f"{stem}_{counter:03d}{extension}"
            
            while new_path.exists() and counter <= self.MAX_COLLISION_ATTEMPTS:
                counter += 1
                new_path = directory / f"{stem}_{counter:03d}{extension}"
        
        if new_path.exists():
            raise RuntimeError(f"Failed to resolve path collision after {self.MAX_COLLISION_ATTEMPTS} attempts")
        
        final_path = str(new_path)
        if self.debug:
            self.logger.debug(f"Collision resolved: {final_path}")
        
        return final_path
    
    def get_output_info(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """出力ファイル情報を取得
        
        Args:
            input_path: 入力ファイルのパス
            output_path: 出力ファイルのパス
            
        Returns:
            出力ファイル情報の辞書
        """
        input_path_obj = Path(input_path)
        output_path_obj = Path(output_path)
        
        info = {
            'input_file': {
                'path': str(input_path_obj.absolute()),
                'name': input_path_obj.name,
                'stem': input_path_obj.stem,
                'suffix': input_path_obj.suffix,
                'size': input_path_obj.stat().st_size if input_path_obj.exists() else 0,
                'parent': str(input_path_obj.parent.absolute())
            },
            'output_file': {
                'path': str(output_path_obj.absolute()),
                'name': output_path_obj.name,
                'stem': output_path_obj.stem,
                'suffix': output_path_obj.suffix,
                'exists': output_path_obj.exists(),
                'parent': str(output_path_obj.parent.absolute())
            },
            'same_directory': input_path_obj.parent == output_path_obj.parent,
            'name_changed': input_path_obj.name != output_path_obj.name,
            'generation_timestamp': datetime.now().isoformat()
        }
        
        # 出力ディレクトリの情報
        output_dir = output_path_obj.parent
        info['output_directory'] = {
            'path': str(output_dir.absolute()),
            'exists': output_dir.exists(),
            'writable': os.access(str(output_dir), os.W_OK) if output_dir.exists() else False,
            'free_space': self._get_free_space(str(output_dir)) if output_dir.exists() else 0
        }
        
        return info
    
    def _get_free_space(self, path: str) -> int:
        """ディスクの空き容量を取得
        
        Args:
            path: パス
            
        Returns:
            空き容量（バイト）
        """
        try:
            stat_result = os.statvfs(path)
            # 空きブロック数 × ブロックサイズ
            return stat_result.f_bavail * stat_result.f_frsize
        except (OSError, AttributeError):
            return 0
    
    def validate_output_path(self, output_path: str, min_free_space: int = 1024 * 1024) -> Tuple[bool, List[str]]:
        """出力パスの妥当性を検証
        
        Args:
            output_path: 出力ファイルのパス
            min_free_space: 最小必要空き容量（バイト、デフォルト: 1MB）
            
        Returns:
            (妥当性, 問題のリスト)
        """
        issues = []
        output_path_obj = Path(output_path)
        
        # 親ディレクトリの存在確認
        parent_dir = output_path_obj.parent
        if not parent_dir.exists():
            issues.append(f"出力ディレクトリが存在しません: {parent_dir}")
        
        # 書き込み権限の確認
        if parent_dir.exists() and not os.access(str(parent_dir), os.W_OK):
            issues.append(f"出力ディレクトリへの書き込み権限がありません: {parent_dir}")
        
        # 空き容量の確認
        if parent_dir.exists():
            free_space = self._get_free_space(str(parent_dir))
            if free_space < min_free_space:
                issues.append(f"ディスクの空き容量が不足しています: {free_space:,} bytes < {min_free_space:,} bytes")
        
        # ファイル名の有効性確認
        try:
            # 無効な文字のチェック（Windows/Linuxで共通的に問題となる文字）
            invalid_chars = set('<>:"|?*')
            if any(char in output_path_obj.name for char in invalid_chars):
                issues.append(f"ファイル名に無効な文字が含まれています: {output_path_obj.name}")
        except Exception:
            issues.append(f"ファイル名が無効です: {output_path_obj.name}")
        
        # 既存ファイルの上書き警告
        if output_path_obj.exists():
            issues.append(f"出力ファイルが既に存在します: {output_path}")
        
        return len(issues) == 0, issues
    
    def suggest_alternative_paths(self, input_path: str, count: int = 3) -> List[str]:
        """代替出力パスの提案
        
        Args:
            input_path: 入力ファイルのパス
            count: 提案する代替パスの数
            
        Returns:
            代替パスのリスト
        """
        alternatives = []
        
        # 異なるサフィックスでの提案
        suffixes = ["_enhanced", "_processed", "_modified", "_updated", "_v2"]
        
        for suffix in suffixes[:count]:
            try:
                alt_path = self.generate_output_path(input_path, suffix=suffix)
                alternatives.append(alt_path)
            except Exception:
                continue
        
        # タイムスタンプベースの提案
        if len(alternatives) < count:
            try:
                timestamp_path = self.generate_output_path(
                    input_path, 
                    suffix=f"_{datetime.now().strftime(self.TIMESTAMP_FORMAT)}",
                    preserve_timestamp=True
                )
                alternatives.append(timestamp_path)
            except Exception:
                pass
        
        return alternatives[:count]
    
    def _is_docker_container(self) -> bool:
        """Dockerコンテナ内で実行されているかどうかを判定
        
        Returns:
            Dockerコンテナ内で実行されている場合True
        """
        try:
            # /.dockerenvファイルの存在チェック（最も一般的な方法）
            if os.path.exists('/.dockerenv'):
                return True
            
            # /proc/1/cgroupでcontainerが含まれているかチェック
            if os.path.exists('/proc/1/cgroup'):
                with open('/proc/1/cgroup', 'r') as f:
                    return 'docker' in f.read() or 'containerd' in f.read()
            
            # 環境変数による判定
            if os.environ.get('DOCKER_CONTAINER') == '1':
                return True
            
            # /app/inputと/app/outputディレクトリの存在チェック（このプロジェクト専用）
            if os.path.exists('/app/input') and os.path.exists('/app/output'):
                return True
            
            return False
        except Exception:
            return False


if __name__ == '__main__':
    # テスト実行
    generator = OutputPathGenerator(debug=True)
    
    # テスト用のサンプルファイルがある場合
    test_file = "sample.mp4"
    if os.path.exists(test_file):
        print(f"\n{'='*50}")
        print(f"Testing output path generation for: {test_file}")
        print('='*50)
        
        try:
            # 基本的な出力パス生成
            output_path = generator.generate_output_path(test_file)
            print(f"Generated output path: {output_path}")
            
            # 出力情報の取得
            info = generator.get_output_info(test_file, output_path)
            print(f"\nOutput info:")
            print(f"  Input: {info['input_file']['name']}")
            print(f"  Output: {info['output_file']['name']}")
            print(f"  Same directory: {info['same_directory']}")
            print(f"  Name changed: {info['name_changed']}")
            
            # 妥当性検証
            is_valid, issues = generator.validate_output_path(output_path)
            print(f"\nValidation: {'✓ Valid' if is_valid else '✗ Invalid'}")
            if issues:
                for issue in issues:
                    print(f"  - {issue}")
            
            # 代替パス提案
            alternatives = generator.suggest_alternative_paths(test_file)
            print(f"\nAlternative paths:")
            for i, alt in enumerate(alternatives, 1):
                print(f"  {i}. {alt}")
            
        except Exception as e:
            print(f"Error: {e}")
    else:
        print(f"Test file '{test_file}' not found. Creating a dummy file for testing.")
        
        # ダミーファイルでテスト
        dummy_file = "test_input.mp4"
        with open(dummy_file, 'w') as f:
            f.write("dummy video file")
        
        try:
            output_path = generator.generate_output_path(dummy_file)
            print(f"Generated output path: {output_path}")
            
            # 重複テスト
            print("\nTesting collision resolution:")
            for i in range(3):
                collision_path = generator.generate_output_path(dummy_file)
                print(f"  Attempt {i+1}: {collision_path}")
                # ダミーファイル作成で重複をシミュレート
                with open(collision_path, 'w') as f:
                    f.write("dummy output")
        
        finally:
            # クリーンアップ
            for file_to_remove in [dummy_file] + [f"test_input_enhanced_{i:03d}.mp4" for i in range(1, 10)]:
                try:
                    os.remove(file_to_remove)
                except FileNotFoundError:
                    pass
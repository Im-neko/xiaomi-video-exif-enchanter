#!/usr/bin/env python3
"""
Batch Processor
バッチ処理を統一管理するモジュール
"""

import os
import gc
import time
import multiprocessing
from typing import Optional, List, Dict, Any
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

from progress_manager import ProgressManager, ParallelProgressManager, print_batch_summary
from file_manager import FileManager, create_results_dict


def process_single_video_worker(input_path: str, output_path: str, location: Optional[str],
                               languages: List[str], use_gpu: bool, debug: bool) -> bool:
    """並列処理用のワーカー関数（プロセスプール用）"""
    try:
        # 動的インポートで循環インポートを回避
        import sys
        import importlib
        
        # exif_enhancerモジュールを動的にインポート
        if 'exif_enhancer' in sys.modules:
            exif_enhancer = sys.modules['exif_enhancer']
        else:
            exif_enhancer = importlib.import_module('exif_enhancer')
        
        # 各プロセスで独立したEnhancerインスタンスを作成
        enhancer = exif_enhancer.XiaomiVideoExifEnhancer(debug=debug, languages=languages, use_gpu=use_gpu)
        
        # 動画を処理
        success = enhancer.process_video(input_path, output_path, location)
        
        return success
        
    except Exception as e:
        if debug:
            print(f"Worker process error for {os.path.basename(input_path)}: {e}")
        return False


class BatchProcessor:
    """バッチ処理を管理するクラス"""
    
    def __init__(self, enhancer, debug: bool = False):
        self.enhancer = enhancer
        self.debug = debug
        self.file_manager = FileManager(debug=debug)
        
    def process_batch(self, input_directory: str, output_directory: Optional[str] = None,
                     location: Optional[str] = None, skip_errors: bool = True, 
                     max_workers: Optional[int] = None, use_threading: bool = False,
                     batch_size: Optional[int] = None) -> Dict[str, Any]:
        """ディレクトリ内のすべてのMP4ファイルをバッチ処理"""
        
        # 出力ディレクトリの設定
        if output_directory is None:
            output_directory = input_directory
        
        # 出力ディレクトリを作成
        self.file_manager.create_output_directory(output_directory)
        
        # 動画ファイルを取得
        video_files = self.file_manager.get_video_files(input_directory)
        
        if not video_files:
            print(f"No MP4 files found in directory: {input_directory}")
            return create_results_dict(0)
        
        # 未処理ファイルのフィルタリング
        unprocessed_files = self.file_manager.filter_unprocessed_files(video_files, output_directory)
        skipped_count = len(video_files) - len(unprocessed_files)
        
        if not unprocessed_files:
            print(f"All {len(video_files)} files have already been processed.")
            return create_results_dict(len(video_files), skipped_count)
        
        print(f"Found {len(video_files)} MP4 files, {len(unprocessed_files)} unprocessed")
        
        # バッチサイズの制限を適用
        video_files = self.file_manager.limit_batch_size(unprocessed_files, batch_size, max_workers)
        
        # 並列処理の設定を決定
        processing_config = self._determine_processing_config(video_files, max_workers)
        
        # 出力パス生成器を初期化
        path_generator = self._initialize_path_generator()
        
        # 処理結果を格納する辞書
        original_count = len(video_files) + skipped_count
        results = create_results_dict(original_count, skipped_count)
        
        # 並列処理または逐次処理の選択
        if processing_config['enable_parallel']:
            return self._process_batch_parallel(
                video_files, output_directory, location, skip_errors, 
                processing_config['max_workers'], use_threading, path_generator, results
            )
        else:
            return self._process_batch_sequential(
                video_files, output_directory, location, skip_errors, 
                path_generator, results
            )
    
    def _determine_processing_config(self, video_files: List[str], max_workers: Optional[int]) -> Dict[str, Any]:
        """並列処理の設定を決定"""
        original_max_workers = max_workers  # 元の値を保存
        
        if max_workers is None:
            # CPUコア数に基づいて自動設定（メモリ不足対応で少なめに設定）
            max_workers = min(len(video_files), max(1, multiprocessing.cpu_count() // 4))
        
        # 並列処理の有効性を決定
        if max_workers == 1:
            # 明示的に並列処理が無効化されている場合
            enable_parallel = False
            if self.debug:
                print("Parallel processing explicitly disabled")
        elif len(video_files) > 500 and original_max_workers != 1:
            # 500ファイル以上は並列処理を無効化（ただし明示的に1が指定された場合は除く）
            max_workers = 1
            enable_parallel = False
            if self.debug:
                print(f"Large file count ({len(video_files)}), disabling parallel processing to prevent memory issues")
        elif len(video_files) > 100:
            max_workers = min(max_workers, 2)  # 100-500ファイル時は最大2プロセス
            enable_parallel = True
        else:
            enable_parallel = len(video_files) > 2 and max_workers > 1
        
        if self.debug:
            print(f"Parallel processing: {'Enabled' if enable_parallel else 'Disabled'}")
            if enable_parallel:
                print(f"Max workers: {max_workers}")
        
        return {
            'enable_parallel': enable_parallel,
            'max_workers': max_workers
        }
    
    def _initialize_path_generator(self):
        """出力パス生成器を初期化"""
        try:
            from output_path_generator import OutputPathGenerator
            return OutputPathGenerator(debug=self.debug)
        except ImportError:
            if self.debug:
                print("OutputPathGenerator not available, using simple naming")
            return None
    
    def _process_batch_sequential(self, video_files: List[str], output_directory: str, 
                                 location: Optional[str], skip_errors: bool,
                                 path_generator, results: Dict[str, Any]) -> Dict[str, Any]:
        """逐次バッチ処理"""
        
        # プログレス管理の初期化
        progress = ProgressManager(debug=self.debug)
        progress.start_batch_progress(len(video_files))
        
        start_time = time.time()
        
        # 各ファイルを処理
        for i, input_file in enumerate(video_files, 1):
            file_name = os.path.basename(input_file)
            progress.update_progress(file_name)
            progress.write_debug_info(i, len(video_files), file_name)
            
            # 定期的なガベージコレクション
            if progress.check_gc_time():
                progress.write_debug_message("  Running garbage collection...")
                gc.collect()
            
            try:
                # 出力ファイルパスを生成
                output_file = self.file_manager.generate_output_path(
                    input_file, output_directory, path_generator)
                
                # 既存ファイルのスキップチェック
                existing_file = self.file_manager.check_existing_files(input_file, output_directory)
                if existing_file:
                    progress.write_debug_message(f"  ⚠ Output file already exists, skipping: {os.path.basename(existing_file)}")
                    results['skipped_files'].append({
                        'input': input_file,
                        'output': existing_file,
                        'reason': 'Output file already exists'
                    })
                    continue
                
                # ファイルを処理
                success = self.enhancer.process_video(input_file, output_file, location)
                
                if success:
                    results['successful'] += 1
                    results['processed_files'].append({
                        'input': input_file,
                        'output': output_file,
                        'status': 'success'
                    })
                    progress.write_debug_message(f"  ✅ Success: {os.path.basename(output_file)}")
                else:
                    results['failed'] += 1
                    results['failed_files'].append({
                        'input': input_file,
                        'output': output_file,
                        'error': 'Processing failed - moved to failed folder'
                    })
                    progress.write_debug_message(f"  ❌ Failed: {file_name}")
                    
                    if not skip_errors:
                        progress.write_message(f"Stopping batch processing due to error in: {file_name}")
                        break
                        
            except Exception as e:
                results['failed'] += 1
                results['failed_files'].append({
                    'input': input_file,
                    'output': '',
                    'error': str(e)
                })
                progress.write_message(f"  ❌ Error processing {file_name}: {e}")
                
                # バッチ処理での例外も失敗フォルダに移動
                try:
                    self.file_manager.move_to_failed_folder(
                        input_file, f"Batch processing error: {str(e)}", output_directory)
                except Exception as move_error:
                    progress.write_debug_message(f"Could not move failed file in batch processing: {move_error}")
                
                if not skip_errors:
                    progress.write_message(f"Stopping batch processing due to error in: {file_name}")
                    break
        
        progress.close()
        
        # 処理結果のサマリー
        print_batch_summary(results)
        
        return results
    
    def _process_batch_parallel(self, video_files: List[str], output_directory: str,
                               location: Optional[str], skip_errors: bool,
                               max_workers: int, use_threading: bool,
                               path_generator, results: Dict[str, Any]) -> Dict[str, Any]:
        """並列バッチ処理"""
        if self.debug:
            print(f"Starting parallel batch processing with {max_workers} workers")
        
        # プログレス管理の初期化
        progress = ParallelProgressManager(debug=self.debug)
        
        # 実行器の選択
        executor_class = ThreadPoolExecutor if use_threading else ProcessPoolExecutor
        
        try:
            with executor_class(max_workers=max_workers) as executor:
                # 処理タスクを作成
                future_to_file = {}
                
                # タスク投入用プログレスバー
                progress.start_submission_progress(len(video_files))
                
                for input_file in video_files:
                    progress.update_submission(os.path.basename(input_file))
                    
                    try:
                        # 出力ファイルパスを生成
                        output_file = self.file_manager.generate_output_path(
                            input_file, output_directory, path_generator)
                        
                        # 既存ファイルのスキップチェック
                        existing_file = self.file_manager.check_existing_files(input_file, output_directory)
                        if existing_file:
                            results['skipped_files'].append({
                                'input': input_file,
                                'output': existing_file,
                                'reason': 'Output file already exists'
                            })
                            continue
                        
                        # 並列処理タスクを投入
                        if use_threading:
                            # スレッドプール: 同一プロセス内でのOCRリーダー共有
                            future = executor.submit(self.enhancer._process_single_file_thread_safe, 
                                                    input_file, output_file, location)
                        else:
                            # プロセスプール: 各プロセスで独立したリーダー初期化
                            future = executor.submit(process_single_video_worker, 
                                                    input_file, output_file, location, 
                                                    self.enhancer.languages, self.enhancer.use_gpu, self.debug)
                        
                        future_to_file[future] = (input_file, output_file)
                        
                    except Exception as e:
                        results['failed'] += 1
                        results['failed_files'].append({
                            'input': input_file,
                            'output': '',
                            'error': f'Path generation error: {str(e)}'
                        })
                
                # 処理用プログレスバーに切り替え
                progress.start_processing_progress(len(future_to_file))
                
                # 結果を収集
                completed = 0
                total_tasks = len(future_to_file)
                
                for future in as_completed(future_to_file):
                    input_file, output_file = future_to_file[future]
                    file_name = os.path.basename(input_file)
                    completed += 1
                    
                    progress.update_processing(file_name)
                    
                    try:
                        success = future.result()
                        
                        if success:
                            results['successful'] += 1
                            results['processed_files'].append({
                                'input': input_file,
                                'output': output_file,
                                'status': 'success'
                            })
                            progress.write_debug_message(f"[{completed}/{total_tasks}] ✅ Success: {file_name}")
                        else:
                            results['failed'] += 1
                            results['failed_files'].append({
                                'input': input_file,
                                'output': output_file,
                                'error': 'Processing failed - moved to failed folder'
                            })
                            progress.write_debug_message(f"[{completed}/{total_tasks}] ❌ Failed: {file_name}")
                            
                            if not skip_errors:
                                # 残りのタスクをキャンセル
                                for remaining_future in future_to_file:
                                    if not remaining_future.done():
                                        remaining_future.cancel()
                                break
                                
                    except Exception as e:
                        results['failed'] += 1
                        results['failed_files'].append({
                            'input': input_file,
                            'output': output_file,
                            'error': str(e)
                        })
                        progress.write_message(f"[{completed}/{total_tasks}] ❌ Error: {file_name} - {e}")
                        
                        if not skip_errors:
                            break
                
                progress.close()
                            
        except Exception as e:
            print(f"❌ Parallel processing error: {e}")
            # フォールバックとして逐次処理を試行
            print("Falling back to sequential processing...")
            return self._process_batch_sequential(
                video_files, output_directory, location, skip_errors, 
                path_generator, results
            )
        
        # 処理結果のサマリー
        print(f"\n{'='*60}")
        print(f"PARALLEL BATCH PROCESSING SUMMARY")
        print_batch_summary(results)
        
        return results
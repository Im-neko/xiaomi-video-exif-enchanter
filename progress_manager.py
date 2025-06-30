#!/usr/bin/env python3
"""
Progress Manager
プログレスバーと進捗表示を統一管理するモジュール
"""

import time
from typing import Optional, List, Dict, Any
from tqdm import tqdm


class ProgressManager:
    """プログレスバーと進捗表示の統一管理クラス"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.progress_bar: Optional[tqdm] = None
        self.start_time: Optional[float] = None
        self.last_gc_time: Optional[float] = None
        
    def start_batch_progress(self, total_files: int, description: str = "Processing videos") -> None:
        """バッチ処理用プログレスバーを開始"""
        self.progress_bar = tqdm(total=total_files, desc=description, unit="file")
        self.start_time = time.time()
        self.last_gc_time = self.start_time
        
    def update_progress(self, filename: str, max_length: int = 30) -> None:
        """プログレスバーを更新"""
        if self.progress_bar:
            short_name = filename[:max_length] if len(filename) > max_length else filename
            self.progress_bar.set_description(f"Processing: {short_name}")
            self.progress_bar.update(1)
            
    def write_debug_info(self, current_index: int, total_files: int, filename: str) -> None:
        """デバッグ情報を出力"""
        if not self.debug or not self.progress_bar or not self.start_time:
            return
            
        elapsed_time = time.time() - self.start_time
        if current_index > 1:
            avg_time_per_file = elapsed_time / (current_index - 1)
            estimated_remaining = avg_time_per_file * (total_files - current_index + 1)
            self.progress_bar.write(f"[{current_index}/{total_files}] Processing: {filename}")
            self.progress_bar.write(f"  Elapsed: {elapsed_time:.1f}s | Est. remaining: {estimated_remaining:.1f}s")
        else:
            self.progress_bar.write(f"[{current_index}/{total_files}] Processing: {filename}")
            
    def write_message(self, message: str) -> None:
        """プログレスバーの下にメッセージを出力"""
        if self.progress_bar:
            self.progress_bar.write(message)
        else:
            print(message)
            
    def write_debug_message(self, message: str) -> None:
        """デバッグメッセージを出力"""
        if self.debug:
            self.write_message(message)
            
    def check_gc_time(self, gc_interval: int = 300) -> bool:
        """ガベージコレクション実行タイミングをチェック"""
        if not self.last_gc_time:
            return False
            
        current_time = time.time()
        if current_time - self.last_gc_time > gc_interval:
            self.last_gc_time = current_time
            return True
        return False
        
    def close(self) -> None:
        """プログレスバーを閉じる"""
        if self.progress_bar:
            self.progress_bar.close()
            self.progress_bar = None


class ParallelProgressManager:
    """並列処理用のプログレスマネージャー"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.submission_bar: Optional[tqdm] = None
        self.processing_bar: Optional[tqdm] = None
        
    def start_submission_progress(self, total_tasks: int) -> None:
        """タスク投入用プログレスバーを開始"""
        self.submission_bar = tqdm(total=total_tasks, desc="Submitting tasks", unit="task")
        
    def update_submission(self, filename: str, max_length: int = 20) -> None:
        """タスク投入の進捗を更新"""
        if self.submission_bar:
            short_name = filename[:max_length] if len(filename) > max_length else filename
            self.submission_bar.set_description(f"Submitting: {short_name}")
            self.submission_bar.update(1)
            
    def start_processing_progress(self, total_tasks: int) -> None:
        """処理用プログレスバーを開始"""
        if self.submission_bar:
            self.submission_bar.close()
            
        self.processing_bar = tqdm(total=total_tasks, desc="Processing videos", unit="file")
        
    def update_processing(self, filename: str, max_length: int = 25) -> None:
        """処理の進捗を更新"""
        if self.processing_bar:
            short_name = filename[:max_length] if len(filename) > max_length else filename
            self.processing_bar.set_description(f"Completed: {short_name}")
            self.processing_bar.update(1)
            
    def write_debug_message(self, message: str) -> None:
        """デバッグメッセージを出力"""
        if self.debug:
            if self.processing_bar:
                self.processing_bar.write(message)
            elif self.submission_bar:
                self.submission_bar.write(message)
            else:
                print(message)
                
    def write_message(self, message: str) -> None:
        """メッセージを出力"""
        if self.processing_bar:
            self.processing_bar.write(message)
        elif self.submission_bar:
            self.submission_bar.write(message)
        else:
            print(message)
            
    def close(self) -> None:
        """すべてのプログレスバーを閉じる"""
        if self.submission_bar:
            self.submission_bar.close()
            self.submission_bar = None
            
        if self.processing_bar:
            self.processing_bar.close()
            self.processing_bar = None


def print_batch_summary(results: Dict[str, Any]) -> None:
    """バッチ処理結果のサマリーを表示"""
    print(f"\n{'='*60}")
    print(f"BATCH PROCESSING SUMMARY")
    print(f"{'='*60}")
    print(f"Total files found: {results['total_files']}")
    print(f"Successfully processed: {results['successful']}")
    print(f"Failed: {results['failed']}")
    print(f"Skipped (already processed): {results['skipped']}")
    
    if results['successful'] > 0:
        print(f"\n✅ Successfully processed files:")
        for item in results['processed_files']:
            import os
            print(f"  {os.path.basename(item['input'])} → {os.path.basename(item['output'])}")
    
    if results['failed_files']:
        print(f"\n❌ Failed files:")
        for item in results['failed_files']:
            import os
            print(f"  {os.path.basename(item['input'])}: {item['error']}")
    
    if results['skipped_files']:
        print(f"\n⚠ Skipped files:")
        for item in results['skipped_files']:
            import os
            print(f"  {os.path.basename(item['input'])}: {item['reason']}")
    
    print(f"{'='*60}")
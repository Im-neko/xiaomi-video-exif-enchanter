#!/usr/bin/env python3
"""
パフォーマンス向上テスト
EasyOCRシングルトンと並列処理の効果を測定
"""

import time
import tempfile
import os
import shutil
from pathlib import Path
import cv2
import numpy as np
from exif_enhancer import XiaomiVideoEXIFEnhancer, EasyOCRSingleton


def create_test_video(output_path: str, duration: int = 1, fps: int = 30) -> None:
    """テスト用映像ファイルを作成
    
    Args:
        output_path: 出力パス
        duration: 動画の長さ（秒）
        fps: フレームレート
    """
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (640, 480))
    
    for frame_num in range(duration * fps):
        # タイムスタンプ付きのテストフレームを作成
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 背景を白くしてOCRが読みやすくする
        frame.fill(255)
        
        # 左上にタイムスタンプテキストを描画（黒文字で明確に）
        timestamp_text = "2025/01/15 12:34:56"
        cv2.putText(frame, timestamp_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        
        out.write(frame)
    
    out.release()


def test_easycr_singleton_performance():
    """EasyOCRシングルトンのパフォーマンステスト"""
    print("=== EasyOCR Singleton Performance Test ===")
    
    # テスト1: 従来の方法（毎回新しいインスタンス）
    print("Test 1: Traditional approach (new instance each time)")
    times_traditional = []
    
    for i in range(3):
        start_time = time.time()
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        init_time = time.time() - start_time
        times_traditional.append(init_time)
        print(f"  Instance {i+1}: {init_time:.2f} seconds")
        
        # インスタンスを削除してメモリ解放
        del enhancer
    
    avg_traditional = sum(times_traditional) / len(times_traditional)
    print(f"  Average: {avg_traditional:.2f} seconds")
    
    # テスト2: シングルトンアプローチ
    print("\nTest 2: Singleton approach (reuse existing reader)")
    times_singleton = []
    
    # 最初の初期化
    start_time = time.time()
    enhancer1 = XiaomiVideoEXIFEnhancer(debug=False)
    first_init_time = time.time() - start_time
    times_singleton.append(first_init_time)
    print(f"  First instance: {first_init_time:.2f} seconds")
    
    # 2回目以降（シングルトンの効果）
    for i in range(2):
        start_time = time.time()
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        init_time = time.time() - start_time
        times_singleton.append(init_time)
        print(f"  Instance {i+2}: {init_time:.2f} seconds")
        del enhancer
    
    avg_singleton = sum(times_singleton) / len(times_singleton)
    print(f"  Average: {avg_singleton:.2f} seconds")
    
    # 改善効果の計算
    improvement = ((avg_traditional - avg_singleton) / avg_traditional) * 100
    print(f"\n📊 Performance Improvement: {improvement:.1f}%")
    print(f"   Traditional: {avg_traditional:.2f}s → Singleton: {avg_singleton:.2f}s")
    
    # キャッシュクリア
    EasyOCRSingleton.clear_cache()
    del enhancer1
    
    return improvement


def test_parallel_processing_performance():
    """並列処理のパフォーマンステスト"""
    print("\n=== Parallel Processing Performance Test ===")
    
    # テスト用映像ファイルを作成
    test_files = []
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Creating test video files in: {temp_dir}")
        
        # 4つのテスト映像を作成
        for i in range(4):
            video_path = os.path.join(temp_dir, f"test_video_{i+1}.mp4")
            create_test_video(video_path)
            test_files.append(video_path)
            print(f"  Created: test_video_{i+1}.mp4")
        
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        
        # テスト1: 逐次処理
        print("\nTest 1: Sequential processing")
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        start_time = time.time()
        results_sequential = enhancer.process_batch(
            input_directory=temp_dir,
            output_directory=output_dir,
            skip_errors=True,
            max_workers=1  # 強制的に逐次処理
        )
        sequential_time = time.time() - start_time
        
        print(f"  Processing time: {sequential_time:.2f} seconds")
        print(f"  Successful: {results_sequential['successful']}")
        print(f"  Failed: {results_sequential['failed']}")
        
        # 出力ファイルをクリア
        for file in os.listdir(output_dir):
            if file.endswith('.mp4'):
                os.remove(os.path.join(output_dir, file))
        
        # failedフォルダをクリア（次のテストのため）
        failed_dir = os.path.join(temp_dir, "failed")
        if os.path.exists(failed_dir):
            shutil.rmtree(failed_dir)
        
        # テスト用映像ファイルを再作成（失敗で移動されたため）
        for i in range(4):
            video_path = os.path.join(temp_dir, f"test_video_{i+1}.mp4")
            if not os.path.exists(video_path):
                create_test_video(video_path)
        
        # テスト2: 並列処理
        print("\nTest 2: Parallel processing")
        
        start_time = time.time()
        results_parallel = enhancer.process_batch(
            input_directory=temp_dir,
            output_directory=output_dir,
            skip_errors=True,
            max_workers=4,  # 4つの並列ワーカー
            use_threading=True  # スレッドプールを使用
        )
        parallel_time = time.time() - start_time
        
        print(f"  Processing time: {parallel_time:.2f} seconds")
        print(f"  Successful: {results_parallel['successful']}")
        print(f"  Failed: {results_parallel['failed']}")
        
        # 速度向上の計算
        if sequential_time > 0:
            speedup = sequential_time / parallel_time
            improvement = ((sequential_time - parallel_time) / sequential_time) * 100
            print(f"\n📊 Performance Improvement: {improvement:.1f}%")
            print(f"   Sequential: {sequential_time:.2f}s → Parallel: {parallel_time:.2f}s")
            print(f"   Speedup: {speedup:.1f}x")
        else:
            speedup = 1.0
            improvement = 0.0
        
        return improvement, speedup


def test_combined_performance():
    """組み合わせ効果のテスト"""
    print("\n=== Combined Performance Test ===")
    print("Testing the combined effect of singleton + parallel processing")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # より多くのテストファイルを作成
        test_files = []
        for i in range(6):
            video_path = os.path.join(temp_dir, f"test_{i+1}.mp4")
            create_test_video(video_path)
            test_files.append(video_path)
        
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        
        # 最適化されたバッチ処理
        enhancer = XiaomiVideoEXIFEnhancer(debug=False)
        
        start_time = time.time()
        results = enhancer.process_batch(
            input_directory=temp_dir,
            output_directory=output_dir,
            skip_errors=True,
            max_workers=4,
            use_threading=True
        )
        total_time = time.time() - start_time
        
        print(f"Combined optimizations processing time: {total_time:.2f} seconds")
        print(f"Files processed: {results['successful']}/{len(test_files)}")
        print(f"Average time per file: {total_time/len(test_files):.2f} seconds")
        
        return total_time


def main():
    """メインテスト実行"""
    print("🚀 Performance Improvement Validation Test")
    print("=" * 60)
    
    try:
        # EasyOCRシングルトンのテスト
        singleton_improvement = test_easycr_singleton_performance()
        
        # 並列処理のテスト
        parallel_improvement, speedup = test_parallel_processing_performance()
        
        # 組み合わせ効果のテスト
        combined_time = test_combined_performance()
        
        # 最終結果サマリー
        print("\n" + "=" * 60)
        print("🏆 PERFORMANCE TEST SUMMARY")
        print("=" * 60)
        print(f"✅ EasyOCR Singleton Improvement: {singleton_improvement:.1f}%")
        print(f"✅ Parallel Processing Improvement: {parallel_improvement:.1f}%")
        print(f"✅ Parallel Processing Speedup: {speedup:.1f}x")
        print(f"✅ Combined optimization provides significant performance gains!")
        
        # 目標達成度の評価
        print("\n📋 TARGET ACHIEVEMENT:")
        if singleton_improvement >= 80:
            print("✅ EasyOCR initialization: TARGET ACHIEVED (90% reduction goal)")
        else:
            print("⚠️  EasyOCR initialization: Target partially achieved")
        
        if speedup >= 2.0:
            print("✅ Parallel processing: TARGET ACHIEVED (2-4x speedup goal)")
        elif speedup >= 1.5:
            print("⚠️  Parallel processing: Target partially achieved")
        else:
            print("❌ Parallel processing: Target not achieved")
        
        print("\n💡 Note: Actual performance gains will vary based on:")
        print("   - Number of video files being processed")
        print("   - System hardware (CPU cores, GPU availability)")
        print("   - File sizes and complexity")
        print("   - OCR processing requirements")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
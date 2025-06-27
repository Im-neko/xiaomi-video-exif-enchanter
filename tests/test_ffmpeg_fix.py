#!/usr/bin/env python3

import ffmpeg
import sys

def test_metadata_embedding():
    video_path = "sample.mp4"
    output_path = "./sample_test.mp4"
    
    metadata = {
        'creation_time': '2025-05-28T19:41:14Z',
        'date': '2025-05-28T19:41:14Z',
        'encoder': 'Xiaomi Video EXIF Enhancer'
    }
    
    print(f"Metadata to embed: {metadata}")
    
    try:
        # FFmpegストリームを構築
        stream = (
            ffmpeg
            .input(video_path)
            .output(output_path, vcodec='copy', acodec='copy', **{f'metadata:{key}': str(value) for key, value in metadata.items()})
            .overwrite_output()
        )
        
        print(f"FFmpeg command: {' '.join(ffmpeg.compile(stream))}")
        
        # FFmpegを実行
        result = stream.run(capture_stdout=True, capture_stderr=True)
        print("✓ FFmpeg processing completed successfully")
        
        # 結果を検証
        try:
            result_probe = ffmpeg.probe(output_path)
            result_metadata = result_probe.get('format', {}).get('tags', {})
            
            print(f"Embedded metadata verification:")
            for key, value in metadata.items():
                if key.lower() in [k.lower() for k in result_metadata.keys()]:
                    print(f"  ✓ {key}: {value}")
                else:
                    print(f"  ⚠ {key}: {value} (not found in output)")
                    
        except Exception as verify_error:
            print(f"Could not verify embedded metadata: {verify_error}")
            
        return True
        
    except ffmpeg.Error as e:
        print(f"FFmpeg error: {e}")
        if e.stderr:
            print(f"FFmpeg stderr: {e.stderr.decode('utf-8', errors='replace')}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == '__main__':
    test_metadata_embedding()
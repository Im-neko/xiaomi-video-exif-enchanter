#!/usr/bin/env python3
"""
Test script to verify batch resume functionality
"""

import os
import glob
from pathlib import Path

def test_file_filtering():
    """Test which files would be processed"""
    
    # Get all video files 
    input_dir = "input/"
    output_dir = "output/"
    
    video_extensions = ['*.mp4', '*.MP4']
    video_files = []
    
    for extension in video_extensions:
        pattern = os.path.join(input_dir, extension)
        video_files.extend(glob.glob(pattern))
    
    print(f"Total video files found: {len(video_files)}")
    
    # Sort by filename for consistent ordering
    video_files.sort()
    
    # Show first 10 files
    print(f"\nFirst 10 files in order:")
    for i, f in enumerate(video_files[:10]):
        print(f"  {i+1:3d}: {os.path.basename(f)}")
    
    # Filter unprocessed files
    unprocessed_files = []
    
    for input_file in video_files:
        base_name = Path(input_file).stem
        
        # Check all output patterns
        output_patterns = [
            os.path.join(output_dir, f"{base_name}_enhanced.mp4"),
            os.path.join(output_dir, f"{base_name}_processed.mp4"), 
            os.path.join(output_dir, f"{base_name}_modified.mp4"),
            os.path.join(output_dir, f"{base_name}.mp4"),
            os.path.join(output_dir, "failed", f"{base_name}.mp4"),
            os.path.join(output_dir, "failed", f"{base_name}_1.mp4"),
            os.path.join(output_dir, "failed", f"{base_name}_2.mp4"),
            os.path.join(output_dir, "failed", f"{base_name}_3.mp4")
        ]
        
        # Check if any pattern exists
        already_processed = any(os.path.exists(pattern) for pattern in output_patterns)
        
        if not already_processed:
            unprocessed_files.append(input_file)
    
    print(f"\nProcessed files: {len(video_files) - len(unprocessed_files)}")
    print(f"Unprocessed files: {len(unprocessed_files)}")
    
    if unprocessed_files:
        print(f"\nNext 10 unprocessed files that would be processed:")
        for i, f in enumerate(unprocessed_files[:10]):
            print(f"  {i+1:3d}: {os.path.basename(f)}")
    else:
        print(f"\n✅ All files have been processed!")
    
    return unprocessed_files

if __name__ == "__main__":
    test_file_filtering()
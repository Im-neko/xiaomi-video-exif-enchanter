#!/usr/bin/env python3
"""
Simple test to verify improved batch processing logic
"""

import subprocess
import sys

def test_batch_processing():
    """Test batch processing without GPU to avoid initialization delays"""
    
    print("Testing batch processing with CPU mode...")
    
    # Run with CPU mode to avoid GPU initialization delay
    cmd = [
        'python3', 'exif_enhancer.py',
        '--batch', 'input/',
        '--output', 'output/',
        '--batch-size', '3',
        '--disable-parallel',
        '--debug'
    ]
    
    # Set CPU mode environment
    import os
    env = os.environ.copy()
    env['FORCE_CPU_MODE'] = '1'
    
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)
    
    try:
        result = subprocess.run(cmd, 
                              capture_output=True, 
                              text=True, 
                              env=env,
                              timeout=30)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)
            
        print(f"\nExit code: {result.returncode}")
        
    except subprocess.TimeoutExpired:
        print("⚠ Command timed out after 30 seconds")
    except Exception as e:
        print(f"❌ Error running command: {e}")

if __name__ == "__main__":
    test_batch_processing()
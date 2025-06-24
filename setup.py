#!/usr/bin/env python3
"""Setup script for Xiaomi Video EXIF Enhancer."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="xiaomi-video-exif-enhancer",
    version="1.0.0",
    author="Xiaomi Video EXIF Enhancer",
    description="A tool to extract timestamps from Xiaomi camera videos and embed them as EXIF metadata",
    long_description=long_description,
    long_description_content_type="text/markdown",
    py_modules=["exif_enhancer"],
    install_requires=requirements,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "xiaomi-video-exif-enhancer=exif_enhancer:main",
        ],
    },
)
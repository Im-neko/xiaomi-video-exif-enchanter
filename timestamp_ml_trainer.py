#!/usr/bin/env python3
"""
Xiaomi Timestamp Recognition Model Trainer
既存の成功データから機械学習モデルを訓練してタイムスタンプ認識精度を向上
"""

import os
import re
import cv2
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import tensorflow as tf
from tensorflow import keras
from sklearn.model_selection import train_test_split
import subprocess

class XiaomiTimestampDataExtractor:
    """成功処理済みファイルから学習データを抽出"""
    
    def __init__(self, output_dir: str, debug: bool = False):
        self.output_dir = Path(output_dir)
        self.debug = debug
        self.timestamp_pattern = r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})'
    
    def extract_timestamp_from_filename(self, filename: str) -> Optional[str]:
        """ファイル名からタイムスタンプを抽出（拡張されたメタデータから）"""
        try:
            # FFprobeでメタデータからタイムスタンプを取得
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', str(filename)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                metadata = json.loads(result.stdout)
                creation_time = metadata.get('format', {}).get('tags', {}).get('creation_time')
                if creation_time:
                    # ISO形式から標準形式に変換
                    dt = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                    return dt.strftime('%Y/%m/%d %H:%M:%S')
            
            return None
        except Exception as e:
            if self.debug:
                print(f"Failed to extract timestamp from {filename}: {e}")
            return None
    
    def extract_frame_timestamp_region(self, video_path: str) -> Optional[np.ndarray]:
        """動画からタイムスタンプ領域を抽出"""
        try:
            cap = cv2.VideoCapture(str(video_path))
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return None
            
            # Xiaomi固定タイムスタンプ位置でクロップ
            height, width = frame.shape[:2]
            x_start = int(5 * width // 149)
            y_start = 0
            x_end = int(32 * width // 149)
            y_end = int(3 * height // 68)
            
            cropped = frame[y_start:y_end, x_start:x_end]
            return cropped
            
        except Exception as e:
            if self.debug:
                print(f"Failed to extract frame from {video_path}: {e}")
            return None
    
    def generate_training_data(self, max_samples: int = 1000) -> Tuple[List[np.ndarray], List[str]]:
        """成功処理済みファイルから学習データを生成"""
        images = []
        labels = []
        
        video_files = list(self.output_dir.glob("*.mp4"))
        
        if self.debug:
            print(f"Found {len(video_files)} processed video files")
        
        for i, video_path in enumerate(video_files[:max_samples]):
            if self.debug and i % 100 == 0:
                print(f"Processing {i}/{min(max_samples, len(video_files))}")
            
            # メタデータからタイムスタンプを取得
            timestamp_label = self.extract_timestamp_from_filename(video_path)
            if not timestamp_label:
                continue
            
            # フレームからタイムスタンプ画像を抽出
            timestamp_image = self.extract_frame_timestamp_region(video_path)
            if timestamp_image is None:
                continue
            
            # データの前処理
            # グレースケール変換
            if len(timestamp_image.shape) == 3:
                timestamp_image = cv2.cvtColor(timestamp_image, cv2.COLOR_BGR2GRAY)
            
            # サイズ正規化（64x16に統一）
            timestamp_image = cv2.resize(timestamp_image, (64, 16))
            
            # 正規化
            timestamp_image = timestamp_image.astype(np.float32) / 255.0
            
            images.append(timestamp_image)
            labels.append(timestamp_label)
        
        if self.debug:
            print(f"Generated {len(images)} training samples")
        
        return images, labels

class XiaomiTimestampCNN:
    """Xiaomiタイムスタンプ認識用CNNモデル"""
    
    def __init__(self, input_shape: Tuple[int, int] = (16, 64), debug: bool = False):
        self.input_shape = input_shape
        self.debug = debug
        self.model = None
        self.char_to_idx = self._build_char_mapping()
        self.idx_to_char = {v: k for k, v in self.char_to_idx.items()}
        self.max_length = 19  # "2025/07/01 12:34:56"
    
    def _build_char_mapping(self) -> Dict[str, int]:
        """文字とインデックスのマッピングを構築"""
        chars = "0123456789/:. "
        char_to_idx = {char: idx + 1 for idx, char in enumerate(chars)}
        char_to_idx['<PAD>'] = 0  # パディング文字
        return char_to_idx
    
    def encode_text(self, text: str) -> List[int]:
        """テキストを数値配列に変換"""
        encoded = [self.char_to_idx.get(char, 0) for char in text]
        # 固定長にパディング
        if len(encoded) < self.max_length:
            encoded.extend([0] * (self.max_length - len(encoded)))
        else:
            encoded = encoded[:self.max_length]
        return encoded
    
    def decode_text(self, encoded: List[int]) -> str:
        """数値配列をテキストに変換"""
        return ''.join([self.idx_to_char.get(idx, '') for idx in encoded if idx != 0])
    
    def build_model(self):
        """CNNモデルを構築"""
        inputs = keras.Input(shape=(*self.input_shape, 1), name='image')
        
        # CNN特徴抽出
        x = keras.layers.Conv2D(32, (3, 3), activation='relu', padding='same')(inputs)
        x = keras.layers.MaxPooling2D((2, 2))(x)
        
        x = keras.layers.Conv2D(64, (3, 3), activation='relu', padding='same')(x)
        x = keras.layers.MaxPooling2D((2, 2))(x)
        
        x = keras.layers.Conv2D(128, (3, 3), activation='relu', padding='same')(x)
        
        # RNN部分への準備
        x = keras.layers.Reshape((-1, 128))(x)
        
        # LSTM層
        x = keras.layers.LSTM(128, return_sequences=True)(x)
        x = keras.layers.LSTM(64, return_sequences=True)(x)
        
        # Dense層で文字予測
        x = keras.layers.TimeDistributed(
            keras.layers.Dense(len(self.char_to_idx), activation='softmax')
        )(x)
        
        # 固定長出力に調整
        x = keras.layers.Lambda(lambda x: x[:, :self.max_length, :])(x)
        
        self.model = keras.Model(inputs=inputs, outputs=x)
        
        # モデルコンパイル
        self.model.compile(
            optimizer='adam',
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )
        
        if self.debug:
            self.model.summary()
    
    def prepare_training_data(self, images: List[np.ndarray], labels: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """学習データの準備"""
        # 画像データの準備
        X = np.array(images)
        X = np.expand_dims(X, axis=-1)  # チャンネル次元追加
        
        # ラベルデータの準備
        y = []
        for label in labels:
            encoded = self.encode_text(label)
            y.append(encoded)
        
        y = np.array(y)
        
        return X, y
    
    def train(self, X: np.ndarray, y: np.ndarray, validation_split: float = 0.2, epochs: int = 50):
        """モデルの訓練"""
        if self.model is None:
            self.build_model()
        
        # データ分割
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=validation_split, random_state=42
        )
        
        # コールバック設定
        callbacks = [
            keras.callbacks.EarlyStopping(patience=10, restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=5),
            keras.callbacks.ModelCheckpoint(
                'xiaomi_timestamp_model.h5', 
                save_best_only=True, 
                monitor='val_loss'
            )
        ]
        
        # 訓練実行
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=32,
            callbacks=callbacks,
            verbose=1 if self.debug else 0
        )
        
        return history
    
    def predict_timestamp(self, image: np.ndarray) -> str:
        """画像からタイムスタンプを予測"""
        if self.model is None:
            raise ValueError("Model not trained yet")
        
        # 前処理
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        image = cv2.resize(image, (64, 16))
        image = image.astype(np.float32) / 255.0
        image = np.expand_dims(image, axis=(0, -1))
        
        # 予測
        predictions = self.model.predict(image, verbose=0)
        predicted_indices = np.argmax(predictions[0], axis=-1)
        
        # デコード
        timestamp = self.decode_text(predicted_indices.tolist())
        return timestamp.strip()
    
    def save_model(self, filepath: str):
        """モデルを保存"""
        if self.model:
            self.model.save(filepath)
            # 文字マッピングも保存
            mapping_path = filepath.replace('.h5', '_char_mapping.json')
            with open(mapping_path, 'w') as f:
                json.dump({
                    'char_to_idx': self.char_to_idx,
                    'max_length': self.max_length
                }, f)
    
    def load_model(self, filepath: str):
        """モデルを読み込み"""
        self.model = keras.models.load_model(filepath)
        # 文字マッピングも読み込み
        mapping_path = filepath.replace('.h5', '_char_mapping.json')
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r') as f:
                data = json.load(f)
                self.char_to_idx = data['char_to_idx']
                self.idx_to_char = {v: k for k, v in self.char_to_idx.items()}
                self.max_length = data['max_length']

def main():
    """メイン実行関数"""
    output_dir = "/mnt/c/Users/micro/apps/xiaomi-video-exif-enchanter/output"
    debug = True
    
    print("🚀 Xiaomi Timestamp ML Training Started")
    
    # 1. データ抽出
    print("📊 Extracting training data from successful files...")
    extractor = XiaomiTimestampDataExtractor(output_dir, debug=debug)
    images, labels = extractor.generate_training_data(max_samples=500)  # 最初は500サンプルでテスト
    
    if len(images) == 0:
        print("❌ No training data generated")
        return
    
    print(f"✅ Generated {len(images)} training samples")
    
    # 2. モデル構築と訓練
    print("🧠 Building and training timestamp recognition model...")
    model = XiaomiTimestampCNN(debug=debug)
    X, y = model.prepare_training_data(images, labels)
    
    print(f"📈 Training data shape: X={X.shape}, y={y.shape}")
    
    # 3. 訓練実行
    history = model.train(X, y, epochs=30)
    
    # 4. モデル保存
    model_path = "xiaomi_timestamp_model.h5"
    model.save_model(model_path)
    print(f"💾 Model saved to: {model_path}")
    
    # 5. 簡単なテスト
    print("🧪 Testing model with sample data...")
    if len(images) > 0:
        test_image = images[0]
        predicted = model.predict_timestamp(test_image)
        actual = labels[0]
        print(f"Actual: {actual}")
        print(f"Predicted: {predicted}")
    
    print("🎉 Training completed!")

if __name__ == "__main__":
    main()
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
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
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

class TimestampDataset(Dataset):
    """PyTorch Dataset for timestamp images and labels"""
    
    def __init__(self, images, labels, char_to_idx, max_length=19):
        self.images = images
        self.labels = labels
        self.char_to_idx = char_to_idx
        self.max_length = max_length
    
    def __len__(self):
        return len(self.images)
    
    def __getitem__(self, idx):
        image = self.images[idx]
        label = self.labels[idx]
        
        # Convert image to tensor
        image_tensor = torch.FloatTensor(image).unsqueeze(0)  # Add channel dimension
        
        # Encode label
        encoded_label = self.encode_text(label)
        label_tensor = torch.LongTensor(encoded_label)
        
        return image_tensor, label_tensor
    
    def encode_text(self, text: str) -> List[int]:
        """テキストを数値配列に変換"""
        encoded = [self.char_to_idx.get(char, 0) for char in text]
        # 固定長にパディング
        if len(encoded) < self.max_length:
            encoded.extend([0] * (self.max_length - len(encoded)))
        else:
            encoded = encoded[:self.max_length]
        return encoded

class XiaomiTimestampCNN(nn.Module):
    """Xiaomiタイムスタンプ認識用CNNモデル"""
    
    def __init__(self, num_chars: int, max_length: int = 19):
        super(XiaomiTimestampCNN, self).__init__()
        self.max_length = max_length
        
        # CNN特徴抽出
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.3)
        
        # LSTM for sequence modeling
        self.lstm = nn.LSTM(128, 128, batch_first=True, bidirectional=True)
        
        # Output layer
        self.fc = nn.Linear(256, num_chars)  # 256 because bidirectional LSTM
    
    def forward(self, x):
        # CNN feature extraction
        x = F.relu(self.conv1(x))
        x = self.pool(x)
        
        x = F.relu(self.conv2(x))
        x = self.pool(x)
        
        x = F.relu(self.conv3(x))
        
        # Reshape for LSTM (batch, seq_len, features)
        batch_size, channels, height, width = x.size()
        x = x.view(batch_size, channels, -1).permute(0, 2, 1)
        
        # LSTM
        x, _ = self.lstm(x)
        x = self.dropout(x)
        
        # Take first max_length timesteps
        x = x[:, :self.max_length, :]
        
        # Output layer
        x = self.fc(x)
        
        return x

class XiaomiTimestampTrainer:
    """PyTorchベースのタイムスタンプ認識トレーナー"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.char_to_idx = self._build_char_mapping()
        self.idx_to_char = {v: k for k, v in self.char_to_idx.items()}
        self.max_length = 19  # "2025/07/01 12:34:56"
        self.model = None
        self.device = torch.device('cpu')  # Force CPU mode for compatibility
        
        if self.debug:
            print(f"Using device: {self.device}")
    
    def _build_char_mapping(self) -> Dict[str, int]:
        """文字とインデックスのマッピングを構築"""
        chars = "0123456789/:. "
        char_to_idx = {char: idx + 1 for idx, char in enumerate(chars)}
        char_to_idx['<PAD>'] = 0  # パディング文字
        return char_to_idx
    
    def decode_text(self, encoded: List[int]) -> str:
        """数値配列をテキストに変換"""
        return ''.join([self.idx_to_char.get(idx, '') for idx in encoded if idx != 0])
    
    def build_model(self):
        """モデルを構築"""
        self.model = XiaomiTimestampCNN(
            num_chars=len(self.char_to_idx),
            max_length=self.max_length
        ).to(self.device)
        
        if self.debug:
            print(f"Model parameters: {sum(p.numel() for p in self.model.parameters())}")
    
    def train(self, images: List[np.ndarray], labels: List[str], epochs: int = 30, batch_size: int = 32):
        """モデルの訓練"""
        if self.model is None:
            self.build_model()
        
        # データ分割
        X_train, X_val, y_train, y_val = train_test_split(
            images, labels, test_size=0.2, random_state=42
        )
        
        # Dataset とDataLoader作成
        train_dataset = TimestampDataset(X_train, y_train, self.char_to_idx, self.max_length)
        val_dataset = TimestampDataset(X_val, y_val, self.char_to_idx, self.max_length)
        
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
        
        # オプティマイザーと損失関数
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss(ignore_index=0)  # パディングを無視
        
        best_val_loss = float('inf')
        
        for epoch in range(epochs):
            # Training phase
            self.model.train()
            train_loss = 0.0
            
            for batch_images, batch_labels in train_loader:
                batch_images = batch_images.to(self.device)
                batch_labels = batch_labels.to(self.device)
                
                optimizer.zero_grad()
                outputs = self.model(batch_images)
                
                # Reshape for loss calculation
                outputs = outputs.view(-1, len(self.char_to_idx))
                batch_labels = batch_labels.view(-1)
                
                loss = criterion(outputs, batch_labels)
                loss.backward()
                optimizer.step()
                
                train_loss += loss.item()
            
            # Validation phase
            self.model.eval()
            val_loss = 0.0
            
            with torch.no_grad():
                for batch_images, batch_labels in val_loader:
                    batch_images = batch_images.to(self.device)
                    batch_labels = batch_labels.to(self.device)
                    
                    outputs = self.model(batch_images)
                    outputs = outputs.view(-1, len(self.char_to_idx))
                    batch_labels = batch_labels.view(-1)
                    
                    loss = criterion(outputs, batch_labels)
                    val_loss += loss.item()
            
            train_loss /= len(train_loader)
            val_loss /= len(val_loader)
            
            if self.debug:
                print(f"Epoch {epoch+1}/{epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
            
            # Save best model
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                torch.save(self.model.state_dict(), 'xiaomi_timestamp_model.pth')
        
        if self.debug:
            print("Training completed!")
    
    def predict_timestamp(self, image: np.ndarray) -> str:
        """画像からタイムスタンプを予測"""
        if self.model is None:
            raise ValueError("Model not trained yet")
        
        # 前処理
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        image = cv2.resize(image, (64, 16))
        image = image.astype(np.float32) / 255.0
        image_tensor = torch.FloatTensor(image).unsqueeze(0).unsqueeze(0).to(self.device)
        
        # 予測
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(image_tensor)
            predicted_indices = torch.argmax(outputs, dim=-1).squeeze().cpu().numpy()
        
        # デコード
        timestamp = self.decode_text(predicted_indices.tolist())
        return timestamp.strip()
    
    def save_model(self, filepath: str):
        """モデルを保存"""
        if self.model:
            torch.save({
                'model_state_dict': self.model.state_dict(),
                'char_to_idx': self.char_to_idx,
                'max_length': self.max_length
            }, filepath)
    
    def load_model(self, filepath: str):
        """モデルを読み込み"""
        checkpoint = torch.load(filepath, map_location=self.device)
        self.char_to_idx = checkpoint['char_to_idx']
        self.idx_to_char = {v: k for k, v in self.char_to_idx.items()}
        self.max_length = checkpoint['max_length']
        
        self.build_model()
        self.model.load_state_dict(checkpoint['model_state_dict'])

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
    trainer = XiaomiTimestampTrainer(debug=debug)
    
    # 3. 訓練実行
    trainer.train(images, labels, epochs=30)
    
    # 4. モデル保存
    model_path = "xiaomi_timestamp_model.pth"
    trainer.save_model(model_path)
    print(f"💾 Model saved to: {model_path}")
    
    # 5. 簡単なテスト
    print("🧪 Testing model with sample data...")
    if len(images) > 0:
        test_image = images[0]
        predicted = trainer.predict_timestamp(test_image)
        actual = labels[0]
        print(f"Actual: {actual}")
        print(f"Predicted: {predicted}")
    
    print("🎉 Training completed!")

if __name__ == "__main__":
    main()
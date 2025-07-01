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
import torch.nn.init as init
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
            x_start = int(20 * width // 640)  # 20/640 * width
            y_start = 0
            x_end = int(155 * width // 640)  # 155/640 * width
            y_end = int(16 * height // 360)  # 16/360 * height
            
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
            
            # 改良されたデータ前処理
            timestamp_image = self.preprocess_image(timestamp_image)
            if timestamp_image is None:
                continue
            
            images.append(timestamp_image)
            labels.append(timestamp_label)
        
        if self.debug:
            print(f"Generated {len(images)} training samples")
        
        # データオーグメンテーションでデータを増強
        augmented_images, augmented_labels = self.augment_data(images, labels)
        images.extend(augmented_images)
        labels.extend(augmented_labels)
        
        return images, labels
    
    def preprocess_image(self, image: np.ndarray) -> Optional[np.ndarray]:
        """改良された画像前処理"""
        try:
            # グレースケール変換
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()
            
            # コントラスト強化
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            
            # ガウシアンフィルタでノイズ除去
            denoised = cv2.GaussianBlur(enhanced, (3, 3), 0.5)
            
            # シャープニング
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(denoised, -1, kernel)
            
            # サイズ正規化（96x24に変更して精度向上）
            resized = cv2.resize(sharpened, (96, 24), interpolation=cv2.INTER_LANCZOS4)
            
            # 正規化
            normalized = resized.astype(np.float32) / 255.0
            
            return normalized
        except Exception as e:
            return None
    
    def augment_data(self, images: List[np.ndarray], labels: List[str]) -> Tuple[List[np.ndarray], List[str]]:
        """データオーグメンテーションでデータを増強"""
        augmented_images = []
        augmented_labels = []
        
        for image, label in zip(images, labels):
            # ノイズ追加
            noise = np.random.normal(0, 0.02, image.shape).astype(np.float32)
            noisy_image = np.clip(image + noise, 0, 1)
            augmented_images.append(noisy_image)
            augmented_labels.append(label)
            
            # 明度調整
            brightness_factor = np.random.uniform(0.8, 1.2)
            bright_image = np.clip(image * brightness_factor, 0, 1)
            augmented_images.append(bright_image)
            augmented_labels.append(label)
            
            # 軽微な回転
            angle = np.random.uniform(-2, 2)
            h, w = image.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            augmented_images.append(rotated)
            augmented_labels.append(label)
        
        return augmented_images, augmented_labels

class TimestampDataset(Dataset):
    """CTC用PyTorch Dataset for timestamp images and labels"""
    
    def __init__(self, images, labels, char_to_idx):
        self.images = images
        self.labels = labels
        self.char_to_idx = char_to_idx
        self.max_target_length = max(len(label) for label in labels) if labels else 20
    
    def __len__(self):
        return len(self.images)
    
    def __getitem__(self, idx):
        image = self.images[idx]
        label = self.labels[idx]
        
        # Convert image to tensor
        image_tensor = torch.FloatTensor(image).unsqueeze(0)  # Add channel dimension
        
        # Encode label for CTC (without blank padding)
        encoded_label = self.encode_text_ctc(label)
        
        # Pad to consistent length for batching
        padded_label = encoded_label + [0] * (self.max_target_length - len(encoded_label))
        label_tensor = torch.LongTensor(padded_label[:self.max_target_length])
        
        return image_tensor, label_tensor
    
    def encode_text_ctc(self, text: str) -> List[int]:
        """CTC用テキストエンコーディング（blankなし）"""
        encoded = []
        for char in text:
            if char in self.char_to_idx and self.char_to_idx[char] != 0:  # Skip blank
                encoded.append(self.char_to_idx[char])
        return encoded

class XiaomiTimestampCRNN(nn.Module):
    """CRNN-CTC based Xiaomiタイムスタンプ認識モデル（2024最新技術）"""
    
    def __init__(self, num_chars: int, img_height: int = 24, img_width: int = 96):
        super(XiaomiTimestampCRNN, self).__init__()
        self.num_chars = num_chars
        self.img_height = img_height
        self.img_width = img_width
        
        # 改良されたCNN特徴抽出層（ResNet風のブロック）
        self.conv_block1 = self._conv_block(1, 64)
        self.conv_block2 = self._conv_block(64, 128)
        self.conv_block3 = self._conv_block(128, 256)
        self.conv_block4 = self._conv_block(256, 512)
        
        # Adaptive Average Pooling for consistent feature size
        self.adaptive_pool = nn.AdaptiveAvgPool2d((1, None))
        
        # Bidirectional LSTM layers
        self.lstm1 = nn.LSTM(512, 256, batch_first=True, bidirectional=True)
        self.lstm2 = nn.LSTM(512, 256, batch_first=True, bidirectional=True)
        self.dropout_lstm = nn.Dropout(0.25)
        
        # Attention mechanism
        self.attention = nn.MultiheadAttention(512, 8, batch_first=True, dropout=0.1)
        
        # Layer normalization
        self.layer_norm = nn.LayerNorm(512)
        
        # CTC output layer (no activation - CTC handles this)
        self.classifier = nn.Linear(512, num_chars)
        
        # Initialize weights
        self._initialize_weights()
    
    def _conv_block(self, in_channels: int, out_channels: int) -> nn.Module:
        """ResNet風の畳み込みブロック"""
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2)
        )
    
    def _initialize_weights(self):
        """重み初期化"""
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                init.constant_(m.weight, 1)
                init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                init.normal_(m.weight, 0, 0.01)
                if m.bias is not None:
                    init.constant_(m.bias, 0)
            elif isinstance(m, nn.LSTM):
                for param in m.parameters():
                    if len(param.shape) >= 2:
                        init.orthogonal_(param.data)
                    else:
                        init.normal_(param.data)
    
    def forward(self, x):
        # CNN特徴抽出
        x = self.conv_block1(x)  # (B, 64, H/2, W/2)
        x = self.conv_block2(x)  # (B, 128, H/4, W/4)
        x = self.conv_block3(x)  # (B, 256, H/8, W/8)
        x = self.conv_block4(x)  # (B, 512, H/16, W/16)
        
        # Adaptive pooling to ensure consistent feature size
        x = self.adaptive_pool(x)  # (B, 512, 1, W/16)
        
        # Reshape for RNN: (batch, seq_len, features)
        batch_size, channels, height, width = x.size()
        x = x.squeeze(2)  # Remove height dimension: (B, 512, W/16)
        x = x.permute(0, 2, 1)  # (B, W/16, 512)
        
        # First LSTM layer
        x, _ = self.lstm1(x)  # (B, W/16, 512)
        x = self.dropout_lstm(x)
        
        # Self-attention mechanism
        attn_out, _ = self.attention(x, x, x)
        x = x + attn_out  # Residual connection
        x = self.layer_norm(x)
        
        # Second LSTM layer
        x, _ = self.lstm2(x)  # (B, W/16, 512)
        x = self.dropout_lstm(x)
        
        # CTC output layer (no softmax - CTC loss handles this)
        x = self.classifier(x)  # (B, W/16, num_chars)
        
        # For CTC loss, we need (seq_len, batch, num_chars)
        x = x.permute(1, 0, 2)
        
        return x

class XiaomiTimestampTrainer:
    """CRNN-CTC based PyTorchタイムスタンプ認識トレーナー（2024最新技術）"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.char_to_idx = self._build_char_mapping()
        self.idx_to_char = {v: k for k, v in self.char_to_idx.items()}
        self.blank_idx = 0  # CTC blank character index
        self.model = None
        # RTX 5070 Ti with sm_120 CUDA capability support
        if torch.cuda.is_available():
            try:
                # Test if CUDA actually works with a simple operation
                test_tensor = torch.tensor([1.0], device='cuda')
                _ = test_tensor + 1
                self.device = torch.device('cuda')
                
                # Enable optimizations for RTX 5070 Ti
                if hasattr(torch.backends.cudnn, 'benchmark'):
                    torch.backends.cudnn.benchmark = True
                if hasattr(torch.backends.cudnn, 'allow_tf32'):
                    torch.backends.cudnn.allow_tf32 = True
                if hasattr(torch.backends.cuda, 'matmul'):
                    torch.backends.cuda.matmul.allow_tf32 = True
                    
                # AMP scaler for mixed precision training
                self.amp_enabled = True
                self.scaler = torch.amp.GradScaler('cuda')
                
            except RuntimeError as e:
                if "no kernel image is available" in str(e):
                    print(f"Warning: CUDA kernel compatibility issue detected. Falling back to CPU.")
                    print(f"Consider installing PyTorch nightly build: pip install --pre torch --index-url https://download.pytorch.org/whl/nightly/cu128")
                    self.device = torch.device('cpu')
                    self.amp_enabled = False
                    self.scaler = None
                else:
                    raise e
        else:
            self.device = torch.device('cpu')
            self.amp_enabled = False
            self.scaler = None
        
        if self.debug:
            print(f"Using device: {self.device}")
            if torch.cuda.is_available():
                print(f"GPU: {torch.cuda.get_device_name(0)}")
                print(f"CUDA version: {torch.version.cuda}")
                print(f"Mixed Precision (AMP): {self.amp_enabled}")
                print(f"TensorFloat-32 (TF32): {torch.backends.cuda.matmul.allow_tf32 if hasattr(torch.backends.cuda, 'matmul') else 'Not available'}")
                print(f"cuDNN Benchmark: {torch.backends.cudnn.benchmark if hasattr(torch.backends.cudnn, 'benchmark') else 'Not available'}")
            else:
                print("GPU not available, using CPU")
    
    def _build_char_mapping(self) -> Dict[str, int]:
        """CTC用文字マッピングを構築"""
        chars = "0123456789/:. @-"
        char_to_idx = {'<BLANK>': 0}  # CTC blank character
        char_to_idx.update({char: idx + 1 for idx, char in enumerate(chars)})
        return char_to_idx
    
    def decode_ctc(self, predictions: torch.Tensor) -> str:
        """CTCデコーディングでテキストを抽出"""
        # CTC greedy decoding
        _, max_indices = torch.max(predictions, dim=2)
        max_indices = max_indices.squeeze(1).cpu().numpy()
        
        # CTC decoding: remove duplicates and blanks
        decoded = []
        prev_idx = -1
        for idx in max_indices:
            if idx != prev_idx and idx != self.blank_idx:
                decoded.append(idx)
            prev_idx = idx
        
        # Convert to text
        text = ''.join([self.idx_to_char.get(idx, '') for idx in decoded])
        return self.validate_and_correct_timestamp(text)
    
    def validate_and_correct_timestamp(self, timestamp: str) -> str:
        """タイムスタンプの数値制約をチェックし、修正する"""
        import re
        
        # 基本パターンで数値を抽出
        pattern = r'(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})'
        match = re.search(pattern, timestamp)
        
        if match:
            year, month, day, hour, minute, second = match.groups()
            
            # 数値制約を適用
            year = max(2020, min(2030, int(year)))
            month = max(1, min(12, int(month)))
            day = max(1, min(31, int(day)))
            hour = max(0, min(23, int(hour)))
            minute = max(0, min(59, int(minute)))
            second = max(0, min(59, int(second)))
            
            # 月日の妙細なチェック
            if month == 2:
                day = min(day, 29)
            elif month in [4, 6, 9, 11]:
                day = min(day, 30)
            
            return f"{year:04d}/{month:02d}/{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        
        return timestamp
    
    def build_model(self):
        """モデルを構築"""
        self.model = XiaomiTimestampCRNN(
            num_chars=len(self.char_to_idx),
            img_height=24,
            img_width=96
        ).to(self.device)
        
        if self.debug:
            print(f"Model parameters: {sum(p.numel() for p in self.model.parameters())}")
            print(f"Character mapping size: {len(self.char_to_idx)}")
            print(f"Characters: {list(self.char_to_idx.keys())}")
    
    def train(self, images: List[np.ndarray], labels: List[str], epochs: int = 30, batch_size: int = 32, accumulation_steps: int = 4):
        """モデルの訓練 - AMP + Gradient Accumulation対応"""
        if self.model is None:
            self.build_model()
        
        # データ分割
        X_train, X_val, y_train, y_val = train_test_split(
            images, labels, test_size=0.2, random_state=42
        )
        
        # Dataset とDataLoader作成（最適化されたパラメータ）
        train_dataset = TimestampDataset(X_train, y_train, self.char_to_idx)
        val_dataset = TimestampDataset(X_val, y_val, self.char_to_idx)
        
        # DataLoader最適化：pin_memory, num_workers, prefetch_factor
        num_workers = min(4, torch.get_num_threads())
        
        train_loader = DataLoader(
            train_dataset, 
            batch_size=batch_size, 
            shuffle=True,
            num_workers=num_workers,
            pin_memory=self.device.type == 'cuda',
            prefetch_factor=2 if num_workers > 0 else None,
            persistent_workers=num_workers > 0
        )
        val_loader = DataLoader(
            val_dataset, 
            batch_size=batch_size, 
            shuffle=False,
            num_workers=num_workers,
            pin_memory=self.device.type == 'cuda',
            prefetch_factor=2 if num_workers > 0 else None,
            persistent_workers=num_workers > 0
        )
        
        # CTC損失関数と最適化器
        criterion = nn.CTCLoss(blank=self.blank_idx, reduction='mean', zero_infinity=True)
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=0.001, weight_decay=1e-4, 
                                      betas=(0.9, 0.999), eps=1e-8)
        
        # Effective batch size through gradient accumulation
        effective_steps_per_epoch = len(train_loader) // accumulation_steps
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=0.001, steps_per_epoch=effective_steps_per_epoch, 
            epochs=epochs, pct_start=0.3, anneal_strategy='cos'
        )
        
        best_val_loss = float('inf')
        
        if self.debug:
            print(f"Training configuration:")
            print(f"  Batch size: {batch_size}")
            print(f"  Accumulation steps: {accumulation_steps}")
            print(f"  Effective batch size: {batch_size * accumulation_steps}")
            print(f"  Mixed precision: {self.amp_enabled}")
            print(f"  Workers: {num_workers}")
        
        for epoch in range(epochs):
            # Training phase
            self.model.train()
            train_loss = 0.0
            accumulation_loss = 0.0
            
            for i, (batch_images, batch_labels) in enumerate(train_loader):
                batch_images = batch_images.to(self.device, non_blocking=True)
                batch_labels = batch_labels.to(self.device, non_blocking=True)
                
                # Mixed precision forward pass
                if self.amp_enabled:
                    with torch.amp.autocast('cuda'):
                        log_probs = self.model(batch_images)  # (seq_len, batch, num_chars)
                        log_probs = F.log_softmax(log_probs, dim=2)
                        
                        # Prepare for CTC loss
                        input_lengths = torch.full((batch_images.size(0),), log_probs.size(0), dtype=torch.long)
                        target_lengths = torch.sum(batch_labels != 0, dim=1)  # Count non-blank chars
                        
                        # Remove blank characters from targets for CTC
                        targets = []
                        for label in batch_labels:
                            target = label[label != 0].cpu()  # Remove padding/blank
                            targets.append(target)
                        targets = torch.cat(targets)
                        
                        # CTC loss (normalized by accumulation steps)
                        loss = criterion(log_probs, targets, input_lengths, target_lengths) / accumulation_steps
                else:
                    # Standard precision forward pass
                    log_probs = self.model(batch_images)  # (seq_len, batch, num_chars)
                    log_probs = F.log_softmax(log_probs, dim=2)
                    
                    # Prepare for CTC loss
                    input_lengths = torch.full((batch_images.size(0),), log_probs.size(0), dtype=torch.long)
                    target_lengths = torch.sum(batch_labels != 0, dim=1)  # Count non-blank chars
                    
                    # Remove blank characters from targets for CTC
                    targets = []
                    for label in batch_labels:
                        target = label[label != 0].cpu()  # Remove padding/blank
                        targets.append(target)
                    targets = torch.cat(targets)
                    
                    # CTC loss (normalized by accumulation steps)
                    loss = criterion(log_probs, targets, input_lengths, target_lengths) / accumulation_steps
                
                # Backward pass with AMP
                if self.amp_enabled:
                    self.scaler.scale(loss).backward()
                else:
                    loss.backward()
                
                accumulation_loss += loss.item()
                
                # Perform optimizer step after accumulation
                if (i + 1) % accumulation_steps == 0:
                    if self.amp_enabled:
                        # Gradient clipping for stability
                        self.scaler.unscale_(optimizer)
                        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                        
                        self.scaler.step(optimizer)
                        self.scaler.update()
                    else:
                        # Gradient clipping for stability
                        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                        optimizer.step()
                    
                    optimizer.zero_grad(set_to_none=True)  # More memory efficient
                    scheduler.step()  # Step scheduler after effective batch
                    
                    train_loss += accumulation_loss
                    accumulation_loss = 0.0
            
            # Validation phase
            self.model.eval()
            val_loss = 0.0
            
            with torch.no_grad():
                for batch_images, batch_labels in val_loader:
                    batch_images = batch_images.to(self.device, non_blocking=True)
                    batch_labels = batch_labels.to(self.device, non_blocking=True)
                    
                    if self.amp_enabled:
                        with torch.amp.autocast('cuda'):
                            log_probs = self.model(batch_images)
                            log_probs = F.log_softmax(log_probs, dim=2)
                            
                            input_lengths = torch.full((batch_images.size(0),), log_probs.size(0), dtype=torch.long)
                            target_lengths = torch.sum(batch_labels != 0, dim=1)
                            
                            targets = []
                            for label in batch_labels:
                                target = label[label != 0].cpu()
                                targets.append(target)
                            targets = torch.cat(targets)
                            
                            loss = criterion(log_probs, targets, input_lengths, target_lengths)
                    else:
                        log_probs = self.model(batch_images)
                        log_probs = F.log_softmax(log_probs, dim=2)
                        
                        input_lengths = torch.full((batch_images.size(0),), log_probs.size(0), dtype=torch.long)
                        target_lengths = torch.sum(batch_labels != 0, dim=1)
                        
                        targets = []
                        for label in batch_labels:
                            target = label[label != 0].cpu()
                            targets.append(target)
                        targets = torch.cat(targets)
                        
                        loss = criterion(log_probs, targets, input_lengths, target_lengths)
                    
                    val_loss += loss.item()
            
            # Adjust loss calculation for accumulation steps
            train_loss /= effective_steps_per_epoch
            val_loss /= len(val_loader)
            
            if self.debug:
                print(f"Epoch {epoch+1}/{epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
            
            # OneCycleLRはバッチごとに更新するため、エポックごとの更新は不要
            
            # Save best model
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                torch.save({
                    'model_state_dict': self.model.state_dict(),
                    'char_to_idx': self.char_to_idx,
                    'epoch': epoch,
                    'val_loss': val_loss
                }, 'xiaomi_timestamp_model.pth')
        
        if self.debug:
            print("Training completed!")
    
    def predict_timestamp(self, image: np.ndarray) -> str:
        """CTCで画像からタイムスタンプを予測 - AMP対応"""
        if self.model is None:
            raise ValueError("Model not trained yet")
        
        # 前処理
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        image = cv2.resize(image, (96, 24), interpolation=cv2.INTER_LANCZOS4)
        image = image.astype(np.float32) / 255.0
        image_tensor = torch.FloatTensor(image).unsqueeze(0).unsqueeze(0).to(self.device)
        
        # 予測
        self.model.eval()
        with torch.no_grad():
            if self.amp_enabled:
                with torch.amp.autocast('cuda'):
                    log_probs = self.model(image_tensor)  # (seq_len, 1, num_chars)
                    log_probs = F.log_softmax(log_probs, dim=2)
            else:
                log_probs = self.model(image_tensor)  # (seq_len, 1, num_chars)
                log_probs = F.log_softmax(log_probs, dim=2)
        
        # CTCデコーディング
        timestamp = self.decode_ctc(log_probs)
        return timestamp.strip()
    
    def save_model(self, filepath: str):
        """モデルを保存"""
        if self.model:
            torch.save({
                'model_state_dict': self.model.state_dict(),
                'char_to_idx': self.char_to_idx
            }, filepath)
    
    def load_model(self, filepath: str):
        """モデルを読み込み"""
        checkpoint = torch.load(filepath, map_location=self.device)
        self.char_to_idx = checkpoint['char_to_idx']
        self.idx_to_char = {v: k for k, v in self.char_to_idx.items()}
        self.blank_idx = 0  # CTC blank index
        
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
    
    # 3. 訓練実行（CRNN-CTCで高精度を目指す + GPU最適化）
    trainer.train(images, labels, epochs=100, batch_size=16, accumulation_steps=8)  # GPU最適化
    
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
# UMuse — 技术栈详情

## Python 环境

- **Python**: 3.13.7
- **包管理**: pip + requirements.txt (conda 备选)
- **虚拟环境**: 建议 venv 或 conda env

## 核心依赖

### ML 框架
| 包名 | 版本 | 用途 |
|------|------|------|
| torch | ≥2.5.0 (CUDA) | 深度学习框架，Demucs 后端 |
| torchaudio | ≥2.5.0 | 音频 I/O for PyTorch |
| onnxruntime | ≥1.18.0 | ONNX 模型推理 (basic-pitch) |
| demucs | ≥4.0.1 | 音频分轨模型 |

### 音频处理
| 包名 | 版本 | 用途 |
|------|------|------|
| librosa | ≥0.10.0 | 音频特征提取、频谱分析 |
| soundfile | ≥0.12.0 | 高质量 WAV/FLAC 读写 |
| pydub | ≥0.25.0 | MP3 解码 / 格式转换 (依赖 ffmpeg) |
| pedalboard | ≥0.9.0 | 音频效果器处理 |
| scipy | ≥1.11.0 | 科学计算、曲线拟合 |
| numpy | ≥1.24.0, <2.0 | 数值计算 |

### MIDI & 乐谱
| 包名 | 版本 | 用途 |
|------|------|------|
| pretty_midi | ≥0.2.10 | MIDI 创建/编辑 |
| mido | ≥1.3.0 | MIDI 文件 I/O |
| music21 | ≥9.1.0 | 乐谱表示、MusicXML/LilyPond 导出 |

### GUI
| 包名 | 版本 | 用途 |
|------|------|------|
| PySide6 | ≥6.6.0 | Qt for Python GUI |

### 工具
| 包名 | 版本 | 用途 |
|------|------|------|
| PyYAML | ≥6.0 | 配置文件解析 |
| scikit-learn | ≥1.3.0 | 特征匹配 (k-NN) |
| tqdm | ≥4.66.0 | 进度条 |

## 系统依赖

| 工具 | 安装方式 | 用途 |
|------|----------|------|
| ffmpeg | `winget install ffmpeg` | 音频解码/编码 |
| LilyPond | `winget install LilyPond` | 乐谱 PDF 渲染 |
| CUDA Toolkit | NVIDIA 驱动自带 | GPU 加速 (可选) |

## GPU 环境

- **显卡**: NVIDIA GeForce RTX 5060 (8GB VRAM)
- **CUDA**: 13.2
- **驱动**: 595.71
- **当前 PyTorch**: CPU 版本 → 需重装 CUDA 版

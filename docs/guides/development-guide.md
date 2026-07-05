# UMuse — 开发指南

## 快速开始

### 环境准备
```bash
# 1. 克隆/进入项目目录
cd "U Muse"

# 2. 创建虚拟环境 (推荐)
python -m venv venv
venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装 CUDA PyTorch (Windows + GPU)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126

# 5. 安装系统依赖
winget install ffmpeg
winget install LilyPond

# 6. 下载模型文件
python scripts/download_models.py
```

### 运行
```bash
# CLI 模式 (Phase 1-5)
python main.py separate input.mp3 -o output/

# GUI 模式 (Phase 6)
python main.py --gui
```

## 项目结构

```
U Muse/
├── main.py                    # 入口 (CLI + GUI 启动)
├── requirements.txt           # Python 依赖
├── CLAUDE.md                  # Claude 工作指引
│
├── src/                       # 源代码
│   ├── config/                # 配置层 (单例, YAML load)
│   ├── core/                  # 核心引擎 (零 GUI 依赖)
│   │   ├── audio/             # 音频 I/O 工具
│   │   ├── separation/        # 分轨 (Demucs)
│   │   ├── transcription/     # MIDI 转录 + 鼓采样切片
│   │   ├── notation/          # 乐谱生成
│   │   ├── timbre/            # 音色匹配
│   │   └── effects/           # 效果器分析
│   ├── gui/                   # PySide6 桌面界面
│   │   ├── windows/           # 窗口
│   │   ├── pages/             # 页面
│   │   ├── widgets/           # 自定义控件
│   │   └── workers/           # QThread 异步任务
│   └── utils/                 # 通用工具
│
├── assets/                    # 静态资源
│   ├── theme/                 # QSS 主题 + 图标
│   └── models/                # ML 模型文件
│
├── data/
│   ├── presets/               # 音源预设特征库
│   └── examples/              # 示例音频
│
├── docs/                      # 项目文档
│   ├── requirements/          # 需求文档
│   ├── technical/             # 技术文档 (架构/技术栈)
│   ├── design/                # 设计规范 (UI/UX)
│   └── guides/                # 指南 (开发/执行步骤)
│
├── devlog/                    # 开发日志 (每日自动记录)
├── tests/                     # 单元测试
└── scripts/                   # 独立工具脚本
```

## 编码规范

### 命名
- **文件**: snake_case `demucs_runner.py`
- **类**: PascalCase `StemSeparator`
- **函数/方法**: snake_case `separate_stems()`
- **常量**: UPPER_SNAKE `DEFAULT_SAMPLE_RATE`

### 类型标注
所有公共函数必须标注类型：
```python
def separate(input_path: Path, output_dir: Path) -> dict[str, Path]:
    ...
```

### Docstring
关键函数使用中英双语：
```python
def separate(...):
    """运行音频分轨 / Run stem separation.
    
    Args:
        input_path: 输入音频文件路径
        output_dir: 输出目录
        
    Returns:
        {乐器名: stem文件路径} 字典
    """
```

### 进度回调
所有耗时函数接受 `progress_callback: Callable[[int, str], None] | None`:
```python
def long_task(..., progress_callback=None):
    for i, item in enumerate(items):
        # do work
        if progress_callback:
            progress_callback(int(i/len(items)*100), f"处理中: {item}")
```

## 调试技巧

1. **先 CLI 后 GUI**: 在 CLI 模式下调试核心逻辑，比 GUI 中快 10 倍
2. **小文件测试**: 用 15 秒音频片段测试，不要用完整歌曲
3. **保留中间产物**: 每阶段输出到独立子目录，方便单独检查
4. **检查 GPU 使用**: `nvidia-smi` 确认 PyTorch 在用 GPU

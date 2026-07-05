# UMuse — 开发执行步骤

## Phase 架构

采用**渐进式交付**：每个 Phase 产出一个可独立运行的功能模块。

### Phase 1 — 项目基础 + 音频分轨 ✅ 完成 (2026-07-02)
**目标**: 输入一首歌 → 输出 6 轨分离音频

| 步骤 | 内容 | 文件 | 状态 |
|------|------|------|------|
| 1.1 | 创建项目结构 | 全部目录 | ✅ |
| 1.2 | 编写依赖文件 | requirements.txt, pyproject.toml | ✅ |
| 1.3 | 安装 CUDA PyTorch | pip install | ✅ |
| 1.4 | 配置层 | src/config/settings.py, constants.py | ✅ |
| 1.5 | 音频 I/O 工具 | src/core/audio/loader.py | ✅ |
| 1.6 | Project 数据类 | src/core/project.py | ✅ |
| 1.7 | 分轨引擎 (audio-separator, 双策略) | src/core/separation/audio_separator_runner.py | ✅ |
| 1.7b | 旧 Demucs 封装 (已替换) | src/core/separation/demucs_runner.py | 📦 |
| 1.8 | 流程编排器 | src/core/pipeline.py | ✅ |
| 1.9 | CLI 入口 + 测试 | main.py | ✅ |

**验收**: `python main.py separate <音频文件> -s vocal_priority` 输出 6 轨 WAV
- 人声: BS-Roformer (SDR 12.9)
- 乐器: Demucs 6s

---

### Phase 2 — MIDI 转录 ✅ 完成 (2026-07-02)
**目标**: 分轨音频 → MIDI 文件

| 步骤 | 内容 | 文件 | 状态 |
|------|------|------|------|
| 2.1 | 安装 basic-pitch + ONNX 模型 | pip install basic-pitch --no-deps | ✅ |
| 2.2 | ONNX 推理封装 | src/core/transcription/basic_pitch_onnx.py | ✅ |
| 2.3 | 鼓组采样切片 | src/core/transcription/drum_slicer.py | ✅ |
| 2.4 | MIDI 后处理 (量化/去噪) | src/core/transcription/midi_cleaner.py | ✅ |
| 2.5 | 集成到 Pipeline + CLI | 更新 pipeline.py, main.py | ✅ |

**验收**: 钢琴 stem → 88 音符 MIDI, 鼓组 stem → 28 切片 ✅

---

### Phase 3 — 乐谱生成 ✅ 完成 (2026-07-03)
**目标**: MIDI → 简谱/五线谱/六线谱/总谱

| 步骤 | 内容 | 文件 | 状态 |
|------|------|------|------|
| 3.1 | 安装 music21 + LilyPond | pip + winget | ✅ |
| 3.2 | MIDI → music21 Score | src/core/notation/midi_to_score.py | ✅ |
| 3.3 | 四种谱式生成 | src/core/notation/notation_formats.py | ✅ |
| 3.4 | LilyPond 模板 | src/core/notation/lilypond_exporter.py | ✅ |

**验收**: 输出 PDF 乐谱在 MuseScore 中可打开 ✅

---

### Phase 4 — 音色预设匹配 ★
**目标**: 旋律 stem → 最匹配的音源预设

| 步骤 | 内容 | 文件 |
|------|------|------|
| 4.1 | 特征提取器 | src/core/timbre/feature_extractor.py |
| 4.2 | 预设数据库 | src/core/timbre/preset_database.py |
| 4.3 | 匹配器 (k-NN) | src/core/timbre/matcher.py |
| 4.4 | 建库工具 | scripts/build_preset_db.py |

**验收**: 钢琴 stem → Top 5 预设匹配结果

---

### Phase 5 — 效果器参数预估 ★
**目标**: 对比干/湿音频 → EQ + 混响 + 压缩参数

| 步骤 | 内容 | 文件 |
|------|------|------|
| 5.1 | EQ 参数预估 | src/core/effects/eq_estimator.py |
| 5.2 | 混响参数预估 | src/core/effects/reverb_estimator.py |
| 5.3 | 动态处理器预估 | src/core/effects/dynamics_estimator.py |
| 5.4 | 效果链构建 | src/core/effects/chain_builder.py |

**验收**: 能输出可导入 DAW 的效果器参数 JSON

---

### Phase 6 — GUI 桌面应用 ✅ 完成 (2026-07-04)
**目标**: 完整紫色科技风桌面应用

| 步骤 | 内容 | 文件 | 状态 |
|------|------|------|------|
| 6.0 | 依赖安装 (PySide6 6.11.1) | pip install | ✅ |
| 6.1 | PySide6 + 深紫主题系统 | src/gui/app.py, theme/qss_dark_purple.py | ✅ |
| 6.2 | 主窗口 + 侧边栏 | src/gui/windows/main_window.py | ✅ |
| 6.3 | 6 个功能页面 | src/gui/pages/*.py | ✅ |
| 6.4 | 自定义控件 (6 个) | src/gui/widgets/*.py | ✅ |
| 6.5 | 异步 Worker (5 个) | src/gui/workers/*.py | ✅ |
| 6.6 | 打包发布 | PyInstaller | ⏳ 延后 |

**验收**: 全流程 GUI 操作 → 输出完整结果 ✅ (模块导入/页面切换/Worker 信号均验证通过)

---

## 开发规则

1. **每个 Phase 完成后才进入下一个**
2. **每天开发结束后更新 devlog/**
3. **每个模块完成后在 tests/ 补充测试**
4. **遇到 API 不兼容时优先 ONNX 方案而非降级 Python**
5. **所有核心函数接受 progress_callback 参数**

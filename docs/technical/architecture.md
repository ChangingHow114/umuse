# UMuse — 技术架构文档

## 架构概览

```
┌──────────────────────────────────────────────┐
│                  GUI Layer                     │
│         PySide6 + QSS Purple Theme             │
│   pages: 项目/分轨/转录/音色/效果/乐谱         │
│   workers: QThread 异步任务                    │
├──────────────────────────────────────────────┤
│                Core Engine                     │
│  Separator → Transcriber → Matcher →          │
│  EffectsAnalyzer → NotationEngine             │
│  PipelineManager (流程编排)                    │
├──────────────────────────────────────────────┤
│              Data & Services                   │
│  Demucs | basic-pitch ONNX | music21 |        │
│  PresetDB | pedalboard | librosa              │
└──────────────────────────────────────────────┘
```

## 模块设计原则

1. **核心引擎零 GUI 依赖**: core/ 下的所有代码不导入 PySide6，可 CLI 独立运行
2. **单向数据流**: GUI → PipelineManager → 各引擎 → 文件系统 → Project 状态更新
3. **Worker 模式**: GUI 中所有耗时任务通过 QThread Worker 执行，信号通知进度
4. **配置集中管理**: 所有可调参数集中在 config/settings.py，支持 YAML 加载

## 关键设计决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 桌面框架 | PySide6 | Qt 原生性能，丰富控件，QSS 主题 |
| 分轨模型 | Demucs htdemucs_6s | 6 轨分离，PyTorch，GPU 加速 |
| MIDI 转录 | basic-pitch ONNX | 绕过 TF 依赖，Python 3.13 兼容 |
| 乐谱渲染 | music21 + LilyPond | 开源专业打谱引擎 |
| 音色匹配 | 特征搜索 (k-NN) | 无需大量标注数据，可迭代升级 |
| 效果器分析 | 频谱差分 + 曲线拟合 | 可解释、参数可控 |

## 分轨乐器分类处理策略

不同乐器类型采用不同处理路径，不"一刀切"：

| 乐器类型 | 分轨来源 | MIDI转录 | 音色匹配 | 处理方式 |
|----------|----------|----------|----------|----------|
| **钢琴/键盘** | Piano | ✅ | ✅ 预设匹配 | 提取旋律+和弦 → 匹配合成器/采样器预设 |
| **吉他** | Guitar | ✅ | ✅ 预设匹配 | 提取音符 → 匹配音箱/效果器链预设 |
| **贝斯** | Bass | ✅ | ✅ 预设匹配 | 低音区单音转录 → 匹配贝斯音色预设 |
| **人声** | Vocals | ✅ | — | 单音音高提取 → 直接生成旋律 MIDI |
| **鼓组** | Drums | — | — | **直接提取采样**: Kick/Snare/HH 等 one-shot 切片 |
| **FX/其他** | Other | — | — | **直接提取采样**: 保留原始音频片段 |

### 处理流水线

```
Audio File → Demucs htdemucs_6s
              │
              ├─ Piano  → basic-pitch → .mid → 乐谱
              │            └─ Feature Match → 预设参数 (.json)
              │
              ├─ Guitar → basic-pitch → .mid → 乐谱 (含六线谱)
              │            └─ Feature Match → 预设参数 (.json)
              │
              ├─ Bass   → basic-pitch → .mid → 乐谱
              │            └─ Feature Match → 预设参数 (.json)
              │
              ├─ Vocals → CREPE/pitch → .mid (含弯音) → 简谱旋律
              │
              ├─ Drums  → Onset Detect → Sample Slicer → 采样切片 (.wav)
              │            └─ 分类: Kick / Snare / Hi-hat / Tom / Cymbal
              │
              └─ Other  → 保留原始音频 (.wav)
                           └─ 可选: FX 分类 (Riser/Impact/Sweep/Ambience)
```

## 数据流

```
Audio File → Demucs → 6 Stems (.wav)
                     ↓
          ┌──────────┴──────────┐
          │ 旋律乐器 (4轨)       │  节奏/音效 (2轨)
          │ Piano/Guitar/Bass   │  Drums/Other
          │ /Vocals             │
          └──────────┬──────────┘
                     ↓                    ↓
          basic-pitch ONNX        Onset Detect
                     ↓                    ↓
          4 MIDI (.mid)           采样切片 (.wav)
                     ↓
          music21/LilyPond → Sheet Music (.pdf)
                     ↓
          Feature Extractor → Feature Vectors
                     ↓
          k-NN Search → Preset Matches (.json)
                     ↓
          Spectral Diff → Effects Params (.json)
```

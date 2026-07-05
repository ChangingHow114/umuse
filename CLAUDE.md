# CLAUDE.md — UMuse 项目工作指引

## 项目信息

- **项目名**: UMuse
- **语言**: Python 3.13
- **平台**: Windows 11
- **硬件**: RTX 5060 8GB, CUDA 13.2
- **开发者水平**: CS 初学者，基础 Python

## 标准文件路径

### 需求 & 设计
| 文档 | 路径 |
|------|------|
| 项目需求 | [docs/requirements/project-requirements.md](docs/requirements/project-requirements.md) |
| 技术架构 | [docs/technical/architecture.md](docs/technical/architecture.md) |
| 技术栈 | [docs/technical/tech-stack.md](docs/technical/tech-stack.md) |
| 依赖清单 | [docs/technical/dependencies.md](docs/technical/dependencies.md) |
| UI 设计规范 | [docs/design/ui-design-spec.md](docs/design/ui-design-spec.md) |

### 开发指引
| 文档 | 路径 |
|------|------|
| 开发指南 | [docs/guides/development-guide.md](docs/guides/development-guide.md) |
| 执行步骤 | [docs/guides/execution-steps.md](docs/guides/execution-steps.md) |

### 开发日志
| 文档 | 路径 |
|------|------|
| 日志说明 | [devlog/README.md](devlog/README.md) |
| 今日日志 | `devlog/YYYY-MM-DD.md` |

## 工作规则

### 每次开发会话必须
1. **开始时**: 阅读 `docs/guides/execution-steps.md` 确认当前 Phase 和进度
2. **过程中**: 遵循 `docs/guides/development-guide.md` 中的编码规范
3. **结束时**: 更新 `devlog/YYYY-MM-DD.md` 记录今日完成和待办
4. **不要一口气做太多**: 按 Phase 步骤逐个完成，每完成一个步骤停下来确认

### 编码规范
- 核心引擎 (`src/core/`) 零 GUI 依赖，可 CLI 独立运行
- 所有公共函数标注类型 (type hints)
- 所有耗时函数接受 `progress_callback` 参数
- 使用 `pathlib.Path` 处理路径，不用字符串拼接
- 错误处理: 预设友好的中文错误信息 + 英文技术细节

### 架构关键点
- **鼓组/Other 轨**: 直接提取采样切片，不做 MIDI 转录，不做音色匹配
- **旋律乐器 (Piano/Guitar/Bass/Vocals)**: 完整走 MIDI → 乐谱 → 音色匹配流程
- **basic-pitch**: 必须走 ONNX Runtime 方案，不装 TensorFlow
- **Demucs**: 通过 subprocess 调用 CLI，不直接 import

### 测试规则
- 用 15 秒音频片段测试，不要用完整歌曲
- 每个模块完成后在 `tests/` 补充测试
- 先 CLI 验证，再接入 GUI

### 沟通风格
- 技术解释用中文
- 代码注释中英双语
- 面对不确定的 API 行为，先验证再使用

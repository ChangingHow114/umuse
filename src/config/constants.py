"""应用常量 / Application Constants.

不可变的常量值 — 修改这些需要重新审视架构。
Tunable parameters 请修改 settings.py。
"""

from pathlib import Path

# === 应用元信息 ===
APP_NAME: str = "UMuse"
APP_VERSION: str = "0.1.0"
APP_DESCRIPTION: str = "AI 音乐逆向工程工作站"

# === 音频参数 ===
DEFAULT_SAMPLE_RATE: int = 44100  # Hz
DEMUCS_SAMPLE_RATE: int = 44100  # Demucs 内部采样率
BASIC_PITCH_SAMPLE_RATE: int = 22050  # basic-pitch 内部采样率
SUPPORTED_AUDIO_FORMATS: tuple[str, ...] = (".wav", ".mp3", ".flac", ".ogg", ".m4a")
MAX_AUDIO_DURATION_SEC: float = 600.0  # 最长 10 分钟
MAX_FILE_SIZE_MB: int = 500

# === FFT 参数 ===
DEFAULT_N_FFT: int = 2048
DEFAULT_HOP_LENGTH: int = 512
DEFAULT_WIN_LENGTH: int = 2048
N_MELS: int = 229  # basic-pitch 用的 mel 频带数

# === MIDI 参数 ===
MIDI_NOTES: int = 128  # 0-127
MIDI_VELOCITY_MAX: int = 127
MIN_NOTE_DURATION_SEC: float = 0.03  # 短于 30ms 的音符视为噪音
QUANTIZE_GRID: tuple[str, ...] = ("16th", "8th", "quarter")

# === 音色特征 ===
N_MFCC: int = 20  # MFCC 系数数量
FEATURE_VECTOR_DIM: int = 59  # 总特征维度

# === 效果器 ===
EQ_MAX_BANDS: int = 5  # 参数 EQ 最大频段数
EQ_FREQ_RANGE: tuple[float, float] = (20.0, 20000.0)  # Hz

# === 乐器分类 ===
# 旋律乐器 — 需要 MIDI 转录 + 音色匹配
MELODIC_INSTRUMENTS: tuple[str, ...] = ("piano", "guitar", "bass", "vocals")
# 节奏/音效 — 仅提取采样
SAMPLE_INSTRUMENTS: tuple[str, ...] = ("drums", "other")

# Demucs 6轨模型 → 乐器名映射
DEMUCS_6S_STEMS: dict[str, str] = {
    "drums": "鼓组",
    "bass": "贝斯",
    "other": "其他/音效",
    "vocals": "人声",
    "guitar": "吉他",
    "piano": "钢琴",
}

# Demucs 4轨模型 → 乐器名映射 (备选)
DEMUCS_4S_STEMS: dict[str, str] = {
    "drums": "鼓组",
    "bass": "贝斯",
    "other": "其他",
    "vocals": "人声",
}

# === 预设数据库 ===
PRESET_CATEGORIES: tuple[str, ...] = (
    "acoustic_piano", "electric_piano", "organ",
    "synth_lead", "synth_pad", "synth_bass",
    "clean_guitar", "distorted_guitar", "acoustic_guitar",
    "bass_guitar", "synth_bass",
    "strings", "brass", "woodwinds",
)

# === 乐谱 ===
# music21 支持的谱式
NOTATION_FORMATS: tuple[str, ...] = (
    "staff",       # 五线谱
    "jianpu",      # 简谱
    "tablature",   # 六线谱 (吉他 TAB)
    "full_score",  # 乐队总谱
)

# === 路径常量 ===
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR: Path = PROJECT_ROOT / "assets"
MODELS_DIR: Path = ASSETS_DIR / "models"
PRESETS_DIR: Path = PROJECT_ROOT / "data" / "presets"
DEFAULT_OUTPUT_DIR: Path = PROJECT_ROOT / "output"

# === 模型下载 URLs ===
BASIC_PITCH_ONNX_URL: str = (
    "https://github.com/spotify/basic-pitch/releases/download/v0.3.0/"
    "basic-pitch-onnx-v0.3.0.zip"
)
# Demucs 模型由 demucs 包自动下载，无需手动 URL

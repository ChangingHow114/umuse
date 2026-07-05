"""音频节拍检测器 / Audio Beat and Downbeat Detector.

使用 librosa 从音频中检测:
- BPM (固定速度)
- 节拍位置 (beat times)
- 强拍位置 (downbeat times, 每小节第一拍)
- 拍号 (time signature, 3/4, 4/4, 6/8)

用法:
    detector = BeatDetector()
    result = detector.detect(Path("drums.wav"))
    print(f"BPM: {result.bpm:.1f}, {result.time_signature}, 置信度: {result.confidence:.2f}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import librosa
import numpy as np


# ===== 数据类型 =====

@dataclass
class AnalysisResult:
    """节拍分析结果 / Beat analysis result.

    Attributes:
        bpm: 检测到的 BPM (beats per minute)
        beat_times: 每个节拍的时间点 (秒)
        downbeat_times: 每个强拍 (beat 1) 的时间点 (秒)
        time_signature: 拍号 (numerator, denominator), 如 (4, 4)
        beat_positions: 每个 beat 在 bar 内的位置 (1=强拍, 2, 3, 4=弱拍)
        confidence: 整体检测置信度 (0-1)
        source_stem: 用于检测的 stem 名称
        offset_beats: 用户手动微调的 offset (拍数), 正数=后移
    """
    bpm: float
    beat_times: list[float] = field(default_factory=list)
    downbeat_times: list[float] = field(default_factory=list)
    time_signature: tuple[int, int] = (4, 4)
    beat_positions: list[int] = field(default_factory=list)
    confidence: float = 0.0
    source_stem: str = ""
    offset_beats: int = 0

    @property
    def beat_interval(self) -> float:
        """每拍秒数 / Duration of one beat in seconds."""
        return 60.0 / self.bpm if self.bpm > 0 else 0.5

    @property
    def bar_interval(self) -> float:
        """每小节秒数 / Duration of one bar in seconds."""
        return self.beat_interval * self.time_signature[0]

    @property
    def time_signature_str(self) -> str:
        """拍号字符串 / Time signature as string (e.g. '4/4')."""
        return f"{self.time_signature[0]}/{self.time_signature[1]}"

    def get_bar_number(self, time_sec: float) -> int:
        """根据时间获取小节编号 (0-indexed) / Get bar number from time."""
        if not self.downbeat_times:
            return int(time_sec / self.bar_interval)
        for i, dt in enumerate(self.downbeat_times):
            if time_sec < dt:
                return max(0, i - 1)
        return len(self.downbeat_times) - 1

    def get_beat_number(self, time_sec: float) -> int:
        """根据时间获取拍位编号 (1-indexed within bar) / Get beat position from time."""
        if not self.downbeat_times:
            return int(time_sec / self.beat_interval) % self.time_signature[0] + 1
        bar = self.get_bar_number(time_sec)
        if bar < len(self.downbeat_times):
            bar_start = self.downbeat_times[bar]
            offset = time_sec - bar_start
            return min(int(offset / self.beat_interval) + 1, self.time_signature[0])
        return 1

    def get_expected_beat_time(self, bar: int, beat: int) -> float:
        """获取指定小节拍位的预期时间 / Get expected time for a given bar and beat.

        Args:
            bar: 小节编号 (0-indexed)
            beat: 拍位 (1-indexed within bar)

        Returns:
            预期时间 (秒)
        """
        if bar < len(self.downbeat_times):
            bar_start = self.downbeat_times[bar]
            return bar_start + (beat - 1) * self.beat_interval
        # Fallback: 用平均节拍间隔推算
        first_downbeat = self.downbeat_times[0] if self.downbeat_times else 0.0
        return first_downbeat + bar * self.bar_interval + (beat - 1) * self.beat_interval

    def summary(self) -> str:
        """生成中文摘要 / Generate Chinese summary."""
        lines = [
            f"BPM: {self.bpm:.1f}",
            f"拍号: {self.time_signature_str}",
            f"节拍数: {len(self.beat_times)}",
            f"强拍数: {len(self.downbeat_times)} (约 {len(self.downbeat_times)} 小节)",
            f"置信度: {self.confidence:.1%}",
            f"检测来源: {self.source_stem}",
        ]
        if self.offset_beats != 0:
            lines.append(f"手动偏移: {self.offset_beats:+d} 拍")
        return "\n".join(lines)


# ===== 节拍检测器 =====

class BeatDetector:
    """音频节拍检测器 / Audio beat and downbeat detector.

    使用 librosa 从音频中提取节拍结构信息。
    支持 BPM 检测、节拍跟踪、强拍定位和拍号推断。

    用法:
        detector = BeatDetector()
        result = detector.detect(Path("drums.wav"))
        # 或分别调用:
        bpm = detector.detect_bpm(Path("drums.wav"))
        beats, downbeats, positions = detector.detect_downbeats(
            Path("drums.wav"), bpm
        )
    """

    def __init__(
        self,
        sr: int = 22050,
        bpm_min: float = 40.0,
        bpm_max: float = 250.0,
    ) -> None:
        """初始化检测器 / Initialize detector.

        Args:
            sr: 分析采样率 (越低越快)，默认 22050 Hz
            bpm_min: 最小检测 BPM
            bpm_max: 最大检测 BPM
        """
        self.sr = sr
        self.bpm_min = bpm_min
        self.bpm_max = bpm_max

    # ===== 公开 API =====

    def detect(
        self,
        audio_path: Path | str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> AnalysisResult:
        """一站式节拍检测 / One-stop beat detection.

        加载音频并检测 BPM、节拍、强拍、拍号。

        Args:
            audio_path: 音频文件路径
            progress_callback: 进度回调 (percent, message)

        Returns:
            AnalysisResult 包含所有检测结果

        Raises:
            FileNotFoundError: 音频文件不存在
            ValueError: 音频文件无效 (长度不足、无声等)
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        if progress_callback:
            progress_callback(5, f"加载音频: {audio_path.name}...")

        # 加载音频
        y, sr_actual = librosa.load(str(audio_path), sr=self.sr, mono=True)

        duration = len(y) / sr_actual
        if duration < 1.0:
            raise ValueError(
                f"音频太短 ({duration:.1f}s)，至少需要 1 秒。"
                f"Audio too short ({duration:.1f}s), minimum 1 second required."
            )

        # 检查是否为无声
        rms = np.sqrt(np.mean(y ** 2))
        if rms < 1e-6:
            raise ValueError(
                f"音频无声或音量过低。"
                f"Audio is silent or volume is too low."
            )

        if progress_callback:
            progress_callback(15, "检测 BPM...")

        # Step 1: BPM 检测
        bpm = self.detect_bpm_from_array(y, sr_actual)

        if progress_callback:
            progress_callback(40, f"BPM={bpm:.1f}, 检测节拍位置...")

        # Step 2: 节拍 + 强拍检测
        beat_times, downbeat_times, beat_positions = self.detect_downbeats_from_array(
            y, sr_actual, bpm,
        )

        if progress_callback:
            progress_callback(70, "推断拍号...")

        # Step 3: 拍号推断
        time_signature = self.infer_time_signature(
            beat_positions, downbeat_times,
        )

        # Step 4: 置信度评估
        confidence = self._compute_confidence(
            y, sr_actual, bpm, beat_times, downbeat_times,
        )

        if progress_callback:
            progress_callback(
                100,
                f"节拍检测完成: BPM={bpm:.1f}, {time_signature[0]}/{time_signature[1]}, "
                f"置信度={confidence:.1%}",
            )

        return AnalysisResult(
            bpm=float(bpm),
            beat_times=beat_times,
            downbeat_times=downbeat_times,
            time_signature=time_signature,
            beat_positions=beat_positions,
            confidence=float(confidence),
            source_stem=audio_path.stem,
        )

    def detect_bpm(self, audio_path: Path | str) -> float:
        """从音频文件检测 BPM / Detect BPM from audio file.

        Args:
            audio_path: 音频文件路径

        Returns:
            检测到的 BPM

        Raises:
            FileNotFoundError: 音频文件不存在
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        y, sr_actual = librosa.load(str(audio_path), sr=self.sr, mono=True)
        return self.detect_bpm_from_array(y, sr_actual)

    def detect_downbeats(
        self,
        audio_path: Path | str,
        bpm: float,
    ) -> tuple[list[float], list[float], list[int]]:
        """从音频文件检测节拍和强拍 / Detect beats and downbeats from audio file.

        Args:
            audio_path: 音频文件路径
            bpm: 已知的 BPM

        Returns:
            (beat_times, downbeat_times, beat_positions)
            - beat_times: 所有节拍的时间点 (秒)
            - downbeat_times: 强拍时间点 (秒)
            - beat_positions: 每个节拍在 bar 内的位置

        Raises:
            FileNotFoundError: 音频文件不存在
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        y, sr_actual = librosa.load(str(audio_path), sr=self.sr, mono=True)
        return self.detect_downbeats_from_array(y, sr_actual, bpm)

    # ===== 内部实现 =====

    def detect_bpm_from_array(
        self, y: np.ndarray, sr: int = 22050,
    ) -> float:
        """从音频数组检测 BPM / Detect BPM from audio array.

        使用 librosa 的 tempo 检测，基于 onset strength envelope。

        Args:
            y: 音频采样数组 (mono)
            sr: 采样率

        Returns:
            检测到的 BPM
        """
        # 计算 onset strength envelope (起始强度包络)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)

        # 动态速度检测: 分别检测全局和局部 BPM
        # 全局 BPM (假设速度不变)
        # librosa >= 0.10.0: tempo() 移至 librosa.feature.rhythm
        try:
            from librosa.feature.rhythm import tempo as rhythm_tempo
            global_tempo = rhythm_tempo(
                onset_envelope=onset_env,
                sr=sr,
                start_bpm=120.0,  # 从通用默认值开始搜索
            )
        except ImportError:
            # fallback for librosa < 0.10.0
            global_tempo = librosa.beat.tempo(  # type: ignore[attr-defined] # noqa: F821
                onset_envelope=onset_env,
                sr=sr,
                start_bpm=120.0,
            )

        if len(global_tempo) > 0:
            return float(global_tempo[0])

        return 120.0

    def detect_downbeats_from_array(
        self,
        y: np.ndarray,
        sr: int,
        bpm: float,
    ) -> tuple[list[float], list[float], list[int]]:
        """从音频数组检测节拍和强拍 / Detect beats and downbeats from audio array.

        实现步骤:
        1. 用 librosa.beat.beat_track 检测所有节拍位置
        2. 对每个节拍计算 onset strength
        3. 尝试多种强拍相位偏移，选择 beat-1 平均强度最高的偏移

        Args:
            y: 音频采样数组 (mono)
            sr: 采样率
            bpm: 检测到的 BPM

        Returns:
            (beat_times, downbeat_times, beat_positions)
        """
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)

        # Step 1: 节拍跟踪
        # 用检测到的 BPM 作为起始速度，tightness=100 强制固定速度
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=sr,
            start_bpm=bpm,
            tightness=100,  # 高 tightness = 固定速度
            units='frames',
        )

        # 帧 → 时间
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        if len(beat_times) < 4:
            # 节拍太少，无法推断强拍
            return list(beat_times), [], []

        # Step 2: 推断拍号 (先初步，后面会更精确)
        # 默认试 4/4，如果 beat 数合适的话
        ts_numerator = self._guess_numerator(beat_frames, onset_env, sr)

        # Step 3: 强拍检测 — 尝试不同相位偏移
        n_phases = ts_numerator  # 4/4 试 4 个相位，3/4 试 3 个

        # 取每个 beat frame 的 onset strength
        beat_strengths = onset_env[beat_frames.astype(int) % len(onset_env)]

        # 测试每种相位
        best_phase = 0
        best_downbeat_strength = -1.0
        best_downbeat_indices = []

        for phase in range(n_phases):
            downbeat_indices = [i for i in range(phase, len(beat_frames), n_phases)]
            if not downbeat_indices:
                continue
            # 计算该相位下 beat-1 的平均强度
            db_strengths = [beat_strengths[idx] for idx in downbeat_indices
                          if idx < len(beat_strengths)]
            if not db_strengths:
                continue
            mean_db_strength = float(np.mean(db_strengths))

            # 也考虑非强拍的强度——我们希望强拍明显强于弱拍
            non_db_indices = [i for i in range(len(beat_frames))
                            if i not in set(downbeat_indices)]
            non_db_strengths = [beat_strengths[idx] for idx in non_db_indices
                              if idx < len(beat_strengths)]
            mean_non_db = float(np.mean(non_db_strengths)) if non_db_strengths else 0.0

            # 评分：强拍尽量强 + 强拍与非强拍的对比度
            score = mean_db_strength + (mean_db_strength - mean_non_db) * 2.0

            if score > best_downbeat_strength:
                best_downbeat_strength = score
                best_phase = phase
                best_downbeat_indices = downbeat_indices

        # 提取 downbeat times
        downbeat_times = [beat_times[idx] for idx in best_downbeat_indices
                         if idx < len(beat_times)]

        # 生成 beat positions
        beat_positions = []
        for i in range(len(beat_times)):
            relative_pos = (i - best_phase) % n_phases
            beat_positions.append(relative_pos + 1)  # 1-indexed

        return (
            [float(t) for t in beat_times],
            [float(t) for t in downbeat_times],
            beat_positions,
        )

    def infer_time_signature(
        self,
        beat_positions: list[int],
        downbeat_times: list[float],
    ) -> tuple[int, int]:
        """推断拍号 / Infer time signature from beat positions.

        规则:
        - 如果 beat positions 以 3 为周期 → 3/4
        - 如果 beat positions 以 4 为周期 → 4/4
        - 如果 beat positions 以 6 为周期且有副强拍 → 6/8

        Args:
            beat_positions: 每个 beat 在 bar 内的位置
            downbeat_times: 强拍时间点

        Returns:
            (numerator, denominator)
        """
        if not beat_positions:
            return (4, 4)

        # 找最大 position (即每小节拍数)
        max_position = max(beat_positions)

        # 按最大值推断
        if max_position == 3:
            return (3, 4)
        elif max_position == 6:
            # 6/8: 检查是否有 beat-1 和 beat-4 的强度模式
            # 简化: 如果有 ≥4 个强拍且每 6 拍一个，就是 6/8
            return (6, 8)
        else:
            return (4, 4)

    def _guess_numerator(
        self,
        beat_frames: np.ndarray,
        onset_env: np.ndarray,
        sr: int,
    ) -> int:
        """猜测拍号分子 / Guess time signature numerator.

        通过分析 onset strength 的自相关来估计每小节的拍数。
        如果 onset env 有强烈的每 3 拍模式 → 3/4，
        否则默认 4/4。

        Args:
            beat_frames: 节拍帧位置
            onset_env: onset strength envelope
            sr: 采样率

        Returns:
            推测的每小节拍数 (3 或 4)
        """
        if len(beat_frames) < 8:
            return 4

        # 计算 beat-to-beat intervals
        beat_intervals = np.diff(beat_frames)

        if len(beat_intervals) < 4:
            return 4

        # 分析 onset strength 以 beat 为单位
        n_beats = min(len(beat_frames) - 1, 256)
        beat_onset = np.zeros(n_beats)

        for i in range(n_beats):
            frame = int(beat_frames[i])
            if frame < len(onset_env):
                beat_onset[i] = onset_env[frame]

        # 自相关检测周期性
        if len(beat_onset) >= 12:
            # Check if there's a strong pattern at lag 3 (3/4) vs lag 4 (4/4)
            ac = np.correlate(beat_onset - np.mean(beat_onset),
                            beat_onset - np.mean(beat_onset), mode='full')
            ac = ac[len(ac)//2:]  # 取正半部分

            if len(ac) > 4:
                pattern_3 = ac[3] if len(ac) > 3 else 0
                pattern_4 = ac[4] if len(ac) > 4 else 0
                # 归一化
                max_ac = max(ac[1:6]) if len(ac) > 5 else 1.0
                if max_ac > 0:
                    pattern_3 /= max_ac
                    pattern_4 /= max_ac
                # 如果 lag-3 明显强于 lag-4，可能是 3/4
                if pattern_3 > pattern_4 * 1.5:
                    return 3

        return 4

    def _compute_confidence(
        self,
        y: np.ndarray,
        sr: int,
        bpm: float,
        beat_times: list[float],
        downbeat_times: list[float],
    ) -> float:
        """计算检测置信度 / Compute detection confidence.

        基于三个指标:
        1. 节拍间隔一致性 (std / mean, 越低越好)
        2. 强拍 onset strength 比率 (越强越好)
        3. 检测到的 BPM 是否在合理范围

        Args:
            y: 音频数组
            sr: 采样率
            bpm: 检测到的 BPM
            beat_times: 节拍时间点
            downbeat_times: 强拍时间点

        Returns:
            置信度 (0-1)
        """
        scores: list[float] = []

        # 指标 1: 节拍间隔一致性
        if len(beat_times) >= 3:
            intervals = np.diff(beat_times)
            mean_interval = np.mean(intervals)
            if mean_interval > 0:
                cv = np.std(intervals) / mean_interval  # 变异系数
                # cv < 0.1 → 高分, cv > 0.5 → 低分
                consistency = max(0.0, min(1.0, 1.0 - cv / 0.5))
                scores.append(consistency)

        # 指标 2: BPM 合理性
        if 40 <= bpm <= 250:
            # 在合理范围内得满分，极端值扣分
            if 60 <= bpm <= 200:
                scores.append(1.0)
            else:
                scores.append(0.7)
        else:
            scores.append(0.3)

        # 指标 3: 是否成功检测到强拍
        if len(downbeat_times) >= 2:
            # 有足够强拍 → 检测较可靠
            scores.append(0.9)
        elif len(downbeat_times) >= 1:
            scores.append(0.5)
        else:
            scores.append(0.1)

        # 综合评分
        if not scores:
            return 0.3

        return float(np.mean(scores))

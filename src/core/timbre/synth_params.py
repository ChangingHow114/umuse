"""合成器参数映射 / Synth Parameter Mapper.

将音色匹配的 high-level 参数 (brightness/warmth/attack/sustain/body)
映射为具体合成器/插件的可用参数。

支持的合成器:
  - Xfer Serum / Vital (wavetable)
  - LennarDigital Sylenth1 (subtractive analog)
  - Native Instruments Massive (wavetable)
  - General MIDI (program/bank select)

用法:
    mapper = SynthParamMapper()
    serum_params = mapper.to_serum(brightness=0.7, warmth=0.4, attack=0.3, sustain=0.7, body=0.6)
    vital_params = mapper.to_vital(brightness=0.7, warmth=0.4, attack=0.3, sustain=0.7, body=0.6)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ===== Serum 参数 =====

@dataclass
class SerumParams:
    """Xfer Serum 合成器参数 / Serum wavetable synth parameters.

    所有值均为归一化范围 (Serum 内部使用 0.0-1.0),
    标注关键实际值的映射供 DAW 手动输入。
    """

    # ---- Oscillator A ----
    osc_a_wavetable: str = "Basic Shapes"        # 波表名
    osc_a_wt_position: float = 0.5               # 波表位置 (0=左端, 1=右端)
    osc_a_unison_voices: int = 1                  # 同音数 (1-16)
    osc_a_unison_detune: float = 0.1              # 同音失谐 (0-1, 实际 ~0-100 cents)
    osc_a_level: float = 0.8                      # 振荡器音量 (0-1)

    # ---- Oscillator B (Sub / 第二振荡器) ----
    osc_b_enabled: bool = False
    osc_b_wavetable: str = "Basic Mg"            # 通常用作 Sub
    osc_b_wt_position: float = 0.5
    osc_b_level: float = 0.0
    osc_b_coarse: int = -12                       # 粗调 (半音, -24 ~ +24)
    osc_b_unison_voices: int = 1
    osc_b_unison_detune: float = 0.0

    # ---- Noise Oscillator ----
    noise_enabled: bool = False
    noise_type: str = "White"
    noise_level: float = 0.0

    # ---- Filter ----
    filter_type: str = "Low 24"                   # 滤波器类型
    filter_cutoff: float = 0.7                    # 截止频率 (0-1, 实际 ~40Hz-20kHz)
    filter_cutoff_hz: float = 2000.0              # 实际推荐 Hz 值 (供 DAW 手动输入)
    filter_resonance: float = 0.15                # 共振 (0-1)
    filter_drive: float = 0.0                     # 过载 (0-1)
    filter_keytrack: float = 0.5                  # 键盘跟随 (0-1)
    filter_env_amount: float = 0.3               # 包络调制量 (0-1)

    # ---- Amp Envelope ----
    amp_attack: float = 0.02                      # 起音时间 (0-1, 实际 0ms-2s)
    amp_attack_ms: float = 20.0                   # 实际推荐毫秒值
    amp_decay: float = 0.3                        # 衰减时间
    amp_decay_ms: float = 300.0
    amp_sustain: float = 0.7                      # 保持电平
    amp_release: float = 0.3                      # 释音时间
    amp_release_ms: float = 400.0

    # ---- Filter Envelope ----
    filt_attack: float = 0.0
    filt_attack_ms: float = 0.0
    filt_decay: float = 0.3
    filt_decay_ms: float = 300.0
    filt_sustain: float = 0.3
    filt_release: float = 0.3
    filt_release_ms: float = 300.0

    # ---- LFO 1 ----
    lfo1_rate: float = 0.3                        # LFO 速率 (0-1, 实际 0.05Hz-100Hz)
    lfo1_rate_hz: float = 1.5                     # 实际推荐 Hz
    lfo1_depth: float = 0.0                       # 调制深度 (0-1)
    lfo1_target: str = "Filter Cutoff"

    # ---- Effects ----
    reverb_mix: float = 0.15                      # 混响混合量 (0-1)
    reverb_size: float = 0.3                      # 混响空间大小 (0-1)
    delay_mix: float = 0.0                        # 延迟混合量 (0-1)
    delay_time: float = 0.25                      # 延迟时间 (0-1, 实际 1/16~1/1)
    chorus_depth: float = 0.0                     # 合唱深度 (0-1)
    distortion_mix: float = 0.0                   # 失真混合量 (0-1)
    compressor_threshold: float = -12.0           # 压缩阈值 (dB)
    compressor_ratio: float = 2.0                 # 压缩比率

    # ---- Master ----
    master_volume: float = 0.8                    # 总音量 (0-1)
    portamento: float = 0.0                       # 滑音时间 (0-1)
    polyphony: int = 8                            # 复音数

    def to_dict(self) -> dict[str, Any]:
        """转为前端可读的字典 / Convert to frontend-friendly dict."""
        return {
            "synth": "Xfer Serum",
            "oscillator_a": {
                "wavetable": self.osc_a_wavetable,
                "wt_position": round(self.osc_a_wt_position, 3),
                "unison_voices": self.osc_a_unison_voices,
                "unison_detune": f"{int(self.osc_a_unison_detune * 100)} cents",
                "level": round(self.osc_a_level, 2),
            },
            "oscillator_b": {
                "enabled": self.osc_b_enabled,
                "wavetable": self.osc_b_wavetable,
                "coarse": f"{self.osc_b_coarse:+d} st",
                "level": round(self.osc_b_level, 2),
            },
            "filter": {
                "type": self.filter_type,
                "cutoff": f"{self.filter_cutoff_hz:.0f} Hz",
                "resonance": f"{self.filter_resonance:.0%}",
                "drive": round(self.filter_drive, 2),
                "env_amount": f"{self.filter_env_amount:.0%}",
            },
            "amp_envelope": {
                "attack": f"{self.amp_attack_ms:.0f} ms",
                "decay": f"{self.amp_decay_ms:.0f} ms",
                "sustain": f"{self.amp_sustain:.0%}",
                "release": f"{self.amp_release_ms:.0f} ms",
            },
            "filter_envelope": {
                "attack": f"{self.filt_attack_ms:.0f} ms",
                "decay": f"{self.filt_decay_ms:.0f} ms",
                "sustain": f"{self.filt_sustain:.0%}",
                "release": f"{self.filt_release_ms:.0f} ms",
            },
            "lfo1": {
                "rate": f"{self.lfo1_rate_hz:.1f} Hz",
                "depth": f"{self.lfo1_depth:.0%}",
                "target": self.lfo1_target,
            },
            "effects": {
                "reverb": f"{self.reverb_mix:.0%}",
                "delay": f"{self.delay_mix:.0%}",
                "chorus": f"{self.chorus_depth:.0%}",
                "distortion": f"{self.distortion_mix:.0%}",
            },
            "master": {
                "volume": f"{self.master_volume:.0%}",
                "portamento": round(self.portamento, 2),
                "polyphony": self.polyphony,
            },
        }


# ===== Vital 参数 =====

@dataclass
class VitalParams:
    """Vital 合成器参数 / Vital spectral warping wavetable synth.

    与 Serum 类似但有自己的参数命名体系。
    """

    # ---- Oscillator 1 ----
    osc1_wavetable: str = "Basic Shapes"
    osc1_frame: float = 0.5                       # 波表帧位置 (0-1)
    osc1_unison_voices: int = 1
    osc1_unison_detune: float = 0.1
    osc1_level: float = 0.8
    osc1_transpose: int = 0                       # 移调 (半音)

    # ---- Oscillator 2 ----
    osc2_enabled: bool = False
    osc2_wavetable: str = "Sine"
    osc2_level: float = 0.0
    osc2_transpose: int = -12

    # ---- Oscillator 3 (Sample) ----
    osc3_enabled: bool = False
    osc3_level: float = 0.0

    # ---- Filter ----
    filter_type: str = "Low Pass 24dB"
    filter_cutoff: float = 0.7
    filter_cutoff_hz: float = 2000.0
    filter_resonance: float = 0.15
    filter_blend: float = 0.0                     # 串/并联混合 (0=串, 1=并)
    filter_env_amount: float = 0.3

    # ---- Amp Envelope ----
    amp_attack: float = 0.02
    amp_attack_ms: float = 20.0
    amp_decay: float = 0.3
    amp_decay_ms: float = 300.0
    amp_sustain: float = 0.7
    amp_release: float = 0.3
    amp_release_ms: float = 400.0

    # ---- Filter Envelope ----
    filt_attack_ms: float = 0.0
    filt_decay_ms: float = 300.0
    filt_sustain: float = 0.3
    filt_release_ms: float = 300.0

    # ---- LFO 1 ----
    lfo1_rate_hz: float = 1.5
    lfo1_depth: float = 0.0
    lfo1_target: str = "Filter Cutoff"

    # ---- Effects ----
    reverb_mix: float = 0.15
    reverb_decay: float = 0.3
    delay_mix: float = 0.0
    delay_time: float = 0.25
    chorus_mix: float = 0.0
    compressor_enabled: bool = True

    # ---- Master ----
    master_volume: float = 0.8
    portamento: float = 0.0
    polyphony: int = 8

    def to_dict(self) -> dict[str, Any]:
        """转为前端可读的字典."""
        return {
            "synth": "Vital",
            "oscillator_1": {
                "wavetable": self.osc1_wavetable,
                "frame": round(self.osc1_frame, 3),
                "unison_voices": self.osc1_unison_voices,
                "unison_detune": f"{int(self.osc1_unison_detune * 100)} cents",
                "level": round(self.osc1_level, 2),
                "transpose": f"{self.osc1_transpose:+d} st",
            },
            "oscillator_2": {
                "enabled": self.osc2_enabled,
                "wavetable": self.osc2_wavetable,
                "level": round(self.osc2_level, 2),
                "transpose": f"{self.osc2_transpose:+d} st",
            },
            "filter": {
                "type": self.filter_type,
                "cutoff": f"{self.filter_cutoff_hz:.0f} Hz",
                "resonance": f"{self.filter_resonance:.0%}",
                "env_amount": f"{self.filter_env_amount:.0%}",
            },
            "amp_envelope": {
                "attack": f"{self.amp_attack_ms:.0f} ms",
                "decay": f"{self.amp_decay_ms:.0f} ms",
                "sustain": f"{self.amp_sustain:.0%}",
                "release": f"{self.amp_release_ms:.0f} ms",
            },
            "filter_envelope": {
                "attack": f"{self.filt_attack_ms:.0f} ms",
                "decay": f"{self.filt_decay_ms:.0f} ms",
                "sustain": f"{self.filt_sustain:.0%}",
                "release": f"{self.filt_release_ms:.0f} ms",
            },
            "lfo1": {
                "rate": f"{self.lfo1_rate_hz:.1f} Hz",
                "depth": f"{self.lfo1_depth:.0%}",
                "target": self.lfo1_target,
            },
            "effects": {
                "reverb": f"{self.reverb_mix:.0%}",
                "delay": f"{self.delay_mix:.0%}",
                "chorus": f"{self.chorus_mix:.0%}",
                "compressor": "On" if self.compressor_enabled else "Off",
            },
            "master": {
                "volume": f"{self.master_volume:.0%}",
                "portamento": round(self.portamento, 2),
                "polyphony": self.polyphony,
            },
        }


# ===== General MIDI 参数 =====

@dataclass
class GeneralMidiParams:
    """通用 MIDI 参数 / General MIDI program & controller settings.

    用于硬件音源、SoundFont、Kontakt 等 GM 兼容设备。
    """

    program_number: int = 0                        # 音色号 (0-127)
    program_name: str = "Acoustic Grand Piano"    # GM 标准名称
    bank_msb: int = 0                             # Bank Select MSB (0-127)
    bank_lsb: int = 0                             # Bank Select LSB (0-127)
    channel: int = 0                               # MIDI 通道 (0-15)
    velocity_sensitivity: float = 0.7              # 力度灵敏度 (0-1)
    expression: int = 127                          # Expression CC11
    modulation: int = 0                            # Modulation CC1
    reverb_send: int = 40                          # Reverb Send CC91
    chorus_send: int = 0                           # Chorus Send CC93
    pan: int = 64                                  # Pan CC10 (0=左, 64=中, 127=右)

    def to_dict(self) -> dict[str, Any]:
        """转为前端可读的字典."""
        return {
            "synth": "General MIDI",
            "program": {
                "number": self.program_number,
                "name": self.program_name,
                "bank_msb": self.bank_msb,
                "bank_lsb": self.bank_lsb,
            },
            "channel": self.channel + 1,  # 用户习惯 1-based
            "velocity_sensitivity": f"{self.velocity_sensitivity:.0%}",
            "controllers": {
                "expression_cc11": self.expression,
                "modulation_cc1": self.modulation,
                "reverb_cc91": self.reverb_send,
                "chorus_cc93": self.chorus_send,
                "pan_cc10": self.pan,
            },
        }


# ===== 映射器 =====

class SynthParamMapper:
    """合成器参数映射器 / Maps high-level timbre params to synth-specific params.

    将 5 个 high-level 抽象参数映射到具体合成器的可控参数。
    映射逻辑基于声学直觉 + 常见合成器设计模式。

    用法:
        mapper = SynthParamMapper()
        serum = mapper.to_serum(brightness=0.7, warmth=0.4, attack=0.3, sustain=0.7, body=0.6)
    """

    # 核心映射常量
    # 截止频率范围
    CUTOFF_MIN_HZ = 60.0
    CUTOFF_MAX_HZ = 18000.0

    # 包络时间范围
    ATTACK_MIN_MS = 0.0
    ATTACK_MAX_MS = 800.0
    DECAY_MIN_MS = 10.0
    DECAY_MAX_MS = 2000.0
    RELEASE_MIN_MS = 20.0
    RELEASE_MAX_MS = 3000.0

    # LFO 速率范围
    LFO_RATE_MIN_HZ = 0.05
    LFO_RATE_MAX_HZ = 40.0

    # --- 内部映射辅助 ---

    @staticmethod
    def _map_cutoff(brightness: float, warmth: float) -> tuple[float, float]:
        """将 brightness+warmth 映射为 cutoff 归一化值和 Hz 值.

        brightness 高 → cutoff 高
        warmth 高 → cutoff 略低 (温暖=高频滚降)
        """
        normalized = brightness * 0.8 + 0.1 - warmth * 0.2
        normalized = max(0.01, min(0.99, normalized))
        # 对数映射到 Hz
        import math
        log_min = math.log10(SynthParamMapper.CUTOFF_MIN_HZ)
        log_max = math.log10(SynthParamMapper.CUTOFF_MAX_HZ)
        hz = 10 ** (log_min + normalized * (log_max - log_min))
        return normalized, round(hz, 1)

    @staticmethod
    def _map_attack_ms(attack: float) -> float:
        """将 attack (0-1) 映射为起音毫秒值."""
        return round(SynthParamMapper.ATTACK_MIN_MS +
                     attack * (SynthParamMapper.ATTACK_MAX_MS - SynthParamMapper.ATTACK_MIN_MS), 1)

    @staticmethod
    def _map_decay_ms(sustain: float) -> float:
        """sustain 越低 → decay 越快 (音头后迅速衰减)."""
        # sustain=0.8 → decay~150ms; sustain=0.2 → decay~1200ms
        normalized = 1.0 - sustain
        return round(SynthParamMapper.DECAY_MIN_MS +
                     normalized * (SynthParamMapper.DECAY_MAX_MS - SynthParamMapper.DECAY_MIN_MS), 1)

    @staticmethod
    def _map_release_ms(sustain: float) -> float:
        """sustain 越高 → release 适中; 越低 → release 短."""
        normalized = sustain
        return round(SynthParamMapper.RELEASE_MIN_MS +
                     normalized * (SynthParamMapper.RELEASE_MAX_MS - SynthParamMapper.RELEASE_MIN_MS), 1)

    # --- 公共映射接口 ---

    def to_serum(
        self,
        brightness: float = 0.5,
        warmth: float = 0.5,
        attack: float = 0.5,
        sustain: float = 0.5,
        body: float = 0.5,
        instrument: str = "synth",
    ) -> SerumParams:
        """将 high-level 参数映射为 Serum 合成器参数.

        Args:
            brightness: 亮度 (0-1)
            warmth: 温暖度 (0-1)
            attack: 起音强度 (0-1, 越大越有力)
            sustain: 持续度 (0-1, 越大越持久)
            body: 饱满度 (0-1, 越大越厚实)
            instrument: 目标乐器类型 (piano/guitar/bass/synth)

        Returns:
            SerumParams 实例
        """
        cutoff_norm, cutoff_hz = self._map_cutoff(brightness, warmth)
        atk_ms = self._map_attack_ms(attack)
        dec_ms = self._map_decay_ms(sustain)
        rel_ms = self._map_release_ms(sustain)

        # body → unison 和 detune (越饱满 = 越多 unison detune)
        unison_voices = max(1, min(16, int(body * 10 + 1)))
        unison_detune = body * 0.35

        # warmth → resonance 略高 (温暖模拟感)
        resonance = warmth * 0.35 + body * 0.1

        # brightness → wavetable position 偏右 (更亮)
        wt_position = 0.3 + brightness * 0.5

        # 根据乐器类型调整波表选择
        wavetable_map = {
            "piano": "Basic Shapes",
            "guitar": "Analog Saw",
            "bass": "Basic Mg",
            "synth": "Basic Shapes",
        }
        wavetable = wavetable_map.get(instrument, "Basic Shapes")

        # 根据乐器类型调整滤波器类型
        filter_map = {
            "piano": "Low 24",
            "guitar": "Low 18",
            "bass": "Low 24",
            "synth": "Low 24",
        }
        filter_type = filter_map.get(instrument, "Low 24")

        # reverb: 温暖声音多一点混响
        reverb_mix = warmth * 0.25 + sustain * 0.1

        return SerumParams(
            osc_a_wavetable=wavetable,
            osc_a_wt_position=round(wt_position, 3),
            osc_a_unison_voices=unison_voices,
            osc_a_unison_detune=round(unison_detune, 3),
            osc_a_level=round(0.7 + body * 0.3, 2),

            osc_b_enabled=body > 0.4,
            osc_b_wavetable="Basic Mg",
            osc_b_level=round((body - 0.3) * 0.6, 2) if body > 0.3 else 0.0,
            osc_b_coarse=-12,
            osc_b_unison_voices=max(1, unison_voices // 2),

            noise_enabled=attack > 0.6,
            noise_level=round((attack - 0.5) * 0.2, 2) if attack > 0.5 else 0.0,

            filter_type=filter_type,
            filter_cutoff=round(cutoff_norm, 3),
            filter_cutoff_hz=cutoff_hz,
            filter_resonance=round(resonance, 3),
            filter_drive=round(warmth * 0.2, 3),
            filter_env_amount=round(attack * 0.6, 3),

            amp_attack=round(atk_ms / 2000, 3),  # 归一化到 0-2s
            amp_attack_ms=atk_ms,
            amp_decay=round(dec_ms / 2000, 3),
            amp_decay_ms=dec_ms,
            amp_sustain=round(0.4 + sustain * 0.5, 3),
            amp_release=round(rel_ms / 3000, 3),
            amp_release_ms=rel_ms,

            filt_attack=0.0,
            filt_attack_ms=0.0,
            filt_decay=round(dec_ms * 0.8 / 2000, 3),
            filt_decay_ms=round(dec_ms * 0.8, 1),
            filt_sustain=round(sustain * 0.5, 3),
            filt_release=round(rel_ms / 3000, 3),
            filt_release_ms=rel_ms,

            lfo1_rate=round(0.05 + brightness * 0.4, 3),
            lfo1_rate_hz=round(0.1 + brightness * 4.0, 1),
            lfo1_depth=round((1.0 - sustain) * 0.3, 3),
            lfo1_target="Filter Cutoff",

            reverb_mix=round(reverb_mix, 2),
            reverb_size=round(warmth * 0.4 + 0.1, 2),
            delay_mix=round(sustain * 0.15, 2),
            delay_time=0.25,  # 1/4 note
            chorus_depth=round(body * 0.2, 2),
            distortion_mix=round(attack * 0.15, 2),

            master_volume=0.8,
            portamento=0.0,
            polyphony=8 if sustain > 0.5 else 4,
        )

    def to_vital(
        self,
        brightness: float = 0.5,
        warmth: float = 0.5,
        attack: float = 0.5,
        sustain: float = 0.5,
        body: float = 0.5,
        instrument: str = "synth",
    ) -> VitalParams:
        """将 high-level 参数映射为 Vital 合成器参数."""
        cutoff_norm, cutoff_hz = self._map_cutoff(brightness, warmth)
        atk_ms = self._map_attack_ms(attack)
        dec_ms = self._map_decay_ms(sustain)
        rel_ms = self._map_release_ms(sustain)

        unison_voices = max(1, min(16, int(body * 10 + 1)))
        unison_detune = body * 0.35
        resonance = warmth * 0.35 + body * 0.1
        wt_frame = 0.3 + brightness * 0.5

        wavetable_map = {
            "piano": "Basic Shapes",
            "guitar": "Saw Wave",
            "bass": "Saw Wave",
            "synth": "Basic Shapes",
        }
        wavetable = wavetable_map.get(instrument, "Basic Shapes")

        filter_map = {
            "piano": "Low Pass 24dB",
            "guitar": "Low Pass 12dB",
            "bass": "Low Pass 24dB",
            "synth": "Low Pass 24dB",
        }
        filter_type = filter_map.get(instrument, "Low Pass 24dB")

        reverb_mix = warmth * 0.25 + sustain * 0.1

        return VitalParams(
            osc1_wavetable=wavetable,
            osc1_frame=round(wt_frame, 3),
            osc1_unison_voices=unison_voices,
            osc1_unison_detune=round(unison_detune, 3),
            osc1_level=round(0.7 + body * 0.3, 2),

            osc2_enabled=body > 0.4,
            osc2_level=round((body - 0.3) * 0.5, 2) if body > 0.3 else 0.0,
            osc2_transpose=-12,

            osc3_enabled=False,

            filter_type=filter_type,
            filter_cutoff=round(cutoff_norm, 3),
            filter_cutoff_hz=cutoff_hz,
            filter_resonance=round(resonance, 3),
            filter_blend=0.0,
            filter_env_amount=round(attack * 0.6, 3),

            amp_attack=round(atk_ms / 2000, 3),
            amp_attack_ms=atk_ms,
            amp_decay=round(dec_ms / 2000, 3),
            amp_decay_ms=dec_ms,
            amp_sustain=round(0.4 + sustain * 0.5, 3),
            amp_release=round(rel_ms / 3000, 3),
            amp_release_ms=rel_ms,

            filt_attack_ms=0.0,
            filt_decay_ms=round(dec_ms * 0.8, 1),
            filt_sustain=round(sustain * 0.5, 3),
            filt_release_ms=rel_ms,

            lfo1_rate_hz=round(0.1 + brightness * 4.0, 1),
            lfo1_depth=round((1.0 - sustain) * 0.3, 3),
            lfo1_target="Filter Cutoff",

            reverb_mix=round(reverb_mix, 2),
            reverb_decay=round(warmth * 0.4 + 0.1, 2),
            delay_mix=round(sustain * 0.15, 2),
            delay_time=0.25,
            chorus_mix=round(body * 0.15, 2),
            compressor_enabled=True,

            master_volume=0.8,
            portamento=0.0,
            polyphony=8 if sustain > 0.5 else 4,
        )

    def to_general_midi(
        self,
        brightness: float = 0.5,
        warmth: float = 0.5,
        attack: float = 0.5,
        sustain: float = 0.5,
        body: float = 0.5,
        instrument: str = "piano",
    ) -> GeneralMidiParams:
        """将 high-level 参数映射为 General MIDI 参数.

        主要是选择合适的 program number 和效果器发送量。
        """
        # GM Program 映射: 根据 instrument 类型和音色特征选择
        gm_piano_programs = {
            # (brightness_level, warmth_level) → (program, name)
            # brightness: 0-0.4=dark, 0.4-0.7=medium, 0.7-1.0=bright
            # warmth: 0-0.4=cool, 0.4-0.7=medium, 0.7-1.0=warm
        }

        prog = 0
        prog_name = "Acoustic Grand Piano"

        if instrument in ("piano",):
            if brightness > 0.6:
                prog, prog_name = 0, "Acoustic Grand Piano"  # Bright
            elif warmth > 0.7:
                prog, prog_name = 3, "Honky-tonk Piano"
            elif brightness < 0.3:
                prog, prog_name = 1, "Bright Acoustic Piano"
            else:
                prog, prog_name = 0, "Acoustic Grand Piano"
        elif instrument == "guitar":
            if brightness > 0.5:
                prog, prog_name = 26, "Electric Guitar (jazz)"
            elif attack > 0.6:
                prog, prog_name = 30, "Distortion Guitar"
            else:
                prog, prog_name = 25, "Acoustic Guitar (nylon)"
        elif instrument == "bass":
            if attack > 0.7:
                prog, prog_name = 37, "Slap Bass 1"
            elif body > 0.7:
                prog, prog_name = 39, "Synth Bass 1"
            else:
                prog, prog_name = 33, "Electric Bass (finger)"
        elif instrument == "synth":
            if sustain > 0.7:
                prog, prog_name = 91, "Pad 2 (warm)"
            elif brightness > 0.7:
                prog, prog_name = 81, "Lead 1 (square)"
            elif attack < 0.3:
                prog, prog_name = 89, "Pad 1 (new age)"
            else:
                prog, prog_name = 81, "Lead 1 (square)"

        reverb_send = int(warmth * 80 + sustain * 20)
        chorus_send = int(body * 50)

        return GeneralMidiParams(
            program_number=prog,
            program_name=prog_name,
            bank_msb=0,
            bank_lsb=0,
            channel=0,
            velocity_sensitivity=round(0.4 + attack * 0.5, 2),
            expression=127,
            modulation=int((1.0 - sustain) * 60),
            reverb_send=min(127, reverb_send),
            chorus_send=min(127, chorus_send),
            pan=64,
        )

    def generate_all(
        self,
        brightness: float = 0.5,
        warmth: float = 0.5,
        attack: float = 0.5,
        sustain: float = 0.5,
        body: float = 0.5,
        instrument: str = "synth",
    ) -> dict[str, dict[str, Any]]:
        """一键生成所有支持合成器的参数 / Generate params for all supported synths.

        Returns:
            {"serum": {...}, "vital": {...}, "general_midi": {...}}
        """
        return {
            "serum": self.to_serum(brightness, warmth, attack, sustain, body, instrument).to_dict(),
            "vital": self.to_vital(brightness, warmth, attack, sustain, body, instrument).to_dict(),
            "general_midi": self.to_general_midi(brightness, warmth, attack, sustain, body, instrument).to_dict(),
        }

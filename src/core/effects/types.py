"""效果器参数类型定义 / Effects parameter type definitions.

定义 Phase 5 效果器估算中使用的所有数据类.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EQBand:
    """单个 EQ 频段 / A single parametric EQ band.

    Attributes:
        center_freq_hz: 中心频率 (Hz)
        gain_db: 增益 (dB), 正值=提升, 负值=衰减
        q: Q 值 (带宽), 越小带宽越宽
        filter_type: 滤波器类型: peak / low_shelf / high_shelf
    """

    center_freq_hz: float
    gain_db: float
    q: float = 1.4
    filter_type: str = "peak"

    def to_dict(self) -> dict:
        return {
            "freq_hz": round(self.center_freq_hz, 1),
            "gain_db": round(self.gain_db, 2),
            "q": round(self.q, 2),
            "type": self.filter_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EQBand":
        return cls(
            center_freq_hz=d["freq_hz"],
            gain_db=d["gain_db"],
            q=d.get("q", 1.4),
            filter_type=d.get("type", "peak"),
        )


@dataclass
class EQEstimate:
    """EQ 估算结果 / EQ estimation result.

    Attributes:
        bands: EQ 频段列表 (最多 5 个)
        pre_gain_db: 宽带增益偏移 (dB)
    """

    bands: list[EQBand] = field(default_factory=list)
    pre_gain_db: float = 0.0

    def to_dict(self) -> dict:
        return {
            "bands": [b.to_dict() for b in self.bands],
            "pre_gain_db": round(self.pre_gain_db, 2),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EQEstimate":
        return cls(
            bands=[EQBand.from_dict(b) for b in d.get("bands", [])],
            pre_gain_db=d.get("pre_gain_db", 0.0),
        )

    def __bool__(self) -> bool:
        return len(self.bands) > 0 or abs(self.pre_gain_db) > 0.5


@dataclass
class ReverbEstimate:
    """混响估算结果 / Reverb estimation result.

    Attributes:
        rt60_sec: RT60 混响时间 (秒), 0 表示无混响
        dry_wet_ratio: 干湿比 (0=全干, 1=全湿)
    """

    rt60_sec: float = 0.0
    dry_wet_ratio: float = 0.0

    def to_dict(self) -> dict:
        return {
            "rt60_sec": round(self.rt60_sec, 3),
            "dry_wet_ratio": round(self.dry_wet_ratio, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReverbEstimate":
        return cls(
            rt60_sec=d.get("rt60_sec", 0.0),
            dry_wet_ratio=d.get("dry_wet_ratio", 0.0),
        )

    def __bool__(self) -> bool:
        return self.rt60_sec > 0.05


@dataclass
class CompressionEstimate:
    """压缩器估算结果 / Compression estimation result.

    Attributes:
        threshold_db: 阈值 (dB)
        ratio: 压缩比
        attack_ms: 启动时间 (ms)
        release_ms: 释放时间 (ms)
        makeup_gain_db: 补偿增益 (dB)
    """

    threshold_db: float = -20.0
    ratio: float = 1.0  # 1.0 = 无压缩
    attack_ms: float = 10.0
    release_ms: float = 100.0
    makeup_gain_db: float = 0.0

    def to_dict(self) -> dict:
        return {
            "threshold_db": round(self.threshold_db, 1),
            "ratio": round(self.ratio, 2),
            "attack_ms": round(self.attack_ms, 1),
            "release_ms": round(self.release_ms, 1),
            "makeup_gain_db": round(self.makeup_gain_db, 2),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CompressionEstimate":
        return cls(
            threshold_db=d.get("threshold_db", -20.0),
            ratio=d.get("ratio", 1.0),
            attack_ms=d.get("attack_ms", 10.0),
            release_ms=d.get("release_ms", 100.0),
            makeup_gain_db=d.get("makeup_gain_db", 0.0),
        )

    def __bool__(self) -> bool:
        return self.ratio > 1.2 or abs(self.makeup_gain_db) > 0.5


@dataclass
class EffectsProfile:
    """完整效果器分析结果 / Complete effects analysis profile for one stem.

    Attributes:
        eq: EQ 估算结果
        reverb: 混响估算结果
        compression: 压缩估算结果
        stem_name: 乐器名
        preset_name: 匹配到的预设名
        iteration: 迭代次数 (0=initial)
        confidence: 置信度 (0-1)
    """

    eq: EQEstimate | None = None
    reverb: ReverbEstimate | None = None
    compression: CompressionEstimate | None = None
    stem_name: str = ""
    preset_name: str = ""
    iteration: int = 0
    confidence: float = 0.0

    def to_dict(self) -> dict:
        """转为 JSON 友好字典."""
        d: dict = {
            "version": 1,
            "stem_name": self.stem_name,
            "matched_preset": self.preset_name,
            "iteration": self.iteration,
            "confidence": round(self.confidence, 4),
            "effects_chain": [],
        }
        chain = d["effects_chain"]
        order = 1
        if self.eq and self.eq:
            chain.append({"type": "eq", "order": order, **self.eq.to_dict()})
            order += 1
        if self.compression and self.compression:
            chain.append({"type": "compressor", "order": order, **self.compression.to_dict()})
            order += 1
        if self.reverb and self.reverb:
            chain.append({"type": "reverb", "order": order, **self.reverb.to_dict()})
            order += 1
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EffectsProfile":
        """从 JSON 字典恢复."""
        profile = cls(
            stem_name=d.get("stem_name", ""),
            preset_name=d.get("matched_preset", ""),
            iteration=d.get("iteration", 0),
            confidence=d.get("confidence", 0.0),
        )
        for item in d.get("effects_chain", []):
            t = item["type"]
            if t == "eq":
                profile.eq = EQEstimate.from_dict(item)
            elif t == "reverb":
                profile.reverb = ReverbEstimate.from_dict(item)
            elif t == "compressor":
                profile.compression = CompressionEstimate.from_dict(item)
        return profile

    def summary(self) -> str:
        """生成人类可读的摘要 / Human-readable summary."""
        lines = [
            f"Effects Profile: {self.stem_name} (preset={self.preset_name})",
            f"  Confidence: {self.confidence:.2f}",
        ]
        if self.eq and self.eq:
            lines.append(f"  EQ: {len(self.eq.bands)} band(s)")
            for b in self.eq.bands:
                lines.append(
                    f"    {b.filter_type} @ {b.center_freq_hz:.0f}Hz: "
                    f"{b.gain_db:+.1f}dB (Q={b.q:.1f})"
                )
        if self.compression and self.compression:
            lines.append(
                f"  Compressor: threshold={self.compression.threshold_db:.0f}dB, "
                f"ratio={self.compression.ratio:.1f}:1, "
                f"attack={self.compression.attack_ms:.0f}ms, "
                f"release={self.compression.release_ms:.0f}ms"
            )
        if self.reverb and self.reverb:
            lines.append(
                f"  Reverb: RT60={self.reverb.rt60_sec:.2f}s, "
                f"dry/wet={1-self.reverb.dry_wet_ratio:.1f}/{self.reverb.dry_wet_ratio:.1f}"
            )
        return "\n".join(lines)

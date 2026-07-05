"""效果器参数分析 / Effects Analysis.

模块:
  - types: 数据类定义 (EQBand, EffectsProfile 等)
  - eq_estimator: EQ 参数估算 (频谱差分 + 曲线拟合)
  - reverb_estimator: 混响参数估算 (EDC + 能量比)
  - dynamics_estimator: 压缩参数估算 (RMS 分布 + 瞬态分析)
  - chain_builder: 效果器链编排 + 干音参考合成
"""

from src.core.effects.types import (
    EQBand,
    EQEstimate,
    ReverbEstimate,
    CompressionEstimate,
    EffectsProfile,
)
from src.core.effects.eq_estimator import EQEstimator
from src.core.effects.reverb_estimator import ReverbEstimator
from src.core.effects.dynamics_estimator import DynamicsEstimator
from src.core.effects.chain_builder import EffectsChainBuilder

__all__ = [
    "EQBand",
    "EQEstimate",
    "ReverbEstimate",
    "CompressionEstimate",
    "EffectsProfile",
    "EQEstimator",
    "ReverbEstimator",
    "DynamicsEstimator",
    "EffectsChainBuilder",
]

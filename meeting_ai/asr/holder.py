"""FunASR 批量引擎懒加载，避免仅使用听悟实时转写时占用大量内存。"""
from asr.engine import FunASREngine

_engine: FunASREngine | None = None


def get_asr_engine() -> FunASREngine:
    global _engine
    if _engine is None:
        _engine = FunASREngine()
    return _engine

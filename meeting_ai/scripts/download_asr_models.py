"""
预下载 FunASR 批量转写所需模型（从 .env / config 读取模型名）。

用法（在项目根目录、asr 环境中）:
  python scripts/download_asr_models.py          # 批量 ASR + VAD（批量上传必需）
  python scripts/download_asr_models.py --all   # 额外下载流式 ASR（本地实时备用）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.config import (
    asr_model_hub,
    asr_model_name,
    asr_streaming_model_name,
    asr_vad_model_name,
)
from asr.engine import _resolve_funasr_model_name


def download_one(label: str, model_name: str) -> str:
    from funasr.download.download_model_from_hub import download_model

    resolved = _resolve_funasr_model_name(model_name)
    if resolved != model_name:
        print(f"\n==> [{label}] {model_name}  ->  {resolved}")
    else:
        print(f"\n==> [{label}] {resolved}")
    print(f"    hub={asr_model_hub}，首次下载可能较慢，请保持网络畅通…")

    kwargs = download_model(
        model=resolved,
        hub=asr_model_hub,
        disable_update=True,
    )
    model_path = kwargs.get("model_path") or resolved
    config_yaml = Path(model_path) / "config.yaml"
    configuration_json = Path(model_path) / "configuration.json"
    if not config_yaml.exists() and not configuration_json.exists():
        raise RuntimeError(
            f"模型未成功落地: {model_path}\n"
            "请检查能否访问 modelscope.cn，或配置 ModelScope 镜像后重试。"
        )
    print(f"    [OK] {model_path}")
    return str(model_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="预下载 FunASR 模型")
    parser.add_argument(
        "--all",
        action="store_true",
        help="同时下载流式 ASR 模型（仅本地 FunASR 实时备用，听悟实时可不下）",
    )
    args = parser.parse_args()

    print("将下载以下模型（名称来自 .env / config.py）:")
    print(f"  批量 ASR : {asr_model_name}")
    print(f"  VAD      : {asr_vad_model_name}")
    if args.all:
        print(f"  流式 ASR : {asr_streaming_model_name}")

    paths: list[str] = []
    paths.append(download_one("批量 ASR", asr_model_name))
    paths.append(download_one("VAD", asr_vad_model_name))
    if args.all:
        paths.append(download_one("流式 ASR", asr_streaming_model_name))

    print("\n全部完成。模型目录示例:")
    for p in paths:
        print(f"  - {p}")
    print("\n可重启服务后使用「批量处理」上传音频。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[失败] {e}", file=sys.stderr)
        sys.exit(1)

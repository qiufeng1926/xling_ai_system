"""
无需长录音：用长文本直接测试图文速览（含分段合并）

用法（在项目根目录）:
  python scripts/test_visual_chunk.py
  python scripts/test_visual_chunk.py --chars 1200   # 模拟更短即触发分段
"""
import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import config as cfg
from llm.client_holder import create_llm_client
from llm.summary_service import _generate_visual_with_retry
from llm.visual_schema import split_transcript_chunks


def _build_long_transcript(target_chars: int) -> str:
    """构造多话题的模拟会议转写"""
    topics = [
        ('项目进度', '目前前端完成约八成，后端接口联调中，预计两周内可提测。'),
        ('资源协调', '设计需再补一版移动端稿；测试人力下周可投入两人天。'),
        ('风险项', '第三方短信通道配额可能不足，需本周内确认商务续费。'),
        ('客户反馈', '客户希望增加导出 PDF，优先级排在二期。'),
        ('预算讨论', '本季度市场预算已批，会务物料控制在五万以内。'),
        ('合规要求', '对外宣传文案需法务过审，不得提前承诺上线日期。'),
        ('下次会议', '周五下午三点复盘，请各部门提前整理 blocker 列表。'),
    ]
    parts: list[str] = []
    i = 0
    while sum(len(p) for p in parts) < target_chars:
        title, body = topics[i % len(topics)]
        speaker = f'说话人{(i % 3) + 1}'
        parts.append(f'[{speaker}] 关于{title}：{body} 另外补充一点细节编号{i + 1}。')
        i += 1
    return '\n\n'.join(parts)


async def main():
    parser = argparse.ArgumentParser(description='测试图文速览分段生成')
    parser.add_argument(
        '--chars',
        type=int,
        default=0,
        help='模拟转写总字数，0 表示用 VISUAL_CHUNK_CHARS+500',
    )
    parser.add_argument(
        '--chunk',
        type=int,
        default=0,
        help='临时覆盖 VISUAL_CHUNK_CHARS（便于触发分段）',
    )
    args = parser.parse_args()

    if args.chunk:
        cfg.visual_chunk_chars = args.chunk

    chunk_size = cfg.visual_chunk_chars
    total_chars = args.chars or (chunk_size + 800)

    transcript = _build_long_transcript(total_chars)
    chunks = split_transcript_chunks(
        transcript,
        max_chars=chunk_size,
        overlap=cfg.visual_chunk_overlap,
    )

    print(f'VISUAL_CHUNK_CHARS = {chunk_size}')
    print(f'模拟转写长度 = {len(transcript)} 字')
    print(f'将分为 {len(chunks)} 段生成\n')

    if cfg.llm_provider == "deepseek":
        if not cfg.deepseek_api_key:
            print('错误: LLM_PROVIDER=deepseek 但未配置 DEEPSEEK_API_KEY')
            sys.exit(1)
    elif not cfg.glm_api_key:
        print('错误: LLM_PROVIDER=glm 但未配置 GLM_API_KEY')
        sys.exit(1)

    client = create_llm_client()
    visual, visual_json, err = await _generate_visual_with_retry(
        client,
        transcript,
        meeting_name='分段测试会议',
        max_retries=cfg.visual_summary_retry_max,
    )

    if err or not visual:
        print(f'生成失败: {err}')
        sys.exit(1)

    print(f'标题: {visual.title}')
    print(f'分区数: {len(visual.sections)}')
    for sec in visual.sections:
        print(f'  [{sec.id}] {sec.title} ({sec.layout}, {len(sec.cards)} 张卡片)')
    if visual.footer.core_consensus:
        print(f'\n核心共识: {visual.footer.core_consensus[:120]}...')
    print(f'\nJSON 长度: {len(visual_json or "")} 字符')
    print('完成。可将 VISUAL_CHUNK_CHARS 改回 6000 用于正式环境。')


if __name__ == '__main__':
    asyncio.run(main())

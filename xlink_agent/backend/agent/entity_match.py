"""实体精确匹配（方案第二步：低成本字面/指代召回）。

在向量检索之前优先：
- 文件名 / 扩展名
- 单据号、订单号类标识
- 《书名》/引号专名
- 「刚才那个文件」等指示代词 → 最近产物

输出结构化命中，供编排层注入；预留 MemoryRecallPort 供第三步摘要召回、第四步向量检索实现同一接口。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from db.models import Message, WorkspaceFile
from utils.logger import get_logger

logger = get_logger("entity_match")

_FILE_EXT_RE = re.compile(
    r"([\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_.]{0,80}\.(?:docx|xlsx|xls|pptx|pdf|md|txt|csv|json))",
    re.I,
)
_DOC_NO_RE = re.compile(
    r"(?:"
    r"(?:单号|订单号|工单号|编号|单据号|合同号|发票号)\s*[:：#]?\s*([A-Za-z0-9\-]{4,32})"
    r"|([A-Z]{2,}[-_]\d{3,})"
    r"|(NO\.?\s*\d{4,})"
    r")",
    re.I,
)
_TITLE_RE = re.compile(r"《([^》]{1,60})》|[「『\"“]([^」』\"”]{1,60})[」』\"”]")
_DEICTIC_FILE_RE = re.compile(
    r"(刚才|刚刚|上次|上轮|之前|那个|这份|这个|刚生成的?|刚写的?)"
    r".{0,6}(文件|文档|表格|报告|附件|docx|xlsx|excel|word|pdf|ppt)",
    re.I,
)
_DEICTIC_GENERIC_RE = re.compile(
    r"^(?:把|将|打开|下载|发给我|看一下|修改|润色|总结)?\s*"
    r"(?:刚才|刚刚|那个|这份|这个)\s*(?:的)?\s*"
    r"(?:文件|文档|表格|报告|附件)?\s*"
    r"(?:打开|下载|发给我|看一下|改一下|润色|总结)?\s*[吗么吧]?[？?]?$",
    re.I,
)


@dataclass
class EntityHit:
    kind: str
    value: str
    source: str
    score: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "source": self.source,
            "score": self.score,
            "meta": self.meta,
        }


@dataclass
class EntityMatchResult:
    hits: list[EntityHit] = field(default_factory=list)
    query_entities: list[str] = field(default_factory=list)
    deictic_resolved: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.hits)

    def top_values(self, *, limit: int = 6) -> list[str]:
        out: list[str] = []
        for h in sorted(self.hits, key=lambda x: -x.score):
            if h.value not in out:
                out.append(h.value)
            if len(out) >= limit:
                break
        return out

    def render_injection(self) -> str:
        if not self.hits:
            return ""
        lines = [
            "# 实体精确匹配（优先于模糊语义，办公指代核心）",
        ]
        if self.query_entities:
            lines.append("- 提问中识别到的实体: " + "、".join(self.query_entities[:8]))
        lines.append("- 命中历史/产物:")
        for h in sorted(self.hits, key=lambda x: -x.score)[:8]:
            extra = ""
            if h.meta.get("file_id"):
                extra = f" file_id={h.meta['file_id']}"
            if h.meta.get("path"):
                extra = f" path={h.meta['path']}"
            lines.append(f"  · [{h.kind}/{h.source}] {h.value}{extra} (score={h.score:.2f})")
        if self.deictic_resolved:
            lines.append(
                "- 规则: 用户使用了「刚才/那个文件」类指代，已解析为最近产物；"
                "回答与操作必须针对上述命中项，禁止另搜无关文件。"
            )
        else:
            lines.append(
                "- 规则: 若用户点名上述文件/编号，优先使用已有产物或工作区文件，"
                "不要假装找不到或重新生成同名空文件。"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": [h.to_dict() for h in self.hits],
            "query_entities": list(self.query_entities),
            "deictic_resolved": self.deictic_resolved,
        }


@runtime_checkable
class MemoryRecallPort(Protocol):
    """第三/四步可实现：摘要召回、向量召回；与实体匹配同一消费形状。"""

    def recall(
        self,
        *,
        user_id: int,
        conversation_id: int,
        query: str,
        limit: int = 8,
    ) -> EntityMatchResult: ...


def extract_query_entities(text: str) -> list[str]:
    """从用户话术抽取可精确匹配的实体字面。"""
    t = text or ""
    found: list[str] = []
    for m in _FILE_EXT_RE.finditer(t):
        found.append(m.group(1))
    for m in _DOC_NO_RE.finditer(t):
        g = next((x for x in m.groups() if x), None)
        if g:
            found.append(g.strip())
    for m in _TITLE_RE.finditer(t):
        g = next((x for x in m.groups() if x), None)
        if g:
            found.append(g.strip())
    # 去重保序
    out: list[str] = []
    seen: set[str] = set()
    for x in found:
        key = x.lower()
        if key not in seen and len(x) >= 2:
            seen.add(key)
            out.append(x)
    return out


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip().lower())


def _candidate_from_task_artifacts(artifacts: list[str] | None) -> list[EntityHit]:
    hits: list[EntityHit] = []
    for i, a in enumerate(artifacts or []):
        name = str(a or "").strip()
        if not name:
            continue
        hits.append(
            EntityHit(
                kind="file",
                value=name,
                source="task_artifact",
                score=0.95 - i * 0.02,
                meta={"artifact": name},
            )
        )
    return hits


def _candidate_from_workspace(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    limit: int = 30,
) -> list[EntityHit]:
    rows = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.user_id == user_id)
        .order_by(WorkspaceFile.id.desc())
        .limit(limit)
        .all()
    )
    hits: list[EntityHit] = []
    for i, row in enumerate(rows):
        # 本会话文件略加权
        same_conv = row.conversation_id == conversation_id
        hits.append(
            EntityHit(
                kind="file",
                value=row.name,
                source="workspace",
                score=(0.9 if same_conv else 0.75) - i * 0.01,
                meta={
                    "file_id": row.id,
                    "path": row.path,
                    "conversation_id": row.conversation_id,
                },
            )
        )
    return hits


def _candidate_from_messages(history: list[Any], *, limit_msgs: int = 12) -> list[EntityHit]:
    hits: list[EntityHit] = []
    msgs = list(history or [])[-limit_msgs:]
    for mi, item in enumerate(reversed(msgs)):
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "") or ""
        meta_raw = getattr(item, "metadata_json", None) or (
            item.get("metadata_json") if isinstance(item, dict) else None
        )
        # 助手消息里的文件名
        for m in _FILE_EXT_RE.finditer(content):
            hits.append(
                EntityHit(
                    kind="file",
                    value=m.group(1),
                    source="message",
                    score=0.7 - mi * 0.02,
                )
            )
        for m in _DOC_NO_RE.finditer(content):
            g = next((x for x in m.groups() if x), None)
            if g:
                hits.append(
                    EntityHit(
                        kind="doc_no",
                        value=g.strip(),
                        source="message",
                        score=0.72 - mi * 0.02,
                    )
                )
        if meta_raw:
            try:
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            except Exception:
                meta = None
            if isinstance(meta, dict):
                for f in meta.get("files") or []:
                    if isinstance(f, dict):
                        name = str(f.get("name") or "").strip()
                        if name:
                            hits.append(
                                EntityHit(
                                    kind="file",
                                    value=name,
                                    source="message_meta",
                                    score=0.88 - mi * 0.02,
                                    meta={"file_id": f.get("file_id")},
                                )
                            )
                arts = (meta.get("task_context") or {}).get("artifacts") or []
                for a in arts:
                    if a:
                        hits.append(
                            EntityHit(
                                kind="file",
                                value=str(a),
                                source="message_meta",
                                score=0.85 - mi * 0.02,
                            )
                        )
    return hits


def _dedupe_candidates(cands: list[EntityHit]) -> list[EntityHit]:
    best: dict[str, EntityHit] = {}
    for h in cands:
        key = f"{h.kind}:{_norm_name(h.value)}"
        prev = best.get(key)
        if prev is None or h.score > prev.score:
            best[key] = h
    return list(best.values())


def _score_literal_match(query_ent: str, cand: EntityHit) -> float | None:
    q = _norm_name(query_ent)
    v = _norm_name(cand.value)
    if not q or not v:
        return None
    if q == v:
        return cand.score + 0.2
    if q in v or v in q:
        return cand.score + 0.1
    # 无扩展名时用 stem 比
    q_stem = q.rsplit(".", 1)[0]
    v_stem = v.rsplit(".", 1)[0]
    if q_stem and v_stem and (q_stem == v_stem or q_stem in v_stem or v_stem in q_stem):
        return cand.score + 0.08
    return None


def match_entities(
    db: Session | None,
    *,
    user_id: int,
    conversation_id: int,
    user_text: str,
    task_artifacts: list[str] | None = None,
    history: list[Any] | None = None,
) -> EntityMatchResult:
    """对当前提问做实体精确/指代匹配。"""
    text = (user_text or "").strip()
    query_ents = extract_query_entities(text)
    cands: list[EntityHit] = []
    cands.extend(_candidate_from_task_artifacts(task_artifacts))
    if db is not None:
        try:
            cands.extend(
                _candidate_from_workspace(
                    db, user_id=user_id, conversation_id=conversation_id
                )
            )
        except Exception as exc:
            logger.warning("workspace entity scan failed: %s", exc)
    cands.extend(_candidate_from_messages(history or []))
    cands = _dedupe_candidates(cands)

    hits: list[EntityHit] = []
    deictic = bool(_DEICTIC_FILE_RE.search(text) or _DEICTIC_GENERIC_RE.match(text))

    # 1) 字面实体命中
    for qe in query_ents:
        for cand in cands:
            sc = _score_literal_match(qe, cand)
            if sc is None:
                continue
            hits.append(
                EntityHit(
                    kind=cand.kind,
                    value=cand.value,
                    source=cand.source,
                    score=min(1.2, sc),
                    meta={**cand.meta, "matched_query": qe},
                )
            )

    # 2) 指示代词 → 最近文件类候选
    if deictic:
        file_cands = [c for c in cands if c.kind == "file"]
        file_cands.sort(key=lambda x: -x.score)
        if file_cands:
            top = file_cands[0]
            hits.append(
                EntityHit(
                    kind="file",
                    value=top.value,
                    source=f"deictic:{top.source}",
                    score=min(1.25, top.score + 0.25),
                    meta={**top.meta, "deictic": True},
                )
            )

    # 去重取高分
    hits = _dedupe_candidates(hits)
    hits.sort(key=lambda x: -x.score)
    # 过滤过低分噪声
    hits = [h for h in hits if h.score >= 0.7][:8]

    result = EntityMatchResult(
        hits=hits,
        query_entities=query_ents,
        deictic_resolved=bool(deictic and hits),
    )
    if result.ok:
        logger.info(
            "entity match uid=%s conv=%s hits=%s deictic=%s",
            user_id,
            conversation_id,
            [h.value for h in hits[:4]],
            result.deictic_resolved,
        )
    return result


def expand_goal_with_entities(effective_goal: str, result: EntityMatchResult) -> str:
    """将命中实体并入有效目标，便于工具选择与写文件。"""
    if not result.ok:
        return effective_goal
    goal = (effective_goal or "").strip()
    vals = result.top_values(limit=4)
    tip = "、".join(vals)
    if tip and tip not in goal:
        prefix = "实体指代已解析" if result.deictic_resolved else "实体精确命中"
        return f"{goal}\n{prefix}：{tip}（优先使用这些已有文件/编号，勿忽略）"
    return goal


def merge_entity_hits_into_task_artifacts(
    artifacts: list[str],
    result: EntityMatchResult,
) -> list[str]:
    """把高置信文件命中并入任务产物列表（供下一轮指代）。"""
    out = list(artifacts or [])
    for h in result.hits:
        if h.kind == "file" and h.value and h.value not in out:
            out.insert(0, h.value)
    return out[:20]

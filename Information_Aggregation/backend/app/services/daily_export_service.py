"""每日定时导出：将全部业务文件备份到本地分级目录。"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.models.feishu_document import FeishuDocumentMirror, FeishuDocumentSnapshot
from app.services.offboarding_document_service import UPLOAD_ROOT as OFFBOARDING_ROOT

logger = logging.getLogger(__name__)


def _safe_filename(name: str, max_len: int = 120) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    cleaned = cleaned[:max_len].strip(". ")
    return cleaned or "unnamed"


@dataclass
class ExportStats:
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    export_date: str = ""
    dest_root: str = ""
    categories: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_manifest(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "export_date": self.export_date,
            "dest_root": self.dest_root,
            "categories": self.categories,
            "errors": self.errors,
        }


class DailyExportService:
    @staticmethod
    def resolve_export_root(for_date: date | None = None) -> Path:
        d = for_date or date.today()
        return Path(settings.DAILY_EXPORT_ROOT) / d.strftime("%Y-%m-%d")

    @staticmethod
    def _copy_tree(src: Path, dest: Path, *, category: str, stats: ExportStats) -> None:
        cat: dict = {"files": 0, "bytes": 0}
        stats.categories[category] = cat
        if not src.exists():
            cat["skipped"] = True
            cat["reason"] = "source_not_found"
            cat["source"] = str(src)
            logger.warning("导出源目录不存在: %s", src)
            return

        dest.mkdir(parents=True, exist_ok=True)
        files = 0
        total_bytes = 0
        for item in src.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(src)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            files += 1
            total_bytes += item.stat().st_size

        cat["files"] = files
        cat["bytes"] = total_bytes
        cat["source"] = str(src)
        logger.info("已导出 %s: %d 个文件, %d bytes", category, files, total_bytes)

    @staticmethod
    def _export_feishu_documents(db: Session, dest_root: Path, stats: ExportStats) -> None:
        category = "feishu_documents"
        cat: dict = {"files": 0, "bytes": 0, "documents": 0}
        stats.categories[category] = cat
        base = dest_root / category
        base.mkdir(parents=True, exist_ok=True)

        mirrors = (
            db.query(FeishuDocumentMirror)
            .filter(FeishuDocumentMirror.status == "active")
            .order_by(FeishuDocumentMirror.user_id.asc(), FeishuDocumentMirror.id.asc())
            .all()
        )

        for mirror in mirrors:
            snapshot = (
                db.query(FeishuDocumentSnapshot)
                .filter(FeishuDocumentSnapshot.mirror_id == mirror.id)
                .order_by(desc(FeishuDocumentSnapshot.synced_at))
                .first()
            )
            user_dir = base / str(mirror.user_id)
            user_dir.mkdir(parents=True, exist_ok=True)

            safe_title = _safe_filename(mirror.title)
            txt_path = user_dir / f"{mirror.doc_id}_{safe_title}.txt"
            meta_path = user_dir / f"{mirror.doc_id}_meta.json"

            content = (snapshot.content if snapshot else "") or ""
            txt_path.write_text(content, encoding="utf-8")

            meta = {
                "doc_id": mirror.doc_id,
                "user_id": mirror.user_id,
                "feishu_token": mirror.feishu_token,
                "feishu_type": mirror.feishu_type,
                "title": mirror.title,
                "feishu_url": mirror.feishu_url,
                "feishu_modified_at": mirror.feishu_modified_at.isoformat()
                if mirror.feishu_modified_at
                else None,
                "synced_at": mirror.synced_at.isoformat() if mirror.synced_at else None,
                "content_format": snapshot.content_format if snapshot else "plain_text",
                "content_length": len(content),
                "snapshot_synced_at": snapshot.synced_at.isoformat()
                if snapshot and snapshot.synced_at
                else None,
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            cat["documents"] += 1
            cat["files"] += 2
            cat["bytes"] += txt_path.stat().st_size + meta_path.stat().st_size

        logger.info("已导出 %s: %d 篇文档", category, cat["documents"])

    @staticmethod
    def run_export(db: Session, *, export_date: date | None = None) -> dict:
        """执行一次全量导出，返回 manifest 字典。"""
        d = export_date or date.today()
        dest_root = DailyExportService.resolve_export_root(d)
        dest_root.mkdir(parents=True, exist_ok=True)

        stats = ExportStats(export_date=d.isoformat(), dest_root=str(dest_root))
        logger.info("开始每日全量导出 -> %s", dest_root)

        try:
            DailyExportService._copy_tree(
                OFFBOARDING_ROOT,
                dest_root / "offboarding",
                category="offboarding",
                stats=stats,
            )
        except Exception as exc:
            msg = f"offboarding 导出失败: {exc}"
            stats.errors.append(msg)
            logger.exception(msg)

        upload_dir = Path(settings.MEETING_AI_UPLOAD_DIR)
        output_dir = Path(settings.MEETING_AI_OUTPUT_DIR)
        meeting_dest = dest_root / "meeting_ai"

        meeting_pairs = [
            (upload_dir, meeting_dest / "upload", "meeting_ai/upload"),
            (output_dir / "transcripts", meeting_dest / "transcripts", "meeting_ai/transcripts"),
            (output_dir / "summaries", meeting_dest / "summaries", "meeting_ai/summaries"),
        ]
        for src, dest, category in meeting_pairs:
            try:
                DailyExportService._copy_tree(src, dest, category=category, stats=stats)
            except Exception as exc:
                msg = f"{category} 导出失败: {exc}"
                stats.errors.append(msg)
                logger.exception(msg)

        # output 根目录下除 transcripts/summaries 外的散落文件
        try:
            extra_cat = "meeting_ai/output_misc"
            extra_stats: dict = {"files": 0, "bytes": 0}
            stats.categories[extra_cat] = extra_stats
            misc_dest = meeting_dest / "output_misc"
            if output_dir.exists():
                for item in output_dir.iterdir():
                    if not item.is_file():
                        continue
                    misc_dest.mkdir(parents=True, exist_ok=True)
                    target = misc_dest / item.name
                    shutil.copy2(item, target)
                    extra_stats["files"] += 1
                    extra_stats["bytes"] += item.stat().st_size
        except Exception as exc:
            msg = f"meeting_ai/output_misc 导出失败: {exc}"
            stats.errors.append(msg)
            logger.exception(msg)

        try:
            DailyExportService._export_feishu_documents(db, dest_root, stats)
        except Exception as exc:
            msg = f"feishu_documents 导出失败: {exc}"
            stats.errors.append(msg)
            logger.exception(msg)

        stats.finished_at = datetime.now()
        manifest = stats.to_manifest()
        manifest_path = dest_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(
            "每日全量导出完成: %s, 错误 %d 项",
            dest_root,
            len(stats.errors),
        )
        return manifest

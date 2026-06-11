-- Phase 2 增量迁移（已有库执行一次即可）
USE influencer_db;

ALTER TABLE collection_tasks
    ADD COLUMN IF NOT EXISTS retry_count INT DEFAULT 0 AFTER error_message;

ALTER TABLE collection_tasks
    ADD COLUMN IF NOT EXISTS error_category VARCHAR(30) AFTER retry_count;

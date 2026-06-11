-- 本地 MySQL 初始化（需 root 权限执行）
CREATE DATABASE IF NOT EXISTS influencer_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'app_user'@'localhost' IDENTIFIED BY 'app123';
GRANT ALL PRIVILEGES ON influencer_db.* TO 'app_user'@'localhost';
FLUSH PRIVILEGES;

USE influencer_db;

CREATE TABLE IF NOT EXISTS users (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    nickname        VARCHAR(100),
    role            VARCHAR(20) DEFAULT 'operator',
    status          TINYINT DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agencies (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(200) NOT NULL,
    platform            VARCHAR(20),
    contact_person      VARCHAR(100),
    contact_phone       VARCHAR(50),
    contact_wechat      VARCHAR(100),
    policy_notes        TEXT,
    cooperation_terms   JSON,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS influencers (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    platform        VARCHAR(20) NOT NULL,
    platform_uid    VARCHAR(100) NOT NULL,
    nickname        VARCHAR(200),
    avatar_url      TEXT,
    profile_url     TEXT,
    agency_id       BIGINT,
    follower_count  BIGINT DEFAULT 0,
    engagement_rate DECIMAL(5,4),
    source          VARCHAR(50),
    status          TINYINT DEFAULT 1,
    extra_data      JSON,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_platform_uid (platform, platform_uid),
    KEY idx_follower_count (follower_count),
    KEY idx_platform (platform),
    KEY idx_agency_id (agency_id),
    CONSTRAINT fk_influencer_agency FOREIGN KEY (agency_id) REFERENCES agencies(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS influencer_profiles (
    influencer_id       BIGINT PRIMARY KEY,
    contact_info        JSON,
    shooting_style      JSON,
    persona_traits      JSON,
    cooperation_policy  TEXT,
    internal_notes      TEXT,
    last_contact_date   DATE,
    updated_by          BIGINT,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_profile_influencer FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tags (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    parent_id   BIGINT,
    name        VARCHAR(100) NOT NULL,
    category    VARCHAR(50),
    level       TINYINT DEFAULT 1,
    KEY idx_parent_id (parent_id),
    KEY idx_category (category),
    CONSTRAINT fk_tag_parent FOREIGN KEY (parent_id) REFERENCES tags(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS influencer_tags (
    influencer_id   BIGINT NOT NULL,
    tag_id          BIGINT NOT NULL,
    source          VARCHAR(20),
    confidence      DECIMAL(3,2),
    PRIMARY KEY (influencer_id, tag_id),
    KEY idx_tag_id (tag_id),
    CONSTRAINT fk_it_influencer FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE,
    CONSTRAINT fk_it_tag FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS match_requests (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    title           VARCHAR(200),
    requirements    JSON NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    result_count    INT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user_id (user_id),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS match_results (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id      BIGINT NOT NULL,
    influencer_id   BIGINT NOT NULL,
    match_score     DECIMAL(5,2),
    rank_order      INT,
    reason          JSON,
    is_selected     TINYINT(1) DEFAULT 0,
    KEY idx_request_id (request_id),
    KEY idx_influencer_id (influencer_id),
    KEY idx_match_score (match_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS collection_tasks (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    title           VARCHAR(200),
    platform        VARCHAR(20) NOT NULL,
    keyword         VARCHAR(200) NOT NULL,
    filters         JSON,
    status          VARCHAR(20) DEFAULT 'pending',
    result_count    INT DEFAULT 0,
    approved_count  INT DEFAULT 0,
    error_message   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at      DATETIME,
    completed_at    DATETIME,
    KEY idx_user_id (user_id),
    KEY idx_status (status),
    KEY idx_platform (platform)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS collected_influencers (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id         BIGINT NOT NULL,
    platform        VARCHAR(20) NOT NULL,
    platform_uid    VARCHAR(100) NOT NULL,
    nickname        VARCHAR(200),
    avatar_url      TEXT,
    profile_url     TEXT,
    follower_count  BIGINT DEFAULT 0,
    engagement_rate DECIMAL(5,4),
    avg_views       BIGINT,
    source          VARCHAR(50),
    matched_tags    JSON,
    match_score     DECIMAL(5,2),
    extra_data      JSON,
    review_status   VARCHAR(20) DEFAULT 'pending',
    reviewed_by     BIGINT,
    reviewed_at     DATETIME,
    influencer_id   BIGINT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_task_id (task_id),
    KEY idx_review_status (review_status),
    KEY idx_match_score (match_score),
    CONSTRAINT fk_collected_task FOREIGN KEY (task_id) REFERENCES collection_tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_collected_influencer FOREIGN KEY (influencer_id) REFERENCES influencers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

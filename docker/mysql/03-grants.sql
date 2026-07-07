-- meeting_ai 库授权（MySQL 官方镜像只为 MYSQL_DATABASE 建用户权限，需单独授权 meeting_ai）
-- 已有数据卷请运行 fix-mysql-grants 脚本
GRANT ALL PRIVILEGES ON meeting_ai.* TO 'app_user'@'%';
GRANT ALL PRIVILEGES ON meeting_ai.* TO 'app_user'@'localhost';
FLUSH PRIVILEGES;

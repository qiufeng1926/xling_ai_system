-- meeting_ai 库授权（MySQL 官方镜像只为 MYSQL_DATABASE 建用户权限，需单独授权 meeting_ai）
GRANT ALL PRIVILEGES ON meeting_ai.* TO 'app_user'@'%';
FLUSH PRIVILEGES;

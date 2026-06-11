"""
数据库初始化脚本
运行此脚本将自动创建数据库和表结构
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from db.models import init_database
from db.session import seed_default_users, SessionFactory
from config.config import database_url
from utils.logger import get_logger

logger = get_logger("db_init")


def init_db():
    """初始化数据库"""
    try:
        logger.info("开始初始化数据库...")
        logger.info(f"数据库连接URL: {database_url}")
        
        # 创建数据库引擎和所有表
        engine = init_database(database_url)

        session = SessionFactory()
        try:
            seed_default_users(session)
            session.commit()
        finally:
            session.close()
        
        logger.info("数据库初始化成功！")
        logger.info("已创建的表:")
        for table_name in ['users', 'meetings', 'permission_requests']:
            logger.info(f"  - {table_name}")
        
        return True
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("会议 AI 系统 - 数据库初始化")
    print("=" * 60)
    
    success = init_db()
    
    if success:
        print("\n[OK] 数据库初始化成功！")
        print("\n数据库配置信息：")
        print(f"  - 主机: localhost")
        print(f"  - 端口: 3306")
        print(f"  - 数据库名: meeting_ai")
        print(f"  - 字符集: utf8mb4")
        print("\n请确保：")
        print("  1. MySQL服务正在运行")
        print("  2. 已在.env文件中配置正确的数据库连接信息")
        print("  3. 数据库用户具有创建表的权限")
    else:
        print("\n[FAIL] 数据库初始化失败！")
        print("\n请检查：")
        print("  1. MySQL服务是否正在运行")
        print("  2. .env文件中的数据库配置是否正确")
        print("  3. 数据库用户是否有足够权限")
        print("  4. 是否已安装PyMySQL依赖（pip install PyMySQL）")
        sys.exit(1)

"""
会议 AI 系统测试脚本
用于验证各个模块是否正常工作
"""

import sys
from pathlib import Path
from utils.logger import get_logger

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

logger = get_logger("test_system")


def test_config():
    """测试配置加载"""
    logger.info("=" * 50)
    logger.info("测试 1: 配置加载")
    logger.info("=" * 50)
    
    try:
        from config.config import (
            glm_api_key, glm_model, glm_temperature,
            asr_model_name, asr_device,
            upload_dir, output_dir
        )
        
        logger.info(f"✓ GLM API Key: {'已配置' if glm_api_key else '未配置'}")
        logger.info(f"✓ GLM 模型: {glm_model}")
        logger.info(f"✓ GLM 温度: {glm_temperature}")
        logger.info(f"✓ ASR 模型: {asr_model_name}")
        logger.info(f"✓ ASR 设备: {asr_device}")
        logger.info(f"✓ 上传目录: {upload_dir}")
        logger.info(f"✓ 输出目录: {output_dir}")
        return True
    except Exception as e:
        logger.error(f"✗ 配置加载失败: {e}")
        return False


def test_logger():
    """测试日志系统"""
    logger.info("=" * 50)
    logger.info("测试 2: 日志系统")
    logger.info("=" * 50)
    
    try:
        from utils.logger import get_logger
        
        test_logger = get_logger("test")
        test_logger.info("这是一条测试日志")
        test_logger.warning("这是一条警告日志")
        
        logger.info("✓ 日志系统初始化成功")
        logger.info("✓ 日志文件应保存在 logs/ 目录下")
        return True
    except Exception as e:
        logger.error(f"✗ 日志系统失败: {e}")
        return False


def test_asr_engine():
    """测试 ASR 引擎"""
    logger.info("=" * 50)
    logger.info("测试 3: ASR 引擎")
    logger.info("=" * 50)
    
    try:
        from asr.engine import FunASREngine
        
        logger.info("正在初始化 ASR 引擎...")
        engine = FunASREngine()
        
        logger.info("✓ ASR 引擎初始化成功")
        logger.info(f"✓ 模型: paraformer-zh")
        logger.info(f"✓ 设备: cpu")
        return True
    except Exception as e:
        logger.error(f"✗ ASR 引擎失败: {e}")
        return False


def test_llm_client():
    """测试 LLM 客户端"""
    logger.info("=" * 50)
    logger.info("测试 4: LLM 客户端")
    logger.info("=" * 50)
    
    try:
        from llm.glm_chat import GLMClient
        from config.config import glm_api_key
        
        if not glm_api_key:
            logger.warning("⚠ GLM API Key 未配置，跳过测试")
            return True
        
        logger.info("正在初始化 GLM 客户端...")
        client = GLMClient()
        
        logger.info("✓ GLM 客户端初始化成功")
        logger.info(f"✓ 模型: {client.model}")
        return True
    except Exception as e:
        logger.error(f"✗ LLM 客户端失败: {e}")
        return False


def test_fastapi_app():
    """测试 FastAPI 应用"""
    logger.info("=" * 50)
    logger.info("测试 5: FastAPI 应用")
    logger.info("=" * 50)
    
    try:
        from api.main import app
        
        logger.info("✓ FastAPI 应用加载成功")
        logger.info(f"✓ 应用标题: {app.title}")
        logger.info(f"✓ 应用版本: {app.version}")
        
        # 检查路由
        routes = [route.path for route in app.routes]
        logger.info(f"✓ 已注册路由数量: {len(routes)}")
        
        return True
    except Exception as e:
        logger.error(f"✗ FastAPI 应用失败: {e}")
        return False


def main():
    """运行所有测试"""
    logger.info("\n")
    logger.info("╔" + "=" * 48 + "╗")
    logger.info("║" + " " * 10 + "会议 AI 系统 - 功能测试" + " " * 13 + "║")
    logger.info("╚" + "=" * 48 + "╝")
    
    results = []
    
    # 运行测试
    results.append(("配置加载", test_config()))
    results.append(("日志系统", test_logger()))
    results.append(("ASR 引擎", test_asr_engine()))
    results.append(("LLM 客户端", test_llm_client()))
    results.append(("FastAPI 应用", test_fastapi_app()))
    
    # 汇总结果
    logger.info("=" * 50)
    logger.info("测试结果汇总")
    logger.info("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{name:20s} {status}")
    
    logger.info(f"总计: {passed}/{total} 通过")
    
    if passed == total:
        logger.info("\n🎉 所有测试通过！系统可以正常启动。")
        logger.info("\n启动命令:")
        logger.info("  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000")
        logger.info("\n访问地址:")
        logger.info("  http://localhost:8000")
    else:
        logger.info("\n⚠️  部分测试失败，请检查上述错误信息。")


if __name__ == "__main__":
    main()

"""
数据库功能测试脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from db.session import save_meeting_to_db, get_meeting_by_file_id, get_all_meetings
from utils.logger import get_logger

logger = get_logger("db_test")


def test_save_meeting():
    """测试保存会议记录"""
    print("\n=== 测试1: 保存会议记录 ===")
    
    meeting_data = {
        'file_id': 'test-uuid-12345',
        'meeting_name': '测试会议',
        'original_filename': 'test_audio.wav',
        'meeting_type': 'batch',
        'audio_file_path': '/path/to/audio.wav',
        'transcript_file_path': '/path/to/transcript.txt',
        'summary_file_path': '/path/to/summary.md',
        'transcript': '这是测试转写文本内容',
        'summary': '这是测试会议纪要内容',
        'transcript_length': 12,
        'summary_length': 12,
        'asr_duration_ms': 1500,
        'llm_duration_ms': 3000,
        'total_duration_ms': 5000,
        'status': 'completed'
    }
    
    try:
        meeting = save_meeting_to_db(meeting_data)
        print(f"✓ 保存成功，ID: {meeting.id}")
        print(f"  file_id: {meeting.file_id}")
        print(f"  meeting_name: {meeting.meeting_name}")
        return True
    except Exception as e:
        print(f"✗ 保存失败: {str(e)}")
        return False


def test_get_meeting():
    """测试查询会议记录"""
    print("\n=== 测试2: 查询会议记录 ===")
    
    try:
        meeting = get_meeting_by_file_id('test-uuid-12345')
        if meeting:
            print(f"✓ 查询成功")
            print(f"  ID: {meeting.id}")
            print(f"  会议名称: {meeting.meeting_name}")
            print(f"  会议类型: {meeting.meeting_type}")
            print(f"  状态: {meeting.status}")
            print(f"  创建时间: {meeting.created_at}")
            return True
        else:
            print("✗ 未找到会议记录")
            return False
    except Exception as e:
        print(f"✗ 查询失败: {str(e)}")
        return False


def test_get_all_meetings():
    """测试获取所有会议记录"""
    print("\n=== 测试3: 获取所有会议记录 ===")
    
    try:
        meetings, total = get_all_meetings(limit=10)
        print(f"✓ 查询成功，共 {total} 条记录，当前页 {len(meetings)} 条")
        for i, meeting in enumerate(meetings, 1):
            print(
                f"  {i}. {meeting.get('meeting_name')} "
                f"({meeting.get('meeting_type')}) - {meeting.get('status')}"
            )
        return True
    except Exception as e:
        print(f"✗ 查询失败: {str(e)}")
        return False


def main():
    print("=" * 60)
    print("会议 AI 系统 - 数据库功能测试")
    print("=" * 60)
    
    # 执行测试
    results = []
    
    results.append(("保存会议", test_save_meeting()))
    results.append(("查询会议", test_get_meeting()))
    results.append(("获取列表", test_get_all_meetings()))
    
    # 输出测试结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！数据库功能正常。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查数据库配置和连接。")
        return 1


if __name__ == "__main__":
    sys.exit(main())

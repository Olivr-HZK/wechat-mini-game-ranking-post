"""
测试文件保存功能
"""
from pathlib import Path
import os

def test_file_save():
    """测试文件保存"""
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "data"
    
    print(f"脚本目录: {script_dir}")
    print(f"输出目录: {output_dir}")
    
    # 创建目录
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"目录是否存在: {output_dir.exists()}")
    print(f"目录权限: {os.access(output_dir, os.W_OK)}")
    
    # 测试写入文件
    test_file = output_dir / "test_file.txt"
    try:
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("测试内容\n")
        
        if test_file.exists():
            print(f"\n✓ 测试文件创建成功: {test_file}")
            print(f"  文件大小: {test_file.stat().st_size} 字节")
            print(f"  绝对路径: {test_file.resolve()}")
        else:
            print(f"\n✗ 测试文件未创建")
    except Exception as e:
        print(f"\n✗ 创建测试文件时出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_file_save()

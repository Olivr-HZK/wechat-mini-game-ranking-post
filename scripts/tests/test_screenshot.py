"""
测试游戏截图提取和上传功能
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
import sys
from pathlib import Path
from modules.gdrive_uploader import GoogleDriveUploader


def extract_screenshot(video_path: str, output_path: str = None) -> str:
    """
    从视频中提取截图
    
    Args:
        video_path: 视频文件路径
        output_path: 输出图片路径，如果为None则使用临时文件
    
    Returns:
        截图文件路径，如果失败返回None
    """
    try:
        import cv2
        from PIL import Image
        VIDEO_PROCESSING_AVAILABLE = True
    except ImportError:
        print("错误：未安装视频处理库")
        print("请运行: pip install opencv-python Pillow")
        return None
    
    if not os.path.exists(video_path):
        print(f"错误：视频文件不存在：{video_path}")
        return None
    
    print(f"正在从视频提取截图：{video_path}")
    
    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"错误：无法打开视频文件")
        return None
    
    # 获取视频信息
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0
    
    print(f"  视频信息：")
    print(f"    - 总帧数：{total_frames}")
    print(f"    - FPS：{fps:.2f}")
    print(f"    - 时长：{duration:.2f}秒")
    
    if total_frames == 0:
        print("错误：视频没有帧数据")
        cap.release()
        return None
    
    # 获取中间帧
    middle_frame = total_frames // 2
    print(f"  提取第 {middle_frame} 帧（中间帧）")
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        print("错误：无法读取视频帧")
        return None
    
    # 转换BGR到RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(frame_rgb)
    
    print(f"  原始尺寸：{pil_image.width} x {pil_image.height}")
    
    # 调整大小（限制最大尺寸为1920x1080）
    max_width, max_height = 1920, 1080
    if pil_image.width > max_width or pil_image.height > max_height:
        pil_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        print(f"  调整后尺寸：{pil_image.width} x {pil_image.height}")
    
    # 保存图片
    if not output_path:
        import tempfile
        temp_dir = tempfile.gettempdir()
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(temp_dir, f"{video_name}_screenshot.jpg")
    
    pil_image.save(output_path, format='JPEG', quality=90)
    print(f"  ✓ 截图已保存到：{output_path}")
    
    return output_path


def upload_screenshot(screenshot_path: str) -> str:
    """
    上传截图到Google Drive
    
    Args:
        screenshot_path: 截图文件路径
    
    Returns:
        截图URL，如果失败返回None
    """
    if not os.path.exists(screenshot_path):
        print(f"错误：截图文件不存在：{screenshot_path}")
        return None
    
    print(f"\n正在上传截图到Google Drive...")
    
    try:
        uploader = GoogleDriveUploader()
        result = uploader.upload_image(screenshot_path, folder_name="Game Screenshots")
        
        if result and result.get('public_url'):
            print(f"  ✓ 上传成功！")
            print(f"  截图URL：{result['public_url']}")
            print(f"  文件ID：{result.get('file_id')}")
            print(f"  Web视图链接：{result.get('web_view_link')}")
            return result['public_url']
        else:
            print(f"  ✗ 上传失败")
            return None
            
    except Exception as e:
        print(f"  ✗ 上传时出错：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_feishu_display(screenshot_url: str):
    """
    测试在飞书卡片中显示截图
    
    Args:
        screenshot_url: 截图URL
    """
    print(f"\n测试飞书卡片显示...")
    print(f"  截图URL：{screenshot_url}")
    print(f"\n  飞书Markdown格式：")
    print(f"  ![游戏截图]({screenshot_url})")
    print(f"\n  可以在飞书卡片中使用此格式显示截图")


def main():
    """主函数"""
    print("=" * 60)
    print("测试游戏截图提取和上传功能")
    print("=" * 60)
    
    # 检查参数
    if len(sys.argv) < 2:
        print("\n使用方法：")
        print("  python test_screenshot.py <视频文件路径> [输出图片路径]")
        print("\n示例：")
        print("  python test_screenshot.py data/videos/羊了个羊_7594525897388113832.mp4")
        print("  python test_screenshot.py data/videos/羊了个羊_7594525897388113832.mp4 screenshot.jpg")
        print("\n或者自动查找视频文件：")
        print("  python test_screenshot.py")
        return
    
    video_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 如果只提供了游戏名称，尝试查找视频
    if not os.path.exists(video_path):
        # 尝试在data/videos目录下查找
        videos_dir = Path("data/videos")
        if videos_dir.exists():
            video_files = list(videos_dir.glob(f"*{video_path}*.mp4"))
            if video_files:
                video_path = str(video_files[0])
                print(f"找到视频文件：{video_path}")
            else:
                print(f"错误：未找到视频文件：{video_path}")
                return
        else:
            print(f"错误：视频文件不存在：{video_path}")
            return
    
    # 步骤1：提取截图
    print("\n【步骤1】提取视频截图")
    print("-" * 60)
    screenshot_path = extract_screenshot(video_path, output_path)
    
    if not screenshot_path:
        print("✗ 截图提取失败")
        return
    
    # 步骤2：上传到Google Drive
    print("\n【步骤2】上传截图到Google Drive")
    print("-" * 60)
    screenshot_url = upload_screenshot(screenshot_path)
    
    if not screenshot_url:
        print("✗ 截图上传失败")
        print(f"  本地截图已保存到：{screenshot_path}")
        return
    
    # 步骤3：测试飞书显示
    print("\n【步骤3】测试飞书卡片显示")
    print("-" * 60)
    test_feishu_display(screenshot_url)
    
    # 清理临时文件
    if output_path is None and os.path.exists(screenshot_path):
        try:
            os.remove(screenshot_path)
            print(f"\n  已清理临时文件：{screenshot_path}")
        except:
            pass
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print(f"\n截图URL（可用于飞书日报）：")
    print(screenshot_url)


if __name__ == "__main__":
    main()

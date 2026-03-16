"""
测试通过飞书机器人发送图片
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
import sys
from pathlib import Path
from modules.feishu_sender import FeishuSender
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
    
    print(f"  视频信息：总帧数={total_frames}, FPS={fps:.2f}, 时长={duration:.2f}秒")
    
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
            return result['public_url']
        else:
            print(f"  ✗ 上传失败")
            return None
            
    except Exception as e:
        print(f"  ✗ 上传时出错：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_send_image_by_url(feishu_sender: FeishuSender, image_url: str, title: str = "游戏截图"):
    """
    测试通过URL发送图片
    
    Args:
        feishu_sender: 飞书发送器
        image_url: 图片URL
        title: 图片标题
    """
    print(f"\n【测试1】通过图片URL发送到飞书")
    print("-" * 60)
    print(f"  图片URL：{image_url}")
    print(f"  标题：{title}")
    
    success = feishu_sender.send_image(image_url, title)
    
    if success:
        print(f"  ✓ 发送成功！请查看飞书群聊")
    else:
        print(f"  ✗ 发送失败")


def test_send_image_by_file(feishu_sender: FeishuSender, image_path: str, title: str = "游戏截图"):
    """
    测试通过文件上传并发送图片（需要飞书应用凭证）
    
    Args:
        feishu_sender: 飞书发送器
        image_path: 本地图片文件路径
        title: 图片标题
    """
    print(f"\n【测试2】通过文件上传并发送到飞书（需要app_id和app_secret）")
    print("-" * 60)
    print(f"  图片路径：{image_path}")
    print(f"  标题：{title}")
    
    success = feishu_sender.send_image_by_file(image_path, title)
    
    if success:
        print(f"  ✓ 发送成功！请查看飞书群聊")
    else:
        print(f"  ✗ 发送失败（可能需要配置FEISHU_APP_ID和FEISHU_APP_SECRET）")


def main():
    """主函数"""
    print("=" * 60)
    print("测试通过飞书机器人发送图片")
    print("=" * 60)
    
    # 检查飞书配置
    try:
        import config
        if not config.FEISHU_WEBHOOK_URL:
            print("\n⚠ 警告：未配置飞书Webhook URL")
            print("  请在.env文件中配置 FEISHU_WEBHOOK_URL")
            return
    except Exception as e:
        print(f"⚠ 配置检查失败：{str(e)}")
        return
    
    # 初始化飞书发送器
    print("\n初始化飞书发送器...")
    feishu_sender = FeishuSender()
    print("  ✓ 初始化成功")
    
    # 检查参数
    if len(sys.argv) < 2:
        print("\n使用方法：")
        print("  方式1：从视频提取截图并发送")
        print("    python test_send_image.py <视频文件路径>")
        print("\n  方式2：发送本地图片文件")
        print("    python test_send_image.py <图片文件路径> --file")
        print("\n  方式3：通过图片URL发送")
        print("    python test_send_image.py <图片URL> --url")
        print("\n示例：")
        print("    python test_send_image.py data/videos/羊了个羊_7594525897388113832.mp4")
        print("    python test_send_image.py screenshot.jpg --file")
        print("    python test_send_image.py https://drive.google.com/uc?export=view&id=xxx --url")
        return
    
    input_path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 判断输入类型
    if mode == "--url":
        # 直接使用URL发送
        print(f"\n使用图片URL发送：{input_path}")
        test_send_image_by_url(feishu_sender, input_path, "游戏截图")
        
    elif mode == "--file" or (os.path.exists(input_path) and input_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))):
        # 本地图片文件
        if not os.path.exists(input_path):
            print(f"错误：图片文件不存在：{input_path}")
            return
        
        print(f"\n使用本地图片文件：{input_path}")
        
        # 测试通过文件上传（主要测试）
        test_send_image_by_file(feishu_sender, input_path, "游戏截图")
        
        # 测试通过URL发送（注释掉，主要关注测试2）
        # print("\n【步骤1】上传图片到Google Drive")
        # print("-" * 60)
        # image_url = upload_screenshot(input_path)
        # if image_url:
        #     test_send_image_by_url(feishu_sender, image_url, "游戏截图")
        
    else:
        # 视频文件，需要先提取截图
        if not os.path.exists(input_path):
            # 尝试在data/videos目录下查找
            videos_dir = Path("data/videos")
            if videos_dir.exists():
                video_files = list(videos_dir.glob(f"*{input_path}*.mp4"))
                if video_files:
                    input_path = str(video_files[0])
                    print(f"找到视频文件：{input_path}")
                else:
                    print(f"错误：未找到视频文件：{input_path}")
                    return
            else:
                print(f"错误：视频文件不存在：{input_path}")
                return
        
        print(f"\n使用视频文件：{input_path}")
        
        # 步骤1：提取截图
        print("\n【步骤1】提取视频截图")
        print("-" * 60)
        screenshot_path = extract_screenshot(input_path)
        
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
        
        # 步骤3：测试通过文件上传（主要测试）
        test_send_image_by_file(feishu_sender, screenshot_path, "游戏截图")
        
        # 步骤4：测试通过URL发送（注释掉，主要关注测试2）
        # test_send_image_by_url(feishu_sender, screenshot_url, "游戏截图")
        
        # 清理临时文件
        if os.path.exists(screenshot_path) and screenshot_path.startswith(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp")):
            try:
                os.remove(screenshot_path)
                print(f"\n  已清理临时文件：{screenshot_path}")
            except:
                pass
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()

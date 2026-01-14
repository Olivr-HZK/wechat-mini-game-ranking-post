"""
测试Google Drive上传功能
"""
import os
import sys
from modules.gdrive_uploader import GoogleDriveUploader


def test_gdrive_upload():
    """测试上传视频到Google Drive"""
    print("=" * 60)
    print("测试Google Drive上传功能")
    print("=" * 60)
    print()
    
    # 检查凭证文件（支持多种文件名）
    credentials_file = None
    if os.path.exists("credentials.json"):
        credentials_file = "credentials.json"
    elif os.path.exists("credential.json"):
        credentials_file = "credential.json"
    
    if not credentials_file:
        print("❌ 错误：未找到凭证文件")
        print()
        print("请按照以下步骤设置：")
        print("1. 访问 https://console.cloud.google.com/")
        print("2. 创建项目并启用Google Drive API")
        print("3. 创建OAuth2凭证并下载")
        print("4. 将文件重命名为 credentials.json 或 credential.json 并放在项目根目录")
        return False
    
    print(f"✓ 找到凭证文件：{credentials_file}")
    print()
    
    # 查找测试视频文件
    test_video = None
    videos_dir = "data/videos"
    
    if os.path.exists(videos_dir):
        video_files = [f for f in os.listdir(videos_dir) if f.endswith('.mp4')]
        if video_files:
            test_video = os.path.join(videos_dir, video_files[0])
            print(f"✓ 找到测试视频：{test_video}")
        else:
            print(f"⚠ 未找到视频文件（{videos_dir}目录为空）")
    else:
        print(f"⚠ 视频目录不存在：{videos_dir}")
    
    # 如果命令行提供了视频路径，使用它
    if len(sys.argv) > 1:
        test_video = sys.argv[1]
        if not os.path.exists(test_video):
            print(f"❌ 错误：指定的视频文件不存在：{test_video}")
            return False
        print(f"✓ 使用指定的视频文件：{test_video}")
    
    if not test_video:
        print()
        print("请提供视频文件路径：")
        print("  python test_gdrive_upload.py <视频文件路径>")
        print()
        print("或者将视频文件放在 data/videos/ 目录下")
        return False
    
    print()
    print("-" * 60)
    print("开始上传...")
    print("-" * 60)
    print()
    
    try:
        # 初始化上传器
        print("【步骤1】初始化Google Drive上传器...")
        uploader = GoogleDriveUploader(credentials_file=credentials_file)
        print("✓ 初始化成功")
        print()
        
        # 上传视频
        print("【步骤2】上传视频到Google Drive...")
        result = uploader.upload_video(
            video_path=test_video,
            folder_name="Game Videos"
        )
        print()
        
        if result:
            print("=" * 60)
            print("✓ 上传成功！")
            print("=" * 60)
            print()
            print("文件信息：")
            print(f"  文件ID: {result.get('file_id')}")
            print(f"  文件名: {result.get('file_name')}")
            print()
            print("访问链接：")
            print(f"  直接下载链接（用于Gemini）:")
            print(f"    {result.get('public_url')}")
            print()
            print(f"  网页查看链接:")
            print(f"    {result.get('web_view_link')}")
            print()
            print("=" * 60)
            print()
            print("✅ 测试成功！可以使用上述链接进行视频分析")
            return True
        else:
            print("❌ 上传失败")
            return False
            
    except FileNotFoundError as e:
        print(f"❌ 错误：{str(e)}")
        return False
    except ImportError as e:
        print(f"❌ 错误：未安装Google Drive API库")
        print()
        print("请运行以下命令安装：")
        print("  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        return False
    except Exception as e:
        print(f"❌ 上传时出错：{str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_link_conversion():
    """测试分享链接转换功能"""
    print("=" * 60)
    print("测试分享链接转换功能")
    print("=" * 60)
    print()
    
    # 测试链接转换
    test_links = [
        "https://drive.google.com/file/d/1ABC123xyz/view?usp=sharing",
        "https://drive.google.com/file/d/1ABC123xyz/edit",
        "https://drive.google.com/open?id=1ABC123xyz",
    ]
    
    for share_link in test_links:
        direct_link = GoogleDriveUploader.convert_share_link_to_direct(share_link)
        print(f"分享链接: {share_link}")
        if direct_link:
            print(f"直接链接: {direct_link}")
        else:
            print("转换失败")
        print()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test-link":
        test_link_conversion()
    else:
        success = test_gdrive_upload()
        sys.exit(0 if success else 1)

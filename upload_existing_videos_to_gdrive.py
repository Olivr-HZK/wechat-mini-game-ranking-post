"""
为数据库中已有的视频上传到Google Drive并更新URL
"""
from modules.database import VideoDatabase
from modules.gdrive_uploader import GoogleDriveUploader
import os


def upload_existing_videos_to_gdrive(game_name: str = None):
    """
    为数据库中已有的视频上传到Google Drive
    
    Args:
        game_name: 游戏名称，如果为None则处理所有游戏
    """
    print("=" * 60)
    print("上传已有视频到Google Drive")
    print("=" * 60)
    print()
    
    db = VideoDatabase()
    
    # 获取需要上传的视频
    if game_name:
        videos = db.get_videos_by_game(game_name)
        print(f"处理游戏：{game_name}")
    else:
        videos = db.get_all_videos()
        print(f"处理所有游戏")
    
    # 筛选出已下载但还没有gdrive_url的视频
    videos_to_upload = []
    for video in videos:
        local_path = video.get("local_path")
        gdrive_url = video.get("gdrive_url")
        downloaded = video.get("downloaded", 0)
        
        if downloaded == 1 and local_path and os.path.exists(local_path) and not gdrive_url:
            videos_to_upload.append(video)
    
    if not videos_to_upload:
        print("✓ 所有视频都已上传到Google Drive，或没有需要上传的视频")
        return
    
    print(f"找到 {len(videos_to_upload)} 个需要上传的视频\n")
    
    # 初始化Google Drive上传器
    try:
        uploader = GoogleDriveUploader()
    except Exception as e:
        print(f"❌ 初始化Google Drive上传器失败：{str(e)}")
        return
    
    # 上传视频
    success_count = 0
    for idx, video in enumerate(videos_to_upload, 1):
        game_name = video.get("game_name", "未知")
        aweme_id = video.get("aweme_id", "")
        local_path = video.get("local_path")
        
        print(f"[{idx}/{len(videos_to_upload)}] {game_name} - {aweme_id}")
        print(f"  本地路径：{local_path}")
        
        try:
            result = uploader.upload_video(local_path, folder_name="Game Videos")
            
            if result and result.get('public_url'):
                gdrive_url = result['public_url']
                gdrive_file_id = result.get('file_id')
                
                # 更新数据库
                db.update_download_status(aweme_id, local_path, gdrive_url, gdrive_file_id)
                
                print(f"  ✓ 上传成功")
                print(f"  Google Drive链接：{gdrive_url[:60]}...")
                success_count += 1
            else:
                print(f"  ✗ 上传失败")
        except Exception as e:
            print(f"  ✗ 上传时出错：{str(e)}")
        
        print()
    
    print("=" * 60)
    print(f"完成！成功上传 {success_count}/{len(videos_to_upload)} 个视频")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    
    game_name = None
    if len(sys.argv) > 1:
        game_name = sys.argv[1]
    
    upload_existing_videos_to_gdrive(game_name)

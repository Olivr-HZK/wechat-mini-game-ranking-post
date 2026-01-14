"""
Google Drive上传模块
将视频上传到Google Drive并获取公开访问链接
"""
import os
import re
from typing import Optional, Dict
import config

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    print("警告：未安装Google Drive API库，请运行: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")


class GoogleDriveUploader:
    """Google Drive上传器"""
    
    # Google Drive API权限范围
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    
    def __init__(self, credentials_file: str = None):
        """
        初始化Google Drive上传器
        
        Args:
            credentials_file: OAuth2凭证文件路径，默认为项目根目录的credentials.json
        """
        if not GOOGLE_DRIVE_AVAILABLE:
            raise ImportError("Google Drive API库未安装")
        
        # 支持多种凭证文件名
        if credentials_file:
            self.credentials_file = credentials_file
        else:
            # 优先使用credentials.json，如果没有则尝试credential.json
            if os.path.exists("credentials.json"):
                self.credentials_file = "credentials.json"
            elif os.path.exists("credential.json"):
                self.credentials_file = "credential.json"
            else:
                self.credentials_file = "credentials.json"  # 默认值
        
        self.token_file = "token.json"
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """认证并创建Drive服务"""
        creds = None
        
        # 检查是否已有保存的token
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
            except Exception as e:
                print(f"加载token时出错：{str(e)}")
        
        # 如果没有有效凭证，进行OAuth流程
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"刷新token时出错：{str(e)}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"未找到凭证文件：{self.credentials_file}\n"
                        "请按照以下步骤设置：\n"
                        "1. 访问 https://console.cloud.google.com/\n"
                        "2. 创建项目并启用Google Drive API\n"
                        "3. 创建OAuth2凭证并下载为credentials.json\n"
                        "4. 将credentials.json放在项目根目录"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            
            # 保存token供下次使用
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        # 创建Drive服务
        self.service = build('drive', 'v3', credentials=creds)
    
    def upload_video(self, video_path: str, folder_name: str = "Game Videos") -> Optional[Dict]:
        """
        上传视频到Google Drive
        
        Args:
            video_path: 本地视频文件路径
            folder_name: 上传到的文件夹名称，默认"Game Videos"
        
        Returns:
            包含file_id和public_url的字典，如果失败返回None
        """
        if not os.path.exists(video_path):
            print(f"错误：视频文件不存在：{video_path}")
            return None
        
        try:
            # 获取或创建文件夹
            folder_id = self._get_or_create_folder(folder_name)
            
            # 获取文件名
            file_name = os.path.basename(video_path)
            
            print(f"正在上传视频到Google Drive：{file_name}")
            
            # 创建文件元数据
            file_metadata = {
                'name': file_name,
                'parents': [folder_id] if folder_id else []
            }
            
            # 上传文件
            media = MediaFileUpload(
                video_path,
                mimetype='video/mp4',
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            
            file_id = file.get('id')
            print(f"  ✓ 上传成功，文件ID：{file_id}")
            
            # 设置文件为公开可访问
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            self.service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()
            
            # 生成直接访问链接
            direct_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            print(f"  ✓ 已设置为公开访问")
            print(f"  直接访问链接：{direct_url}")
            
            return {
                'file_id': file_id,
                'file_name': file.get('name'),
                'public_url': direct_url,
                'web_view_link': file.get('webViewLink')
            }
            
        except HttpError as error:
            print(f"上传到Google Drive时出错：{str(error)}")
            return None
        except Exception as e:
            print(f"上传视频时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def upload_image(self, image_path: str, folder_name: str = "Game Screenshots") -> Optional[Dict]:
        """
        上传图片到Google Drive并获取公开访问链接
        
        Args:
            image_path: 本地图片文件路径
            folder_name: 上传到的文件夹名称，默认"Game Screenshots"
        
        Returns:
            包含file_id和public_url的字典，如果失败返回None
        """
        if not os.path.exists(image_path):
            print(f"错误：图片文件不存在：{image_path}")
            return None
        
        try:
            # 获取或创建文件夹
            folder_id = self._get_or_create_folder(folder_name)
            
            # 获取文件名
            file_name = os.path.basename(image_path)
            
            print(f"正在上传图片到Google Drive：{file_name}")
            
            # 创建文件元数据
            file_metadata = {
                'name': file_name,
                'parents': [folder_id] if folder_id else []
            }
            
            # 检测MIME类型
            mime_type = 'image/jpeg'
            if image_path.lower().endswith('.png'):
                mime_type = 'image/png'
            elif image_path.lower().endswith('.gif'):
                mime_type = 'image/gif'
            
            # 上传文件
            media = MediaFileUpload(
                image_path,
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            
            file_id = file.get('id')
            print(f"  ✓ 上传成功，文件ID：{file_id}")
            
            # 设置文件为公开可访问
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            self.service.permissions().create(
                fileId=file_id,
                body=permission
            ).execute()
            
            # 生成直接访问链接（用于图片显示）
            direct_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            
            print(f"  ✓ 已设置为公开访问")
            print(f"  直接访问链接：{direct_url}")
            
            return {
                'file_id': file_id,
                'file_name': file.get('name'),
                'public_url': direct_url,
                'web_view_link': file.get('webViewLink')
            }
            
        except HttpError as error:
            print(f"上传到Google Drive时出错：{str(error)}")
            return None
        except Exception as e:
            print(f"上传图片时出错：{str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_or_create_folder(self, folder_name: str) -> Optional[str]:
        """
        获取或创建文件夹
        
        Args:
            folder_name: 文件夹名称
        
        Returns:
            文件夹ID，如果失败返回None
        """
        try:
            # 查找文件夹
            results = self.service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            items = results.get('files', [])
            
            if items:
                return items[0]['id']
            
            # 如果不存在，创建文件夹
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            print(f"  ✓ 创建文件夹：{folder_name}")
            return folder.get('id')
            
        except Exception as e:
            print(f"获取或创建文件夹时出错：{str(e)}")
            return None
    
    @staticmethod
    def convert_share_link_to_direct(share_link: str) -> Optional[str]:
        """
        将Google Drive分享链接转换为直接下载链接
        
        Args:
            share_link: Google Drive分享链接，格式如：
                https://drive.google.com/file/d/FILE_ID/view?usp=sharing
        
        Returns:
            直接下载链接，如果转换失败返回None
        """
        # 提取文件ID
        pattern = r'/file/d/([a-zA-Z0-9_-]+)'
        match = re.search(pattern, share_link)
        
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        
        return None

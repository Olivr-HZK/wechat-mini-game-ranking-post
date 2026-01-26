import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.database import VideoDatabase

db = VideoDatabase()
db.clear_gameplay_analysis("合成大西瓜")
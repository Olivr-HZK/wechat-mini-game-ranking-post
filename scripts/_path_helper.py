"""
路径辅助模块
用于scripts目录下的脚本正确导入项目根目录的模块
"""
import sys
from pathlib import Path

# 获取项目根目录（向上两级：scripts/xxx -> scripts -> 项目根目录）
_project_root = Path(__file__).parent.parent

# 将项目根目录添加到Python路径
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

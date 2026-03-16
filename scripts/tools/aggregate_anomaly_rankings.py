"""
汇总所有平台的异动数据到统一 CSV
整合：
- 引力引擎（微信/抖音小游戏）
- SensorTower（iOS/Android）

输出统一格式的 CSV：
排名,游戏名称,游戏类型,平台,来源,榜单,监控日期,发布时间,开发公司,排名变化,地区
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import csv
from datetime import datetime, timedelta
from typing import List, Dict
from pathlib import Path
import glob


def read_csv_file(csv_path: Path) -> List[Dict]:
    """
    读取 CSV 文件
    
    Args:
        csv_path: CSV 文件路径
    
    Returns:
        数据行列表
    """
    if not csv_path.exists():
        return []
    
    rows = []
    try:
        # 尝试多种编码
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
        for encoding in encodings:
            try:
                with csv_path.open("r", encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rows.append(row)
                break
            except UnicodeDecodeError:
                continue
    except Exception as e:
        print(f"  ⚠ 读取 {csv_path.name} 失败：{e}")
    
    return rows


def aggregate_all_anomalies(
    date: str = None,
    wechat_csv: Path = None,
    douyin_csv: Path = None,
    sensortower_csv: Path = None,
) -> List[Dict]:
    """
    汇总所有平台的异动数据
    
    Args:
        date: 监控日期（YYYY-MM-DD），None 表示使用今天
        wechat_csv: 微信小游戏 CSV 路径，None 表示自动查找
        douyin_csv: 抖音小游戏 CSV 路径，None 表示自动查找
        sensortower_csv: SensorTower CSV 路径，None 表示自动查找
    
    Returns:
        汇总后的数据列表
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    data_dir = Path("data") / "人气榜"
    all_data = []
    
    # 1. 读取微信小游戏异动数据
    if wechat_csv:
        wechat_path = Path(wechat_csv)
    else:
        # 自动查找最新的微信异动 CSV
        wechat_files = list(data_dir.glob("*_anomalies.csv"))
        wechat_files = [f for f in wechat_files if not f.name.startswith("dy_") and not f.name.startswith("sensortower_")]
        if wechat_files:
            wechat_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            wechat_path = wechat_files[0]
        else:
            wechat_path = None
    
    if wechat_path and wechat_path.exists():
        print(f"  读取微信小游戏：{wechat_path.name}")
        wechat_data = read_csv_file(wechat_path)
        all_data.extend(wechat_data)
        print(f"    {len(wechat_data)} 条")
    
    # 2. 读取抖音小游戏异动数据
    if douyin_csv:
        douyin_path = Path(douyin_csv)
    else:
        # 自动查找最新的抖音异动 CSV
        douyin_files = list(data_dir.glob("dy_*_anomalies.csv"))
        if douyin_files:
            douyin_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            douyin_path = douyin_files[0]
        else:
            douyin_path = None
    
    if douyin_path and douyin_path.exists():
        print(f"  读取抖音小游戏：{douyin_path.name}")
        douyin_data = read_csv_file(douyin_path)
        all_data.extend(douyin_data)
        print(f"    {len(douyin_data)} 条")
    
    # 3. 读取 SensorTower 异动数据
    if sensortower_csv:
        st_path = Path(sensortower_csv)
    else:
        # 自动查找最新的 SensorTower CSV
        st_files = list(data_dir.glob("sensortower_anomalies_*.csv"))
        if st_files:
            st_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            st_path = st_files[0]
        else:
            st_path = None
    
    if st_path and st_path.exists():
        print(f"  读取 SensorTower：{st_path.name}")
        st_data = read_csv_file(st_path)
        all_data.extend(st_data)
        print(f"    {len(st_data)} 条")
    
    return all_data


def write_aggregated_csv(data: List[Dict], output_csv: Path, monitor_date: str):
    """
    写入汇总后的 CSV
    
    Args:
        data: 数据列表
        output_csv: 输出文件路径
        monitor_date: 监控日期
    """
    fieldnames = [
        "排名",
        "游戏名称",
        "游戏类型",
        "平台",
        "来源",
        "榜单",
        "监控日期",
        "发布时间",
        "开发公司",
        "排名变化",
        "地区",
    ]
    
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    
    with output_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        
        for row in data:
            # 确保所有字段都存在
            output_row = {}
            for field in fieldnames:
                output_row[field] = row.get(field, "")
            
            # 统一监控日期
            output_row["监控日期"] = monitor_date
            
            w.writerow(output_row)


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总所有平台的异动数据")
    parser.add_argument('--date', type=str, help='监控日期（YYYY-MM-DD），默认今天')
    parser.add_argument('--wechat-csv', type=str, help='微信小游戏 CSV 路径（默认自动查找）')
    parser.add_argument('--douyin-csv', type=str, help='抖音小游戏 CSV 路径（默认自动查找）')
    parser.add_argument('--sensortower-csv', type=str, help='SensorTower CSV 路径（默认自动查找）')
    parser.add_argument('--output', type=str, help='输出文件路径（默认：data/人气榜/all_anomalies_YYYY-MM-DD.csv）')
    
    args = parser.parse_args()
    
    # 确定日期
    if args.date:
        monitor_date = args.date
    else:
        monitor_date = datetime.now().strftime("%Y-%m-%d")
    
    print("=" * 60)
    print("汇总所有平台异动数据")
    print("=" * 60)
    print(f"监控日期: {monitor_date}")
    print()
    
    # 汇总数据
    print("【步骤1】读取各平台异动数据...")
    all_data = aggregate_all_anomalies(
        date=monitor_date,
        wechat_csv=Path(args.wechat_csv) if args.wechat_csv else None,
        douyin_csv=Path(args.douyin_csv) if args.douyin_csv else None,
        sensortower_csv=Path(args.sensortower_csv) if args.sensortower_csv else None,
    )
    
    if not all_data:
        print("\n未找到任何异动数据")
        return 1
    
    print(f"\n  总计：{len(all_data)} 条异动数据")
    
    # 写入汇总 CSV
    if args.output:
        output_csv = Path(args.output)
    else:
        output_csv = Path("data") / "人气榜" / f"all_anomalies_{monitor_date}.csv"
    
    print(f"\n【步骤2】写入汇总 CSV...")
    write_aggregated_csv(all_data, output_csv, monitor_date)
    
    print(f"✅ 已写入：{output_csv.resolve()}（{len(all_data)} 条）")
    
    # 统计信息
    print(f"\n【统计信息】")
    platforms = {}
    sources = {}
    for row in all_data:
        platform = row.get("平台", "未知")
        source = row.get("来源", "未知")
        platforms[platform] = platforms.get(platform, 0) + 1
        sources[source] = sources.get(source, 0) + 1
    
    print(f"  按平台：")
    for platform, count in sorted(platforms.items()):
        print(f"    {platform}: {count} 条")
    
    print(f"  按来源：")
    for source, count in sorted(sources.items()):
        print(f"    {source}: {count} 条")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

"""
清空数据库中今日更新的记录，从第12列开始的所有列
"""
import sqlite3
import os
import config
from datetime import datetime, date

def clear_today_updates_from_column_12():
    """清空今日更新的记录，从第12列开始的所有列"""
    
    # 连接数据库
    db_dir = os.path.dirname(config.RANKINGS_CSV_PATH)
    db_path = os.path.join(db_dir, "videos.db")
    
    if not os.path.exists(db_path):
        print(f"错误：找不到数据库文件：{db_path}")
        return
    
    print(f"[*] 数据库路径：{db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有列名
    cursor.execute('PRAGMA table_info(games)')
    all_columns = [row[1] for row in cursor.fetchall()]
    
    print(f"\n[*] 数据库表结构（共 {len(all_columns)} 列）：")
    for i, col in enumerate(all_columns, 1):
        print(f"  {i}. {col}")
    
    # 第12列是索引11（从0开始）
    if len(all_columns) < 12:
        print(f"\n错误：表只有 {len(all_columns)} 列，没有第12列")
        conn.close()
        return
    
    # 从第12列开始（索引11）到倒数第2列（排除created_at和updated_at）
    columns_to_clear = all_columns[11:-2]  # 从第12列开始，排除最后两列（created_at, updated_at）
    
    print(f"\n[*] 将清空以下列（从第12列开始，共 {len(columns_to_clear)} 列）：")
    for i, col in enumerate(columns_to_clear, 12):
        print(f"  {i}. {col}")
    
    # 获取今日日期（格式：YYYY-MM-DD）
    today = date.today().strftime('%Y-%m-%d')
    print(f"\n[*] 查找今日（{today}）更新的记录...")
    
    # 先查看所有记录的updated_at，用于调试
    cursor.execute('SELECT game_name, updated_at FROM games ORDER BY updated_at DESC LIMIT 10')
    recent_records = cursor.fetchall()
    if recent_records:
        print(f"\n[*] 最近更新的10条记录：")
        for game_name, updated_at in recent_records:
            print(f"    - {game_name}: {updated_at}")
    
    # 查找今日更新的记录（使用多种方式匹配）
    # SQLite的DATE()函数可能不工作，尝试使用字符串匹配
    cursor.execute('''
        SELECT game_name, updated_at 
        FROM games 
        WHERE updated_at LIKE ? OR DATE(updated_at) = DATE(?)
    ''', (f'{today}%', today))
    
    today_records = cursor.fetchall()
    
    if not today_records:
        print(f"\n  - 没有找到今日更新的记录")
        print(f"  - 提示：可以使用 --all 参数清空所有记录")
        conn.close()
        return
    
    print(f"\n  ✓ 找到 {len(today_records)} 条今日更新的记录：")
    for game_name, updated_at in today_records:
        print(f"    - {game_name} (更新于: {updated_at})")
    
    # 确认操作
    print(f"\n[*] 准备清空这 {len(today_records)} 条记录的以下列：")
    for col in columns_to_clear:
        print(f"    - {col}")
    
    # 支持命令行参数
    import sys
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    clear_all = '--all' in sys.argv
    
    if clear_all:
        print(f"\n[*] 清空所有记录（不限制今日更新）...")
        # 获取所有记录
        cursor.execute('SELECT game_name FROM games')
        all_records = cursor.fetchall()
        today_records = all_records
        print(f"  ✓ 找到 {len(today_records)} 条记录")
        where_clause = "1=1"  # 匹配所有记录
        where_params = ()
    else:
        where_clause = "updated_at LIKE ? OR DATE(updated_at) = DATE(?)"
        where_params = (f'{today}%', today)
    
    if not auto_confirm:
        confirm = input(f"\n确认清空？(y/N): ").strip().lower()
        if confirm != 'y':
            print("  已取消操作")
            conn.close()
            return
    else:
        print(f"\n[*] 自动确认模式，直接执行清空操作...")
    
    # 构建UPDATE语句，清空所有指定列
    set_clauses = [f"{col} = NULL" for col in columns_to_clear]
    update_sql = f'''
        UPDATE games 
        SET {', '.join(set_clauses)}
        WHERE {where_clause}
    '''
    
    print(f"\n[*] 执行清空操作...")
    print(f"[*] SQL: {update_sql}")
    cursor.execute(update_sql, where_params)
    updated_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"  ✓ 已清空 {updated_count} 条记录的 {len(columns_to_clear)} 个字段")
    print(f"  ✓ 操作完成")

if __name__ == "__main__":
    try:
        clear_today_updates_from_column_12()
    except Exception as e:
        print(f"\n错误：{str(e)}")
        import traceback
        traceback.print_exc()

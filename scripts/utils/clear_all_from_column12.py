"""
直接清空数据库中所有记录，从第12列开始的所有列（不限制日期）
"""
import sqlite3
import os
import config
import sys

def clear_all_from_column_12():
    """清空所有记录，从第12列开始的所有列"""
    
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
    
    # 统计将被清空的记录数
    cursor.execute('SELECT COUNT(*) FROM games')
    total_records = cursor.fetchone()[0]
    
    print(f"\n[*] 数据库中共有 {total_records} 条记录")
    
    # 检查是否有数据需要清空
    has_data = False
    for col in columns_to_clear:
        cursor.execute(f'SELECT COUNT(*) FROM games WHERE {col} IS NOT NULL AND {col} != ""')
        count = cursor.fetchone()[0]
        if count > 0:
            has_data = True
            print(f"  - {col}: {count} 条记录有数据")
    
    if not has_data:
        print("\n  - 所有指定列已经是空的，无需清空")
        conn.close()
        return
    
    # 确认操作
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    
    if not auto_confirm:
        confirm = input(f"\n确认清空所有 {total_records} 条记录的 {len(columns_to_clear)} 个字段？(y/N): ").strip().lower()
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
    '''
    
    print(f"\n[*] 执行清空操作...")
    print(f"[*] SQL: {update_sql}")
    cursor.execute(update_sql)
    updated_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"  ✓ 已清空 {updated_count} 条记录的 {len(columns_to_clear)} 个字段")
    print(f"  ✓ 操作完成")
    
    # 验证清空结果
    print(f"\n[*] 验证清空结果...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for col in columns_to_clear[:5]:  # 只检查前5个列
        cursor.execute(f'SELECT COUNT(*) FROM games WHERE {col} IS NOT NULL AND {col} != ""')
        count = cursor.fetchone()[0]
        print(f"  - {col}: {count} 条记录仍有数据")
    conn.close()

if __name__ == "__main__":
    try:
        clear_all_from_column_12()
    except Exception as e:
        print(f"\n错误：{str(e)}")
        import traceback
        traceback.print_exc()

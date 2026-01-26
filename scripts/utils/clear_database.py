"""
数据库清理脚本
用于快速清空数据库中的某一行或某一列的内容
"""
import sqlite3
import os
import sys
import config
from typing import List, Optional

def list_games(db_path: str) -> List[str]:
    """列出所有游戏名称"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('SELECT game_name FROM games ORDER BY game_name')
    games = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return games

def list_columns(db_path: str) -> List[str]:
    """列出所有列名（不包括id, created_at, updated_at）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('PRAGMA table_info(games)')
    columns = [row[1] for row in cursor.fetchall()]
    
    # 排除系统字段
    exclude = ['id', 'created_at', 'updated_at']
    columns = [col for col in columns if col not in exclude]
    
    conn.close()
    return columns

def clear_game_row(db_path: str, game_name: str) -> bool:
    """清空某个游戏的整行数据（删除记录）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM games WHERE game_name = ?', (game_name,))
    deleted_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    if deleted_count > 0:
        print(f"  ✓ 已删除游戏 '{game_name}' 的记录")
        return True
    else:
        print(f"  ✗ 未找到游戏 '{game_name}' 的记录")
        return False

def clear_game_field(db_path: str, game_name: str, field_name: str) -> bool:
    """清空某个游戏的某个字段"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查字段是否存在
    cursor.execute('PRAGMA table_info(games)')
    columns = [row[1] for row in cursor.fetchall()]
    
    if field_name not in columns:
        print(f"  ✗ 字段 '{field_name}' 不存在")
        conn.close()
        return False
    
    # 检查游戏是否存在
    cursor.execute('SELECT game_name FROM games WHERE game_name = ?', (game_name,))
    if not cursor.fetchone():
        print(f"  ✗ 未找到游戏 '{game_name}' 的记录")
        conn.close()
        return False
    
    # 清空字段（设置为NULL）
    cursor.execute(f'UPDATE games SET {field_name} = NULL WHERE game_name = ?', (game_name,))
    updated_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    if updated_count > 0:
        print(f"  ✓ 已清空游戏 '{game_name}' 的字段 '{field_name}'")
        return True
    else:
        print(f"  ✗ 更新失败")
        return False

def clear_all_field(db_path: str, field_name: str) -> bool:
    """清空某个字段的所有值（所有游戏）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查字段是否存在
    cursor.execute('PRAGMA table_info(games)')
    columns = [row[1] for row in cursor.fetchall()]
    
    if field_name not in columns:
        print(f"  ✗ 字段 '{field_name}' 不存在")
        conn.close()
        return False
    
    # 统计将被清空的记录数
    cursor.execute(f'SELECT COUNT(*) FROM games WHERE {field_name} IS NOT NULL AND {field_name} != ""')
    count = cursor.fetchone()[0]
    
    if count == 0:
        print(f"  - 字段 '{field_name}' 已经是空的")
        conn.close()
        return False
    
    # 清空字段
    cursor.execute(f'UPDATE games SET {field_name} = NULL')
    updated_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"  ✓ 已清空 {updated_count} 条记录的字段 '{field_name}'")
    return True

def show_game_info(db_path: str, game_name: str):
    """显示某个游戏的详细信息"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM games WHERE game_name = ?', (game_name,))
    row = cursor.fetchone()
    
    conn.close()
    
    if row:
        print(f"\n游戏 '{game_name}' 的详细信息：")
        print("-" * 60)
        for key in row.keys():
            value = row[key]
            if value is None:
                value = "(空)"
            elif isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            print(f"  {key}: {value}")
        print("-" * 60)
    else:
        print(f"  ✗ 未找到游戏 '{game_name}' 的记录")

def main():
    """主函数"""
    print("=" * 60)
    print("数据库清理工具")
    print("=" * 60)
    print()
    
    # 连接数据库
    db_dir = os.path.dirname(config.RANKINGS_CSV_PATH)
    db_path = os.path.join(db_dir, "videos.db")
    
    if not os.path.exists(db_path):
        print(f"错误：找不到数据库文件：{db_path}")
        return
    
    print(f"[*] 数据库路径：{db_path}")
    
    # 检查games表是否存在
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='games'
    ''')
    if not cursor.fetchone():
        print("  ✗ 数据库中没有games表")
        conn.close()
        return
    conn.close()
    
    # 获取所有游戏和列
    games = list_games(db_path)
    columns = list_columns(db_path)
    
    print(f"\n[*] 数据库中有 {len(games)} 个游戏")
    print(f"[*] 表中有 {len(columns)} 个可编辑字段")
    
    # 主菜单
    while True:
        print("\n" + "=" * 60)
        print("请选择操作：")
        print("  1. 清空某个游戏的整行数据（删除记录）")
        print("  2. 清空某个游戏的某个字段")
        print("  3. 清空某个字段的所有值（所有游戏）")
        print("  4. 查看某个游戏的详细信息")
        print("  5. 列出所有游戏")
        print("  6. 列出所有字段")
        print("  0. 退出")
        print("=" * 60)
        
        choice = input("\n请输入选项 (0-6): ").strip()
        
        if choice == '0':
            print("\n退出程序")
            break
        
        elif choice == '1':
            # 清空某个游戏的整行
            print("\n【清空某个游戏的整行数据】")
            if games:
                print("\n可用游戏：")
                for i, game in enumerate(games, 1):
                    print(f"  {i}. {game}")
                print(f"  0. 手动输入游戏名称")
                
                game_choice = input("\n请选择游戏编号或输入游戏名称: ").strip()
                
                if game_choice.isdigit():
                    idx = int(game_choice) - 1
                    if 0 <= idx < len(games):
                        game_name = games[idx]
                    elif idx == -1:
                        game_name = input("请输入游戏名称: ").strip()
                    else:
                        print("  ✗ 无效的编号")
                        continue
                else:
                    game_name = game_choice
                
                if game_name:
                    confirm = input(f"  确认删除游戏 '{game_name}' 的所有数据？(y/N): ").strip().lower()
                    if confirm == 'y':
                        clear_game_row(db_path, game_name)
                    else:
                        print("  已取消")
            else:
                print("  数据库中没有游戏")
        
        elif choice == '2':
            # 清空某个游戏的某个字段
            print("\n【清空某个游戏的某个字段】")
            if games:
                print("\n可用游戏：")
                for i, game in enumerate(games, 1):
                    print(f"  {i}. {game}")
                print(f"  0. 手动输入游戏名称")
                
                game_choice = input("\n请选择游戏编号或输入游戏名称: ").strip()
                
                if game_choice.isdigit():
                    idx = int(game_choice) - 1
                    if 0 <= idx < len(games):
                        game_name = games[idx]
                    elif idx == -1:
                        game_name = input("请输入游戏名称: ").strip()
                    else:
                        print("  ✗ 无效的编号")
                        continue
                else:
                    game_name = game_choice
                
                if game_name:
                    print("\n可用字段：")
                    for i, col in enumerate(columns, 1):
                        print(f"  {i}. {col}")
                    
                    field_choice = input("\n请选择字段编号或输入字段名称: ").strip()
                    
                    if field_choice.isdigit():
                        idx = int(field_choice) - 1
                        if 0 <= idx < len(columns):
                            field_name = columns[idx]
                        else:
                            print("  ✗ 无效的编号")
                            continue
                    else:
                        field_name = field_choice
                    
                    if field_name:
                        confirm = input(f"  确认清空游戏 '{game_name}' 的字段 '{field_name}'？(y/N): ").strip().lower()
                        if confirm == 'y':
                            clear_game_field(db_path, game_name, field_name)
                        else:
                            print("  已取消")
            else:
                print("  数据库中没有游戏")
        
        elif choice == '3':
            # 清空某个字段的所有值
            print("\n【清空某个字段的所有值（所有游戏）】")
            print("\n可用字段：")
            for i, col in enumerate(columns, 1):
                print(f"  {i}. {col}")
            
            field_choice = input("\n请选择字段编号或输入字段名称: ").strip()
            
            if field_choice.isdigit():
                idx = int(field_choice) - 1
                if 0 <= idx < len(columns):
                    field_name = columns[idx]
                else:
                    print("  ✗ 无效的编号")
                    continue
            else:
                field_name = field_choice
            
            if field_name:
                confirm = input(f"  确认清空所有游戏的字段 '{field_name}'？(y/N): ").strip().lower()
                if confirm == 'y':
                    clear_all_field(db_path, field_name)
                else:
                    print("  已取消")
        
        elif choice == '4':
            # 查看某个游戏的详细信息
            print("\n【查看某个游戏的详细信息】")
            if games:
                print("\n可用游戏：")
                for i, game in enumerate(games, 1):
                    print(f"  {i}. {game}")
                print(f"  0. 手动输入游戏名称")
                
                game_choice = input("\n请选择游戏编号或输入游戏名称: ").strip()
                
                if game_choice.isdigit():
                    idx = int(game_choice) - 1
                    if 0 <= idx < len(games):
                        game_name = games[idx]
                    elif idx == -1:
                        game_name = input("请输入游戏名称: ").strip()
                    else:
                        print("  ✗ 无效的编号")
                        continue
                else:
                    game_name = game_choice
                
                if game_name:
                    show_game_info(db_path, game_name)
            else:
                print("  数据库中没有游戏")
        
        elif choice == '5':
            # 列出所有游戏
            print("\n【所有游戏列表】")
            if games:
                for i, game in enumerate(games, 1):
                    print(f"  {i}. {game}")
            else:
                print("  数据库中没有游戏")
        
        elif choice == '6':
            # 列出所有字段
            print("\n【所有字段列表】")
            for i, col in enumerate(columns, 1):
                print(f"  {i}. {col}")
        
        else:
            print("  ✗ 无效的选项，请重新选择")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误：{str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

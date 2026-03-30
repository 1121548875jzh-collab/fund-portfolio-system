#!/usr/bin/env python3
"""
四层记忆管理系统 - L1-L4层级 + 向量库同步

L1 索引层: MEMORY.md（核心索引，<50行）
L2 项目层: memory/active-projects/*.md（项目进展）
L3 经验层: memory/tacit-knowledge/*.md（经验教训）
L4 日志层: memory/YYYY-MM-DD.md（每日记录）

写入任何层级时，自动同步到向量库
"""
import os
import sys
import json
import sqlite3
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 自动识别workspace：根据脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)  # scripts的父目录就是workspace

# 如果是贾维斯的workspace，保持原名
if WORKSPACE == "/root/.openclaw/workspace":
    WORKSPACE = "/root/.openclaw/workspace"
# 其他workspace使用各自的路径

VECTOR_DB = "/root/.openclaw/memory/vector_memory.db"  # 共享向量库
CONFIG_FILE = "/root/.openclaw/openclaw.json"

# 四层目录（基于各自workspace）
L1_FILE = os.path.join(WORKSPACE, "MEMORY.md")
L2_DIR = os.path.join(WORKSPACE, "memory", "active-projects")
L3_DIR = os.path.join(WORKSPACE, "memory", "tacit-knowledge")
L4_DIR = os.path.join(WORKSPACE, "memory")


def get_embedding_api():
    """获取嵌入API配置"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        defaults = config.get('agents', {}).get('defaults', {})
        memory_search = defaults.get('memorySearch', {})
        if not memory_search.get('enabled'):
            return None
        remote = memory_search.get('remote', {})
        return {
            'baseUrl': remote.get('baseUrl'),
            'apiKey': remote.get('apiKey'),
            'model': memory_search.get('model', 'BAAI/bge-m3')
        }
    except:
        return None


def get_embedding(text, api_config):
    """调用API获取嵌入向量"""
    if not api_config or not text:
        return None
    
    try:
        url = f"{api_config['baseUrl']}/embeddings"
        headers = {
            'Authorization': f"Bearer {api_config['apiKey']}",
            'Content-Type': 'application/json'
        }
        data = {'model': api_config['model'], 'input': text}
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json().get('data', [{}])[0].get('embedding')
    except Exception as e:
        print(f"嵌入失败: {e}")
    return None


def write_to_vector(content, layer, metadata=None):
    """写入向量库"""
    if not content:
        return False
    
    try:
        conn = sqlite3.connect(VECTOR_DB)
        cursor = conn.cursor()
        
        # 检查是否已存在类似内容
        cursor.execute("SELECT id FROM memories WHERE content = ?", (content,))
        if cursor.fetchone():
            conn.close()
            return True  # 已存在，跳过
        
        # 插入记忆
        created_at = datetime.now().isoformat()
        meta = json.dumps(metadata or {"layer": layer, "source": "memory_manager"})
        cursor.execute(
            "INSERT INTO memories (content, created_at, metadata) VALUES (?, ?, ?)",
            (content, created_at, meta)
        )
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 获取嵌入并更新
        api_config = get_embedding_api()
        embedding = get_embedding(content, api_config)
        if embedding:
            conn = sqlite3.connect(VECTOR_DB)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE memories SET embedding = ? WHERE id = ?",
                (json.dumps(embedding), memory_id)
            )
            conn.commit()
            conn.close()
            print(f"✅ [L{layer}] 已写入向量库 (ID: {memory_id})")
        else:
            print(f"⚠️ [L{layer}] 写入成功但嵌入失败 (ID: {memory_id})")
        
        return True
    except Exception as e:
        print(f"❌ 写入向量库失败: {e}")
        return False


def write_l1(content, section=None):
    """写入L1索引层（MEMORY.md）"""
    # L1保持简洁，只更新关键信息，不全文写入向量库
    # 但新增的重要条目会写入向量库
    
    # 更新MEMORY.md
    try:
        with open(L1_FILE, 'r') as f:
            existing = f.read()
        
        # 找到对应section更新
        if section:
            lines = existing.split('\n')
            new_lines = []
            in_section = False
            section_header = f"## {section}"
            
            for line in lines:
                if line.startswith(section_header):
                    in_section = True
                    new_lines.append(line)
                    new_lines.append(content)
                    continue
                if in_section and line.startswith('## '):
                    in_section = False
                if not in_section:
                    new_lines.append(line)
            
            updated = '\n'.join(new_lines)
        else:
            updated = existing + '\n\n' + content
        
        # 限制L1大小（<50行核心内容）
        if len(updated.split('\n')) > 100:
            print("⚠️ L1内容过长，建议转移到L2/L3")
        
        with open(L1_FILE, 'w') as f:
            f.write(updated)
        
        # 写入向量库（只写新增内容）
        write_to_vector(content, "L1", {"section": section})
        return True
    except Exception as e:
        print(f"❌ 写入L1失败: {e}")
        return False


def write_l2(project_name, content):
    """写入L2项目层"""
    os.makedirs(L2_DIR, exist_ok=True)
    project_file = os.path.join(L2_DIR, f"{project_name}.md")
    
    try:
        # 读取现有内容
        existing = ""
        if os.path.exists(project_file):
            with open(project_file, 'r') as f:
                existing = f.read()
        
        # 添加新内容
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_content = f"\n### [{timestamp}]\n{content}\n"
        
        with open(project_file, 'w') as f:
            f.write(existing + new_content)
        
        # 写入向量库
        write_to_vector(f"[{project_name}] {content}", "L2", {"project": project_name})
        return True
    except Exception as e:
        print(f"❌ 写入L2失败: {e}")
        return False


def write_l3(category, content):
    """写入L3经验层"""
    os.makedirs(L3_DIR, exist_ok=True)
    lesson_file = os.path.join(L3_DIR, "lessons-learned.md")
    
    try:
        with open(lesson_file, 'r') as f:
            existing = f.read()
        
        # 添加到对应分类
        timestamp = datetime.now().strftime("%Y-%m-%d")
        new_entry = f"\n- **[{timestamp}]** {content}\n"
        
        # 找到分类位置插入
        lines = existing.split('\n')
        new_lines = []
        in_category = False
        cat_header = f"## {category}"
        
        for line in lines:
            if line.startswith(cat_header):
                in_category = True
                new_lines.append(line)
                new_lines.append(new_entry)
                continue
            if in_category and line.startswith('## '):
                in_category = False
            if not in_category:
                new_lines.append(line)
        
        # 如果分类不存在，创建新分类
        if cat_header not in existing:
            new_lines.append(f"\n## {category}\n{new_entry}")
        
        with open(lesson_file, 'w') as f:
            f.write('\n'.join(new_lines))
        
        # 写入向量库
        write_to_vector(f"[经验-{category}] {content}", "L3", {"category": category})
        return True
    except Exception as e:
        print(f"❌ 写入L3失败: {e}")
        return False


def write_l4(content):
    """写入L4日志层"""
    os.makedirs(L4_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(L4_DIR, f"{today}.md")
    
    try:
        existing = ""
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                existing = f.read()
        
        # 添加新条目
        time_str = datetime.now().strftime("%H:%M")
        new_entry = f"\n## [{time_str}]\n{content}\n"
        
        with open(log_file, 'w') as f:
            f.write(existing + new_entry)
        
        # 写入向量库（L4内容可能很多，只写摘要）
        summary = content[:200] if len(content) > 200 else content
        write_to_vector(f"[日志-{today}] {summary}", "L4", {"date": today})
        return True
    except Exception as e:
        print(f"❌ 写入L4失败: {e}")
        return False


def read_layer(layer, name=None):
    """读取指定层级内容"""
    if layer == "L1":
        with open(L1_FILE, 'r') as f:
            return f.read()
    elif layer == "L2":
        if name:
            project_file = os.path.join(L2_DIR, f"{name}.md")
            if os.path.exists(project_file):
                with open(project_file, 'r') as f:
                    return f.read()
        else:
            # 返回所有项目
            projects = {}
            for f in Path(L2_DIR).glob("*.md"):
                with open(f, 'r') as fp:
                    projects[f.stem] = fp.read()
            return projects
    elif layer == "L3":
        lesson_file = os.path.join(L3_DIR, "lessons-learned.md")
        if os.path.exists(lesson_file):
            with open(lesson_file, 'r') as f:
                return f.read()
    elif layer == "L4":
        if name:  # name 是日期
            log_file = os.path.join(L4_DIR, f"{name}.md")
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    return f.read()
        else:
            # 返回最近7天日志
            logs = {}
            for i in range(7):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                log_file = os.path.join(L4_DIR, f"{date}.md")
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        logs[date] = f.read()
            return logs
    return None


def search_vectors(query, limit=5):
    """向量检索"""
    api_config = get_embedding_api()
    if not api_config:
        print("向量检索未配置")
        return []
    
    query_embedding = get_embedding(query, api_config)
    if not query_embedding or not isinstance(query_embedding, list):
        print(f"查询嵌入获取失败或格式错误: {type(query_embedding)}")
        return []
    
    try:
        conn = sqlite3.connect(VECTOR_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, embedding, metadata FROM memories WHERE embedding IS NOT NULL LIMIT 100")
        memories = cursor.fetchall()
        conn.close()
        
        # 简单相似度计算（cosine）
        results = []
        for id, content, emb_json, meta_json in memories:
            try:
                emb = json.loads(emb_json)
                if not isinstance(emb, list):
                    continue
                
                # cosine similarity
                dot = sum(a * b for a, b in zip(query_embedding, emb))
                norm_q = sum(a ** 2 for a in query_embedding) ** 0.5
                norm_e = sum(b ** 2 for b in emb) ** 0.5
                similarity = dot / (norm_q * norm_e) if norm_q and norm_e else 0
                
                results.append({
                    "id": id,
                    "content": content,
                    "similarity": similarity,
                    "metadata": json.loads(meta_json) if meta_json else {}
                })
            except Exception as e:
                continue
        
        # 排序返回top结果
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]
    except Exception as e:
        print(f"检索失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def status():
    """显示记忆系统状态"""
    try:
        conn = sqlite3.connect(VECTOR_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL")
        embedded = cursor.fetchone()[0]
        conn.close()
        
        coverage = embedded * 100 // total if total else 0
        
        print(f"📊 四层记忆系统状态")
        print(f"━━━━━━━━━━━━━━━━━━━━")
        print(f"L1 索引: {L1_FILE}")
        print(f"L2 项目: {L2_DIR} ({len(list(Path(L2_DIR).glob('*.md'))) if os.path.exists(L2_DIR) else 0} 个)")
        print(f"L3 经验: {L3_DIR}")
        print(f"L4 日志: {L4_DIR} ({len(list(Path(L4_DIR).glob('*.md'))) if os.path.exists(L4_DIR) else 0} 天)")
        print(f"━━━━━━━━━━━━━━━━━━━━")
        print(f"向量库: {total} 条 ({embedded} 有嵌入, {coverage}% 覆盖)")
    except Exception as e:
        print(f"状态检查失败: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="四层记忆管理系统")
    parser.add_argument("action", choices=["write", "read", "search", "status"])
    parser.add_argument("--layer", choices=["L1", "L2", "L3", "L4"])
    parser.add_argument("--content", help="写入内容")
    parser.add_argument("--section", help="L1的section名称")
    parser.add_argument("--project", help="L2的项目名称")
    parser.add_argument("--category", help="L3的分类名称")
    parser.add_argument("--name", help="L4的日期或L2的项目名")
    parser.add_argument("--query", help="搜索查询")
    parser.add_argument("--limit", type=int, default=5, help="搜索结果数量")
    
    args = parser.parse_args()
    
    if args.action == "status":
        status()
    elif args.action == "write":
        if not args.layer or not args.content:
            print("需要 --layer 和 --content")
            sys.exit(1)
        
        if args.layer == "L1":
            write_l1(args.content, args.section)
        elif args.layer == "L2":
            write_l2(args.project or "default", args.content)
        elif args.layer == "L3":
            write_l3(args.category or "通用", args.content)
        elif args.layer == "L4":
            write_l4(args.content)
    elif args.action == "read":
        if not args.layer:
            print("需要 --layer")
            sys.exit(1)
        result = read_layer(args.layer, args.name)
        if isinstance(result, dict):
            for k, v in result.items():
                print(f"━━━ {k} ━━━")
                print(v[:500])
        else:
            print(result)
    elif args.action == "search":
        if not args.query:
            print("需要 --query")
            sys.exit(1)
        results = search_vectors(args.query, args.limit)
        for i, r in enumerate(results, 1):
            print(f"{i}. [相似度: {r['similarity']:.2f}] {r['content'][:100]}")
#!/usr/bin/env python3
"""
记忆同步Hook - 监听四层文件变化，自动同步向量库

在文件写入后触发：
- 检测 MEMORY.md 变化 → 同步关键更新到向量库
- 检测 active-projects/*.md 变化 → 同步项目进展
- 检测 lessons-learned.md 变化 → 同步新经验
- 检测 YYYY-MM-DD.md 变化 → 同步当日摘要

使用方式：
1. 作为 hook 集成到 OpenClaw
2. 作为独立服务运行（监听文件变化）
"""
import os
import sys
import json
import time
import sqlite3
import requests
from datetime import datetime, timedelta
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 自动识别workspace：根据脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)  # scripts的父目录就是workspace

VECTOR_DB = "/root/.openclaw/memory/vector_memory.db"  # 共享向量库
CONFIG_FILE = "/root/.openclaw/openclaw.json"

# 四层路径（基于各自workspace）
L1_FILE = os.path.join(WORKSPACE, "MEMORY.md")
L2_DIR = os.path.join(WORKSPACE, "memory", "active-projects")
L3_FILE = os.path.join(WORKSPACE, "memory", "tacit-knowledge", "lessons-learned.md")
L4_DIR = os.path.join(WORKSPACE, "memory")


class MemorySyncHandler(FileSystemEventHandler):
    """文件变化处理"""
    
    def __init__(self):
        self.last_sync = {}  # 记录最后同步时间，避免重复
    
    def get_embedding_api(self):
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
    
    def get_embedding(self, text):
        """获取嵌入向量"""
        api = self.get_embedding_api()
        if not api or not text:
            return None
        
        try:
            url = f"{api['baseUrl']}/embeddings"
            headers = {
                'Authorization': f"Bearer {api['apiKey']}",
                'Content-Type': 'application/json'
            }
            resp = requests.post(url, headers=headers, json={'model': api['model'], 'input': text}, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('data', [{}])[0].get('embedding')
        except Exception as e:
            print(f"[{datetime.now()}] 嵌入失败: {e}")
        return None
    
    def sync_to_vector(self, content, layer, metadata=None):
        """同步到向量库"""
        if not content or len(content) < 20:
            return
        
        # 检查是否最近已同步（避免重复）
        content_key = content[:50]
        if content_key in self.last_sync:
            if time.time() - self.last_sync[content_key] < 60:  # 60秒内跳过
                return
        
        try:
            conn = sqlite3.connect(VECTOR_DB)
            cursor = conn.cursor()
            
            # 检查是否已存在
            cursor.execute("SELECT id FROM memories WHERE content = ?", (content,))
            if cursor.fetchone():
                conn.close()
                return
            
            # 插入
            created_at = datetime.now().isoformat()
            meta = json.dumps(metadata or {"layer": layer, "source": "memory_sync_hook"})
            cursor.execute("INSERT INTO memories (content, created_at, metadata) VALUES (?, ?, ?)", (content, created_at, meta))
            memory_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # 嵌入
            embedding = self.get_embedding(content)
            if embedding:
                conn = sqlite3.connect(VECTOR_DB)
                cursor = conn.cursor()
                cursor.execute("UPDATE memories SET embedding = ? WHERE id = ?", (json.dumps(embedding), memory_id))
                conn.commit()
                conn.close()
            
            self.last_sync[content_key] = time.time()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ [{layer}] 同步成功 (ID: {memory_id})")
        
        except Exception as e:
            print(f"[{datetime.now()}] ❌ 同步失败: {e}")
    
    def on_modified(self, event):
        """文件修改事件"""
        path = event.src_path
        
        # L1: MEMORY.md
        if path == L1_FILE:
            self.sync_l1()
        
        # L2: active-projects/*.md
        elif path.startswith(L2_DIR) and path.endswith('.md'):
            self.sync_l2(path)
        
        # L3: lessons-learned.md
        elif path == L3_FILE:
            self.sync_l3()
        
        # L4: YYYY-MM-DD.md
        elif path.startswith(L4_DIR) and path.endswith('.md') and not path.startswith(L2_DIR):
            filename = os.path.basename(path)
            if filename.count('-') == 2 and len(filename) == 13:  # YYYY-MM-DD.md
                self.sync_l4(path)
    
    def sync_l1(self):
        """同步L1索引层"""
        try:
            with open(L1_FILE, 'r') as f:
                content = f.read()
            
            # L1只同步关键条目（标题和重要内容）
            lines = content.split('\n')
            for line in lines:
                if line.startswith('## ') or line.startswith('- **'):
                    self.sync_to_vector(line.strip(), "L1", {"file": "MEMORY.md"})
        except:
            pass
    
    def sync_l2(self, path):
        """同步L2项目层"""
        try:
            project_name = os.path.basename(path).replace('.md', '')
            with open(path, 'r') as f:
                content = f.read()
            
            # 同步最近更新（最后50行）
            lines = content.split('\n')
            recent = lines[-50:] if len(lines) > 50 else lines
            
            for line in recent:
                if line.strip() and not line.startswith('#'):
                    self.sync_to_vector(f"[{project_name}] {line.strip()}", "L2", {"project": project_name})
        except:
            pass
    
    def sync_l3(self):
        """同步L3经验层"""
        try:
            with open(L3_FILE, 'r') as f:
                content = f.read()
            
            # 同步经验条目
            lines = content.split('\n')
            for line in lines:
                if line.strip().startswith('-'):
                    self.sync_to_vector(line.strip(), "L3", {"file": "lessons-learned.md"})
        except:
            pass
    
    def sync_l4(self, path):
        """同步L4日志层"""
        try:
            date = os.path.basename(path).replace('.md', '')
            with open(path, 'r') as f:
                content = f.read()
            
            # 同步摘要（每段的标题）
            lines = content.split('\n')
            for line in lines:
                if line.startswith('## ') or line.startswith('### '):
                    self.sync_to_vector(f"[日志-{date}] {line.strip()}", "L4", {"date": date})
        except:
            pass


def run_daemon():
    """运行监听守护进程"""
    handler = MemorySyncHandler()
    observer = Observer()
    
    # 监听四层目录
    observer.schedule(handler, WORKSPACE, recursive=False)  # L1
    observer.schedule(handler, L2_DIR, recursive=False)  # L2
    observer.schedule(handler, os.path.dirname(L3_FILE), recursive=False)  # L3
    observer.schedule(handler, L4_DIR, recursive=False)  # L4
    
    observer.start()
    print(f"[{datetime.now()}] 🧠 四层记忆同步守护进程启动")
    print(f"  L1: {L1_FILE}")
    print(f"  L2: {L2_DIR}")
    print(f"  L3: {L3_FILE}")
    print(f"  L4: {L4_DIR}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def sync_all():
    """一次性同步所有四层内容"""
    handler = MemorySyncHandler()
    
    print(f"[{datetime.now()}] 🔄 开始全量同步...")
    
    # L1
    if os.path.exists(L1_FILE):
        handler.sync_l1()
    
    # L2
    if os.path.exists(L2_DIR):
        for f in Path(L2_DIR).glob("*.md"):
            handler.sync_l2(str(f))
    
    # L3
    if os.path.exists(L3_FILE):
        handler.sync_l3()
    
    # L4 (最近7天)
    if os.path.exists(L4_DIR):
        for i in range(7):
            date = datetime.now().strftime("%Y-%m-%d") if i == 0 else (datetime.now() - __import__('datetime').timedelta(days=i)).strftime("%Y-%m-%d")
            path = os.path.join(L4_DIR, f"{date}.md")
            if os.path.exists(path):
                handler.sync_l4(path)
    
    # 显示状态
    conn = sqlite3.connect(VECTOR_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM memories")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL")
    embedded = cursor.fetchone()[0]
    conn.close()
    
    print(f"[{datetime.now()}] ✅ 同步完成: {total} 条记忆, {embedded} 有向量 ({embedded*100//total}% 覆盖)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="四层记忆同步Hook")
    parser.add_argument("--daemon", action="store_true", help="运行守护进程")
    parser.add_argument("--sync-all", action="store_true", help="全量同步")
    parser.add_argument("--status", action="store_true", help="显示状态")
    
    args = parser.parse_args()
    
    if args.daemon:
        run_daemon()
    elif args.sync_all:
        sync_all()
    elif args.status:
        conn = sqlite3.connect(VECTOR_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM memories")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL")
        embedded = cursor.fetchone()[0]
        conn.close()
        print(f"向量库: {total} 条, {embedded} 有向量 ({embedded*100//total}% 覆盖)")
    else:
        print("使用 --daemon 运行守护进程, --sync-all 全量同步, --status 查看状态")
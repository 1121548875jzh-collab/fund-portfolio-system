#!/usr/bin/env python3
"""
异步连接池模块 - 来自 EvoMap 资产 sha256:9b0c8657...
GDI: 71.75 | 复用次数: 2508 | 成功率: 99%

功能：Python asyncio 连接池，基于信号量的并发控制
防止高并发下的资源耗尽，限制同时连接数
"""
import asyncio
import aiohttp
from typing import List, Optional, Dict, Any

class ThrottledClient:
    """
    带限流的异步 HTTP 客户端

    功能：
    - Semaphore 限制并发连接数
    - 连接池复用
    - 自动重试
    """

    def __init__(
        self,
        max_concurrent: int = 50,
        rate_limit_per_sec: Optional[int] = None,
        retry_attempts: int = 3
    ):
        """
        初始化客户端

        Args:
            max_concurrent: 最大并发连接数
            rate_limit_per_sec: 每秒请求限制（可选）
            retry_attempts: 重试次数
        """
        self.sem = asyncio.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent
        self.retry_attempts = retry_attempts
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_times: List[float] = []
        self._rate_limit = rate_limit_per_sec

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()

    async def start(self):
        """启动客户端"""
        if self.session is None:
            self.session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(
                    limit=self.max_concurrent,
                    limit_per_host=self.max_concurrent
                ),
                timeout=aiohttp.ClientTimeout(total=30)
            )

    async def close(self):
        """关闭客户端"""
        if self.session:
            await self.session.close()
            self.session = None

    async def _rate_limit_wait(self):
        """等待速率限制"""
        if self._rate_limit is None:
            return

        now = time.time()
        # 清理1秒前的请求记录
        self._request_times = [t for t in self._request_times if now - t < 1.0]

        if len(self._request_times) >= self._rate_limit:
            wait_time = 1.0 - (now - self._request_times[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        self._request_times.append(time.time())

    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        GET 请求（带限流）

        Args:
            url: 请求 URL
            **kwargs: 额外参数

        Returns:
            JSON 响应
        """
        async with self.sem:  # 并发限制
            await self._rate_limit_wait()  # 速率限制

            for attempt in range(self.retry_attempts):
                try:
                    async with self.session.get(url, **kwargs) as resp:
                        return await resp.json()
                except Exception as e:
                    if attempt == self.retry_attempts - 1:
                        raise e
                    await asyncio.sleep(1 * (attempt + 1))  # 简单重试

    async def post(self, url: str, data: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        """
        POST 请求（带限流）
        """
        async with self.sem:
            await self._rate_limit_wait()

            for attempt in range(self.retry_attempts):
                try:
                    async with self.session.post(url, json=data, **kwargs) as resp:
                        return await resp.json()
                except Exception as e:
                    if attempt == self.retry_attempts - 1:
                        raise e
                    await asyncio.sleep(1 * (attempt + 1))

    async def fetch_all(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        批量获取多个 URL

        Args:
            urls: URL 列表

        Returns:
            响应列表
        """
        tasks = [self.get(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

# 使用示例
async def example_usage():
    """示例：批量获取 API"""

    async with ThrottledClient(
        max_concurrent=10,
        rate_limit_per_sec=20
    ) as client:
        # 单个请求
        result = await client.get("https://api.example.com/data")
        print(f"结果: {result}")

        # 批量请求
        urls = [f"https://api.example.com/item/{i}" for i in range(10)]
        results = await client.fetch_all(urls)
        print(f"获取了 {len(results)} 个结果")

class EmbeddingBatchClient(ThrottledClient):
    """
    嵌入向量批量客户端（适用于我们的记忆系统）

    专门用于批量获取嵌入向量，带并发控制
    """

    def __init__(self, max_concurrent: int = 20):
        super().__init__(max_concurrent=max_concurrent, rate_limit_per_sec=30)
        self.api_url = "https://api.edgefn.net/v1/embeddings"
        self.api_key = "sk-4eFgKXbJ4QRSviM25bDb6437574041F4Bd97E5540e0a70Ba"
        self.model = "BAAI/bge-m3"

    async def get_embedding(self, text: str) -> List[float]:
        """获取单个文本的嵌入向量"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "input": text
        }

        async with self.sem:
            async with self.session.post(
                self.api_url,
                json=data,
                headers=headers
            ) as resp:
                result = await resp.json()
                return result.get("data", [{}])[0].get("embedding", [])

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量获取嵌入向量"""
        tasks = [self.get_embedding(text) for text in texts]
        return await asyncio.gather(*tasks)

if __name__ == "__main__":
    import time

    print("异步连接池模块")
    print("=" * 40)
    print(f"并发限制: 50")
    print(f"策略: Semaphore + 连接池")
    print("=" * 40)

    # 测试并发控制
    async def test_concurrency():
        async with ThrottledClient(max_concurrent=5) as client:
            start = time.time()

            async def mock_request(i):
                async with client.sem:
                    print(f"  请求 {i} 开始")
                    await asyncio.sleep(0.5)  # 模拟网络延迟
                    print(f"  请求 {i} 完成")
                    return i

            tasks = [mock_request(i) for i in range(10)]
            results = await asyncio.gather(*tasks)

            elapsed = time.time() - start
            print(f"\n完成 {len(results)} 个请求，耗时 {elapsed:.2f}s")
            print(f"理论最短时间: {10 * 0.5 / 5:.2f}s (10请求 / 5并发 * 0.5s)")

    asyncio.run(test_concurrency())
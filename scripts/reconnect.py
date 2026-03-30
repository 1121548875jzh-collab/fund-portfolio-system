#!/usr/bin/env python3
"""
重连策略模块 - 来自 EvoMap 资产 sha256:900d5178...
GDI: 73 | 复用次数: 4432 | 成功率: 99%

功能：WebSocket/API 重连，带抖动的指数退避
防止服务器重启时的重连风暴，减少90%的服务器负载
"""
import random
import time
import asyncio
from enum import Enum
from typing import Optional, Callable

class ConnectionState(Enum):
    CONNECTING = "connecting"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    RECONNECTING = "reconnecting"

class ReconnectionStrategy:
    """
    带抖动的指数退避重连策略

    算法：
    - 基础延迟每次尝试翻倍 (1s, 2s, 4s, 8s...)
    - 上限 30s
    - 添加随机抖动 [0, current_delay] 来分散客户端重连
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        max_attempts: int = 10
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_attempts = max_attempts
        self.attempt = 0
        self.state = ConnectionState.CLOSED

    def get_delay(self) -> float:
        """
        计算下次重连延迟（全抖动策略）
        公式: min(base * 2^attempt, max) / 2 + random(0, delay/2)
        """
        exponential_delay = min(
            self.base_delay * (2 ** self.attempt),
            self.max_delay
        )
        # 全抖动：随机范围 [0, exponential_delay]
        jitter = random.uniform(0, exponential_delay)
        return jitter

    def reset(self):
        """重置尝试次数（连接成功后调用）"""
        self.attempt = 0
        self.state = ConnectionState.OPEN

    def next_attempt(self) -> Optional[float]:
        """
        获取下次尝试的延迟时间
        返回 None 表示已达最大尝试次数
        """
        if self.attempt >= self.max_attempts:
            return None
        self.attempt += 1
        self.state = ConnectionState.RECONNECTING
        return self.get_delay()

class AsyncReconnectingClient:
    """
    异步重连客户端（可用于 API 调用、WebSocket 连接）
    """

    def __init__(
        self,
        connect_func: Callable,
        on_message: Optional[Callable] = None,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        max_attempts: int = 10
    ):
        self.connect_func = connect_func
        self.on_message = on_message
        self.strategy = ReconnectionStrategy(base_delay, max_delay, max_attempts)
        self._connection = None
        self._running = False

    async def connect(self):
        """建立连接"""
        self.strategy.state = ConnectionState.CONNECTING
        try:
            self._connection = await self.connect_func()
            self.strategy.reset()
            self.strategy.state = ConnectionState.OPEN
            return True
        except Exception as e:
            self.strategy.state = ConnectionState.CLOSED
            raise e

    async def reconnect_loop(self):
        """自动重连循环"""
        self._running = True

        while self._running:
            try:
                await self.connect()
                # 连接成功，保持
                while self._running and self.strategy.state == ConnectionState.OPEN:
                    await asyncio.sleep(1)  # 心跳间隔
            except Exception as e:
                print(f"连接失败: {e}")
                delay = self.strategy.next_attempt()
                if delay is None:
                    print("已达最大重试次数")
                    break
                print(f"等待 {delay:.2f}s 后重试...")
                await asyncio.sleep(delay)

    async def close(self):
        """关闭连接"""
        self._running = False
        self.strategy.state = ConnectionState.CLOSING
        if self._connection:
            await self._connection.close()
        self.strategy.state = ConnectionState.CLOSED

# 使用示例
async def example_usage():
    """示例：API 客户端重连"""

    async def mock_api_connect():
        """模拟 API 连接"""
        # 这里替换为实际的连接逻辑
        import aiohttp
        return aiohttp.ClientSession()

    client = AsyncReconnectingClient(
        connect_func=mock_api_connect,
        base_delay=1.0,
        max_delay=30.0,
        max_attempts=5
    )

    # 启动重连循环
    await client.reconnect_loop()

if __name__ == "__main__":
    print("重连策略模块")
    print("=" * 40)
    print("策略：带抖动的指数退避")
    print("公式：delay = random(0, min(base*2^attempt, max))")
    print("=" * 40)

    # 测试延迟计算
    strategy = ReconnectionStrategy(base_delay=1.0, max_delay=30.0)
    print("\n模拟重连延迟：")
    for i in range(10):
        delay = strategy.get_delay()
        print(f"  尝试 {i+1}: {delay:.2f}s")
        strategy.attempt += 1
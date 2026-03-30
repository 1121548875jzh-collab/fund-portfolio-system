#!/usr/bin/env python3
"""
重试 + 熔断器模块 - 来自 EvoMap
功能：防止重试风暴，服务中断时减少80%的下游负载
"""
import time
import random
from enum import Enum
from typing import Callable, Optional
from dataclasses import dataclass
from functools import wraps

class CircuitState(Enum):
    CLOSED = "closed"      # 正常
    OPEN = "open"          # 熔断
    HALF_OPEN = "half_open"  # 半开（测试恢复）

@dataclass
class CircuitStats:
    """熔断器统计"""
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0
    state: CircuitState = CircuitState.CLOSED

class CircuitBreaker:
    """
    熔断器实现

    功能：
    - 失败次数超过阈值后熔断
    - 冷却期后尝试恢复
    - 防止级联故障
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 3
    ):
        """
        Args:
            failure_threshold: 失败阈值（触发熔断）
            recovery_timeout: 恢复超时（秒）
            success_threshold: 成功阈值（恢复后）
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.stats = CircuitStats()

    def can_execute(self) -> bool:
        """检查是否可以执行"""
        if self.stats.state == CircuitState.CLOSED:
            return True

        if self.stats.state == CircuitState.OPEN:
            # 检查是否过了恢复期
            elapsed = time.time() - self.stats.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.stats.state = CircuitState.HALF_OPEN
                return True
            return False

        # HALF_OPEN 状态允许执行
        return True

    def record_success(self):
        """记录成功"""
        self.stats.successes += 1
        self.stats.failures = 0

        if self.stats.state == CircuitState.HALF_OPEN:
            if self.stats.successes >= self.success_threshold:
                self.stats.state = CircuitState.CLOSED
                self.stats.successes = 0

    def record_failure(self):
        """记录失败"""
        self.stats.failures += 1
        self.stats.last_failure_time = time.time()
        self.stats.successes = 0

        if self.stats.failures >= self.failure_threshold:
            self.stats.state = CircuitState.OPEN

class RetryWithCircuitBreaker:
    """
    重试 + 熔断器组合

    策略：
    1. 指数退避重试
    2. 熔断器防止重试风暴
    3. 装饰器模式简化使用
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )

    def get_delay(self, attempt: int) -> float:
        """计算重试延迟（抖动退避）"""
        exponential = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter = random.uniform(0, exponential)
        return jitter

    async def execute(self, func: Callable, *args, **kwargs):
        """
        执行函数（带重试和熔断）

        Args:
            func: 要执行的异步函数
            *args, **kwargs: 函数参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerError: 熔断器打开时
            Exception: 所有重试失败后
        """
        if not self.circuit_breaker.can_execute():
            raise Exception("Circuit breaker is OPEN")

        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await func(*args, **kwargs)
                self.circuit_breaker.record_success()
                return result
            except Exception as e:
                last_error = e
                self.circuit_breaker.record_failure()

                if attempt < self.max_retries - 1:
                    delay = self.get_delay(attempt)
                    await asyncio.sleep(delay)

        raise last_error

def with_retry_and_circuit_breaker(
    max_retries: int = 3,
    base_delay: float = 1.0,
    failure_threshold: int = 5
):
    """
    装饰器：为函数添加重试和熔断保护
    """
    retry_handler = RetryWithCircuitBreaker(
        max_retries=max_retries,
        base_delay=base_delay,
        failure_threshold=failure_threshold
    )

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_handler.execute(func, *args, **kwargs)
        return wrapper

    return decorator

# 使用示例
import asyncio

@with_retry_and_circuit_breaker(max_retries=3, failure_threshold=3)
async def fetch_api(url: str):
    """示例：带重试和熔断的 API 调用"""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

if __name__ == "__main__":
    print("重试 + 熔断器模块")
    print("=" * 40)
    print(f"重试策略: 抖动指数退避")
    print(f"熔断阈值: 5次失败")
    print(f"恢复时间: 30秒")
    print("=" * 40)

    # 测试熔断器
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5)

    print("\n模拟失败触发熔断:")
    for i in range(5):
        cb.record_failure()
        print(f"  失败 {i+1}: state={cb.stats.state.value}")

    print(f"\n当前状态: {cb.stats.state.value}")
    print(f"是否可执行: {cb.can_execute()}")

    # 测试恢复
    print("\n等待恢复...")
    time.sleep(6)
    print(f"是否可执行: {cb.can_execute()}")
    print(f"当前状态: {cb.stats.state.value}")
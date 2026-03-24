import time
import json
import threading
from functools import wraps
from collections import deque


"""
RateLimiter 類別用於限制在指定時間窗口內的請求數量。
它使用雙端佇列來儲存請求時間戳，並在達到限制時等待一段時間。

使用方式:
先初始化一個RateLimiter物件 max_requests=45, time_window=5
然後建立一個最小請求單位的函數 使用@裝飾氣包裝
"""
class RateLimiter:
    """速率限制器：5秒內最多45個請求"""
    def __init__(self, max_requests=45, time_window=5):
        """
        :param max_requests: int, 最大請求數量
        :param time_window: int, 時間窗口(秒)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.request_times = deque()  # 使用雙端佇列儲存請求時間戳
        self._lock = threading.Lock()
    
    def _clean_old_requests(self, current_time=None):
        """清理過期的請求時間戳"""
        if current_time is None:
            current_time = time.time()
        while self.request_times and current_time - self.request_times[0] >= self.time_window:
            self.request_times.popleft()
    
    def wait_if_needed(self):
        """如果需要，等待直到可以發送請求，並記錄請求時間（線程安全）"""
        while True:
            with self._lock:
                current_time = time.time()
                self._clean_old_requests(current_time)
                if len(self.request_times) < self.max_requests:
                    self.request_times.append(time.time())
                    return
                wait_time = self.request_times[0] + self.time_window - current_time
                if wait_time <= 0:
                    continue
            time.sleep(wait_time)

def retry_on_not_ready(max_retries=3, delay=2, rate_limiter=None):
    """重試裝飾器，處理 Not ready 錯誤，並整合速率限制"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    # 每次實際發送請求前都要檢查速率限制並記錄
                    # 這包括初始請求和所有重試
                    if rate_limiter is not None:
                        rate_limiter.wait_if_needed()
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e)
                    # 檢查是否為 "Not ready" 錯誤
                    if "Not ready" in error_msg:
                        if attempt < max_retries - 1:
                            wait_time = delay * (attempt + 1)  # 遞增等待時間
                            print(f"重試 {attempt + 1}/{max_retries}，等待 {wait_time} 秒...")
                            time.sleep(wait_time)
                            # 重試時會在下一次循環的開始調用 wait_if_needed()
                            # 所以這裡不需要再次檢查速率限制
                        else:
                            raise
                    else:
                        # 非 "Not ready" 錯誤，直接拋出
                        raise
            return None
        return wrapper
    return decorator



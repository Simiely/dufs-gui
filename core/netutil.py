"""网络工具：本机地址枚举、端口占用检测。"""

from __future__ import annotations

import errno
import socket


def _normalize_host(host: str) -> str:
    """去掉 IPv6 方括号，空值回落到回环地址。"""
    h = (host or "127.0.0.1").strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h


def _family(host: str) -> int:
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def local_ips() -> list[str]:
    """枚举本机可用于局域网访问的非回环 IPv4 地址。"""
    ips: set[str] = set()

    # 通过 UDP connect 探测默认出口网卡（最可靠，不需要真的发包）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("223.5.5.5", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass

    ips.discard("127.0.0.1")
    ips.discard("0.0.0.0")
    return sorted(ips, key=lambda x: tuple(int(p) for p in x.split(".")))


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """端口是否已被占用。

    用 bind 探测而不是 connect：
    - Windows 上 connect_ex 第一次成功后，紧接着第二次会返回失败，
      导致 find_free_port() 把刚判定“被占用”的端口又推荐回来；
    - bind 的行为与 dufs 真正启动时一致，连续调用结果稳定。
    """
    host = _normalize_host(host)
    try:
        with socket.socket(_family(host), socket.SOCK_STREAM) as s:
            s.bind((host, int(port)))
        return False
    except OSError as e:
        # EADDRINUSE / EACCES 表示当前用户无法在该地址监听；
        # Windows 的 errno 本身是 10048/10013，winerror 兜底兼容。
        if e.errno in (errno.EADDRINUSE, errno.EACCES) or \
                getattr(e, "winerror", None) in (10048, 10013):
            return True
        return False


def find_free_port(start: int, host: str = "127.0.0.1", max_try: int = 300) -> int:
    """从 start 开始找第一个未被占用的端口。"""
    port = start
    for _ in range(max_try):
        if not port_in_use(port, host):
            return port
        port += 1
        if port > 65535:
            port = 1024
    return start


def wait_port_open(port: int, host: str = "127.0.0.1", timeout: float = 5.0,
                   interval: float = 0.15) -> bool:
    """等待端口开始监听，用于判断子进程是否真正启动成功。"""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_in_use(port, host):
            return True
        time.sleep(interval)
    return False


def normalize_prefix(prefix: str) -> str:
    """把用户填写的路径前缀规范成 dufs 期望的形式：/xxx（无尾斜杠）。"""
    p = (prefix or "").strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    while p.endswith("/"):
        p = p[:-1]
    return p

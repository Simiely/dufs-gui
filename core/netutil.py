"""网络工具：本机地址枚举、端口占用检测。"""

from __future__ import annotations

import socket


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
    """端口是否已被占用（能连上即视为占用）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.35)
            return s.connect_ex((host, port)) == 0
    except OSError:
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

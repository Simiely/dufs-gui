"""网卡枚举与排序（Windows 原生 API，不解析 ipconfig 文本）。

Windows 走 ``GetAdaptersAddresses``（IP Helper API），拿到网卡 FriendlyName、
IfType、OperStatus 与单播地址；其他平台退回 socket 枚举。排序规则见
``sort_interfaces``，纯函数便于单测。
"""

from __future__ import annotations

import ctypes
import ipaddress
import os
import socket
from dataclasses import dataclass, field

# ---------- 排序权重（数字越小越靠前） ----------
RANK_PHYSICAL = 0
RANK_OTHER_IPV4 = 1
RANK_IPV6 = 2
RANK_WILDCARD = 3
RANK_UNAVAILABLE = 4
RANK_LOOPBACK = 5

_KIND_NAMES = {
    "ethernet": "以太网",
    "wifi": "Wi-Fi",
    "vpn": "VPN",
    "virtual": "虚拟网卡",
    "other": "网卡",
    "loopback": "回环",
    "wildcard": "所有网卡",
}

#: 网卡类型图标（emoji）。选择依据：语义直接、Segoe UI Emoji 覆盖稳定。
_KIND_ICONS = {
    "ethernet": "🔌",     # 有线：插头
    "wifi": "📶",         # 无线信号格
    "vpn": "🔒",          # 加密隧道
    "virtual": "🧩",      # 虚拟/叠加组件
    "other": "🔗",
    "loopback": "🔁",     # 本机回环
    "wildcard": "🌐",     # 所有网卡
}

_VPN_HINTS = (
    "vpn", "tap-windows", "tap adapter", "tunnel", "wireguard", "tailscale",
    "zerotier", "openvpn", "forticlient", "sangfor", "easyconnect", "pptp",
    "l2tp", "sstp", "nordlynx", "proton",
)
_VIRTUAL_HINTS = (
    "hyper-v", "vethernet", "vmware", "virtualbox", "qemu", "wsl", "docker",
    "npcap", "pseudo", "bluetooth", "蓝牙", "wan miniport", "teredo",
    "isatap", "loopback", "virtual", "虚拟",
)


@dataclass(frozen=True)
class NetIf:
    """一块网卡上的一个可绑定地址（或一个虚拟选项）。"""

    name: str
    address: str
    family: int = 4
    kind: str = "other"
    is_up: bool = True
    is_private: bool = False
    if_index: int = 0
    description: str = ""

    @property
    def is_loopback(self) -> bool:
        return self.kind == "loopback"

    @property
    def is_wildcard(self) -> bool:
        return self.kind == "wildcard"

    @property
    def bindable(self) -> bool:
        return bool(self.address) and (self.is_wildcard or self.is_up)

    @property
    def display_name(self) -> str:
        """勾选行里的名称：回环写「仅本机」，通配写「所有网卡」。"""
        if self.is_loopback:
            return "仅本机"
        if self.is_wildcard:
            return "所有网卡"
        return self.name

    @property
    def status_text(self) -> str:
        if self.is_wildcard:
            return "允许其他设备访问"
        if self.is_loopback:
            return "仅本机访问"
        if not self.address:
            return "无地址（不可用）"
        return "已连接" if self.is_up else "未连接（不可用）"

    @property
    def icon(self) -> str:
        """语义图标：以太网/无线/虚拟/回环/通配各自不同。"""
        return _KIND_ICONS.get(self.kind, _KIND_ICONS["other"])

    @property
    def label(self) -> str:
        """下拉/勾选行展示文案：以太网 · 192.168.1.5 · 已连接。"""
        shown = self.address or "无地址"
        return f"{self.display_name} · {shown} · {self.status_text}"


def loopback_rows() -> list[NetIf]:
    return [
        NetIf("回环", "127.0.0.1", 4, "loopback", True, True),
        NetIf("回环", "::1", 6, "loopback", True, True),
    ]


def wildcard_row() -> NetIf:
    return NetIf("所有网卡", "0.0.0.0", 4, "wildcard", True, False)


def _ip_key(address: str) -> tuple:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return (1, address)
    return (0, ip.version, int(ip))


def sort_interfaces(items: list[NetIf]) -> list[NetIf]:
    """按需求排序：物理 IPv4 → 其他 IPv4 → IPv6 → 0.0.0.0 → 不可用 → 回环。"""

    def rank(item: NetIf) -> tuple:
        if item.is_loopback:
            # 127.0.0.1 必须是列表最后一行；::1 紧随其后之前
            return (RANK_LOOPBACK, 0 if item.address == "::1" else 1,
                    item.name, item.address)
        if item.is_wildcard:
            return (RANK_WILDCARD, 0, "", "")
        if item.is_up and item.bindable and item.family == 4:
            if item.kind in ("ethernet", "wifi"):
                # 有线优先于无线，再按私有网段优先、名称、地址
                return (RANK_PHYSICAL, 0 if item.kind == "ethernet" else 1,
                        0 if item.is_private else 1,
                        item.name.lower(), _ip_key(item.address))
            return (RANK_OTHER_IPV4,
                    0 if item.is_private else 1,
                    item.kind, item.name.lower(), _ip_key(item.address))
        if item.is_up and item.bindable and item.family == 6:
            return (RANK_IPV6, 0 if item.is_private else 1,
                    item.name.lower(), _ip_key(item.address))
        return (RANK_UNAVAILABLE, 0 if item.is_up else 1,
                item.name.lower(), item.address)

    return sorted(items, key=rank)


def default_binds(items: list[NetIf]) -> list[str]:
    """默认只选第一块已连接的非回环网卡；没有才回退到回环。"""
    ordered = sort_interfaces(items)
    for item in ordered:
        if item.bindable and item.is_up and not item.is_loopback and not item.is_wildcard:
            return [item.address]
    for item in ordered:
        if item.is_loopback and item.address == "127.0.0.1":
            return [item.address]
    for item in ordered:
        if item.is_loopback and item.bindable:
            return [item.address]
    return []


def apply_saved(saved: list[str], items: list[NetIf]) -> tuple[list[str], list[str]]:
    """保留仍然存在的已保存地址；失效地址单独返回，供界面提示。

    返回 ``(selected, invalid)``。若保存的地址全部失效，则回退到默认选择。
    """
    present = {i.address for i in items if i.bindable}
    kept: list[str] = []
    invalid: list[str] = []
    for address in saved:
        address = (address or "").strip()
        if not address:
            continue
        if address in present:
            if address not in kept:
                kept.append(address)
        elif address not in invalid:
            invalid.append(address)
    if kept:
        return kept, invalid
    return default_binds(items), invalid


# ---------- Windows IP Helper ----------
_AF_UNSPEC = 0
_AF_INET = socket.AF_INET
_AF_INET6 = socket.AF_INET6
_GAA_SKIP_ANYCAST = 0x0002
_GAA_SKIP_MULTICAST = 0x0004
_GAA_SKIP_DNS_SERVER = 0x0008
_ERROR_BUFFER_OVERFLOW = 111


class _SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [("lpSockaddr", ctypes.c_void_p), ("iSockaddrLength", ctypes.c_int)]


class _SOCKADDR_IN(ctypes.Structure):
    _fields_ = [
        ("sin_family", ctypes.c_ushort),
        ("sin_port", ctypes.c_ushort),
        ("sin_addr", ctypes.c_ubyte * 4),
        ("sin_zero", ctypes.c_ubyte * 8),
    ]


class _SOCKADDR_IN6(ctypes.Structure):
    _fields_ = [
        ("sin6_family", ctypes.c_ushort),
        ("sin6_port", ctypes.c_ushort),
        ("sin6_flowinfo", ctypes.c_ulong),
        ("sin6_addr", ctypes.c_ubyte * 16),
        ("sin6_scope_id", ctypes.c_ulong),
    ]


class _UNICAST(ctypes.Structure):
    pass


_UNICAST._fields_ = [
    ("Length", ctypes.c_ulong),
    ("Flags", ctypes.c_ulong),
    ("Next", ctypes.POINTER(_UNICAST)),
    ("Address", _SOCKET_ADDRESS),
    ("PrefixOrigin", ctypes.c_int),
    ("SuffixOrigin", ctypes.c_int),
    ("DadState", ctypes.c_int),
    ("ValidLifetime", ctypes.c_ulong),
    ("LeaseLifetime", ctypes.c_ulong),
]


class _ADAPTER(ctypes.Structure):
    pass


_ADAPTER._fields_ = [
    ("Length", ctypes.c_ulong),
    ("IfIndex", ctypes.c_ulong),
    ("Next", ctypes.POINTER(_ADAPTER)),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", ctypes.POINTER(_UNICAST)),
    ("FirstAnycastAddress", ctypes.c_void_p),
    ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p),
    ("DnsSuffix", ctypes.c_wchar_p),
    ("Description", ctypes.c_wchar_p),
    ("FriendlyName", ctypes.c_wchar_p),
    ("PhysicalAddress", ctypes.c_ubyte * 8),
    ("PhysicalAddressLength", ctypes.c_ulong),
    ("Flags", ctypes.c_ulong),
    ("Mtu", ctypes.c_ulong),
    ("IfType", ctypes.c_ulong),
    ("OperStatus", ctypes.c_int),
    ("Ipv6IfIndex", ctypes.c_ulong),
    ("ZoneIndices", ctypes.c_ulong * 16),
    ("FirstPrefix", ctypes.c_void_p),
]


def _friendly_name(friendly: str, description: str, index: int) -> str:
    name = (friendly or "").strip()
    if not name:
        name = (description or "").strip()
    if not name:
        name = f"网卡 #{index}"
    low = name.lower()
    if "wlan" in low or "wireless" in low:
        name = "Wi-Fi"
    return name


def _classify(name: str, description: str, if_type: int) -> str:
    text = f"{name} {description}".lower()
    if if_type == 24 or "loopback" in text:
        return "loopback"
    if any(hint in text for hint in _VPN_HINTS) or if_type in (23, 131):
        return "vpn"
    if any(hint in text for hint in _VIRTUAL_HINTS) or if_type == 243:
        return "virtual"
    if if_type == 71 or "wi-fi" in text or "wifi" in text or "wireless" in text:
        return "wifi"
    if if_type == 6:
        return "ethernet"
    return "other"


def _sockaddr_text(ptr: int) -> tuple[str, int] | None:
    if not ptr:
        return None
    family = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort)).contents.value
    try:
        if family == _AF_INET:
            sin = ctypes.cast(ptr, ctypes.POINTER(_SOCKADDR_IN)).contents
            return socket.inet_ntop(_AF_INET, bytes(sin.sin_addr)), 4
        if family == _AF_INET6:
            sin6 = ctypes.cast(ptr, ctypes.POINTER(_SOCKADDR_IN6)).contents
            return socket.inet_ntop(_AF_INET6, bytes(sin6.sin6_addr)), 6
    except OSError:
        return None
    return None


def _windows_interfaces() -> list[NetIf]:
    iphlpapi = ctypes.WinDLL("iphlpapi.dll")
    iphlpapi.GetAdaptersAddresses.argtypes = [
        ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
        ctypes.POINTER(_ADAPTER), ctypes.POINTER(ctypes.c_ulong),
    ]
    iphlpapi.GetAdaptersAddresses.restype = ctypes.c_ulong
    flags = _GAA_SKIP_ANYCAST | _GAA_SKIP_MULTICAST | _GAA_SKIP_DNS_SERVER
    size = ctypes.c_ulong(64 * 1024)
    buf = ctypes.create_string_buffer(size.value)
    for _ in range(3):
        ret = iphlpapi.GetAdaptersAddresses(
            _AF_UNSPEC, flags, None,
            ctypes.cast(buf, ctypes.POINTER(_ADAPTER)), ctypes.byref(size))
        if ret == _ERROR_BUFFER_OVERFLOW:
            buf = ctypes.create_string_buffer(size.value)
            continue
        break
    if ret != 0:
        return []

    rows: list[NetIf] = []
    seen: set[str] = set()
    adapter = ctypes.cast(buf, ctypes.POINTER(_ADAPTER)).contents
    index = 0
    while True:
        index += 1
        name = _friendly_name(adapter.FriendlyName, adapter.Description, index)
        kind = _classify(name, adapter.Description or "", int(adapter.IfType))
        up = int(adapter.OperStatus) == 1
        has_address = False
        unicast = adapter.FirstUnicastAddress
        while unicast:
            addr_info = _sockaddr_text(unicast.contents.Address.lpSockaddr)
            unicast = unicast.contents.Next
            if not addr_info:
                continue
            address, family = addr_info
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            if ip.is_loopback:
                continue
            if family == 6 and ip.is_link_local:
                # 链路本地 IPv6 需要 zone id，dufs 不能直接绑定，跳过
                continue
            if family == 4 and ip.is_link_local:
                # 169.254.x.x 是 DHCP 失败后的临时地址，列出也不可用
                continue
            if address.lower() in seen:
                continue
            seen.add(address.lower())
            has_address = True
            rows.append(NetIf(
                name=name,
                address=address,
                family=family,
                kind=kind,
                is_up=up,
                is_private=bool(ip.is_private),
                if_index=int(adapter.IfIndex),
                description=adapter.Description or "",
            ))
        if not has_address and kind not in ("loopback",):
            rows.append(NetIf(
                name=name, address="", family=4, kind=kind, is_up=up,
                if_index=int(adapter.IfIndex), description=adapter.Description or "",
            ))
        if not adapter.Next:
            break
        adapter = adapter.Next.contents
    return rows


def _socket_interfaces() -> list[NetIf]:
    rows: list[NetIf] = []
    seen: set[str] = set()
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_UNSPEC,
                                   socket.SOCK_STREAM)
    except OSError:
        infos = []
    for family, _, _, _, sockaddr in infos:
        address = sockaddr[0]
        if address in seen:
            continue
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_loopback:
            continue
        seen.add(address)
        rows.append(NetIf(
            name="网卡", address=address,
            family=6 if family == socket.AF_INET6 else 4,
            kind="ethernet", is_up=True, is_private=bool(ip.is_private)))
    return rows


def list_interfaces() -> list[NetIf]:
    """枚举本机所有可绑定地址，并追加 0.0.0.0 与回环选项；已按规则排序。"""
    real = _windows_interfaces() if os.name == "nt" else _socket_interfaces()
    rows = [*real, wildcard_row(), *loopback_rows()]
    return sort_interfaces(rows)


def preferred_lan_ip(items: list[NetIf] | None = None) -> str:
    """取第一块物理网卡 IPv4，供 0.0.0.0 的展示 URL 使用。"""
    ordered = sort_interfaces(items) if items else list_interfaces()
    for item in ordered:
        if item.bindable and item.family == 4 and not item.is_loopback \
                and not item.is_wildcard and item.is_up:
            return item.address
    return "127.0.0.1"


def sort_loopback_last(addresses) -> list[str]:
    """地址去重并让回环垫底，其余保持原顺序（辅助状态展示用）。"""
    plain: list[str] = []
    loop: list[str] = []
    seen: set[str] = set()
    for raw in addresses:
        addr = (raw or "").strip()
        if not addr or addr.lower() in seen:
            continue
        seen.add(addr.lower())
        try:
            is_loop = ipaddress.ip_address(addr).is_loopback
        except ValueError:
            is_loop = False
        (loop if is_loop else plain).append(addr)
    return plain + loop


def ip_summary(addresses) -> str:
    """紧凑的 IP 摘要：单个就是 IP，多个用 · 分隔。"""
    return " · ".join(sort_loopback_last(addresses))

"""站点配置模型：字段定义、命令行生成、校验、持久化。"""

from __future__ import annotations

import ipaddress
import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .netutil import normalize_prefix

RENDER_MODES = {
    "自动列表（默认）": "",
    "静态站点 index.html": "--render-index",
    "优先 index.html，否则列表": "--render-try-index",
    "单页应用 SPA": "--render-spa",
}


def is_loopback_bind(bind: str) -> bool:
    """监听地址是否只对本机开放。

    空值不是合法监听地址（dufs 默认是 0.0.0.0，这里不能当成安全默认）；
    无法解析的主机名也按"非回环"处理：宁可多要求一次口令，
    也不要把未知地址当成安全地址。
    """
    host = (bind or "").strip().lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class ServerConfig:
    """一个共享站点的全部配置。"""

    share_path: str = ""
    bind: str = "127.0.0.1"
    port: int = 5000
    path_prefix: str = ""
    allow_upload: bool = True
    allow_delete: bool = False
    allow_search: bool = True
    allow_archive: bool = True
    allow_symlink: bool = False
    enable_cors: bool = False
    #: 是否启用界面皮肤。默认开：index.html 已自包含，不会导致 dufs 启动失败；
    #: 即便失败也有 --assets 自动降级兜底
    custom_ui: bool = True
    #: 外部皮肤目录（如第三方 dufs-material-assets），留空则用内置皮肤
    assets_dir: str = ""
    hidden: str = ""
    render_mode: str = "自动列表（默认）"
    save_log: bool = False
    log_path: str = ""
    tls_cert: str = ""
    tls_key: str = ""
    #: 访问口令（dufs 的 -a user:pass）。留空表示不鉴权，此时只允许回环监听。
    #: 注意：明文保存在配置文件中，界面与日志只展示脱敏后的内容。
    auth_user: str = ""
    auth_pass: str = ""

    # ---------- 命令行 ----------
    def to_args(self) -> list[str]:
        args: list[str] = [self.share_path]
        args += ["-b", self.bind, "-p", str(self.port)]

        prefix = normalize_prefix(self.path_prefix)
        if prefix:
            args += ["--path-prefix", prefix]

        for flag, opt in (
            (self.allow_upload, "--allow-upload"),
            (self.allow_delete, "--allow-delete"),
            (self.allow_search, "--allow-search"),
            (self.allow_archive, "--allow-archive"),
            (self.allow_symlink, "--allow-symlink"),
            (self.enable_cors, "--enable-cors"),
        ):
            if flag:
                args.append(opt)

        if self.hidden.strip():
            args += ["--hidden", self.hidden.strip()]

        if self.custom_ui:
            from .dufsbin import webui_dir

            # 外部目录优先；两者都必须含 index.html，否则 dufs 会直接拒绝启动
            assets = self.assets_dir.strip() or None
            if assets is None:
                builtin = webui_dir()
                assets = str(builtin) if builtin else None
            if assets and (Path(assets) / "index.html").is_file():
                args += ["--assets", str(assets)]

        render = RENDER_MODES.get(self.render_mode, "")
        if render:
            args.append(render)

        if self.save_log and self.log_path.strip():
            args += ["--log-file", self.log_path.strip()]

        if self.tls_cert.strip() and self.tls_key.strip():
            args += ["--tls-cert", self.tls_cert.strip(),
                     "--tls-key", self.tls_key.strip()]

        user = self.auth_user.strip()
        if user and self.auth_pass:
            # dufs 0.47 的 -a 必须带路径规则（user:pass@/path[:perm]）；
            # 只写 user:pass 会被拒绝启动（实测：Invalid auth `user:pass`）。
            # rw 表示"登录后仍可写"，是否真的允许上传/删除仍由 --allow-* 控制。
            args += ["-a", f"{user}:{self.auth_pass}@/:rw"]

        return args

    def redacted_args(self) -> list[str]:
        """返回脱敏后的参数，供界面预览 / 日志使用（口令替换为 ***）。

        不能简单用 args.index("-a")：共享目录名也可能叫 "-a"，按位置替换会
        漏掉真正的口令。这里只替换"看起来像 user:pass"的 -a 参数值。
        """
        args = self.to_args()
        for i in range(len(args) - 1):
            if args[i] == "-a" and ":" in args[i + 1]:
                head, sep, tail = args[i + 1].partition("@")
                user = head.split(":", 1)[0]
                args[i + 1] = f"{user}:***" + (sep + tail if sep else "")
        return args

    def command_line(self, binary: str = "dufs") -> str:
        """生成可直接复制到终端的等价命令（便于学习与排错，口令已脱敏）。"""
        def q(v: str) -> str:
            return f'"{v}"' if (" " in v or v == "") else v
        return " ".join([q(binary)] + [q(a) for a in self.redacted_args()])

    # ---------- 展示 ----------
    @property
    def use_https(self) -> bool:
        return bool(self.tls_cert.strip() and self.tls_key.strip())

    def display_host(self) -> str:
        """0.0.0.0 之类通配地址在展示/打开浏览器时换成具体 IP。"""
        host = self.bind.strip()
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if host in ("0.0.0.0", "::", ""):
            from .netutil import local_ips
            return local_ips()[0] if local_ips() else "127.0.0.1"
        return host

    def probe_host(self) -> str:
        """健康探测用的主机：通配绑定换成对应的回环地址。"""
        host = self.bind.strip()
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if host in ("", "0.0.0.0"):
            return "127.0.0.1"
        if host == "::":
            return "::1"
        return host

    def health_url(self) -> str:
        """dufs 官方健康检查地址，保持在 path-prefix 之下。"""
        scheme = "https" if self.use_https else "http"
        path = normalize_prefix(self.path_prefix)
        host = self.probe_host()
        if ":" in host:
            host = f"[{host}]"
        return f"{scheme}://{host}:{self.port}{path}/__dufs__/health"

    def url(self) -> str:
        scheme = "https" if self.use_https else "http"
        path = normalize_prefix(self.path_prefix)
        host = self.display_host()
        # IPv6 字面量在 URL 里必须加方括号，否则 http://::1:5000/ 是非法格式
        if ":" in host:
            host = f"[{host}]"
        return f"{scheme}://{host}:{self.port}{path}/"

    # ---------- 校验 ----------
    def validate(self) -> list[str]:
        errs: list[str] = []
        if not self.share_path.strip():
            errs.append("请先选择要共享的目录")
        elif not os.path.exists(self.share_path):
            errs.append(f"目录不存在：{self.share_path}")
        if not (1 <= int(self.port) <= 65535):
            errs.append("端口需在 1-65535 之间")
        if bool(self.tls_cert.strip()) != bool(self.tls_key.strip()):
            errs.append("HTTPS 证书和私钥必须同时填写")
        for name, val in (("证书", self.tls_cert), ("私钥", self.tls_key)):
            if val.strip() and not os.path.exists(val):
                errs.append(f"{name}文件不存在：{val}")
        if self.save_log and not self.log_path.strip():
            errs.append("勾选保存日志后需要指定日志文件路径")
        user = self.auth_user.strip()
        pwd = self.auth_pass
        if bool(user) != bool(pwd):
            errs.append("访问口令的用户名和密码必须同时填写（留空表示不鉴权）")
        if ":" in user:
            errs.append("访问口令的用户名不能包含冒号（dufs 按 user:pass 解析）")
        for label, val in (("用户名", user), ("密码", pwd)):
            if any(ch in val for ch in ("\r", "\n", "\x00")):
                errs.append(f"访问口令的{label}不能包含换行或空字符")
            if "@/" in val:
                errs.append(f"访问口令的{label}不能包含 \"@/\""
                            "（dufs 按 user:pass@/path 解析）")
        # 安全默认：非回环监听且没有口令时拒绝启动（而不是只弹一个可忽略的提示）。
        # 理由：LAN 共享是高频场景，用户很容易在"确认一次"后忘记自己已经对外暴露。
        if not self.bind.strip():
            errs.append("监听地址不能为空（仅本机使用请填 127.0.0.1）")
        elif not (user and pwd) and not is_loopback_bind(self.bind):
            errs.append(f"监听地址 {self.bind.strip() or '(空)'} 不是回环地址，"
                        "必须设置访问口令后才能启动")
        if self.custom_ui and self.assets_dir.strip():
            from .dufsbin import validate_assets_dir

            ok, msg = validate_assets_dir(self.assets_dir)
            if not ok:
                errs.append(f"网页皮肤目录无效：{msg}")
        return errs

    # ---------- 序列化 ----------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # 只有"明确关闭"才打标记：表示这是用户当下的选择，
        # 载入时不要被自愈逻辑改回 True。重新勾选后标记自然消失。
        if d.get("custom_ui") is False:
            d["_user_set_custom_ui"] = True
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ServerConfig":
        if not data:
            return cls()
        valid = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in valid}
        cfg = cls(**clean)
        # 自愈：v1.2.1 及更早的"皮肤启动失败自动降级"会把 custom_ui=false 写盘，
        # 造成"一次失败 = 永久关闭"。降级写盘的行为 v1.2.2 就去掉了，
        # 但**已经写进用户配置文件的 false 不会自己消失**，
        # 于是出现"代码和打包都修好了，皮肤却始终不生效"。
        # 这里在载入时恢复为默认 True，一次性消除历史污染。
        # 用户之后仍可手动取消勾选 —— 那属于主动选择，会打 _user_set_custom_ui 标记，不再被改写。
        if clean.get("custom_ui") is False and not data.get("_user_set_custom_ui"):
            cfg.custom_ui = True
        try:
            cfg.port = int(cfg.port)
        except (TypeError, ValueError):
            cfg.port = 5000
        return cfg


@dataclass
class AppConfig:
    """应用级配置：多套站点方案 + 最近目录 + 界面偏好。"""

    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    current: str = ""
    recent_paths: list[str] = field(default_factory=list)
    dark_mode: bool = True
    current_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppConfig":
        if not data:
            return cls()
        return cls(
            profiles=dict(data.get("profiles") or {}),
            current=str(data.get("current") or ""),
            recent_paths=list(data.get("recent_paths") or []),
            dark_mode=bool(data.get("dark_mode", True)),
            current_config=dict(data.get("current_config") or {}),
        )


def config_file(path: str | os.PathLike | None = None) -> Path:
    if path:
        return Path(path)
    base = os.environ.get("DUFS_GUI_HOME")
    if base:
        return Path(base) / "config.json"
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
        return root / "DufsGui" / "config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DufsGui" / "config.json"
    return Path.home() / ".config" / "dufs-gui" / "config.json"


def load_config(path: str | os.PathLike | None = None) -> AppConfig:
    p = config_file(path)
    try:
        return AppConfig.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return AppConfig()


def save_config(cfg: AppConfig, path: str | os.PathLike | None = None) -> None:
    p = config_file(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
                 encoding="utf-8")

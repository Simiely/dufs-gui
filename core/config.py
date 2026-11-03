"""站点配置模型：字段定义、命令行生成、校验、持久化。"""

from __future__ import annotations

import ipaddress
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .netutil import normalize_prefix

#: 配置文件 schema 版本。v1 = 无版本号的旧配置；v2 = 增加版本号并规范化字段。
CONFIG_VERSION = 2

#: 窗口标题默认值与上限。新增字段不升 schema：旧配置没有该字段时按默认值读取。
DEFAULT_WINDOW_TITLE = "Dufs GUI"
MAX_WINDOW_TITLE_LEN = 48


def sanitize_window_title(value: str) -> str:
    """去掉控制字符与首尾空白；空串表示使用默认标题。"""
    cleaned = "".join(ch for ch in str(value) if ch >= " " and ch != "\x7f")
    return cleaned.strip()


def check_window_title(value: str) -> tuple[bool, str]:
    """校验用户输入的窗口标题，返回 ``(是否可用, 清理后的值或错误说明)``。"""
    raw = str(value or "")
    if any(ch < " " or ch == "\x7f" for ch in raw):
        return False, "窗口标题不能包含控制字符"
    clean = sanitize_window_title(raw)
    if len(clean) > MAX_WINDOW_TITLE_LEN:
        return False, f"窗口标题最长 {MAX_WINDOW_TITLE_LEN} 个字符"
    return True, clean

RENDER_MODES = {
    "自动列表（默认）": "",
    "静态站点 index.html": "--render-index",
    "优先 index.html，否则列表": "--render-try-index",
    "单页应用 SPA": "--render-spa",
}


def is_loopback_bind(bind: str) -> bool:
    """监听地址是否只对本机开放。

    空值不是合法监听地址（dufs 默认是 0.0.0.0，这里不能当成安全默认）；
    无法解析的主机名也按"非回环"处理。
    该判断只用于 URL/端口检查等展示逻辑，不再作为"必须设口令"的门槛。
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
    #: 兼容旧配置的单地址字段；实际生效地址见 binds / effective_binds()
    bind: str = "127.0.0.1"
    #: 多网卡同时共享：每个地址一个 dufs 实例
    binds: list[str] = field(default_factory=list)
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
    #: 访问口令（dufs 的 -a user:pass）。留空表示匿名访问（不鉴权），不做强制。
    #: 注意：明文保存在配置文件中，界面与日志只展示脱敏后的内容。
    auth_user: str = ""
    auth_pass: str = ""

    # ---------- 监听地址 ----------
    def effective_binds(self) -> list[str]:
        """实际生效的监听地址：binds 优先，旧的单 bind 自动升级。"""
        out: list[str] = []
        for raw in self.binds:
            addr = (raw or "").strip()
            if addr and addr not in out:
                out.append(addr)
        if out:
            return out
        legacy = (self.bind or "").strip()
        return [legacy] if legacy else []

    def all_loopback(self) -> bool:
        """所有监听地址都是回环才算「仅本机」。空地址不算。"""
        binds = self.effective_binds()
        return bool(binds) and all(is_loopback_bind(b) for b in binds)

    # ---------- 命令行 ----------
    def to_args(self, bind: str | None = None) -> list[str]:
        """生成 dufs 参数。bind 指定时只绑定该地址（多进程模式使用）。"""
        args: list[str] = [self.share_path]
        if bind is not None:
            binds = [bind]
        else:
            binds = self.effective_binds()
        args += ["-b", ",".join(binds), "-p", str(self.port)]

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

    def redacted_args(self, bind: str | None = None) -> list[str]:
        """返回脱敏后的参数，供界面预览 / 日志使用（口令替换为 ***）。

        不能简单用 args.index("-a")：共享目录名也可能叫 "-a"，按位置替换会
        漏掉真正的口令。这里只替换"看起来像 user:pass"的 -a 参数值。
        """
        args = self.to_args(bind)
        for i in range(len(args) - 1):
            if args[i] == "-a" and ":" in args[i + 1]:
                head, sep, tail = args[i + 1].partition("@")
                user = head.split(":", 1)[0]
                args[i + 1] = f"{user}:***" + (sep + tail if sep else "")
        return args

    def command_line(self, binary: str = "dufs", bind: str | None = None) -> str:
        """生成可直接复制到终端的等价命令（便于学习与排错，口令已脱敏）。"""
        def q(v: str) -> str:
            return f'"{v}"' if (" " in v or v == "") else v
        return " ".join([q(binary)] + [q(a) for a in self.redacted_args(bind)])

    # ---------- 展示 ----------
    @property
    def use_https(self) -> bool:
        return bool(self.tls_cert.strip() and self.tls_key.strip())

    def _host_for(self, bind: str | None) -> str:
        if bind is None:
            binds = self.effective_binds()
            host = binds[0] if binds else ""
        else:
            host = bind
        host = (host or "").strip()
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        return host

    def display_host(self, bind: str | None = None) -> str:
        """0.0.0.0 之类通配地址在展示/打开浏览器时换成具体 IP。"""
        host = self._host_for(bind)
        if host in ("0.0.0.0", "::", ""):
            from .netutil import local_ips
            return local_ips()[0] if local_ips() else "127.0.0.1"
        return host

    def probe_host(self, bind: str | None = None) -> str:
        """健康探测用的主机：通配绑定换成对应的回环地址。"""
        host = self._host_for(bind)
        if host in ("", "0.0.0.0"):
            return "127.0.0.1"
        if host == "::":
            return "::1"
        return host

    def check_host(self, bind: str | None = None) -> str:
        """端口占用检查用的主机：通配绑定统一换成 IPv4 回环。

        与 probe_host 的区别是 '' / '::' / '[::]' 都回落到 127.0.0.1，
        保持历史行为（Windows 上直接连 ::1 的兼容性更差）。
        """
        host = self._host_for(bind)
        if host in ("", "0.0.0.0", "::"):
            return "127.0.0.1"
        return host

    def health_url(self, bind: str | None = None) -> str:
        """dufs 官方健康检查地址，保持在 path-prefix 之下。"""
        scheme = "https" if self.use_https else "http"
        path = normalize_prefix(self.path_prefix)
        host = self.probe_host(bind)
        if ":" in host:
            host = f"[{host}]"
        return f"{scheme}://{host}:{self.port}{path}/__dufs__/health"

    def url(self, bind: str | None = None) -> str:
        scheme = "https" if self.use_https else "http"
        path = normalize_prefix(self.path_prefix)
        host = self.display_host(bind)
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
        # 匿名访问是允许的：口令只是可选项，不做启动门槛。
        binds = self.effective_binds()
        if not binds:
            errs.append("监听地址不能为空（仅本机使用请填 127.0.0.1）")
        wildcard = {"0.0.0.0", "::", "[::]"}
        if len(binds) > 1 and any(b in wildcard for b in binds):
            errs.append("0.0.0.0 / :: 表示所有网卡，不能与其他地址同时选择")
        if self.custom_ui and self.assets_dir.strip():
            from .dufsbin import validate_assets_dir

            ok, msg = validate_assets_dir(self.assets_dir)
            if not ok:
                errs.append(f"网页皮肤目录无效：{msg}")
        return errs

    # ---------- 序列化 ----------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        binds = self.effective_binds()
        # bind 同步为第一个地址，保证旧版本/旧代码读到仍可用
        d["bind"] = binds[0] if binds else ""
        d["binds"] = list(binds)
        # 只有"明确关闭"才打标记：表示这是用户当下的选择，
        # 载入时不要被自愈逻辑改回 True。重新勾选后标记自然消失。
        if d.get("custom_ui") is False:
            d["_user_set_custom_ui"] = True
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ServerConfig":
        """逐字段类型校验：类型不符的字段回落默认值，不让脏数据进入命令生成。"""
        cfg = cls()
        if not isinstance(data, dict):
            return cfg
        defaults = cls()
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            default = getattr(defaults, f.name)
            if f.name == "port":
                # bool 是 int 的子类，要单独排除；字符串数字是兼容旧配置的必要支持
                if isinstance(value, bool):
                    continue
                if isinstance(value, int):
                    cfg.port = value
                elif isinstance(value, str):
                    try:
                        cfg.port = int(value.strip())
                    except ValueError:
                        pass
            elif isinstance(default, bool):
                if isinstance(value, bool):
                    setattr(cfg, f.name, value)
            elif isinstance(default, str):
                if isinstance(value, str):
                    setattr(cfg, f.name, value)
        # ---- 多地址升级 ----
        # 新格式用 binds 列表；旧配置只有 bind，读入后自动升级为单元素列表。
        raw_binds = data.get("binds")
        binds: list[str] = []
        if isinstance(raw_binds, list):
            for raw in raw_binds:
                if isinstance(raw, str) and raw.strip() and raw.strip() not in binds:
                    binds.append(raw.strip())
        if not binds:
            legacy = data.get("bind")
            if isinstance(legacy, str) and legacy.strip():
                binds = [legacy.strip()]
        if binds:
            cfg.binds = binds
            cfg.bind = binds[0]
        # 自愈：v1.2.1 及更早的"皮肤启动失败自动降级"会把 custom_ui=false 写盘，
        # 造成"一次失败 = 永久关闭"。降级写盘的行为 v1.2.2 就去掉了，
        # 但**已经写进用户配置文件的 false 不会自己消失**，
        # 于是出现"代码和打包都修好了，皮肤却始终不生效"。
        # 这里在载入时恢复为默认 True，一次性消除历史污染。
        # 用户之后仍可手动取消勾选 —— 那属于主动选择，会打 _user_set_custom_ui 标记，不再被改写。
        if data.get("custom_ui") is False and not data.get("_user_set_custom_ui"):
            cfg.custom_ui = True
        return cfg


@dataclass
class AppConfig:
    """应用级配置：多套站点方案 + 最近目录 + 界面偏好。"""

    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    current: str = ""
    recent_paths: list[str] = field(default_factory=list)
    current_config: dict[str, Any] = field(default_factory=dict)
    #: 自定义窗口标题（同时决定任务栏名称）；空串表示使用 DEFAULT_WINDOW_TITLE。
    #: 与 schema 版本无关：旧配置没有该字段时按默认值读取，不需要迁移。
    window_title: str = ""
    config_version: int = CONFIG_VERSION
    #: 载入时的告警（迁移/坏配置恢复）。不落盘，只在界面日志里提示一次。
    notice: str = field(default="", compare=False, repr=False)

    def effective_window_title(self) -> str:
        return sanitize_window_title(self.window_title) or DEFAULT_WINDOW_TITLE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("notice", None)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppConfig":
        if not isinstance(data, dict):
            return cls()

        notes: list[str] = []
        version = data.get("config_version", 1)
        if isinstance(version, bool) or not isinstance(version, int):
            notes.append("config_version 类型无效，按 v1 处理")
            version = 1
        if version > CONFIG_VERSION:
            raise ConfigTooNew(version)
        if version < CONFIG_VERSION:
            notes.append(f"配置已从 v{version} 升级到 v{CONFIG_VERSION}")

        profiles: dict[str, dict[str, Any]] = {}
        raw_profiles = data.get("profiles")
        if isinstance(raw_profiles, dict):
            for key, value in raw_profiles.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    notes.append("profiles 中有条目类型无效，已忽略")
                    continue
                # 逐方案做字段级校验，避免脏类型影响下一次切换
                profiles[key] = ServerConfig.from_dict(value).to_dict()
        elif raw_profiles is not None:
            notes.append("profiles 类型无效，已清空")

        raw_current = data.get("current")
        current = raw_current if isinstance(raw_current, str) else ""
        if raw_current is not None and not isinstance(raw_current, str):
            notes.append("current 类型无效，已忽略")

        raw_recent = data.get("recent_paths")
        recent: list[str] = []
        if isinstance(raw_recent, list):
            kept = [x for x in raw_recent if isinstance(x, str)]
            if len(kept) != len(raw_recent):
                notes.append("recent_paths 中有非字符串项，已忽略")
            recent = kept
        elif raw_recent is not None:
            notes.append("recent_paths 类型无效，已清空")

        raw_cc = data.get("current_config")
        if isinstance(raw_cc, dict):
            current_config = ServerConfig.from_dict(raw_cc).to_dict()
        else:
            current_config = {}
            if raw_cc is not None:
                notes.append("current_config 类型无效，已清空")

        raw_title = data.get("window_title")
        window_title = ""
        if isinstance(raw_title, str):
            ok, clean = check_window_title(raw_title)
            if ok:
                window_title = clean
            else:
                notes.append(f"窗口标题无效（{clean}），已恢复默认")
        elif raw_title is not None:
            notes.append("window_title 类型无效，已忽略")

        cfg = cls(
            profiles=profiles,
            current=current,
            recent_paths=recent,
            current_config=current_config,
            window_title=window_title,
            config_version=CONFIG_VERSION,
        )
        cfg.notice = "；".join(notes)
        return cfg


class ConfigTooNew(ValueError):
    """配置文件由更高版本写入；降级读取可能丢字段，所以按坏配置处理。"""

    def __init__(self, version: int):
        super().__init__(f"配置版本 v{version} 高于当前支持的 v{CONFIG_VERSION}")
        self.version = version


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


def _backup_bad(p: Path) -> Path | None:
    """把坏配置移到 config.bad.json；移动失败再尝试复制，最后失败返回 None。"""
    bad = p.with_name("config.bad.json")
    try:
        os.replace(p, bad)
        return bad
    except OSError:
        try:
            import shutil
            shutil.copy2(p, bad)
            return bad
        except OSError:
            return None


def load_config(path: str | os.PathLike | None = None) -> AppConfig:
    """读取配置；坏文件先备份再回落默认值，并把原因写进 cfg.notice。"""
    p = config_file(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return AppConfig()
    except OSError as e:
        cfg = AppConfig()
        cfg.notice = f"读取配置失败（{e}），本次使用默认配置"
        return cfg

    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("配置根节点必须是 JSON 对象")
        return AppConfig.from_dict(data)
    except ConfigTooNew as e:
        bad = _backup_bad(p)
        cfg = AppConfig()
        cfg.notice = (f"配置文件版本 v{e.version} 高于当前支持的 v{CONFIG_VERSION}，"
                      + (f"已备份为 {bad.name}，" if bad else "备份失败，")
                      + "本次使用默认配置")
        return cfg
    except (ValueError, TypeError) as e:
        bad = _backup_bad(p)
        cfg = AppConfig()
        cfg.notice = (f"配置文件无法解析（{e}），"
                      + (f"已备份为 {bad.name}，" if bad else "备份失败，")
                      + "本次使用默认配置")
        return cfg


def save_config(cfg: AppConfig, path: str | os.PathLike | None = None) -> None:
    """原子写：同目录临时文件 + os.replace，避免崩溃留下半截 JSON。"""
    p = config_file(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass

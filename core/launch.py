"""启动决策：把 UI 之外的启动判断收敛成可测试的纯函数。

这里不弹窗、不启动进程、不写文件；界面层只负责执行计划。
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Sequence

from .config import ServerConfig
from .dufsbin import verify_assets_dir


@dataclass(frozen=True)
class LaunchPlan:
    """一次启动所需的全部决定，界面层据此弹窗/启进程。"""

    errors: tuple[str, ...] = ()
    binary: Path | None = None
    args: tuple[str, ...] = ()
    #: 皮肤启动失败后的降级参数；没有 --assets 时为 None
    fallback_args: tuple[str, ...] | None = None
    host_check: str = ""
    url: str = ""
    auth_log: str = ""
    skin_logs: tuple[str, ...] = ()
    skin_arg: str = ""
    custom_ui: bool = True
    share_is_file: bool = False
    #: 该计划对应的监听地址与端口（多实例启动使用）
    bind: str = ""
    port: int = 0
    #: 可直接复制到终端的等效命令（口令已脱敏），启动时写入运行日志
    command: str = ""

    @property
    def can_start(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class LaunchGroup:
    """多地址启动计划：共享配置校验、皮肤诊断与口令日志。"""

    errors: tuple[str, ...] = ()
    plans: tuple[LaunchPlan, ...] = ()
    auth_log: str = ""
    skin_logs: tuple[str, ...] = ()
    binary: Path | None = None

    @property
    def can_start(self) -> bool:
        return not self.errors and bool(self.plans)


def _skin_arg(args: Sequence[str]) -> str:
    """从参数里取出 --assets 的值；没有则返回空串。"""
    for i, arg in enumerate(args):
        if arg == "--assets" and i + 1 < len(args):
            return args[i + 1]
    return ""


def build_launch_plan(
    cfg: ServerConfig,
    *,
    binary: Path | None = None,
    dufs_version: str = "",
    skin_dir: str = "",
    skin_version: str = "",
    config_path: str = "config.json",
    diagnose_skin: bool = True,
    skin_probe: Callable[[str | None], tuple[bool, str]] = verify_assets_dir,
) -> LaunchPlan:
    """生成启动计划。

    diagnose_skin=False 时只做配置校验与参数生成，便于界面在解析 dufs
    路径之前先拿到错误和口令日志；皮肤诊断（含目录核验）只在需要时执行。
    """
    args = tuple(cfg.to_args())
    logs: list[str] = []
    share_is_file = bool(cfg.share_path.strip() and os.path.isfile(cfg.share_path))
    asset = _skin_arg(args)

    if diagnose_skin:
        # ---- 皮肤诊断 ----
        # dufs 在 --assets 目录不含 index.html 时**不报错**，而是静默回退内置界面，
        # 用户看到"皮肤没生效"却毫无线索。这里在启动前自己核验并写清结论。
        #
        # 目录优先级：用户在高级设置里指定的外部目录 > 内置皮肤目录
        # 皮肤诊断分两步，**必须分开说**：
        #   1) 目录本身是否可用 —— 只是"文件在不在"
        #   2) --assets 是否真的进了命令行 —— 才是"会不会生效"
        try:
            ok, msg = skin_probe(skin_dir or None)
            logs.append(("网页皮肤：目录核验通过 " if ok
                         else "网页皮肤：目录不可用 —— ") + msg)
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc().strip().splitlines()
            loc = tb[-2].strip() if len(tb) >= 2 else "未知位置"
            logs.append(f"网页皮肤：核验异常（{loc}）{type(e).__name__}: {e}")

        if asset:
            logs.append(f"网页皮肤：已加入 --assets → {asset}")
        else:
            # custom_ui 的实际值来自 %APPDATA%\DufsGui\config.json，会覆盖代码默认值。
            # 旧版在"皮肤启动失败自动降级"时把它写成 false 并存盘，
            # 一次失败 = 永久关闭。现在降级已不写盘，但**已存在的旧值不会被自动清掉**。
            logs.append("网页皮肤：本次未传 --assets，网页将是 dufs 默认界面\n"
                        "              原因：配置中 custom_ui=false（勾选「网页美化界面」即可启用）\n"
                        "              该值存于 " + config_path + "，删除此文件可恢复默认")

        # 官方限制：serve-path 传文件（而非目录）时 index.html 模板被完全绕过，
        # 皮肤必然不生效。提前说明，避免用户以为是皮肤坏了。
        # 旧实现无论是否已传 --assets 都会打印这句，未传时会重复两遍；这里去重。
        if share_is_file:
            logs.append("提示：共享的是单个文件，dufs 会绕过 index.html 模板，皮肤不生效（官方行为）")

        # 皮肤版本与 dufs 版本不一致时，DOM / 数据契约可能变化
        if skin_version and dufs_version and skin_version != dufs_version:
            logs.append(f"提示：网页皮肤版本 {skin_version} 与 dufs {dufs_version} 不一致；"
                        "升级皮肤需先更新 tools/skin_checksums.json，"
                        "再执行 python tools/fetch_skin.py")

        # custom_ui 的实际值来自 %APPDATA%\DufsGui\config.json，会覆盖程序默认值
        if not cfg.custom_ui:
            logs.append("网页皮肤：未启用（配置中 custom_ui=false）；"
                        "勾选「网页美化界面」即可启用\n"
                        "              若想彻底恢复默认，删除配置文件：" + config_path)

    fallback_args = None
    if "--assets" in args and cfg.custom_ui:
        # 只改这次启动用的临时副本；界面变量必须保持原值，避免被 _save() 写盘
        fallback_args = tuple(replace(cfg, custom_ui=False).to_args())

    user = cfg.auth_user.strip()
    # 匿名访问完全静默：不写日志、不提示，和"没设口令"的用户预期一致
    auth_log = f"访问口令：已启用（用户名 {user}）" if cfg.auth_pass else ""

    return LaunchPlan(
        errors=tuple(cfg.validate()),
        binary=Path(binary) if binary is not None else None,
        args=args,
        fallback_args=fallback_args,
        host_check=cfg.check_host(),
        url=cfg.url(),
        auth_log=auth_log,
        skin_logs=tuple(logs),
        skin_arg=asset,
        custom_ui=cfg.custom_ui,
        share_is_file=share_is_file,
        bind=cfg.effective_binds()[0] if cfg.effective_binds() else "",
        port=int(cfg.port),
        command=cfg.command_line(binary=str(binary) if binary is not None else "dufs"),
    )


def build_launch_plans(cfg: ServerConfig, **kwargs) -> LaunchGroup:
    """为每个监听地址生成一份独立计划（多进程共享同一端口/目录/参数）。

    皮肤诊断只做一次（取第一个地址），避免日志重复；其余地址只做参数生成。
    每个计划里的 -b 只包含自己的地址，便于按地址独立启动与报错。
    """
    from dataclasses import replace

    binds = cfg.effective_binds()
    errors = tuple(cfg.validate())
    if not binds:
        return LaunchGroup(errors=errors)

    kwargs = dict(kwargs)
    kwargs["diagnose_skin"] = True
    plans: list[LaunchPlan] = []
    for index, bind in enumerate(binds):
        sub = replace(cfg, bind=bind, binds=[bind])
        if index > 0:
            kwargs["diagnose_skin"] = False
        plans.append(build_launch_plan(sub, **kwargs))

    first = plans[0]
    return LaunchGroup(
        errors=errors,
        plans=tuple(plans),
        auth_log=first.auth_log,
        skin_logs=first.skin_logs,
        binary=first.binary,
    )


def summarize_start_results(results: Sequence[tuple[str, bool, str]]) -> str:
    """汇总多实例启动结果，供状态栏/日志直接展示。

    results 每项为 ``(地址, 是否成功, 失败原因)``。
    """
    total = len(results)
    if total == 0:
        return "没有可启动的地址"
    ok = sum(1 for _, success, _ in results if success)
    failed = [(label, reason) for label, success, reason in results if not success]
    if ok == total:
        return f"{total} 个地址均已启动"
    detail = "；".join(f"{label}（{reason or '未知原因'}）" for label, reason in failed)
    if ok == 0:
        return f"{total} 个地址全部启动失败：{detail}"
    return f"{total} 个中 {ok} 个已启动，{len(failed)} 个失败：{detail}"

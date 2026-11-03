"""表单状态：界面变量与 ServerConfig 的双向映射。"""

from __future__ import annotations

import tkinter as tk

from core.config import DEFAULT_WINDOW_TITLE, ServerConfig


class FormStateMixin:
    """把界面变量、端口解析与配置映射从主窗口行为中拆出。

    这里只做"界面值 ⇄ ServerConfig"的转换，不碰进程、文件或弹窗。
    """

    # ---------------- 变量 ----------------
    def _build_vars(self) -> None:
        self.v_path = tk.StringVar(value="")
        # 监听地址是勾选列表（self.bindlist）；这里保留待应用的选择用于加载配置
        self._pending_binds: list[str] = []
        # 用字符串输入：IntVar 在清空/输入非数字时 .get() 会抛 TclError，
        # 而 v_port 绑了 trace，用户在编辑框里删字就会触发错误弹窗。
        self.v_port = tk.StringVar(value="5000")
        self.v_prefix = tk.StringVar(value="")
        self.v_upload = tk.BooleanVar(value=True)
        self.v_delete = tk.BooleanVar(value=False)
        self.v_search = tk.BooleanVar(value=True)
        self.v_archive = tk.BooleanVar(value=True)
        self.v_symlink = tk.BooleanVar(value=False)
        self.v_cors = tk.BooleanVar(value=False)
        self.v_custom_ui = tk.BooleanVar(value=True)
        self.v_assets_dir = tk.StringVar(value="")
        self.v_hidden = tk.StringVar(value="")
        self.v_render = tk.StringVar(value="自动列表（默认）")
        self.v_savelog = tk.BooleanVar(value=False)
        self.v_logpath = tk.StringVar(value="")
        self.v_cert = tk.StringVar(value="")
        self.v_key = tk.StringVar(value="")
        self.v_auth_user = tk.StringVar(value="")
        self.v_auth_pass = tk.StringVar(value="")
        self.v_dufs = tk.StringVar(value="")
        self.v_profile = tk.StringVar(value="")
        self.v_status = tk.StringVar(value="未启动")
        self.v_url = tk.StringVar(value="—")
        #: 标题显示值（窗口标题 + 顶部标题共用）；空配置时回落 DEFAULT_WINDOW_TITLE
        self.v_app_title = tk.StringVar(value=DEFAULT_WINDOW_TITLE)
        #: 高级设置里编辑的原始标题（空串 = 使用默认标题）
        self.v_window_title = tk.StringVar(value="")

        for v in (self.v_path, self.v_port, self.v_prefix, self.v_hidden,
                  self.v_render, self.v_logpath, self.v_cert, self.v_key, self.v_profile,
                  self.v_custom_ui, self.v_assets_dir, self.v_auth_user, self.v_auth_pass):
            v.trace_add("write", lambda *_: self._refresh_preview())

    def selected_binds(self) -> list[str]:
        bindlist = getattr(self, "bindlist", None)
        if bindlist is not None:
            # 以界面勾选为准：全部取消勾选时返回空列表，不能再回退到旧值
            return bindlist.selected()
        return list(self._pending_binds)

    def port_from_form(self) -> tuple[int | None, str]:
        """解析端口输入；无效时返回可读提示，不在编辑过程中抛异常。"""
        raw = str(self.v_port.get() or "").strip()
        if not raw:
            return None, "端口不能为空"
        try:
            port = int(raw)
        except ValueError:
            return None, "端口必须是 1-65535 的整数"
        if not 1 <= port <= 65535:
            return None, "端口需在 1-65535 之间"
        return port, ""

    def current_config(self) -> ServerConfig:
        port, _ = self.port_from_form()
        binds = self.selected_binds()
        return ServerConfig(
            share_path=self.v_path.get().strip(),
            bind=binds[0] if binds else "",
            binds=list(binds),
            # 编辑过程中允许暂时非法；用 5000 占位，提交时由 port_from_form 报错
            port=port if port is not None else 5000,
            path_prefix=self.v_prefix.get().strip(),
            allow_upload=self.v_upload.get(),
            allow_delete=self.v_delete.get(),
            allow_search=self.v_search.get(),
            allow_archive=self.v_archive.get(),
            allow_symlink=self.v_symlink.get(),
            enable_cors=self.v_cors.get(),
            custom_ui=self.v_custom_ui.get(),
            assets_dir=self.v_assets_dir.get(),
            hidden=self.v_hidden.get().strip(),
            render_mode=self.v_render.get(),
            save_log=self.v_savelog.get(),
            log_path=self.v_logpath.get().strip(),
            tls_cert=self.v_cert.get().strip(),
            tls_key=self.v_key.get().strip(),
            auth_user=self.v_auth_user.get().strip(),
            auth_pass=self.v_auth_pass.get(),
        )

    def load_to_form(self, cfg: ServerConfig) -> None:
        self.v_path.set(cfg.share_path)
        self._pending_binds = cfg.effective_binds()
        bindlist = getattr(self, "bindlist", None)
        if bindlist is not None and bindlist.items:
            bindlist.set_selection(self._pending_binds)
        self.v_port.set(str(cfg.port))
        self.v_prefix.set(cfg.path_prefix)
        self.v_upload.set(cfg.allow_upload)
        self.v_delete.set(cfg.allow_delete)
        self.v_search.set(cfg.allow_search)
        self.v_archive.set(cfg.allow_archive)
        self.v_symlink.set(cfg.allow_symlink)
        self.v_cors.set(cfg.enable_cors)
        self.v_custom_ui.set(cfg.custom_ui)
        self.v_assets_dir.set(cfg.assets_dir)
        self.v_hidden.set(cfg.hidden)
        self.v_render.set(cfg.render_mode)
        self.v_savelog.set(cfg.save_log)
        self.v_logpath.set(cfg.log_path)
        self.v_cert.set(cfg.tls_cert)
        self.v_key.set(cfg.tls_key)
        self.v_auth_user.set(cfg.auth_user)
        self.v_auth_pass.set(cfg.auth_pass)

---
id: pitfall.assets-needs-index-html
title: dufs 因 --assets 目录缺 index.html 直接拒绝启动
summary: index.html 是 dufs 启动校验层的硬门槛，缺了 bail，而 css/js 缺失可以运行时回退。
type: explanation
kind: pitfall
status: resolved
owner: "@simiely"
topics: [development]
source_type: code
source: core/dufsbin.py
last_reviewed: 2026-11-04
symptom: 勾选「网页美化界面」后共享启动失败，取消勾选则一切正常，日志里没有更多线索。
cause: dufs 的 sanitize_assets_path 在启动校验阶段就要求 assets 目录含 index.html，否则 bail!；「缺文件回退内置」只对 css/js/favicon 成立。
detect: 日志出现 "doesn't contains index.html"；或开共享前检查皮肤目录是否三件套齐全。
avoid: 皮肤目录必须同时具备 index.html / index.css / index.js；不要只放样式。
recover: 临时关掉网页美化即可恢复共享；补全 index.html 后重开。
applies_to: [docs.usage]
severity: high
related: []
---
# 问题：dufs 因 `--assets` 目录缺少 index.html 拒绝启动

**TL;DR**：dufs 在启动校验阶段就硬性要求 assets 目录含 index.html，缺了直接 `bail!`。

- **问题**：启用「网页美化界面」后共享启动失败，不带该参数则正常
- **根因**：dufs `src/args.rs`：
  ```rust
  fn sanitize_assets_path(path: P) -> Result<PathBuf> {
      let path = Self::sanitize_path(path)?;
      if !path.join("index.html").exists() {
          bail!("Path {} doesn't contains index.html", path.display());
      }
      Ok(path)
  }
  ```
  「缺的文件运行时回退内置」只对 `index.css / index.js / favicon.ico` 成立（那是
  运行时资源解析层），**index.html 在启动校验层是硬门槛**。两个层面规则不同，混为一谈就踩坑
- **解决**：`assets/` 搬运 dufs 官方 v0.47.0 的 `index.html` / `index.js` / `favicon.ico`，
  另加只覆盖 CSS 变量的 `index.css`。上传、下载、预览、搜索全部由官方 JS 提供，我们只改样式；
  升级 dufs 后用 `python tools/fetch_skin.py <版本>` 同步，不要手写前端
- **预防**：三重保险 —— ① 启动前校验 ② 生成命令行时再校验 ③ 失败自动去掉 `--assets` 重试
- **默认策略**：皮肤**默认开启**；启动失败且带 `--assets` 时自动去掉重试一次，
  降级只影响本次运行、不写入配置，下次开启仍会尝试

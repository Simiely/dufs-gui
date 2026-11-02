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
- **解决**：`assets/` 提供完整三件套（index.html + index.css + index.js），全部自研，
  不依赖内置前端，顺带切断版本耦合
- **预防**：三重保险 —— ① 启动前校验 ② 生成命令行时再校验 ③ 失败自动去掉 `--assets` 重试
- **默认策略**：皮肤默认关闭。宁可样式朴素，也不能让皮肤挡住共享本身

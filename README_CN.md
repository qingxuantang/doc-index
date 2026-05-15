# doc-index — 项目文档索引 PWA 生成器

从任意项目仓库的目录结构生成一个可安装为 PWA 的文档索引网站。手机 / 平板上看一眼，就能知道项目的规划 / 规格 / 图表 / 笔记长什么样——**不暴露源代码**。

通过 nginx 服务 + basic auth（默认 ON）。一份 `config.yaml` 跑整个流程。

[English README](./README.md) · MIT 协议 · 单 Python 文件扫描器 + 模板化 HTML

---

## doc-index 的定位

doc-index 是**文档浏览器，不是代码浏览器**。它的目的：让任何人扫一眼就理解你的项目在做什么——读 PDF、md、xlsx、图、Jupyter notebook、YAML 配置。**绝不展示 `.py` / `.js` / `.go` 这种源代码**。

通过白名单实现：`repo.file_types` 里没列的扩展名扫描时直接跳过。

| 类别 | 默认包含的扩展名 |
|---|---|
| 文本类 | `pdf`, `md`, `txt`, `html`, `ipynb`, `yaml`, `yml` |
| Office | `xlsx`, `xls`, `csv`, `docx`, `doc`, `pptx`, `ppt` |
| 图 / 示意 | `png`, `jpg`, `jpeg`, `gif`, `webp`, `svg` |

不在这个清单里的——`.py`, `.js`, `.ts`, `.go`, `.rs`, `.toml`, `.lock`, 各种 dotfiles——一律 silently 跳过。

## 架构

- **Config**：`config.yaml` —— 全部项目相关设置
- **Scripts**：
  - `scripts/scan.py` —— 生成 `index.html`
  - `scripts/serve.py` —— 首次部署 / 认证 / nginx 配置生成
  - `scripts/icon.py` —— 按项目主题色生成 PWA 图标
- **Templates**：`templates/` 下纯 `{{PLACEHOLDER}}` 风格的 HTML/JS/CSS
- **Output**：静态文件由 nginx + basic auth 提供，可在手机上 "添加到主屏" 安装为 PWA

## 首次设置

### 1. 复制 config 模板

把 `serve.domain` 填成你的公开主机名（生成完整 nginx server block 必填）：

```bash
cp config.example.yaml /path/to/project/doc-index.yaml
# 编辑：project.name / repo.path / serve.root / serve.url_base / serve.domain
```

### 2. 初始化部署

```bash
python3 scripts/serve.py init /path/to/project/doc-index.yaml
```

会自动完成：
1. 检查 nginx 是否在运行
2. 检查仓库路径
3. 创建 serve 目录
4. 创建 serve dir → repo 软链
5. 按 `project.color` + `project.short_name` 生成 PWA 图标
6. 拷贝 viewer 模板（PDF.js, Markdown viewer, YAML viewer）
7. **生成 basic-auth 的 htpasswd** + 把密码写回 config.yaml
8. 如果 `triggers.cron` 配了就设置 crontab
9. 跑首次 scan 生成 `index.html`
10. 打印**完整的 nginx server block**（含 ssl 占位 + auth + location + http→https redirect + certbot 提示）

凭证只打印一次——记下来。

### 3. 接 nginx

把打印出的 server block 存到 `/etc/nginx/conf.d/<project>.conf`：

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d docs.example.com     # 装 SSL
```

### 4. 验证 + 登记

在手机 / 平板上打开 URL（用 auth 凭证登录），添加到主屏装为 PWA。

## 日常使用

```bash
# 手动更新索引（git push 之后跑一下）
python3 scripts/scan.py /path/to/project/doc-index.yaml

# 重置 auth 密码
python3 scripts/serve.py reset-auth /path/to/project/doc-index.yaml

# 只打印 nginx block
python3 scripts/serve.py nginx /path/to/project/doc-index.yaml

# 状态检查
python3 scripts/serve.py status /path/to/project/doc-index.yaml
```

也可以在 `.git/hooks/post-merge` 里挂一个钩子：

```bash
#!/bin/bash
python3 /path/to/doc-index/scripts/scan.py /path/to/project/doc-index.yaml
```

或者用 `triggers.cron` 在 config 里配 5 字段 cron 表达式，`serve.py init` 会自动写 crontab。

## Viewer 行为

doc-index 把不同类型路由到合适的 viewer：

- PDF / 图像 / SVG → 内嵌预览
- MD → 内置 markdown viewer
- YAML → 内置 YAML viewer（可浏览、可过滤）
- IPYNB → 新标签页打开（浏览器直接渲染）
- Office（xlsx / docx / pptx）→ Microsoft Office 网页 viewer

## 适配器（外部数据源）

通过适配器把外部 API 的数据也拉进索引：

```yaml
external_sources:
  - name: "GitHub Releases"
    adapter: "github_releases"
    config:
      repo: "owner/repo"
      token_env: "GITHUB_TOKEN"
      download_to: "releases/"
```

参考实现：`adapters/github_releases.py`。

## 核心规则

- **doc-only 是这个工具的核心**——往 `repo.file_types` 里加源代码扩展名几乎都是误用，请用专门的代码搜索工具
- Config 驱动一切——不要在模板和脚本里硬编码项目相关值
- `scan.py` 是幂等的，可以反复跑
- `serve.py init` 不会覆盖已有内容
- HTML 里的所有路径会 URL-encode 处理非 ASCII 文件名
- Basic auth 默认 ON；除非有其他保护层，否则不要设 `serve.auth.enabled: false`

## 依赖

- Python 3.8+
- PyYAML (`pip install pyyaml`)
- nginx（在运行，且对 serve 目录有读权限）
- `htpasswd`（apache2-utils）或 `openssl`，认证生成需要其中之一
- Pillow（可选，仅 `icon.py` 自动生成 PWA 图标时用到）

## 协议

MIT —— 见 [LICENSE](./LICENSE)。

# doc-index — 项目文档索引 PWA 生成器

从任意项目仓库的目录结构生成一个可安装为 PWA 的文档索引网站。手机 / 平板上看一眼，就能知道项目的规划 / 规格 / 图表 / 笔记长什么样——**不暴露源代码**。

通过 nginx 服务 + basic auth（默认 ON）。一份 `config.yaml` 跑整个流程。

[English README](./README.md) · [简体中文](./README_CN.md) · MIT 协议

> **这是一个 Claude Code skill**。把仓库放到 `~/.claude/skills/doc-index/` 下，Claude Code 在你说"更新索引" / "刷新文档站" / "set up doc index for X project" 时会自动调用。也可以脱离 Claude Code 当作普通 Python CLI 用——两种用法等价。

## 作为 Claude Code skill 安装

```bash
# 一次性安装
git clone https://github.com/qingxuantang/doc-index.git ~/.claude/skills/doc-index

# 然后在 Claude Code（或任何兼容 Claude Code skill 加载的 agent）里：
#   "set up doc index for my project at ~/projects/foo"
#   "更新索引"           # 刷新最近活跃的项目
#   "把这个加到索引"      # 加文档 + 重新 scan
```

skill 的 [SKILL.md](./SKILL.md) 里声明了 auto-invoke 触发词，agent 自动接管，不用你记脚本路径。

## 作为独立 CLI 安装（不用 Claude Code）

```bash
git clone https://github.com/qingxuantang/doc-index.git
cd doc-index
cp config.example.yaml /path/to/your-project/doc-index.yaml
# 编辑 yaml
python3 scripts/serve.py init /path/to/your-project/doc-index.yaml
```

功能完全一样——Claude Code 那层只是 auto-invoke 便利，不是功能依赖。

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

## 状态板布局（`sections.promote`）

doc-index 默认按 repo 根目录的一级子文件夹分 section。如果你想要一个**"当前状态一目了然"**的视图——能马上看到 "正在干什么 / 下一步什么 / 已经归档了什么"——可以把文档按状态分子文件夹，然后用 `sections.promote` 把这些子文件夹升格成顶级 section。

📋 **完整指南（含生命周期 / 什么放哪个文件夹 / 迁移技巧）：[RECOMMENDED_LAYOUT.md](./RECOMMENDED_LAYOUT.md)**

约定：状态文件夹用 2 位数字前缀，自然排序。

```
docs/
├── 00-now/         当前正在执行的 sprint（通常 1-3 个文件）
├── 10-next/        已设计 / 待开工
├── 20-design/      架构 / 长期参考
├── 30-guide/       API / 部署 / 操作手册
├── 40-business/    pitch / mockup / 一次性业务
└── 90-archive/     已完成 / 已废弃
```

然后在 `doc-index.yaml`：

```yaml
sections:
  auto: true
  promote:
    - "docs/00-now"
    - "docs/10-next"
    - "docs/20-design"
    - "docs/30-guide"
    - "docs/40-business"
    - "docs/90-archive"
  overrides:
    "docs/00-now":
      title: "🟢 NOW — 当前在执行"
      color: "#27ae60"
    "docs/10-next":
      title: "🟡 NEXT — 已设计待开工"
      color: "#e67e22"
    "docs/20-design":
      title: "📐 DESIGN — 架构 + 长期参考"
      color: "#2d5f8a"
      collapsed: true
    "docs/30-guide":
      title: "📖 GUIDE — API / 操作手册"
      color: "#8e44ad"
      collapsed: true
    "docs/40-business":
      title: "💼 BUSINESS"
      color: "#95a5a6"
      collapsed: true
    "docs/90-archive":
      title: "📦 ARCHIVE"
      color: "#7f8c8d"
      collapsed: true
```

升格的 section 永远渲染在**最前面**，按 `promote` 列表声明的顺序。向后兼容——不配 `promote` 行为完全不变。

## Viewer 行为

doc-index 把不同类型路由到合适的 viewer：

- PDF / 图像 / SVG → 内嵌预览
- MD → 内置 markdown viewer
- YAML → 内置 YAML viewer（可浏览、可过滤）
- IPYNB → 新标签页打开（浏览器直接渲染）
- Office（doc / docx / xls / xlsx / ppt / pptx）→ 本地 `office-viewer.html`：
  优先用预转 PDF 走 PDF.js 预览；缓存未命中时降级为浏览器内的 SheetJS /
  mammoth.js 渲染。详见下方 **Office 预览**。

### Office 预览（PDF 预转换）

如果 doc-index 套了 basic auth，微软的 Office Online viewer
（`view.officeapps.live.com`）就用不了——微软的服务器无法拿到带认证的文件。
doc-index 改为在本地把 Office 文件预先转成 PDF，通过自带的 PDF.js viewer
展示。`serve.root` 下的布局：

```
pdf-cache/
  index.json            # repo 内相对路径 → {key, mtime, size, sha256}
  <key>.pdf             # 转换后的 PDF，key = 源文件 sha256[:16]
```

每次 `scan.py` 跑完会自动调用 `scripts/convert-office.py`（共用同一份
config）。脚本会：

- 跟随 symlink 遍历 `repo.path`，挑出 Office 扩展名
- 对 mtime+size+sha256 命中缓存的文件跳过
- 用 **LibreOffice headless**（`libreoffice --headless --convert-to pdf`）
  转换
- 极少数 LibreOffice 打不开的 .pptx / .docx，自动用 `python-pptx` /
  `python-docx` 重新保存后重试
- 清理源文件已删除的孤儿 PDF

客户端兜底依赖（`sheetjs.min.js`、`mammoth.min.js`）已自托管在 serve 根
目录，**不走 CDN**、不需要 SRI、在 `script-src 'self'` 的严格 CSP 下也能
工作。这套兜底只在缓存未命中时触发——一旦某个文件转过一次，后续都直接
走 PDF。

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

**必需**

- Python 3.8+
- PyYAML（`pip install pyyaml`）
- nginx（在运行，且对 serve 目录有读权限）
- `htpasswd`（apache2-utils）或 `openssl`，认证生成需要其中之一

**可选**

- Pillow —— `icon.py` 自动生成 PWA 图标时用到
- **LibreOffice**（writer + impress + calc）—— Office → PDF 预览
  - Debian/Ubuntu: `apt install libreoffice-writer libreoffice-impress libreoffice-calc`
  - RHEL/Fedora/OpenCloudOS: `dnf install libreoffice-writer libreoffice-impress libreoffice-calc`
- **python-pptx / python-docx / openpyxl** —— 修复 LibreOffice 打不开的
  pptx / docx（soft 兜底；只在 `convert-office.py` 输出有 "failed" 时才需要装）：
  `pip install python-pptx python-docx openpyxl`

不装 LibreOffice 时 PWA 不会挂，只是 Office 文件会降级：`.docx` / `.xlsx`
走浏览器内 JS 渲染；`.doc` / `.xls` / `.ppt` / `.pptx` 降级成下载提示。

## 协议

MIT —— 见 [LICENSE](./LICENSE)。

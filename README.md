# MyKB

**一个以 Markdown 源文件为中心的自托管知识库。**

整理笔记、面试题、代码练习、学习路径和论文阅读记录；在浏览器中编辑文档，为不同账号设置可见范围，并保存各自的收藏与学习记录。

![Checks](https://github.com/Jafekin/mykb/actions/workflows/checks.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-b75a30.svg)

## 功能

- **Markdown 文档管理**：全文搜索、分类筛选、最近修改时间、目录导航、数学公式和代码高亮。
- **所见即所得编辑**：新建、编辑与删除文档，直接写回源文件；修改前备份，删除后移入回收目录。
- **账号与权限**：必须登录后读取正文。管理员可添加、删除用户，重设密码，并配置分类可见性及新建、编辑、删除权限。
- **个人收藏**：收藏站内文档，或粘贴外链自动读取标题、简介与封面；没有封面时展示文字卡片。收藏、进度和草稿按账号保存在服务器。
- **代码练习**：带语法高亮的编辑区、草稿保存和代码下载；可选的 Python/PyTorch 隔离评测。
- **阅读体验**：深浅主题、移动端布局、离线可读的正文与公式、学习记录 JSON 导出。

## 快速开始

需要 Linux、Python 3.11+、Node.js 20+ 和 npm。Python 服务本身只使用标准库；在线评测另有依赖。

```bash
git clone https://github.com/Jafekin/mykb.git
cd mykb
npm ci
npm run setup
npm run build
npm start
```

打开 **http://127.0.0.1:4173**。初始账号为 `admin`，随机生成的密码保存在：

```bash
cat private/admin-initial-password.txt
```

登录后，在右上角齿轮菜单中修改密码、管理用户。每个实例独立生成初始密码，仓库不提供固定密码。

`npm run setup` 会创建知识库目录并写入原创示例；已有文件不会被覆盖。示例用于演示，不包含抓取的第三方文章。

## 接入自己的知识库

默认目录结构：

```text
knowledge-base/
├── note/           # Note
├── 面试题/
├── 手撕题/
├── 学习路径/
└── 最新论文/
```

每个栏目的子文件夹对应内容分类，根目录中的文档归入“综合”。分类设置以网站实际导入的文件为准。Note 默认按修改时间从新到旧排列。

复制配置示例，按需修改路径、监听地址和站点名称：

```bash
cp config.example.json config.local.json
```

相对路径以项目目录为基准。也可使用环境变量覆盖配置：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `MYKB_CONTENT_ROOT` | 项目下的 `knowledge-base/` | 知识库源目录 |
| `MYKB_NOTES_ROOT` | 源目录下的 `note/` | 独立笔记目录 |
| `MYKB_HOST` | `127.0.0.1` | 监听地址 |
| `MYKB_PORT` | `4173` | 监听端口 |
| `MYKB_SITE_NAME` | `MyKB` | 网站名称 |
| `MYKB_SITE_LOGO` | `/logo.svg` | 网站图标路径 |

修改内容路径后重新构建并重启服务；直接在磁盘增删 Markdown 后，管理员可点击右上角刷新图标重建索引。只修改前端时运行 `npm run build:ui`。

## 权限与个人数据

管理员始终拥有所有权限。普通用户可被设为只读，或分别获得新建、编辑、删除权限；分类可见性可选择全部分类（包括今后新增的分类），也可指定分类。

权限在服务器端检查，适用于索引、搜索、正文、附件和文档操作接口。隐藏按钮只是界面反馈，不能替代接口校验。删除用户会删除其个人数据并撤销会话；改密也会撤销已有会话。

| 目录 | 内容 |
| --- | --- |
| `private/` | SQLite 账号、登录会话、个人收藏、进度与草稿 |
| `knowledge-base/` | Markdown 源文档与附件 |
| `content-backups/` | 编辑前的历史备份 |
| `content-trash/` | 删除的文档及恢复路径记录 |
| `dist/` | 构建出的前端与文档索引 |

这些目录均被 Git 忽略。备份时先停止服务，再复制知识库、`private/`、历史备份及回收目录。**不要只备份前端构建文件。**

## 部署与在线评测

默认仅监听本机。内网或 Tailscale 部署、systemd 服务示例、文件写权限和可选评测环境见 [部署说明](docs/deployment.md)。这不是静态站点：登录、收藏持久化和编辑需要 Python 服务，不能直接用 GitHub Pages 托管全部功能。

在线评测使用 Linux、bubblewrap、systemd 用户服务和独立的 PyTorch 环境，包含资源与超时限制。依赖不可用时明确返回“评测环境未配置”，不会退回在宿主机直接执行提交代码。默认示例提供一道 ReLU 练习；内置评测定义覆盖 14 个算子与训练相关题型，新增题目需要匹配约定的接口和文件标识。

## 开发与检查

```bash
npm ci
npx playwright install chromium
npm test
```

检查会启动一个临时实例，使用示例知识库和独立账号数据库，结束后自动清理，**不会修改正在使用的知识库或收藏**。覆盖强制登录、分类可见性、接口权限、用户增删、会话撤销和收藏跨浏览器恢复。可通过 `CHROMIUM_PATH` 指定已有 Chromium。

```text
src/                  前端页面、样式、编辑器
scripts/serve.py       HTTP 服务、文档 API、隔离评测
scripts/accounts.py    账号、会话和个人数据
scripts/import_content.py  Markdown 导入与索引
scripts/link_metadata.py   外链预览读取
examples/             原创示例文档
docs/                 部署与贡献说明
```

欢迎提交问题和改进；请参阅 [贡献说明](CONTRIBUTING.md) 与 [安全说明](SECURITY.md)。

## 许可与内容来源

应用代码和仓库中的原创示例使用 [MIT License](LICENSE)。用户自行导入的文档、图片和外链文章保留各自原有权利，不因导入 MyKB 而改变许可。此项目不分发个人知识库，也不代表任何第三方内容网站。

# 自动同步与索引缓存

`scripts/auto_sync.py` 监听知识库变更，自动更新网站索引、提交 Git 并推送到 **GitHub 私有仓库**。脚本与网站共用 `config.local.json` 中的知识库路径，默认每 5 秒检查一次，文件稳定 20 秒后执行。它不依赖网站登录密码。

索引构建脚本是 `scripts/import_content.py`。内容未变时复用 `dist/data/index.json` 和正文缓存，不重复构建。网页访问只读取缓存；网页编辑已经更新过索引时，自动同步会跳过重复构建。图片也参与变更检测。重建索引不会提交应用的 `dist/` 到知识库仓库。

## 前置条件

需要 Python 3、Git、GitHub CLI（`gh`），后台服务示例适用于 Linux systemd 用户服务。先按 README 完成网站的安装和首次构建。

知识库需要是一个**独立 Git 仓库**，不能直接使用 MyKB 应用代码的仓库。`origin` 的推送地址必须与 `sync_remote` 完全一致，当前分支须与 `sync_branch` 一致，并配置 Git 提交作者：

```bash
gh auth login
gh auth setup-git
git -C /path/to/knowledge-base config user.name "Your Name"
git -C /path/to/knowledge-base config user.email "you@example.com"
git -C /path/to/knowledge-base remote -v
```

先手工完成一次提交与推送，确保账号可访问目标私有仓库。知识库自己的 `.gitignore` 应排除系统缓存、同步冲突副本和本地密钥。使用 Syncthing 时，每台设备的 `.stignore` 都应忽略 `.git`，不要同步 Git 内部状态。

## 配置

在现有 `config.local.json` 中合并以下设置，保留原有网站配置：

```json
{
  "content_root": "/path/to/knowledge-base",
  "notes_root": "/path/to/knowledge-base/note",
  "sync_remote": "https://github.com/OWNER/PRIVATE-REPO.git",
  "sync_branch": "main",
  "sync_poll_seconds": 5,
  "sync_settle_seconds": 20,
  "sync_retry_seconds": 60
}
```

`sync_remote` 必须设置，支持 GitHub HTTPS 或 `git@github.com:OWNER/REPO.git` 地址。私有属性通过 GitHub API 核实；无法确认私有时不会推送。间隔须为正数。

可选设置：`sync_gh` 指定 `gh` 可执行文件的绝对路径；`sync_state_dir` 指定日志与进程锁目录，默认 `mykb/private/auto-sync/`。这些设置也支持环境变量，如 `MYKB_SYNC_REMOTE`。日志轮转保留，默认文件为 `private/auto-sync/sync.log`。凭据使用 GitHub CLI/Git 的本机认证配置，不写入知识库或应用源码。

## 启动

先在 MyKB 目录前台运行，检查配置：

```bash
python3 scripts/auto_sync.py
```

确认正常后用 Ctrl+C 结束。后台运行时，将 `deploy/jkb-auto-sync.service.example` 复制到 `~/.config/systemd/user/jkb-auto-sync.service`，将模板中的 `/opt/mykb` 替换为真实安装路径，然后执行：

```bash
systemctl --user daemon-reload
systemctl --user enable --now jkb-auto-sync.service
systemctl --user status jkb-auto-sync.service
```

用户服务如需在退出登录后继续运行，可由系统管理员启用对应账号的 linger：

```bash
sudo loginctl enable-linger "$USER"
```

服务账号需要读取知识库、写入知识库的 `.git/` 和索引目录，并可调用 Git 与 GitHub CLI。不要同时运行两份监听程序；进程锁会阻止重复启动。

## 日常操作

```bash
# 查看日志
tail -n 30 private/auto-sync/sync.log
# 暂停、恢复或重启
systemctl --user stop jkb-auto-sync.service
systemctl --user start jkb-auto-sync.service
systemctl --user restart jkb-auto-sync.service
# 取消开机自动启动
systemctl --user disable --now jkb-auto-sync.service
```

单独重建索引：

```bash
python3 scripts/import_content.py          # 变化时重建，否则复用缓存
python3 scripts/import_content.py --force  # 强制重建
```

网站右上角重建按钮也是强制刷新。网站评测映射会在索引更新后自动刷新，无需重启网站。

## 故障与同步边界

- GitHub 断网：本地索引仍会先更新，本地提交保留，默认 60 秒后重试推送。
- 远端有新提交：程序不会自动拉取、rebase 或强制推送。先暂停服务，在知识库仓库执行 `git pull --rebase`，解决冲突后恢复服务。
- 正在合并、rebase 或有未解决冲突：暂停自动处理，保留本地内容。
- 修改了分支或 `origin` 推送地址：拒绝自动操作；修改配置或恢复远端后重启服务。
- 知识库不可用、磁盘只读或索引构建失败：记录错误并重试，不删除本地提交。先排查挂载状态、目录权限与日志。

自动提交包含知识库中所有未被 Git 忽略的新增、修改和删除。GitHub 仓库存储文档与图片，账号数据库、个人收藏和网站编辑备份仍属于 MyKB 的本地数据，需分别备份。

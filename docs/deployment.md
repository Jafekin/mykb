# 部署说明

## 内网访问

在 `config.local.json` 中将 `host` 设为服务器的内网或 Tailscale 地址，然后启动 Python 服务。也可临时指定地址：

```bash
npm start -- --host 192.168.1.10 --port 4173
```

访问该地址的设备必须能连接服务器。不要把默认 HTTP 服务直接暴露到公网；跨不受信任网络使用时，应通过 HTTPS 终止代理部署，并按实际架构配置安全 Cookie。当前 Cookie 使用 HttpOnly 和 SameSite=Strict，HTTP 内网部署没有 Secure 标记。

## systemd 用户服务

将 `deploy/mykb.service.example` 复制到 `~/.config/systemd/user/mykb.service`，把其中的 `/opt/mykb` 替换为实际路径：

```bash
systemctl --user daemon-reload
systemctl --user enable --now mykb
systemctl --user status mykb
```

重启与查看日志：

```bash
systemctl --user restart mykb
journalctl --user -u mykb -f
```

服务账号需要读取知识库，并写入知识库源目录、`private/`、`dist/`、`content-backups/` 和 `content-trash/`。如果添加 systemd 文件系统保护设置，也要明确允许这些路径。先完成初次构建，再启动服务。

## 可选的在线评测

评测需要 Linux、bubblewrap、可用的 systemd 用户管理器，以及安装了 PyTorch 的独立 Python 环境：

```bash
python3 -m venv .judge-venv
.judge-venv/bin/python -m pip install torch
```

通过系统包管理器安装 `bubblewrap`。运行服务的账号需要能够执行 `systemd-run --user --scope`，系统也必须允许所需的命名空间。安装依赖并不代表所有平台均已验证；先用示例 ReLU 题提交简单解法，检查隔离运行是否正常。

代码在无网络的隔离命名空间内执行，限制 CPU、墙钟时间、内存、进程数和输出量；宿主目录不挂载到沙箱。服务每个来源地址每分钟最多接受 60 次操作，登录最多 12 次，个人状态保存独立处理；最多同时运行两个评测。评测环境缺失时返回明确错误，不执行无隔离的代码。

## 外链预览

服务从公开 HTTP/HTTPS 网页读取标题、简介与封面元数据，允许编辑后再收藏。重定向重新检查地址；拒绝内网地址，限制响应大小与连接时间。不会运行远端 JavaScript，也不会抓取全文。

如运行环境需要代理，可为服务配置标准 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量。不要将代理凭据写入仓库。网站拒绝抓取、缺少元数据或依赖客户端渲染时，可以手动填写；没有封面就不显示照片。

## 数据与升级

更新源码前备份知识库和 `private/`。更新后运行 `npm ci`、`npm run build` 并重启服务。`config.local.json`、用户数据库与知识库文件被 Git 忽略，更新代码时应保留。

浏览器收藏迁移只适用于初始管理员账号：旧单用户浏览器中的收藏、外链、进度和草稿会合并到该账号；迁移成功后移除旧公共缓存。新账号不会继承其他人的记录。

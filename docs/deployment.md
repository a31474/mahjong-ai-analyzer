# 部署教程（服务端）

面向把 `mahjong-ai-analyzer` 常驻在一台 Linux 服务器上的场景：FastAPI 单进程 + 静态前端，nginx 反代并限速。

模板文件：

- [`deploy/mcr-ai.service`](../deploy/mcr-ai.service)：systemd unit（用户级；文件内注释说明了改成系统级的差异）
- [`deploy/nginx.conf`](../deploy/nginx.conf)：nginx 反代 + 按 IP 限速 + 静态资源缓存

## 1. 资源与前置

| 项目 | 要求 |
|---|---|
| 系统 | Linux x86_64，`git`、`uv`、`gcc`/`g++`（编译 PyMahjongGB）、`curl` |
| CPU/内存 | 单核可用；模型 3×26MB，运行内存 ~250MB（单学生更低） |
| 端口 | 后端只监听 `127.0.0.1:8000`，不对外 |
| 网络 | 服务器需能访问 `salasasa.cn`（按 game_id 拉牌谱）与 HuggingFace（下载权重） |

前端**只需构建一次**：可以在本地 `npm run build` 后把 `web/dist/` 传上服务器，服务器不必装 node。

**不要用 `--workers N`**：模型只在进程内加载一次，多 worker 会让 LRU 缓存互相看不见、内存翻倍。

## 2. 首次部署

```bash
# 1) 代码
git clone <仓库地址> ~/project/mahjong-ai-analyzer
cd ~/project/mahjong-ai-analyzer

# 2) Python 环境（uv 管理，Python 3.12；PyMahjongGB 从源码编译，gcc 必备）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 3) 模型权重（~80MB，来自 HuggingFace）
bash backend/fetch_weights.sh
ls -lh backend/weights/*.npz

# 4) 前端产物（二选一）
#    A. 服务器上构建：cd web && npm install && npm run build && cd ..
#    B. 本地构建后上传（服务器无 node 时用这个）：
#       rsync -a --delete web/dist/ <user>@<host>:~/project/mahjong-ai-analyzer/web/dist/

# 5) 手动验证能起来（前台跑，Ctrl-C 退出）
PYTHONPATH=backend .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 另开一个终端：
curl -s http://127.0.0.1:8000/api/health        # {"status":"ok","model":"ready"}
curl -s http://127.0.0.1:8000/ | grep -q '<div id="app"' && echo OK
```

> 用 `.venv/bin/python -m uvicorn` 而不是直接跑 `.venv/bin/uvicorn`：前者不依赖脚本 shebang 里写死的解释器路径，换机器/换 venv 后更不容易报「错误的解释器」。

### 2.1 常驻（systemd）

```bash
mkdir -p ~/.config/systemd/user
cp deploy/mcr-ai.service ~/.config/systemd/user/mcr-ai.service
sed -i "s#<APP_DIR>#$PWD#g" ~/.config/systemd/user/mcr-ai.service
systemctl --user daemon-reload
systemctl --user enable --now mcr-ai
loginctl enable-linger "$USER"          # 关键：SSH 注销/服务器重启后服务仍运行
systemctl --user status mcr-ai
journalctl --user -u mcr-ai -f         # 看日志
```

用户级 unit 的两个常见坑：

1. **`[Install] WantedBy` 必须是 `default.target`**。写 `multi-user.target`（系统级 target）在 `--user` 模式下无效，`enable` 不会真正开机自启。
2. **必须 `loginctl enable-linger <user>`**，否则用户退出登录后 systemd user manager 被回收，服务跟着停。检查：`loginctl show-user "$USER" | grep Linger` 应为 `Linger=yes`。

改成系统级 unit 时：去掉命令里的 `--user`、`WantedBy` 改回 `multi-user.target`、并在 `[Service]` 里加 `User=`/`Group=`。

`ExecStartPost=scripts/healthcheck.sh` 是启动自检：模型加载成功（`/api/health` 200）才算启动完成，否则 systemd 判 `failed` 并按 `Restart=always` 重试。**别把它注释掉**，否则进程活着但模型没加载（接口 503）时 systemd 仍显示 running，不容易发现。

### 2.2 nginx 反代

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/mcr-ai.conf
sudo sed -i "s#<DOMAIN>#mcr.example.com#g; s#<CERT>#/etc/nginx/ssl/fullchain.cer#g; s#<KEY>#/etc/nginx/ssl/private.key#g" /etc/nginx/conf.d/mcr-ai.conf
sudo nginx -t && sudo systemctl reload nginx
```

签名证书两条路：

- `sudo certbot --nginx -d <域名>`（certbot 会自己改 80 端口那个 server 块）
- 已有证书：直接把 `<CERT>`/`<KEY>` 指到实际路径

要点：

- **限速必须有**：`prepare` 6r/m、`step` 60r/m，按 IP 计。NAT 共享出口（公司/校园网）可能互相挤占，按需放宽。
- **80 端口要跳 HTTPS**：模板里 `location / { return 301 https://$host$request_uri; }`。只写 `server_name` 不写内容会返回 nginx 默认页。
- **gzip 要真的开**：`gzip_types` 只有配合 `gzip on;` 才生效，检查 `nginx -T | grep "gzip on"`（主 `nginx.conf` 里已开就删掉模板那行）。
- **HTTP/2 语法**：`http2 on;` 需要 nginx ≥ 1.25.1，旧版本改成 `listen 443 ssl http2;`。
- **静态资源缓存**：`/assets/` 是 Vite 产物（文件名带 hash）可长缓存；`/game2d-assets/`（牌面、音效，文件名不带 hash）给 1 天缓存 + ETag。刚换过牌面时可临时改成 `no-cache`。
- 若以后套 CDN/Cloudflare，限速取的是 `$binary_remote_addr`（真实客户端 IP 会变成 CDN 节点），需要配 `real_ip` 模块，否则所有人共用一个限速桶。国内服务器一般**不建议**加 CF。

## 3. 更新部署

| 改动类型 | 需要做什么 |
|---|---|
| 只改前端 | 本地 `npm run build` → `rsync -a --delete web/dist/ <user>@<host>:~/project/mahjong-ai-analyzer/web/dist/`（**不用重启服务**，后端直接读磁盘上的 dist） |
| 只改后端 | `git pull` → `systemctl --user restart mcr-ai`（依赖有变时先 `uv pip install --python .venv/bin/python -r requirements.txt`） |
| 权重更新 | `bash backend/fetch_weights.sh` → 重启服务 |
| 其他 | 模板类文件改动：`sudo nginx -t && sudo systemctl reload nginx` |

`web/dist/` 不入库（`.gitignore`），所以服务器上 `git pull` 不会带来新前端，必须单独同步 dist。

**前端更新特别注意**（同步 open_mahjong_unity 2D 界面那次踩过）：

1. `rsync` 一定要带 `--delete`：牌面资源改名过（`Man1.svg` → `11.svg`、花牌改 `Unity/51.svg`），不带 `--delete` 会残留旧文件。
2. 浏览器可能缓存旧的 `game2d-assets`：让用户强刷一次，或临时把 `/game2d-assets/` 改成 `Cache-Control: no-cache` 再改回来。

## 4. 更新后自检清单

```bash
curl -s http://127.0.0.1:8000/api/health                      # 模型就绪
curl -s -o /dev/null -w '%{http_code}\n' https://<域名>/       # 首页 200
curl -s -o /dev/null -w '%{http_code}\n' https://<域名>/game2d-assets/textures/riichi-mahjong-tiles/Regular/11.svg
# 真跑一局（用已缓存的 game_id，避免依赖平台网络）：
curl -s -X POST https://<域名>/api/analyze/prepare -H 'Content-Type: application/json' \
  -d '{"game_id":"maRXmmjmqR"}' | head -c 200
```

浏览器侧：打开首页输入页 → 填 `maRXmmjmqR` → 进入回放页 → 推进到任一「打出」节点，左上角 AI 面板应显示 top3 概率。

## 5. 排错

| 现象 | 原因 / 处理 |
|---|---|
| `/api/health` 返回 503 或 `model":"missing` | 权重没下载或路径不对：`bash backend/fetch_weights.sh`，确认 `backend/weights/kdens_s*.npz` 存在 |
| systemd 状态 running 但接口 503 | `ExecStartPost` 自检被注释；日志看 `journalctl --user -u mcr-ai` |
| `Failed to enable unit` | 用户级 unit 的 `WantedBy` 写成了 `multi-user.target`，改成 `default.target` |
| 服务在 SSH 退出后消失 | 没执行 `loginctl enable-linger $USER` |
| `错误的解释器: ... .venv/bin/python` | venv 是拷贝/移动过来的，shebang 失效；重建 venv，或改用 `python -m uvicorn` 启动 |
| prepare 报拉取失败 | 服务器访问不了 `salasasa.cn`；或 game_id 不存在；已分析过的牌谱有磁盘缓存，可离线查看 |
| 429 / 503 且来自 nginx | 命中限速：`limit_req` 的 `rate`/`burst` 档位，或同一出口 IP 的多人共享额度 |
| 牌面 404 / 显示旧牌面 | dist 没同步或没带 `--delete`；浏览器缓存未刷新 |
| 磁盘满 / 缓存过大 | `backend/cache/` 会累积（step 结果上限 5000 个文件、牌谱 200 个），可 `rm -rf backend/cache/` 清空（会丢失重启保留的分析缓存） |

## 6. 维护

```bash
systemctl --user restart mcr-ai         # 重启
journalctl --user -u mcr-ai -n 200      # 最近日志
journalctl --user -u mcr-ai -f          # 跟踪日志
du -sh backend/cache backend/weights    # 磁盘占用
rm -rf backend/cache                    # 清缓存（可随时删，服务会重建目录）
```

备份只需要 `backend/weights/`（可重新下载）与仓库本身；`backend/cache/` 属于可丢弃数据。

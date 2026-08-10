# mahjong-ai-analyzer

国标麻将 AI 牌谱分析服务：解析 salasasa.cn 平台的真实牌谱，用 IJCAI-2026 冠军模型（kdens3）对每一手打牌决策进行推理，展示「AI 认为应该打什么牌」与「玩家实际打了什么」的对比。

后端为纯 Python（FastAPI + numpy 推理），前端为 Vue 3 + PixiJS 回放渲染。

## 架构

```
                    ┌──────────────────────────────────────────┐
                    │                 web/ (Vue3)              │
                    │   上传牌谱 / 输入 game_id ──┐             │
                    │   回放渲染 + AI 面板 ◄──┐  │             │
                    └───────────────────────┼──┼──────────────┘
                                            │  │ HTTP
                    ┌───────────────────────┼──┼──────────────┐
                    │            backend/ (FastAPI)           │
                    │  main.py  /api/analyze/prepare          │
                    │           /api/analysis/{aid}/step      │
                    │            │             ▲              │
                    │            ▼             │              │
                    │  analyzer.prepare ──► Analyzer(LRU 缓存)│
                    │       │                        │        │
                    │       ▼                        ▼        │
                    │  converter.py          model_loader.py  │
                    │  解析/replay 牌谱       加载 3 学生权重   │
                    │       │                        │        │
                    │       ▼                        ▼        │
                    │  engine/ (IJCAI FeatureAgent)  kdens_s* │
                    │  numpy_resfused 推理 ◄── weights/*.npz  │
                    └──────────────────────────────────────────┘
```

- `backend/engine/`：IJCAI-2026 竞赛推理引擎（FeatureAgent 状态机 + numpy CNN），原样复制，未修改
- `backend/converter.py`：open_mahjong 牌谱 tick 流 → FeatureAgent 观测的转换器
- `backend/analyzer.py`：prepare（转换全部回合/视角）+ analyze_step（单节点推理，LRU 缓存）
- `backend/model_loader.py`：三学生 ensemble 加载（`ENSEMBLE=1` 时单学生）
- `web/`：Vue 3 + PixiJS 前端（回放引擎来自 open_mahjong_unity）

## 运行步骤

```bash
# 1. Python 环境（uv）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 2. 下载模型权重（约 80MB，来自 HuggingFace）
bash backend/fetch_weights.sh

# 3. 启动后端（默认 8000 端口）
PYTHONPATH=backend .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 4. 构建前端（静态文件挂载在 FastAPI 根路径）
cd web
npm install
npm run build
cd ..
```

构建完成后直接访问 `http://localhost:8000` 即可（`web/dist` 由 FastAPI 静态挂载）。

## 部署到服务器

### 前置要求（服务器）

- Linux x86_64，`git`、`uv`、`gcc`/`g++`（编译 PyMahjongGB 扩展）、`curl`（下载权重）
- **前端只需构建一次**：可在本地构建 `web/dist/` 后随代码一起传服务器，服务器无需 node
- 单核 CPU + ≥512MB 内存即可（模型 3×26MB，运行内存 ~250MB）；端口默认 8000

### 步骤

```bash
# 1. 拉取代码
git clone <你的仓库地址> mahjong-ai-analyzer && cd mahjong-ai-analyzer

# 2. Python 环境（uv 管理，Python 3.12；PyMahjongGB 从 PyPI 安装，需编译，gcc 必备）
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt

# 3. 模型权重（~80MB）
bash backend/fetch_weights.sh

# 4. 前端构建产物（若未随代码携带）
cd web && npm install && npm run build && cd ..

# 5. 验证启动
PYTHONPATH=backend .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
curl -s http://127.0.0.1:8000/ | grep -q '<div id="app"' && echo OK
```

### 常驻运行（systemd）

```ini
# /etc/systemd/system/mcr-ai.service
[Unit]
Description=mcr-ai mahjong analyzer
After=network.target

[Service]
WorkingDirectory=/opt/mahjong-ai-analyzer
Environment=PYTHONPATH=backend
ExecStart=/opt/mahjong-ai-analyzer/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 启动自检：模型加载成功（/api/health 200）才判定启动完成；失败则 systemd 报 failed
ExecStartPost=/opt/mahjong-ai-analyzer/scripts/healthcheck.sh
TimeoutStartSec=180
Restart=always
RestartSec=3
# 单核单进程即可（模型全局加载一次）；多 worker 会让 LRU 缓存失效且内存翻倍

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now mcr-ai
```

### nginx 反代 + 速率限制（公网部署）

> 单核 CPU 的瓶颈是 AI 推理（`/api/analyze/step` 单次 10-30ms），必须限速防刷。`prepare` 拉取+解析较重（~几百 ms），限得更严。

```nginx
# /etc/nginx/conf.d/mcr-ai.conf（域名替换 <YOUR.DOMAIN>；SSL 证书用 certbot 生成）
limit_req_zone $binary_remote_addr zone=mcr_prepare:10m rate=6r/m;
limit_req_zone $binary_remote_addr zone=mcr_step:10m rate=60r/m;

server {
    listen 80;
    server_name <YOUR.DOMAIN>;
    # certbot --nginx 自动改写为 443 + 证书
}

server {
    listen 443 ssl;
    http2 on;
    server_name <YOUR.DOMAIN>;
    ssl_certificate     /etc/letsencrypt/live/<YOUR.DOMAIN>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<YOUR.DOMAIN>/privkey.pem;

    client_max_body_size 20m;          # 粘贴大牌谱 JSON 用
    server_tokens off;

    # 静态资源（前端）不限制
    location /assets/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    location = / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # AI 分析接口按 IP 限速（burst 给少量抖动余量，nodelay 立即放行限速内的请求）
    location /api/analyze/prepare {
        limit_req zone=mcr_prepare burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 60s;        # 拉取平台牌谱可能较慢
    }
    location /api/analysis/ {
        limit_req zone=mcr_step burst=10 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

```bash
# 1. 证书（需先解析域名到服务器）
sudo certbot --nginx -d <YOUR.DOMAIN>
# 2. 校验配置并重载
sudo nginx -t && sudo systemctl reload nginx
# 3. 防火墙只放 80/443
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```

注意事项：

- **误伤**：限速按 IP，NAT 共享出口（如公司/校园网）可能被多人挤占限速额度；`rate` 可按需放宽
- **Cloudflare**：国内服务器**不建议加**（CF 免费版国内回源延迟大、不稳定）；源站 IP 暴露风险对本服务可接受。若以后换海外服务器再考虑 CF 隐藏源站
- **防刷加固**（可选）：`limit_req` 之外，可再加 `location` 级 `deny` 名单（恶意 IP 拉黑）、或 nginx access.log 配合 fail2ban
- uvicorn 监听 `127.0.0.1`（本小节 systemd 已改），8000 端口不对外

### 备注

- **内存**：模型加载一次约 80MB 权重 + numpy 开销，单 worker 足够；不要开 `--workers N`（缓存失效 + 内存翻倍）
- **网络**：`/api/analyze/prepare` 按 game_id 拉取时，服务器需能访问 `salasasa.cn`（或把 `platform` 指到你的内网地址）
- **上游地址**：需要 HTTPS 反代（nginx/caddy）时，代理到 `127.0.0.1:8000` 即可；本服务无鉴权，勿直接暴露公网
- **单学生模式**：`Environment=ENSEMBLE=1` 可切单学生（速度更快，精度略降）

## API 说明

### `POST /api/analyze/prepare`

输入牌谱（上传 JSON 或按 game_id 从平台拉取）：

```json
// 方式一：上传（record 为 salasasa 平台返回的完整牌谱）
{"record": {"game_id": "...", "rule": "guobiao", "record": {...}}}

// 方式二：按 game_id 拉取
{"game_id": "maRXmmjmqR", "platform": "https://salasasa.cn"}
```

响应：`{analysis_id, meta, record}`，其中 `meta` 为转换结果：

```json
{
  "game_id": "...",
  "rounds": [{
    "round_index": 1,
    "viewers": {
      "0": {"error": null, "nodes": [
        {"step": 1, "player": 0, "seat": 3, "actual_tile": "F4",
         "hand": ["B2", "T8", ...], "melds": [], "river": [], "draw": "F4"}
      ]}
    }
  }]
}
```

`viewers[v]` 是以玩家 v（original id）视角重放的回合；`nodes` 是该视角下每个「摸牌后打牌」的决策点（`step` 为 tick 序号，`actual_tile` 为玩家实际打出的牌）。`error` 非空表示该视角转换失败（见「已知限制」）。

### `GET /api/analysis/{aid}/step?round=2&step=1&viewer=0`

对单个决策点做 AI 推理，返回：

```json
{
  "step": 1, "player": 0, "seat": 3, "actual_tile": "F4",
  "ai_top": [{"tile": "F4", "prob": 0.866}, {"tile": "F1", "prob": 0.0668}, ...],
  "agree": true
}
```

- `ai_top`：模型概率最高的 3 个合法打牌（含概率）
- `agree`：模型首选与玩家实际打牌是否一致

## 牌谱转换说明

后端将 salasasa 平台（open_mahjong）的 tick 流逐条喂给 IJCAI 推理引擎，关键约定：

- **花牌剔除**：open_mahjong 花牌 id 51-58（春夏秋冬梅兰竹菊）不计入引擎手牌；起手 `bh`（补花）+ `bd`（补摸）成对处理，`bd` 的补摸者按 `bh` 的补花者确定
- **吃牌中间张**：`cl/cm/cr` 的 tick[1] 是被吃的弃牌，引擎 Chi 需要顺子中间张——`cl` 弃牌是顺子右端（-1）、`cm` 中间（0）、`cr` 左端（+1）；换算后越界（如 `cr` 吃 9 → 10）判为数据异常
- **player_index 域（原"original 域"）**：牌谱权威约定（`game_record_format.md:60`）——`p*_tiles` 下标与 tick 中玩家字段（`bh`/`bd` 补花补摸者、`cl/cm/cr/p/g` 鸣牌者、`hu` 和牌者）均为**当局 player_index**（门风位）。`seats[original] = player_index` 仅用于 original ↔ player_index 映射：分析视角以 original 标识，重放时经 `seats` 取该玩家的手牌与座位。摸/打轮转按 player_index。
- **庄家起手 14 张**：`p0_tiles` 恒为庄家 14 张（13 + 首摸 1），剔花后 14 张合法，不做「>13 即异常」误判

## 性能基准

```bash
PYTHONPATH=backend .venv/bin/python scripts/bench_step.py
# 可选: --record <牌谱> --round <局号> --viewer <视角> --iterations <推理次数>
```

输出：prepare 解析耗时、单步分析（冷缓存：重放+3 学生推理 / 热缓存：LRU 命中）、纯推理均值、整局估算。

参考量级（单核 CPU）：单步 ~150-200ms、热缓存命中 0ms、单视角整局 ~2-3s。单核上 numpy 推理耗时波动较大（±20-30%），属正常。

## 测试

```bash
PYTHONPATH=backend .venv/bin/pytest tests/ -v
```

27 个测试全过，含 `tests/test_e2e.py`（权重存在时跑真实模型推理，验证 round 2 viewer 0 首打 T1 概率 ≈ 0.959）。

## 已知限制

- **单学生模式**：默认三学生 ensemble；环境变量 `ENSEMBLE=1` 时仅加载 `kdens_s0_fp16.npz`（单学生，速度更快、精度略降）
- **转换失败局/视角跳过**：个别牌谱数据异常（如起手剔花后 >14 张、鸣牌时手牌缺失）会导致该 viewer 转换失败，`prepare` 中标记 `error` 并跳过，不影响其他视角
- **庄家首打决策点缺失**：庄家起手 14 张（首摸已含）时，首个打牌（首摸后打）无对应 d 事件，无法生成决策点——节点流从庄家的第二个决策点开始
- **xunmuNodes seats 错位（遗留）**：前端回放引擎（来自 open_mahjong_unity）对 `xunmuNodes` 的 seats 字段存在已知错位 bug，仅影响部分回放视角的座位标注，不影响 AI 分析
- **补杠（`jg`）不进入手牌流**：`jg`（补杠）事件不产生打牌决策点，仅更新引擎状态

## 许可与出处

- `backend/engine/`：来自 IJCAI-mahjong 竞赛代码（mcr-ai/IJCAI-mahjong/deploy/caiest_cnn），**无 LICENSE**，仅作研究用途
- `web/src/game2d/`：回放渲染引擎来自 `open_mahjong_unity`（前端），MIT 许可
- `web/public/game2d-assets/`：音效/贴图资产，见 `game2d-assets/sounds/ATTRIBUTION.md`
- 模型权重 `backend/weights/*.npz`：来自 HuggingFace `Dannibal/ijcai-mahjong-ckpts-2026`（champion/ 目录，IJCAI-2026 亚军 bot kdens3），见 `backend/weights/README.md`；权重不入库，需 `bash backend/fetch_weights.sh` 下载
- 牌谱数据：salasasa.cn 平台公开对局

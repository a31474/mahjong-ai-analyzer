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
  - 2D 回放界面已同步上游 `open_mahjong_unity` 提交 `4db27ac0`（dev ver 0.4.76.6，2026-09-17）：`web/src/game2d/`、`web/src/views/game2d/`、`web/src/constants/`、`web/src/i18n/`、`web/public/game2d-assets/`
  - 本地定制（上游同步时保留）：`web/src/game2d/ai/api.ts`（AI 接口）、`Replay.vue` 的 AI 复盘面板（默认右上角，拖动标题可移动、位置记在 `localStorage`、双击标题复位）与牌谱输入页、`salasasa/api.ts` 精简（去掉站点登录相关接口）、`replay/recordReplay.ts` 的最终分缺失兜底
  - 未同步的上游改动：`@/utils/localGameRecordStore`（Unity 客户端本地牌谱库）与 `@/utils/recordShareLink`（站点 2D/3D 分享链接）相关逻辑——本服务无对应页面与存储，保留原有加载/分享实现
- 相关文档：[`docs/deployment.md`](docs/deployment.md)（部署教程、自检清单、排错表）、[`docs/salasasa-botzone-conversion.md`](docs/salasasa-botzone-conversion.md)（与上游转换实现的逐项对比、牌面编码约定、观测一致性验证）

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

前端开发模式（热更新，`/api` 已配好代理到 8000）：

```bash
cd web && npm run dev     # 打开 http://localhost:5173
```

打开后是牌谱输入页：先选**平台**（当前仅 salasasa），再选**输入方式**——「链接 / 对局 ID」（填 game_id 或 2D/Unity 回放链接，由后端向平台拉取）或「牌谱 JSON」（直接粘贴牌谱上传）。示例牌谱可直接填 `maRXmmjmqR`（见 `web/public/records/sample.json`）。进入回放页后按 ←/→ 或点击推进到任一「打出」节点，右上角 AI 面板会给出 top3 概率与「实际打出」对比。

## 部署到服务器

> 可直接使用的模板与排错表：[`docs/deployment.md`](docs/deployment.md)（systemd unit 模板 [`deploy/mcr-ai.service`](deploy/mcr-ai.service)、nginx 配置模板 [`deploy/nginx.conf`](deploy/nginx.conf)）。下面是最小步骤。

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

模板：[`deploy/mcr-ai.service`](deploy/mcr-ai.service)（用户级 unit，`WantedBy=default.target`）。

```bash
mkdir -p ~/.config/systemd/user
cp deploy/mcr-ai.service ~/.config/systemd/user/mcr-ai.service
sed -i "s#<APP_DIR>#$PWD#g" ~/.config/systemd/user/mcr-ai.service
systemctl --user daemon-reload
systemctl --user enable --now mcr-ai
loginctl enable-linger "$USER"     # 关键：SSH 注销/重启后服务不被回收
systemctl --user status mcr-ai --no-pager
```

`ExecStartPost` 会执行 `scripts/healthcheck.sh`：模型加载成功（`/api/health` 返回 200）才算启动完成，否则 systemd 判 `failed` 并按 `Restart=always` 重试。
改成系统级 unit（`/etc/systemd/system/mcr-ai.service`）时：命令去掉 `--user`、`[Install]` 改回 `multi-user.target`、并在 `[Service]` 补 `User=`/`Group=`。

### nginx 反代 + 速率限制（公网部署）

模板：[`deploy/nginx.conf`](deploy/nginx.conf)——含 80 → 443 跳转、`prepare`/`step` 分接口限速、`/assets/` 与 `/game2d-assets/` 缓存头、gzip（兼容 `.js` 的新旧 MIME）。

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/mcr-ai.conf
sudo sed -i "s#<DOMAIN>#<YOUR.DOMAIN>#g; s#<CERT>#<证书链路径>#g; s#<KEY>#<私钥路径>#g" /etc/nginx/conf.d/mcr-ai.conf
sudo nginx -t && sudo systemctl reload nginx
```

注意事项：

- **限速必须有**：单核 CPU 的瓶颈是 AI 推理（实测 `step` 冷 ~0.93s、热 ~0.19s，含网络往返），`prepare` 拉取+解析更重，档位见模板
- **误伤**：限速按 IP，NAT 共享出口（公司/校园网）可能被多人挤占额度，`rate` 可按需放宽
- **gzip**：需主配置已有 `gzip on;`；`.js` 的 MIME 在新发行版是 `text/javascript`、旧版是 `application/javascript`，模板两个都列
- **Cloudflare**：国内服务器不建议加（国内回源延迟大）；限速基于 `$binary_remote_addr`，套 CDN 后须配 `real_ip`，否则所有访客共用一个限速桶
- **备案**：未备案时 80 端口可能被云厂商直接拦截（返回第三方 403 页面，请求到不了服务器），此时只走 HTTPS 即可；备案通过后模板里的跳转自动生效
- **防刷加固**（可选）：`limit_req` 之外可加 `deny` 名单，或 access.log 配合 fail2ban

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

> 与 `open_mahjong_unity` 前端转换实现（`recordConvert/botzoneGuobiao.js`）的逐项对比、牌面字母 T/B 约定与复现脚本，见 [`docs/salasasa-botzone-conversion.md`](docs/salasasa-botzone-conversion.md)。

后端将 salasasa 平台（open_mahjong）的 tick 流逐条喂给 IJCAI 推理引擎，关键约定：

- **花牌剔除**：open_mahjong 花牌 id 51-58（春夏秋冬梅兰竹菊）不计入引擎手牌；起手 `bh`（补花）+ `bd`（补摸）成对处理，`bd` 的补摸者按 `bh` 的补花者确定
- **花牌打出/不补**：玩家摸切打出花牌（`c` 事件带花）不进引擎仅轮转（无决策点、不崩溃）；玩家起手/摸花不补留在手里时花不进引擎，观测手牌 = 真实手牌的数牌部分（**内容逐张正确**），但观测张数比训练分布少 1 张（正常决策点 14 张、不补花玩家恒 13 张）——规则差异的固有偏差，模型建议基于正确牌型、校准度略降
- **吃牌中间张**：`cl/cm/cr` 的 tick[1] 是被吃的弃牌，引擎 Chi 需要顺子中间张——`cl` 弃牌是顺子右端（-1）、`cm` 中间（0）、`cr` 左端（+1）；换算后越界（如 `cr` 吃 9 → 10）判为数据异常
- **player_index 域（原"original 域"）**：牌谱权威约定（`game_record_format.md:60`）——`p*_tiles` 下标与 tick 中玩家字段（`bh`/`bd` 补花补摸者、`cl/cm/cr/p/g` 鸣牌者、`hu` 和牌者）均为**当局 player_index**（门风位）。`seats[original] = player_index` 仅用于 original ↔ player_index 映射：分析视角以 original 标识，重放时经 `seats` 取该玩家的手牌与座位。摸/打轮转按 player_index。
- **庄家起手 14 张**：`p0_tiles` 恒为庄家 14 张（13 + 首摸 1），剔花后 14 张合法，不做「>13 即异常」误判
- **牌面字母约定**：`W`=万（11-19）、`B`=筒（21-29）、`T`=索（31-39），与 Botzone 官方协议、PyMahjongGB 一致（`backend/tiles.py`）。2026-09 前该映射曾反写（筒→T、索→B），已修正；`reset` tick 也改为以 `tick[1]` 为准（与回放引擎一致）。磁盘缓存键内含 `tiles.py`/`converter.py` 内容指纹，改转换逻辑后旧缓存自动失效。依据与实测见 [`docs/salasasa-botzone-conversion.md`](docs/salasasa-botzone-conversion.md) §3/§5

## 缓存

| 缓存 | 位置 | 内容 | 生命周期 |
|---|---|---|---|
| prep 内存缓存 | `main._prep_cache`（LRU cap 20） | `analysis_id → prepare 结果`（节点元数据 + round 重建数据） | 进程内，重启失效 |
| step 内存缓存 | `Analyzer.cache`（LRU cap 2000） | `(cache_key, round, step, viewer) → 单步分析结果` | 进程内，重启失效 |
| **step 磁盘缓存** | `backend/cache/`（gitignore，文件数上限 5000） | 同上（JSON，原子写），键含转换指纹 | **重启保留**（改转换逻辑即失效） |
| **牌谱磁盘缓存** | `backend/cache/record/`（gitignore，文件数上限 200） | 原始牌谱 JSON + players/rule（按 game_id，上传按内容 sha1） | **重启保留**（与转换逻辑无关） |

- step 磁盘缓存键为 `enc<内容指纹>|game_id`（或 `|sha1:<上传内容>`），不依赖 `analysis_id`——重启或新会话后同一牌谱已分析过的步直接命中磁盘（0 推理）
- 指纹取自 `backend/tiles.py` + `backend/converter.py` 的内容，**改了映射/事件处理就自动失效**，无需手工递增版本号或清缓存（历史教训：只按牌谱+位置做键时，改完映射仍读到按旧约定算出的结果）
- 牌谱磁盘缓存让同一 game_id 的 prepare 跳过平台拉取（含重启后）；上传路径按内容 sha1 去重
- 清空缓存：`rm -rf backend/cache/`

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

48 个测试全过，含 `tests/test_e2e.py`（权重存在时跑真实模型推理，校验 round 2 viewer 1 首打 `B1` 与 top-k 概率合法性）。

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/healthcheck.sh` | 启动自检（轮询 `/api/health`），供 systemd `ExecStartPost` 调用 |
| `scripts/bench_step.py` | 单步推理性能基准（见「性能基准」节） |
| `scripts/compare_botzone_conversion.py` | 对比上游 `recordConvert/botzoneGuobiao.js` 与本仓库 `converter.py`：reset tick 统计、双跑输出、牌面编码约定校验 |
| `scripts/upstream_botzone_lines.mjs` | 被上一个脚本调用：用上游实现导出指定小局的 Botzone 协议行 |
| `scripts/verify_feature_parity.py` | 观测 parity：本仓库 `engine/feature.py` 与 IJCAI 训练主线（源码 sha1 + 运行时 obs 逐位/valid 比对） |

```bash
# 转换实现对比（上游仓库默认 ../open_mahjong_unity，可用 OPEN_MAHJONG_UNITY 覆盖）
PYTHONPATH=backend .venv/bin/python scripts/compare_botzone_conversion.py

# 观测一致性（IJCAI 仓库默认 ../mcr-ai/IJCAI-mahjong，可用 --ijcai 覆盖）
PYTHONPATH=backend .venv/bin/python scripts/verify_feature_parity.py --rounds 3
```

结论见 [`docs/salasasa-botzone-conversion.md`](docs/salasasa-botzone-conversion.md)：转换实现逐项对比（§2–§5）、观测一致性验证（§9）。

## 已知限制

- **单学生模式**：默认三学生 ensemble；环境变量 `ENSEMBLE=1` 时仅加载 `kdens_s0_fp16.npz`（单学生，速度更快、精度略降）
- **转换失败局/视角跳过**：个别牌谱数据异常（如起手剔花后 >14 张、鸣牌时手牌缺失）会导致该 viewer 转换失败，`prepare` 中标记 `error` 并跳过，不影响其他视角
- **xunmuNodes seats 错位（遗留）**：前端回放引擎（来自 open_mahjong_unity）对 `xunmuNodes` 的 seats 字段存在已知错位 bug，仅影响部分回放视角的座位标注，不影响 AI 分析
- **补杠（`jg`）不进入手牌流**：`jg`（补杠）事件不产生打牌决策点，仅更新引擎状态

## 许可与出处

- `backend/engine/`：来自 IJCAI-mahjong 竞赛代码（mcr-ai/IJCAI-mahjong/deploy/caiest_cnn），**无 LICENSE**，仅作研究用途
- `web/src/game2d/`、`web/src/views/game2d/`、`web/public/game2d-assets/`：2D 回放界面来自 `open_mahjong_unity`（前端），MIT 许可；同步基线 `cbd226d7`（dev ver 0.4.75.7），当前同步至 `4db27ac0`（dev ver 0.4.76.6）
- `web/public/game2d-assets/`：音效/贴图资产，见 `game2d-assets/sounds/ATTRIBUTION.md`
- 模型权重 `backend/weights/*.npz`：来自 HuggingFace `Dannibal/ijcai-mahjong-ckpts-2026`（champion/ 目录，IJCAI-2026 亚军 bot kdens3），见 `backend/weights/README.md`；权重不入库，需 `bash backend/fetch_weights.sh` 下载
- 牌谱数据：salasasa.cn 平台公开对局

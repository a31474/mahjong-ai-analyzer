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
- **original 域 vs seat 域**：tick 中玩家字段（`bh`/`bd` 补花补摸者、`cl/cm/cr/p/g` 鸣牌者、`hu` 和牌者）均为 **original id**（0-3，与 `p*_tiles` 下标同域）；引擎按当局 `seats` 排列换算座位号。摸/打轮转同样按 original id，`seats` 仅作座位映射
- **庄家起手 14 张**：`p0_tiles` 恒为庄家 14 张（13 + 首摸 1），剔花后 14 张合法，不做「>13 即异常」误判

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
- `web/public/game2d-assets/`：音效/贴图资产，见 `ATTRIBUTION.md`
- 模型权重 `backend/weights/*.npz`：来自 HuggingFace `Dannibal/ijcai-mahjong-ckpts-2026`（champion/ 目录，IJCAI-2026 亚军 bot kdens3），见 `backend/weights/README.md`；权重不入库，需 `bash backend/fetch_weights.sh` 下载
- 牌谱数据：salasasa.cn 平台公开对局

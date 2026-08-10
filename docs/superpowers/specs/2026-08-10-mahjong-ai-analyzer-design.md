# 国标麻将 AI 牌谱复盘分析服务 — 设计文档

日期：2026-08-10
状态：已获用户确认

## 1. 背景与目标

基于开源平台 open_mahjong_unity（salasasa.cn）的国标麻将牌谱，提供 AI 复盘分析服务：

- **核心功能**：对牌谱每一步"应该打出哪张牌"给出 AI 推荐（含 top-k 概率），对比玩家实际打出。
- **视角可切换**：四家玩家均可作为主视角分析。
- **懒分析**：不预计算全量，用户在复盘页翻到某一步时才对该步单次分析，规避单核服务器性能不确定性。
- **部署**：独立服务（独立目录 `~/project/mahjong-ai-analyzer`，独立 git 仓库），单核服务器，纯 numpy 推理，无 torch。
- **AI 模型**：复用 IJCAI-2026 冠军 bot kdens3 的部署推理栈（3×KD-student mean-softmax ensemble，fp16 权重）。

明确不做（YAGNI）：动画回放、吃碰杠鸣牌建议、错手点评/番型预测、用户系统、平台集成。

## 2. 架构总览

```
~/project/mahjong-ai-analyzer/
├── backend/
│   ├── main.py              # FastAPI 入口：prepare/step 分析 API + 静态托管前端
│   ├── analyzer.py          # 编排：牌谱解析 → 重放 → 单步推理 → 结果 JSON
│   ├── converter.py         # ★核心：action_ticks 事件流 → Botzone request 流
│   ├── tiles.py             # 牌编码映射（11-19→W1…47→J3，花牌剔除）
│   ├── engine/              # 复制自 IJCAI-mahjong deploy/caiest_cnn/（原样）
│   │   ├── agent.py         #   MahjongGBAgent 基类
│   │   ├── feature.py       #   38 平面观测 + 235 维 action_mask
│   │   └── numpy_resfused.py#   纯 numpy 推理（仅依赖 numpy）
│   └── weights/             # kdens_s{0,1,2}_fp16.npz（gitignore）
├── web/                     # Vue3 + Vite + TS + PixiJS（复制自 open_mahjong_web）
│   └── ...                  #   回放页改造 + AI 面板
├── tests/
└── README.md
```

数据流：
`game_id / 上传 JSON → 拉取/解析牌谱 → converter 逐事件驱动 FeatureAgent → 在打牌决策点调 numpy 模型 → 单步分析 JSON → 前端 PixiJS 场景 + AI 面板`

### 关键输入材料

| 材料 | 来源 | 用途 |
|---|---|---|
| `engine/` 三个文件 | `mcr-ai/IJCAI-mahjong/deploy/caiest_cnn/`（无 LICENSE，README 注明出处） | 观测构建与推理 |
| `kdens_s{0,1,2}_fp16.npz` | HuggingFace `Dannibal/ijcai-mahjong-ckpts-2026` champion/ | 模型权重（需下载） |
| 牌谱格式参考 | `open_mahjong_server/server/gamestate/public/game_record_format.md`、`game_record_example_guobiao.jsonc` | 事件流语义 |
| 重放参考实现 | `open_mahjong_web/client/src/game2d/replay/recordReplay.ts`（含 `salasasaTileToMmcr`） | 转换器逻辑对照 |
| PyMahjongGB | `mcr-ai/PyMahjongGB`（pip 安装，需编译） | `feature.py` 的 `_check_mahjong` |

## 3. 转换器（核心难点）

把 `action_ticks` 事件流翻译成 FeatureAgent 可消化的 Botzone request 流，每局每视角各维护一个 `FeatureAgent` 实例。

### 3.1 事件映射

| 牌谱事件 | → Botzone request |
|---|---|
| 局头 `pX_tiles`（每 original 玩家 13 张起手牌，剔除花后） | `Deal W1 W2 …`（按视角取该玩家手牌） |
| `d`/`gd`/`bd` 摸牌 | 自己 → `2 <tile>`；他人 → `3 N Draw` |
| `c` 切牌 | `3 N Play <tile>` |
| `p`/`g`/`ag`/`jg` | `3 N Peng/Gang/AnGang/BuGang <tile>`（按 `__main__.py` 语义区分 AnGang/Gang） |
| `cl`/`cm`/`cr` 吃 | `3 <打出者> Play <tile>` 后接 `3 <吃者> Chi <tile>` |
| `hu_self`/`hu_first`/`hu_second`/`hu_third`/`liuju` | 终止本局，不产生打牌决策点 |
| `bh` 补花 | 跳过 |

### 3.2 关键细节

1. **花牌完全剔除**：IJCAI 竞赛牌墙 136 张无花（`judge/main.cpp:564-580`），模型观测无花，训练分布不含花——转换器对花牌（51-58）一律剔除：起手 `pX_tiles` 剔除花后 13 张喂 Deal；`d` 摸到花时吞掉该 Draw、把随后 `bd` 的牌作为真实摸牌；他人摸花同理跳过 `3 N Draw`；`_check_mahjong` 用 `flowerCount=0`。起手剔除花后不足 13 张判为异常牌谱。
2. **`pX_tiles` 语义**：每局每个字段是该局该 original 玩家（p0..p3）的起手牌数组；视角玩家 = original index，当局 `seatWind = seats[original_i]`。
3. **圈风**：`quan = (current_round - 1) // 4`（东 1-4 局 = 0，南 5-8 局 = 1），来自局头 `current_round`。
4. **鸣牌配对**：`cl/cm/cr`/`p`/`g` 紧跟的弃牌事件是 curTile 来源，按事件顺序配对；`ag` 事件带 4 张真实 ID。
5. **事件格式兼容**：`bh` 事件存在 3 元素（`["bh", tile, player]`）与 4 元素（`["bh", tile, player, "T"|"F"]`）两种历史格式，解析时兼容。
6. **一致性自检**：转换中 FeatureAgent 抛异常（如手牌找不到牌）→ 标记该局/该步转换失败而非崩溃；测试断言"每个 `c` 事件的牌都在重建手牌中"。

## 4. 按需单步分析（API）

### 4.1 接口

```
POST /api/analyze/prepare
  body: { "game_id": "xxx", "platform": "https://salasasa.cn" }   # 从平台拉取
     或 { "record": {…原始牌谱 JSON…} }                            # 直接上传
  → { analysis_id, meta: { game_id, created_at, players[4], rounds: [
       { round_index, current_round, dealer, viewer_players,
         steps: [ { step, player, actual_tile, hand[], melds[], river[], draw } ] } ] } }
  # meta 不含任何 AI 数据，立即返回

GET /api/analysis/{id}/step?round=1&step=12&viewer=0
  → { step, player, actual_tile, ai_top: [{tile, prob}…], agree }
  # 重放（<10ms）+ 单次模型推理（10-30ms/学生）
  # LRU 缓存键 (id, round, step, viewer)，翻回已分析步零开销
```

### 4.2 推理编排

- 每局每视角一个 `FeatureAgent`；事件驱动到打牌决策点（`agent.valid` 为 Play 集合）时取 `_obs()` → `NumpyResFused.logits(obs, mask)` → softmax → mask 内 34 张打牌 top-k。
- 默认 3 学生 ensemble（mean softmax）；环境变量 `ENSEMBLE=1` 切单学生提速。
- 鸣牌决策点（mask 无 Play）不分析，跳过。
- 每步分析时从头重放 `action_ticks` 到目标步（纯状态重建，毫秒级），保证状态独立可复现、无会话漂移。

### 4.3 缓存

- 解析缓存：`analysis_id → 解析后的牌谱结构`（内存，LRU，容量 ~20 局）。
- 分析缓存：`(id, round, step, viewer) → 结果`（LRU，容量 ~2000 条）。

## 5. 前端（复用 game2d/replay 引擎）

- **技术栈**：Vue3 + Vite + TypeScript + PixiJS 独立应用（非静态页）。
- **复制来源**：`open_mahjong_web/client/src/` 下：
  - `views/game2d/Replay.vue`（回放页，改造）
  - `game2d/replay/`（`recordReplay.ts`、`localReplayRecord.ts`，原样）
  - `game2d/game/`（PixiJS 场景，原样）
  - `game2d/salasasa/gameAdapter.ts` + `types.ts`（tile 转换等，原样；`api.ts`/`client.ts` 不用）
  - 最小依赖集：i18n（tr）、stores、composables、layouts
  - 牌面素材 `game2d/game/resources.ts` 随代码复制（MIT）
- **改造点**：
  1. 牌谱来源改走本服务后端（prepare/step API），去掉平台登录/列表依赖。
  2. **AI 面板 = DOM overlay**（不侵入 PixiJS 场景）：当前步 AI 推荐 top-3 概率条 + 实际打出对比 + 一致/分歧标记；整局分歧列表（点击跳转）；与场景滚轮步进联动（步进变化 → 按需请求该步分析，加载态）。
  3. **视角切换器**：若 `Replay.vue` 现无切换视角能力则新增（切换后按新 viewer 重新请求/重放）。
  4. 裁剪与平台账号相关的 UI。

## 6. 验证策略

1. **单元测试**：`tiles.py` 映射全量覆盖（34 张）；converter 各事件类型用 `game_record_example_guobiao.jsonc` 作 fixture。
2. **一致性断言**：转换重放中每个 `c` 事件牌必须存在于该玩家重建手牌（FeatureAgent 内部状态校验）。
3. **观测一致性抽样**：后端 Python 重放手牌状态 vs 前端 `recordReplay.ts` 推进结果一致（对同一真实牌谱抽样若干步）。
4. **端到端**：从 salasasa.cn 拉 1-2 局真实牌谱 → prepare → 逐 step 分析 → 前端渲染。
5. **模型完整性**：加载 `kdens_s*.npz` 校验 logits 形状（38,4,9 → 235）与数值非 NaN。

## 7. 部署与运行

- 后端：`pip install numpy fastapi uvicorn PyMahjongGB`（独立 venv，避免与任何 torch/jax 环境混装）；`uvicorn main:app --host 0.0.0.0 --port 8000`。
- 前端：`vite build` 产物由后端静态托管（后端 `web/dist`）。
- 模型权重放 `backend/weights/`（gitignore）。
- 服务器需可访问 salasasa.cn（或自建平台内网地址，通过 `platform` 参数指定）。

## 8. 待办资产（用户需提供/操作）

1. 从 HF 下载 `kdens_s{0,1,2}_fp16.npz` 到 `backend/weights/`（本地目前没有）。
2. `pip install PyMahjongGB`（源码已 clone 在 `mcr-ai/PyMahjongGB`，需编译 C 扩展）。
3. 确认服务器到 salasasa.cn 的网络可达性。
4. `engine/` 代码来自 IJCAI-mahjong（无 LICENSE 文件），README 注明出处，内部使用。

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| 转换器对某事件语义理解错误 | recordReplay.ts 参考实现对照 + 一致性断言测试 |
| 单核推理过慢 | 懒分析天然规避；可降级单学生（`ENSEMBLE=1`） |
| 平台接口/牌谱格式变化 | converter 单模块隔离，fixture 测试兜底 |
| 花牌/暗杠等边缘事件 | 真实牌谱端到端覆盖 + 转换失败标记而非崩溃 |

# 上游 2D 界面同步

本项目的 `web/src/game2d/`、`web/src/views/game2d/`、`web/src/constants/`、`web/src/i18n/`、`web/public/game2d-assets/`
来自 [`open_mahjong_unity`](../../open_mahjong_unity)（MIT），按需跟随上游更新。

**当前同步点**: `1a76ab42`（dev ver 0.4.78.1，2026-10-04）

## 1. 判定原则

上游是完整的多规则麻将平台（国标/日麻/川麻/杭州/贵州/温州/红中/长春/广东/山西/宜兴…），本项目**只做国标 AI 复盘**，
所以不能照单全收。按类别取舍：

| 类别 | 处理 | 例子 |
|---|---|---|
| 2D 回放渲染 / 交互的通用修复 | ✅ 同步 | 花牌显示模糊修复、牌河布局、手牌与鸣牌渲染 |
| 国标牌谱数据的解析 / 归一化修复 | ✅ 同步 | 赤五 `105/205/305` 归一化 |
| 引擎 API 的向后兼容扩展 | ✅ 同步（连带整文件） | `setRound(..., labelOverride?)`、`setPlayerInfo(..., duplicateRemaining?)` |
| 其他麻将规则 | ❌ 跳过 | `utils/*Replay.js`、`components/*ReplayDetail.vue`、`Replay.vue` 里对应分支 |
| 复式赛制 | ❌ 跳过（分支保留但不触发） | `duplicateWalls`、`duplicate_remaining_tile_count` |
| 站点功能 | ❌ 跳过 | `stores/playerAuth`、`utils/localGameRecordStore`、`utils/recordShareLink` |
| 站点页面 | ❌ 跳过 | `Lobby.vue`、`CustomRoomPanel.vue`、`LobbyRecordPanel.vue` |

两条操作纪律（都是踩过坑总结的）：

1. **自包含的文件整文件覆盖**：若新版只依赖本项目已有的模块（含对既有 API 的向后兼容扩展，如新增可选参数），
   直接整文件同步，**比手工摘 hunk 安全**——上游的复式/物理牌分支在本项目里「存在但永不触发」。
   覆盖前先确认该文件在本项目没有本地定制（`diff` 对基线快照）。
2. **引入站点依赖的文件单点摘取**：若新版 import 了 `@/stores/*`、`@/utils/*Replay.js`、`@/components/*` 等本项目没有的模块，
   则只摘需要的几行（典型：`recordReplay.ts`、`Replay.vue`）。

## 2. 工具

```bash
# 扫描上游更新：变更清单 + diff 规模 + 缺失依赖（自动打标：站点专属 / 其他规则 / 需人工判断）
.venv/bin/python scripts/scan_upstream_web_changes.py --from <上次同步点>
# --from 省略时读本文档的「当前同步点」

# 转换实现对比、观测 parity（详见 salasasa-botzone-conversion.md）
PYTHONPATH=backend .venv/bin/python scripts/compare_botzone_conversion.py
PYTHONPATH=backend .venv/bin/python scripts/verify_feature_parity.py
```

扫描输出里**「缺失依赖」是关键信号**：

- 缺失依赖全是「站点专属 / 其他规则」→ 该文件不能整文件覆盖，需单点摘取
- 没有缺失依赖 → 可以整文件同步

## 3. 同步历史

| 日期 | 上游版本 | commit | 范围 |
|---|---|---|---|
| 2026-09-25 | 0.4.74.x → 0.4.76.6 | `cbd226d7` → `4db27ac0` | 全量同步（当时 2D 与站点耦合较少） |
| 2026-10-04 | 0.4.76.6 → 0.4.78.1 | `4db27ac0` → `1a76ab42` | 只摘通用修复（见 §4） |

## 4. 最近一次（0.4.78.1）的结论

上游这版的主体是**其他规则 + 复式 + 站点**（27 文件 / +1704 −200），与本项目相关的只有 4 项，已同步：

| 项 | 文件 | 说明 |
|---|---|---|
| 花牌显示模糊修复 | `game2d/game/scene/River.ts` | 花牌区布局重做 + 「按画布分辨率淡化，不再降采样到 1×」 |
| 赤五归一化 | `game2d/replay/recordReplay.ts`、`game2d/salasasa/gameAdapter.ts` | `normalizedTile` 改为显式处理 `105/205/305`（旧的 `tile % 100` 语义不同） |
| 抢杠和事件 | `game2d/game/scene/MahjongScene.ts` | 新增 `rob_kong_tile` 分支 |
| AbortSignal | `game2d/salasasa/api.ts` | `publicApiGet(path, signal?)` |

连带整文件同步（自包含、向后兼容）：`game/scene/Hand.ts`、`game/scene/Display.ts`、`game/scene/types.ts`、`lib/types.ts`
（新增 `physical_mask` / `physical_tiles` / `concealed_face_down` / `duplicate_remaining_tile_count` 等**可选**字段，本项目不传即不触发）。

跳过的重点：`Replay.vue`（+183，全是其他规则面板与复式牌墙）、`recordReplay.ts` 其余 380 行（其他规则事件流）、
`localReplayRecord.ts`（复式本地牌谱）、`salasasa/client.ts`（站点对局重连）、`waitTips.ts` + 新增 `lanshiV4.ts`（蓝十子规则）、
`i18n/messages.js`（多规则文案）。

> **未引入蓝十（`guobiao/lanshi`）子规则**：本项目当前牌谱为 `guobiao/standard`。若以后需要，
> 同步 `game2d/calc/guobiao/lanshiV4.ts`（625 行，纯算法、无站点依赖）并在 `waitTips.ts` 接入即可。

## 5. 验证

同步后至少跑：

```bash
cd web && npm run build          # 构建通过（能暴露类型/调用不兼容）
cd .. && PYTHONPATH=backend .venv/bin/pytest tests/ -q
```

再起服务目视确认回放页：牌桌/手牌/牌河/花牌区渲染正常，推进到任一「打出」节点后右上角 AI 面板出 top3。
渲染类改动（如 `River.ts` 的花牌布局）只能靠目视，建议留一张截图。

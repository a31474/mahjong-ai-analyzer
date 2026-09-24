# salasasa → Botzone 转换：两种实现对比

对比两处「salasasa 牌谱 → Botzone 风格」的转换实现，并给出可复现的验证脚本：

| | 位置 | 输出 |
|---|---|---|
| 上游（网页转换工具） | `open_mahjong_unity/open_mahjong_web/client/src/utils/recordConvert/botzoneGuobiao.js`（404 行，配合 `index.js` / `tiles.js`） | Botzone 协议文本行（`0/1/2/3 …`），**上帝视角合并**的一份 log |
| 本仓库（AI 分析用） | [`backend/converter.py`](../backend/converter.py) + [`backend/tiles.py`](../backend/tiles.py) + [`backend/engine/feature.py`](../backend/engine/feature.py) | FeatureAgent request 流（`Wind/Deal/Draw/Player N Play …`），**按 4 个 viewer 各重放一份** |

复现：

```bash
PYTHONPATH=backend .venv/bin/python scripts/compare_botzone_conversion.py            # 三项全跑
PYTHONPATH=backend .venv/bin/python scripts/compare_botzone_conversion.py --no-ab    # 无需权重
```

---

## 1. 先分清三种「Botzone 格式」

它们长得像，但不是一回事：

| 格式 | 谁在用 | 样例 |
|---|---|---|
| **Botzone 官方对局 request** | [Botzone wiki](https://wiki.botzone.org.cn/index.php?title=Chinese-Standard-Mahjong) | `2 T6`、`3 2 PLAY T1`、`3 2 CHI T2 W3`（CHI 后**必须**跟打出的牌） |
| **IJCAI FeatureAgent request** | 本仓库引擎、`mcr-ai/IJCAI-mahjong/deploy/caiest_cnn`、`bot/botzone_engine.py` | `Wind 0`、`Deal W1 …`、`Draw T6`、`Player 2 Play T1`、`Player 2 Chi T2`（**只给中间张，不含打出牌**） |
| **上游 botzoneGuobiao 导出** | 网页转换工具导出给人看/训练 | 官方协议的子集 + 自定义注释行（`# fans …`、`# seat N drew`、`3 p HU`、`3 HUANG`） |

本仓库的 engine 直接来自 `mcr-ai/IJCAI-mahjong/deploy/caiest_cnn`，其 Botzone 入口把官方 request 逐条转成 FeatureAgent request（`process()`：`t[0]=='1'` → `Deal`，`'2'` → `Draw`，`'3'` → `Player N …`）。**本仓库的 `converter.py` 是把 salasasa tick 转成同一套 FeatureAgent request**，等于把「Botzone 官方协议 → FeatureAgent」这一步换成了「salasasa tick → FeatureAgent」。

## 2. 逐项对比

| 维度 | 上游 botzoneGuobiao | 本仓库 converter |
|---|---|---|
| 座位来源 | 启发式猜测（向前找鸣牌/补花者，向后找切牌者） | tick 字段 + **轮转状态机**（含 player_index 域映射） |
| 视角 | 一份合并 log，发牌行混多家信息 | 每人只看到自己 13/14 张（Botzone 单座语义） |
| 摸牌 | 所有 `d` 都写成 `2 CARD` + 注释 | 自己 `Draw X`，他人 `Player N Draw` |
| 花牌 | 出现在发牌行（`H1-H8`）+ 各家花数 | 完全剔除（136 张墙），`bh`/`bd` 配对补花 |
| 鸣牌+打出 | 合并进同一条（官方协议要求） | 拆成 `Chi/Peng` + 后续 `Play`，并建立决策点 |
| 吃中间张 | 三张牌排序取中位数 | 按 `cl/cm/cr` 位置 ±1 换算，越界抛错 |
| 和牌 | `3 p HU` + `# fans`/`# score` 注释 | `Player N Hu`；**错和跳过、不终局** |
| reset tick | `continue` 跳过 | 跳过（等价性见 §5） |
| 错误处理 | 无校验，缺失用占位（`?? 11`、`?? h1`） | 起手张数校验→error；鸣牌前弃牌喂入失败→状态漂移 error |
| 额外能力 | 反向转换、`hu_self/first/second/third` 归类、雀渣/MJAI 互转 | 决策点提取（`pending` + valid 掩码）、LRU 缓存键 |

## 3. 发现一：牌面字母 T/B 语义（本仓库曾反写，**已修正**）

### 3.1 权威约定

- **Botzone 官方 wiki**：「W4」=四万，**「B6」=六筒，「T8」=8条**。
- **PyMahjongGB（本仓库 engine 依赖的算番库）源码**：`mcr-ai/PyMahjongGB/MahjongGB/mahjong-algorithm/tile.h`
  ```cpp
  TILE_1m = 0x11, …   // 万
  TILE_1s = 0x21, …   // s = sou = 索/条
  TILE_1p = 0x31, …   // p = pin = 饼/筒
  ```
  而 `mahjong.cpp` 的字符串表 `tile2str[34]` 是 `"W1".."W9", "T1".."T9", "B1".."B9"` —— 即 **T=索、B=筒**。两者一致。
- **绿一色实验**（用本仓库 `.venv` 直接调 PyMahjongGB）：

  ```
  234/234/666/888 + 发发，全用 T → ['绿一色', 门前清, 双暗刻, 一般高, 独听・单钓]
  同一牌型，全用 B            → ['混一色', 门前清, 双暗刻, 一般高, 独听・单钓]
  ```

  绿一色只由索子（2/3/4/6/8）+ 发组成，所以 **T=索、B=筒** 确认无疑。

### 3.2 本仓库的映射曾写反（已修正）

修正前 [`backend/tiles.py`](../backend/tiles.py)：

```python
table = {1: 'W', 2: 'T', 3: 'B', 4: 'F'}   # 21-29(筒)→T ✗  31-39(索)→B ✗
```

现为 `{1: 'W', 2: 'B', 3: 'T', 4: 'F'}`（21-29 筒→B、31-39 索→T）。上游 `tiles.js` 的 `salasasaToBotzone` 一直是按官方约定写的（21-29→B、31-39→T）。

修正前后的双跑输出（同一局同一手牌）：

```
上游     1 1 0 1 1 T2 T3 B8 T3 B9 B6 B5 F1 J3 B7 B6 W2 W5 H4 H3 H6
                    ↑32   ↑28
修正前   Deal B2 B3 T8 B3 T9 T6 T5 F1 J3 T7 T6 W2 W5      ← 32 被叫 B2、28 被叫 T8
                ↑32  ↑28
修正后   Deal T2 T3 B8 T3 B9 B6 B5 F1 J3 B7 B6 W2 W5      ← 与上游一致
```

同一张 32（3索）修正前叫 `B2`、28（8筒）叫 `T8`，与上游相反；修正后两边一致。
字牌 `45/46/47 → J1/J3/J2`（中/白/发）两边始终一致。

### 3.3 为什么「看起来还能用」

转换端（`to_csm`）与消费端（`engine/feature.py` 的 `TILE_LIST = W,T,B,F,J`）用的是**同一套互换标签**，所以：

- 维度索引自洽，牌型结构完全同构 → 打牌建议（首选）基本不变；
- PyMahjongGB 只做「能否和牌」的校验，`筒索互换` 后**结构同构**，大多数番型不变。

但两处会出错：

1. **花色敏感番型**：`绿一色`（只认索）、`推不倒`（筒/索牌集不同）等会把番数算错 → 影响 8 番起胡的判定（真·绿一色 88 番可能被算成混一色 6 番）；
2. **模型输入与训练分布不一致**：模型训练/评测走的是 Botzone 官方约定（T=索），推理时却被喂了筒索互换的局面，等于在一个镜像牌局上做决策。

### 3.4 影响量化（A/B，单学生）

```
step 1  实际 北 | 现状 北 0.803 东 0.099 白 0.059 | 修正 北 0.855 东 0.053 白 0.042
step 51 实际 9索| 现状 2万 0.587 9索 0.194 3索 0.089 | 修正 2万 0.511 9索 0.196 3索 0.116
step 79 实际 8万| 现状 2万 0.806 8万 0.134 3索 0.024 | 修正 2万 0.661 8万 0.284 3索 0.023
step 95 实际 4筒| 现状 3索 0.737 4筒 0.217 2索 0.015 | 修正 3索 0.731 4筒 0.225 2索 0.012
首选一致: 11/11
```

结论：**首选建议 11/11 不变**（结构同构的必然结果），但**概率分布差异可观**（step 79 的次选 8万 从 0.134 升到 0.284，翻倍；step 1 首选从 0.803 升到 0.855）。也就是说：AI 面板上「AI 认为该打什么」的排序基本可靠，但**概率置信度与次选排序不可靠**，且和牌/番型判定会错。

### 3.5 修复记录（已实施）

1. [`backend/tiles.py`](../backend/tiles.py)：`table = {1: 'W', 2: 'B', 3: 'T', 4: 'F'}`，并补上约定来源注释；
2. [`web/src/views/game2d/Replay.vue`](../web/src/views/game2d/Replay.vue)：`AI_SUIT_PREFIX = { W: 1, T: 3, B: 2, F: 4 }`（T=索=3、B=筒=2）；
3. [`backend/analyzer.py`](../backend/analyzer.py) 的 `_TILE_NAMES` 与 `engine/feature.py` 的 `TILE_LIST` **未动**（必须与训练权重一致，字母只是通道标签）；
4. 测试断言同步：`test_tiles.py`（21→B1、31→T1）、`test_analyzer.py`、`test_api.py`（stub 偏好索引 9→18）、`test_cache_store.py`、`test_converter_replay.py`（29 处牌名互换）、`test_e2e.py`；全套 48 个测试通过；
5. README「牌谱转换说明」「已知限制」「测试」三处描述同步。

**附带修掉的缓存坑**：磁盘缓存键原先只含「牌谱 + 局 + 节点 + 视角」，改完映射后仍会读到按旧约定算出的结果（表现为 `actual_tile` 是新的、`ai_top` 却还是旧牌名）。现在 [`backend/main.py`](../backend/main.py) 把 `tiles.py` + `converter.py` 的**内容指纹**并进缓存键（`enc<sha1[:8]>|…`），改转换逻辑即自动失效，无需人工递增版本号、也不必手动清 `backend/cache/`。

## 4. 发现二：座位归属——状态机 vs 启发式猜测

同一局开头 tick：`[bh 54 0][bd 44 0][bh 53 2][bd 21 2][bh 56 3][bd 32 3][c 44 'T']`

```
本仓库    Player 0 Play F4
上游      3 3 PLAY F4        ← 座位 3
```

判据：`p0_tiles` 14 张（庄家）、p1–p3 各 13 张；`bd 44` 的补花者是 p0，且该 `c` 的第三字段是 `'T'`（摸切）——**摸到 44 的人打 44，只能是 p0**。

上游 `guessCutSeat` 往前找到「最后一个补花者」（`bh 56` = p3）就返回，于是**开局首打就错**，之后整局座位整体偏移（上游 `3,0,1,2…` vs 正确 `0,1,2,3…`）。上游自己在 `approxRows` 里标了「切牌动作里的座位：近似」，但 AI 复盘要求座位 100% 准确，这也是本仓库不能复用上游实现的核心原因。

## 5. 发现三：reset tick 两边都跳过，等价性依赖数据

统计 7 份真实牌谱 98 局：

```
含 reset 的局: 48，不含: 50
reset[1] == start_player_index: 48/48
reset 出现在首个 c 之前: 48/48
```

典型形态（`['reset', 0]` 紧跟开局补花块，位于首个 `c` 之前）：

```
['bh', 54, 0, 'F'] ['bd', 44, 0] ['bh', 53, 2, 'F'] ['bd', 21, 2] ['bh', 56, 3, 'F'] ['bd', 32, 3] ['reset', 0] ['c', 44, 'T'] …
```

- 上游转换器 `continue` 忽略；本仓库 converter 原先也忽略，但用 `start_player_index` 初始化轮转 → **当前数据下等价**；
- 两边的**回放引擎**（`web/src/game2d/replay/recordReplay.ts`）是**以 `reset` 为准**（`currentPlayer = tick[1]`）→ 更健壮。

**已实施**：[`backend/converter.py`](../backend/converter.py) 现以 `reset` 为准（`if a == 'reset': current = tick[1]`），与回放引擎一致，可防住「`reset[1] != start_player_index`」（寻摸/跳转类牌谱）的错位。

## 6. 各自独有

**本仓库独有（AI 推理必需）**

- 决策点提取：只在「自己摸牌/鸣牌后、打牌前」用 `pending` + `agent.valid` 生成节点（上游不产出）
- 单座观测：每人只拿自己的手牌（上游是上帝视角合并）
- 花牌全剔除 + 补花者队列（多花/交错补花安全）
- 错和继续（不喂 Hu、不 break）
- 状态漂移防御（鸣牌前补喂弃牌失败即报 error，不静默产出错观测）
- 吃中间张越界（`cr` 吃 9 → 10）判数据异常

**上游独有**

- 反向转换 `botzoneToSalasasa`
- `hu_self/hu_first/hu_second/hu_third` 归类（`huClassFromRelative`）
- 雀渣（`tziakchaGuobiao.js`）与 MJAI（`mjaiRiichi.js`）互转
- 可读性注释（`# fans` / `# score` / `# seat N drew`）

## 7. 互操作建议

- 想要「给 Botzone 机器人/回放用的协议文本」→ 用上游，但需修 `guessCutSeat` 的开局首打（判据：庄家 14 张 + `bd` 摸牌者 = 打出者）
- 想要「喂本仓库引擎」→ 只能用 `converter.py`；把上游输出硬塞进来会因 T/B 相反 + 上帝视角而错
- 两边真正共享的权威事实是 salasasa tick 里的 `player_index`；合理做法是把本仓库的轮转状态机思路回移到上游 JS，替换那套启发式猜测
- 另有一条疑似脏数据：缓存牌谱中出现 `['cl', 22, 1, 20, 21]`（20 不在 21-29 筒区间内），两边算出的中间张都是 21，但本仓库不看 `t[3]/t[4]`、上游要用它们取中位数

## 8. 参考资料（mcr-ai 工作区）

| 资料 | 用途 |
|---|---|
| `mcr-ai/PyMahjongGB/MahjongGB/mahjong-algorithm/tile.h` | 牌值枚举（`TILE_1m/TILE_1s/TILE_1p`）——T/B 语义的源码级依据 |
| `mcr-ai/PyMahjongGB/MahjongGB/mahjong.cpp` | `tile2str[34]` 字符串表 |
| `mcr-ai/IJCAI-mahjong/deploy/caiest_cnn/__main__.py` | 原版 Botzone bot：官方 request → FeatureAgent request 的权威适配（本仓库 converter 的「对偶」） |
| `mcr-ai/IJCAI-mahjong/bot/botzone_engine.py` | 同一适配的精简版（stdin/stdout 协议循环） |
| `mcr-ai/Chinese-Standard-Mahjong/` | 官方规则与裁判程序 |
| `mcr-ai/rule.md` | 国标规则要点（144 张、不设连庄、截和制等） |

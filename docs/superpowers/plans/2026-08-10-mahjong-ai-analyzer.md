# 国标麻将 AI 牌谱复盘分析服务 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建一个独立服务：输入 open_mahjong_unity 平台的国标牌谱（game_id 或 JSON），按需对每一步"该打哪张牌"给出 kdens3 模型的 AI 推荐（top-k 概率），并在复用 game2d 引擎的前端上展示。

**Architecture:** 后端 Python（FastAPI + numpy 推理）：converter 把 open_mahjong 的 `action_ticks` 事件流翻译成 Botzone request 字符串流，驱动复制自 IJCAI 冠军 bot 的 `FeatureAgent`（38 平面观测 + 235 维 mask），在打牌决策点调 `NumpyResFused`（3 学生 mean-softmax ensemble）得到打牌概率；懒分析（prepare 只解析，翻步时单步推理 + LRU 缓存）。前端为 Vue3+PixiJS 应用（复制 open_mahjong_web 的 game2d 回放引擎），加 DOM AI 面板。

**Tech Stack:** Python 3.12、numpy、fastapi、uvicorn、PyMahjongGB（编译安装）；Vue3、Vite、TypeScript、PixiJS。

## Global Constraints

- 推理栈纯 numpy，**禁止** torch/jax（单核服务器、避免与任何 torch 环境混装）。
- **Python 环境纪律（已发生事故，必须遵守）**：项目虚拟环境为 `~/project/mahjong-ai-analyzer/.venv`（uv 创建，Python 3.12，依赖已装好）。所有 python/pytest/uvicorn 命令一律用 `.venv/bin/` 前缀（本计划中已统一写为 `.venv/bin/python`、`.venv/bin/pytest`）。**禁止**：向 uv 受管解释器（`~/.local/share/uv/python/*`、`~/.local/bin/python3.12` 等）全局 `pip install`（污染共享环境，PEP 668 会拒绝）；不使用 `--break-system-packages`。装新依赖用 `uv pip install --python .venv/bin/python <pkg>`（或在激活的 venv 内 `uv pip install <pkg>`）。
- `backend/engine/` 三个文件（`agent.py`、`feature.py`、`numpy_resfused.py`）从 `~/project/mcr-ai/IJCAI-mahjong/deploy/caiest_cnn/` **原样复制**，不修改其逻辑（`numpy_resfused.py` 的 torch import 本就在 `convert()` 函数内，顶层无 torch，无需改动）。
- `feature.py` 顶层 `from MahjongGB import MahjongFanCalculator` 是硬依赖 → 已在 venv 内安装 PyMahjongGB（本地源码 `~/project/mcr-ai/PyMahjongGB` 编译安装，已验证 `from MahjongGB import ...` 可导入）。
- 花牌（51-58）在转换中完全剔除（IJCAI 牌墙 136 张无花，`flowerCount=0`）。
- 牌编码：open_mahjong 11-19 万 / 21-29 筒 / 31-39 索 / 41-44 风 / 45-47 箭 / 51-58 花 → IJCAI `W1-W9/T1-T9/B1-B9/F1-F4/J1-J3`。
- 权重 `kdens_s{0,1,2}_fp16.npz` 放 `backend/weights/`（gitignore），来自 HF `Dannibal/ijcai-mahjong-ckpts-2026` champion/。
- 模型权重缺失时单步分析必须返回明确的 503 错误（而非崩溃）。
- 前端复制自 `~/project/open_mahjong_unity/open_mahjong_web/client/`（MIT），README 注明出处；engine/ 来自 IJCAI-mahjong（无 LICENSE 文件），README 注明出处。
- 所有测试数据放 `tests/fixtures/`；`game_record_example_guobiao.jsonc` 含注释（JSONC），作为 fixture 前转成纯 JSON。

---

### Task 1: 项目脚手架 + 引擎复制

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/main.py`（占位，Task 7 填充）
- Create: `backend/tiles.py`（占位，Task 2 填充）
- Create: `backend/converter.py`（占位，Task 3 填充）
- Create: `backend/analyzer.py`（占位，Task 6 填充）
- Create: `backend/engine/__init__.py`
- Copy: `backend/engine/agent.py`、`backend/engine/feature.py`、`backend/engine/numpy_resfused.py`（来自 `~/project/mcr-ai/IJCAI-mahjong/deploy/caiest_cnn/`）
- Create: `backend/weights/.gitkeep`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `README.md`（骨架）
- Create: `tests/__init__.py`

**Interfaces:**
- Produces: `backend/engine.feature.FeatureAgent`、`backend/engine.numpy_resfused.NumpyResFused`（现有 API，原样）

- [ ] **Step 1: 确认 venv 与 PyMahjongGB 就位（已由控制器完成）**

```bash
cd ~/project/mahjong-ai-analyzer && .venv/bin/python -c "from MahjongGB import MahjongFanCalculator; import numpy, fastapi, uvicorn, pytest; print('venv ok')"
```

Expected: `venv ok`。若失败，用 `uv pip install --python .venv/bin/python <缺失包>` 补装，**绝不**对 uv 受管解释器全局 pip install。

- [ ] **Step 2: 建目录并复制引擎**

```bash
mkdir -p ~/project/mahjong-ai-analyzer/backend/engine ~/project/mahjong-ai-analyzer/backend/weights ~/project/mahjong-ai-analyzer/tests/fixtures
cp ~/project/mcr-ai/IJCAI-mahjong/deploy/caiest_cnn/{agent.py,feature.py,numpy_resfused.py} ~/project/mahjong-ai-analyzer/backend/engine/
touch ~/project/mahjong-ai-analyzer/backend/__init__.py ~/project/mahjong-ai-analyzer/backend/engine/__init__.py ~/project/mahjong-ai-analyzer/backend/weights/.gitkeep ~/project/mahjong-ai-analyzer/tests/__init__.py
```

（注意：目录/文件已部分存在则跳过已存在项；复制必须用 `cp` 保证与源字节一致。）

- [ ] **Step 3: 核对 numpy_resfused 顶层无 torch**

检查 `backend/engine/numpy_resfused.py` 第 48 行附近：`import torch` 应在 `convert()` 函数内部（缩进），模块顶层无 torch。若与源文件有任何差异，用 `cp` 重新复制（原样，不修改）。

- [ ] **Step 4: 验证引擎可导入**

`feature.py` 用 Botzone 风格扁平导入（`from agent import`），必须从 engine 目录运行（cwd 即 sys.path[0]）：

```bash
cd ~/project/mahjong-ai-analyzer/backend/engine && PYTHONPATH=.. ~/project/mahjong-ai-analyzer/.venv/bin/python -c "
from feature import FeatureAgent
from numpy_resfused import NumpyResFused
a = FeatureAgent(0)
print('engine ok:', a.OBS_SIZE, a.ACT_SIZE)
"
```

Expected: `engine ok: 38 235`

- [ ] **Step 5: 写 requirements.txt / .gitignore / 补充 .gitignore 排除 venv**

```txt
# requirements.txt
numpy
fastapi
uvicorn
PyMahjongGB
pytest
httpx
```

```gitignore
# .gitignore
__pycache__/
*.pyc
.venv/
backend/weights/*
!backend/weights/.gitkeep
web/node_modules/
web/dist/
```

（依赖已在 `.venv` 安装；requirements.txt 供新机器重建环境：`uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt`。）

- [ ] **Step 6: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add -A && git -c user.name="a314" -c user.email="a314@localhost" commit -m "chore: 脚手架 + 复制 caiest_cnn numpy 推理引擎"
```

---

### Task 2: tiles.py — 牌编码映射

**Files:**
- Create: `backend/tiles.py`
- Test: `tests/test_tiles.py`

**Interfaces:**
- Produces:
  - `is_flower(tile_id: int) -> bool` — 51-58 为花
  - `to_csm(tile_id: int) -> str` — open_mahjong id → `W1..J3`；花牌抛 `ValueError`
  - `FLOWER_IDS: frozenset[int]`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tiles.py
import pytest
from tiles import to_csm, is_flower, FLOWER_IDS

CASES = {11: 'W1', 19: 'W9', 21: 'T1', 29: 'T9', 31: 'B1', 39: 'B9',
         41: 'F1', 42: 'F2', 43: 'F3', 44: 'F4', 45: 'J1', 46: 'J2', 47: 'J3'}

def test_suits_and_honors():
    for tid, csm in CASES.items():
        assert to_csm(tid) == csm

def test_flowers():
    assert is_flower(51) and is_flower(58)
    assert not is_flower(47)
    assert FLOWER_IDS == frozenset(range(51, 59))

def test_flower_raises():
    with pytest.raises(ValueError):
        to_csm(53)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_tiles.py -v`
Expected: FAIL（`ModuleNotFoundError: tiles`）

- [ ] **Step 3: 实现**

```python
# backend/tiles.py
"""open_mahjong tile_id <-> IJCAI CSM string code."""

FLOWER_IDS = frozenset(range(51, 59))  # 51-58 春夏秋冬梅兰竹菊

def is_flower(tile_id: int) -> bool:
    return tile_id in FLOWER_IDS

def to_csm(tile_id: int) -> str:
    if is_flower(tile_id):
        raise ValueError('flower tile %d is excluded from CSM view' % tile_id)
    suit, num = divmod(tile_id, 10)          # 11..47
    table = {1: 'W', 2: 'T', 3: 'B', 4: 'F', 5: 'J'}
    if suit not in table:
        raise ValueError('invalid tile_id %d' % tile_id)
    if suit == 5:
        return table[suit] + str(num - 4)    # 45->J1, 46->J2, 47->J3
    return table[suit] + str(num)            # 11->W1, 31->B1
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_tiles.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add backend/tiles.py tests/test_tiles.py && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: 牌编码映射"
```

---

### Task 3: converter.py — 牌谱解析与归一化

**Files:**
- Create: `tests/fixtures/guobiao_example.json`（由 `game_record_example_guobiao.jsonc` 去注释转换）
- Create: `backend/converter.py`
- Test: `tests/test_converter_parse.py`

**Interfaces:**
- Consumes: `tiles.is_flower`
- Produces:
  - `@dataclass RoundRecord`: `round_index: int`, `current_round: int`, `seats: list[int]`, `dealer_index: int`, `start_player_index: int`, `hands: list[list[int]]`（`hands[p]` = original 玩家 p 的起手牌，含花）, `action_ticks: list[list]`
  - `@dataclass GameRecord`: `game_id: str`, `rule: str`, `players: list[dict]`（含 `original`/`username`）, `rounds: list[RoundRecord]`
  - `parse_record(record: dict, game_id: str, players: list[dict], rule: str) -> GameRecord`
  - `normalize_tick(tick: list) -> list` — 元素 int 化、`bh` 兼容 3/4 元素

- [ ] **Step 1: 制作 fixture**

```bash
cp ~/project/open_mahjong_unity/open_mahjong_server/server/gamestate/public/game_record_example_guobiao.jsonc ~/project/mahjong-ai-analyzer/tests/fixtures/guobiao_example.jsonc
cd ~/project/mahjong-ai-analyzer && python3 -c "
import re, json
src = open('tests/fixtures/guobiao_example.jsonc').read()
src = re.sub(r'//[^\n]*', '', src)          # 删除 // 注释（含行尾）
src = re.sub(r',\s*([\]}])', r'\1', src)    # 删除尾随逗号（jsonc 允许，json 不允许）
data = json.loads(src)
json.dump(data, open('tests/fixtures/guobiao_example.json', 'w'), ensure_ascii=False, indent=1)
print('fixture ok,', len(data['record']['game_round']), 'rounds')
"
```

Expected: `fixture ok, 2 rounds`

- [ ] **Step 2: 写失败测试**

```python
# tests/test_converter_parse.py
import json
from converter import parse_record, RoundRecord, GameRecord

def _load():
    with open('tests/fixtures/guobiao_example.json') as f:
        data = json.load(f)
    return data

def test_parse_rounds():
    data = _load()
    g = parse_record(data['record'], 'demo1', [], 'guobiao')
    assert isinstance(g, GameRecord)
    assert len(g.rounds) == 2
    r1 = g.rounds[0]
    assert r1.current_round == 1
    assert r1.seats == [0, 1, 2, 3]
    assert len(r1.hands[0]) == 13

def test_hands_contain_flower():
    data = _load()
    g = parse_record(data['record'], 'demo1', [], 'guobiao')
    assert 53 in g.rounds[0].hands[0]      # p0 起手含花 53

def test_bh_variants():
    data = _load()
    g = parse_record(data['record'], 'demo1', [], 'guobiao')
    bh3 = [t for t in g.rounds[0].action_ticks if t[0] == 'bh']
    assert bh3 and bh3[0][0] == 'bh'       # 3 元素 bh 可解析
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_converter_parse.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 parse 层**

```python
# backend/converter.py  (Task 3 部分；Task 4 继续追加)
from dataclasses import dataclass, field

@dataclass
class RoundRecord:
    round_index: int
    current_round: int
    seats: list
    dealer_index: int
    start_player_index: int
    hands: list          # hands[original_player] -> 起手牌 list（含花）
    action_ticks: list

@dataclass
class GameRecord:
    game_id: str
    rule: str
    players: list        # [{original, username}, ...]
    rounds: list

def normalize_tick(tick):
    out = []
    for v in tick:
        if isinstance(v, str) and v.isdigit():
            out.append(int(v))
        else:
            out.append(v)
    return out

def parse_record(record, game_id, players, rule):
    game_round = record.get('game_round') or {}
    rounds = []
    for key in sorted(game_round.keys(), key=lambda k: int(k.rsplit('_', 1)[-1])):
        r = game_round[key]
        hands = []
        for p in range(4):
            hands.append(list(r.get('p%d_tiles' % p) or []))
        rounds.append(RoundRecord(
            round_index=r.get('round_index'),
            current_round=r.get('current_round'),
            seats=list(r.get('seats') or []),
            dealer_index=r.get('dealer_index'),
            start_player_index=r.get('start_player_index'),
            hands=hands,
            action_ticks=[normalize_tick(t) for t in (r.get('action_ticks') or [])],
        ))
    return GameRecord(game_id=game_id, rule=rule, players=players, rounds=rounds)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_converter_parse.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add backend/converter.py tests/ && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: 牌谱解析与归一化"
```

---

### Task 4: converter.py — 事件流驱动 FeatureAgent，提取打牌决策点

**Files:**
- Modify: `backend/converter.py`
- Test: `tests/test_converter_replay.py`

**Interfaces:**
- Consumes: `parse_record`、`tiles.to_csm`、`engine.feature.FeatureAgent`
- Produces:
  - `@dataclass DiscardNode`: `step: int`（action_ticks 下标）, `player: int`（original）, `seat: int`（当局座位）, `actual_tile: str`, `hand: list[str]`, `melds: list`, `river: list[str]`, `draw: str|None`, `obs: dict`（FeatureAgent `_obs()` 输出）, `ok: bool`
  - `@dataclass RoundAnalysis`: `round_index: int`, `viewer: int`（original）, `seat_wind: int`, `quan: int`, `nodes: list[DiscardNode]`, `error: str|None`
  - `replay_round(round_rec: RoundRecord, viewer: int) -> RoundAnalysis` — 从头重放本局、收集 viewer 视角全部打牌决策点；任何一步异常 → `error` 置描述并停止该局（不崩溃）
  - `quan_of(current_round: int) -> int` — `(current_round - 1) // 4`

**关键算法（currentPlayer 轮转，与 recordReplay.ts `xunmuNodes` 一致）：**
- 初始 `current = round.start_player_index`
- `bh`：跳过不喂 FeatureAgent（起手 Deal 已剔花）
- `d`/`gd`/`bd`：当前玩家摸牌。自己（`current == seat_wind`）→ `agent.request2obs('Draw <tile>')`，返回值即 obs（含 Play valid）→ 记为**待定决策点**；他人 → `'Player %d Draw'`。摸到花（51-58）→ 吞掉（不喂）；`bd` 的牌是真实补摸，正常喂
- `c`：`agent.request2obs('Player %d Play <tile>' % current)`；若 `current == seat_wind` 且有待定决策点 → 以 c 的牌为 `actual_tile` 生成 `DiscardNode`（obs 用待定决策点存的、含该牌的手牌）；然后 `current = (current + 1) % 4`
- `cl/cm/cr`：吃者 = tick[2]；先 `'Player %d Play <tile>' % (上一条 c 的打出者)`（鸣牌配对），再 `'Player %d Chi <tile>' % 吃者`；吃者是自己 → 返回值即 obs（Play valid）→ 待定决策点；`current = 吃者`
- `p`：`'Player %d Peng' % tick[2]`；自己 → 待定决策点；`current = tick[2]`
- `g`：`'Player %d Gang' % tick[2]`；`current = tick[2]`（杠者不直接打牌？不——明杠后打牌者是杠者，FeatureAgent 对非自己 Gang 返回 None，自己 Gang 也不返回 obs → 无待定决策点；杠后摸牌由后续 d/gd 事件产生新 Draw → 新待定决策点）
- `ag`：暗杠——自己：`'Player %d AnGang <tile>'`；他人：`'Player %d AnGang'`；清空待定决策点（杠了没打）
- `jg`：`'Player %d BuGang <tile>'`；清空待定决策点
- `hu_self/hu_first/hu_second/hu_third`：`agent.request2obs('Player %d Hu' % tick[1])` 后终止本局
- `liuju`：`'Huang'`，终止
- 补花后起手：`Deal` 时剔除花牌（`hands[viewer]` 剔花后必须 13 张，否则 `error`）
- 任何一步 FeatureAgent 抛异常 → `RoundAnalysis.error` 置描述并停止该局（不崩溃）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_converter_replay.py
import json
from converter import parse_record, replay_round, quan_of

def _load():
    with open('tests/fixtures/guobiao_example.json') as f:
        return json.load(f)

def test_quan():
    assert quan_of(1) == 0 and quan_of(4) == 0
    assert quan_of(5) == 1 and quan_of(8) == 1

def test_replay_example_round2():
    data = _load()
    g = parse_record(data['record'], 'demo1', [], 'guobiao')
    r = g.rounds[1]                          # 第 2 局: seats=[3,0,1,2]（seats[original]=player_index）
    # 事件: bd(43) d(21) c(21) d(35) c(35) d(42) c(42) hu_first(1)
    # original 1 = player_index 0（start_player_index=0，第 1 个摸打者）→ 摸 43/21、打 21(W3)
    ra = replay_round(r, viewer=1)
    assert ra.error is None
    assert ra.quan == 0
    assert ra.seat_wind == 0
    assert len(ra.nodes) == 1
    n = ra.nodes[0]
    assert n.actual_tile == 'W3'             # 21 -> W3
    assert n.ok

def test_replay_other_viewer_no_node():
    data = _load()
    g = parse_record(data['record'], 'demo1', [], 'guobiao')
    ra = replay_round(g.rounds[1], viewer=0) # original 0 = player_index 3，本局未摸打即结束
    assert ra.nodes == []

def test_round1_hu_terminates():
    data = _load()
    g = parse_record(data['record'], 'demo1', [], 'guobiao')
    ra = replay_round(g.rounds[0], viewer=0) # 补花后即 hu_self，无打牌决策点
    assert ra.nodes == []

def test_flower_draw_bridged():
    # 构造: 0 摸花 53 -> 补花 -> bd 摸 43（西），随后 c 打出 43
    from converter import RoundRecord
    ticks = [['d', 53], ['bh', 53, 0], ['bd', 43], ['c', 43, 'T']]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0,1,2,3], dealer_index=0,
        start_player_index=0,
        hands=[[11]*13, [21]*13, [31]*13, [41]*13], action_ticks=ticks)
    ra = replay_round(fake, viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 1
    assert ra.nodes[0].actual_tile == 'F3'   # 43 -> F3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_converter_replay.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 replay_round**

在 `backend/converter.py` 追加（核心实现，注意与 Step 1 测试契约一致；`obs` 用 `agent._obs()` 返回值 `{'observation', 'action_mask'}`）：

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'engine'))
from engine.feature import FeatureAgent
from tiles import to_csm, is_flower

@dataclass
class DiscardNode:
    step: int
    player: int
    seat: int
    actual_tile: str
    hand: list
    melds: list
    river: list
    draw: str
    obs: dict
    ok: bool = True

@dataclass
class RoundAnalysis:
    round_index: int
    viewer: int
    seat_wind: int
    quan: int
    nodes: list
    error: str = None

def quan_of(current_round):
    return (current_round - 1) // 4

def replay_round(round_rec, viewer):
    seats = round_rec.seats
    seat_wind = seats[viewer] if viewer < len(seats) else viewer
    quan = quan_of(round_rec.current_round)
    agent = FeatureAgent(seat_wind)
    agent.request2obs('Wind %d' % quan)
    hand = [t for t in round_rec.hands[viewer] if not is_flower(t)]
    if len(hand) != 13:
        return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, [],
                             error='viewer%d 起手 %d 张(剔花后), 需要 13' % (viewer, len(hand)))
    try:
        agent.request2obs('Deal ' + ' '.join(to_csm(t) for t in hand))
    except Exception as e:
        return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, [],
                             error='Deal 失败: %r' % e)

    nodes = []
    current = round_rec.start_player_index
    last_discarder = None
    last_discard_tile = None
    pending = None               # 待定决策点: (obs, step) —— 自己摸牌/鸣牌后尚未打牌

    def mine():
        return current == seat_wind

    def is_draw_action(a):
        return a in ('d', 'gd', 'bd')

    try:
        for step, tick in enumerate(round_rec.action_ticks):
            a = tick[0]
            if a == 'bh':
                continue
            if is_draw_action(a):
                if len(tick) > 2 and isinstance(tick[2], int):
                    current = tick[2]               # bd 可能带 action_player
                tid = tick[1]
                if is_flower(tid):
                    continue                        # 花牌 Draw 吞掉（bd 才是真实补摸）
                tile = to_csm(tid)
                if mine():
                    obs = agent.request2obs('Draw ' + tile)
                    pending = (obs, step, tile)     # 摸牌后待打牌（含摸到的牌）
                else:
                    agent.request2obs('Player %d Draw' % current)
                continue
            if a == 'c':
                tile = to_csm(tick[1])
                agent.request2obs('Player %d Play %s' % (current, tile))
                if mine() and pending is not None:
                    obs, dstep, draw_tile = pending
                    po = agent.OFFSET_ACT['Play']
                    if obs['action_mask'][po:po+34].any():
                        nodes.append(DiscardNode(
                            step=dstep, player=viewer, seat=seat_wind,
                            actual_tile=tile,
                            hand=[str(t) for t in agent.hand],
                            melds=[list(m) for m in agent.packs[0]],
                            river=list(agent.history[0]),
                            draw=draw_tile,
                            obs=obs))
                pending = None
                last_discarder, last_discard_tile = current, tile
                current = (current + 1) % 4
                continue
            if a in ('cl', 'cm', 'cr'):
                actor = tick[2]
                if last_discarder is not None:
                    agent.request2obs('Player %d Play %s' % (last_discarder, last_discard_tile))
                obs = agent.request2obs('Player %d Chi %s' % (actor, to_csm(tick[1])))
                if obs is not None:
                    pending = (obs, step, None)     # 自己吃后待打牌（无摸牌）
                current = actor
                continue
            if a == 'p':
                actor = tick[2]
                if last_discarder is not None:
                    agent.request2obs('Player %d Play %s' % (last_discarder, last_discard_tile))
                obs = agent.request2obs('Player %d Peng' % actor)
                if obs is not None:
                    pending = (obs, step, None)     # 自己碰后待打牌
                current = actor
                continue
            if a == 'g':
                actor = tick[2]
                if last_discarder is not None:
                    agent.request2obs('Player %d Play %s' % (last_discarder, last_discard_tile))
                agent.request2obs('Player %d Gang' % actor)
                current = actor
                continue
            if a == 'ag':
                if mine():
                    agent.request2obs('Player %d AnGang %s' % (current, to_csm(tick[1])))
                else:
                    agent.request2obs('Player %d AnGang' % current)
                pending = None                      # 杠了，没有打牌决策
                continue
            if a == 'jg':
                agent.request2obs('Player %d BuGang %s' % (current, to_csm(tick[1])))
                pending = None
                continue
            if a.startswith('hu'):
                if len(tick) > 1 and isinstance(tick[1], int):
                    agent.request2obs('Player %d Hu' % tick[1])
                break
            if a == 'liuju':
                agent.request2obs('Huang')
                break
            # ask_hand/ask_other/ca/end 等: 跳过
    except Exception as e:
        return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, nodes,
                             error='step%d %r: %r' % (step, tick, e))
    return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, nodes)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_converter_replay.py -v`
Expected: PASS（若示例 fixture 第二局的 expected 与实际不符，以"该局实际 c 事件数"修正断言后重新验证——测试目的是一致性而非示例数据本身）

- [ ] **Step 5: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add backend/converter.py tests/test_converter_replay.py && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: 事件流驱动 FeatureAgent 提取打牌决策点"
```

---

### Task 5: 模型权重加载（NumpyResFused + 3 学生 ensemble）

**Files:**
- Create: `backend/weights/README.md`（下载指引）
- Create: `backend/model_loader.py`
- Create: `backend/fetch_weights.sh`
- Test: `tests/test_model_loader.py`

**Interfaces:**
- Consumes: `engine.numpy_resfused.NumpyResFused`
- Produces:
  - `load_model(weights_dir: str) -> ModelHandle`；`ModelHandle.logits(obs: np.ndarray, mask: np.ndarray) -> np.ndarray`（235 维；ensemble = 3 学生 mean logits，单学生时直接返回）
  - 权重缺失：`ModelMissingError` 异常（message 指明 weights_dir 与文件名）
  - `N_STUDENTS = 3`，文件名 `kdens_s0_fp16.npz`、`kdens_s1_fp16.npz`、`kdens_s2_fp16.npz`；环境变量 `ENSEMBLE=1` 时只加载 `kdens_s0_fp16.npz`

- [ ] **Step 1: 写失败测试（无权重时）**

```python
# tests/test_model_loader.py
import pytest
from model_loader import load_model, ModelMissingError

def test_missing_weights_raises():
    with pytest.raises(ModelMissingError):
        load_model('tests/fixtures/empty_weights_dir')
```

（Step 1 先建 `tests/fixtures/empty_weights_dir/` 空目录）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_model_loader.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 model_loader.py**

```python
# backend/model_loader.py
import os, glob
import numpy as np

N_STUDENTS = 3
STUDENT_FILES = ['kdens_s%d_fp16.npz' % i for i in range(N_STUDENTS)]
PRIMARY = STUDENT_FILES[0]

class ModelMissingError(Exception):
    pass

class ModelHandle:
    def __init__(self, students):
        self.students = students
    def logits(self, obs, mask):
        lg = sum(s.logits(obs, mask) for s in self.students) / len(self.students)
        return lg

def _load_one(path):
    from engine.numpy_resfused import NumpyResFused
    return NumpyResFused(path)

def load_model(weights_dir, single=False):
    """默认 3 学生 ensemble；ENSEMBLE=1 环境变量或 single=True 时只加载 s0 单学生。"""
    names = [PRIMARY] if (single or os.environ.get('ENSEMBLE') == '1') else STUDENT_FILES
    paths = []
    missing = []
    for n in names:
        p = os.path.join(weights_dir, n)
        if os.path.exists(p):
            paths.append(p)
        else:
            missing.append(n)
    if not paths:
        raise ModelMissingError('缺少模型权重: %s（从 HF Dannibal/ijcai-mahjong-ckpts-2026 champion/ 下载 %s）'
                                % (weights_dir, ', '.join(names)))
    students = [_load_one(p) for p in paths]
    return ModelHandle(students)
```

- [ ] **Step 4: 写权重下载脚本（用户执行，或用户手动放置）**

```bash
# backend/fetch_weights.sh
#!/usr/bin/env bash
# 从 HuggingFace 下载 kdens3 三学生权重到 backend/weights/
# 用法: bash backend/fetch_weights.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)/weights"
BASE="https://huggingface.co/Dannibal/ijcai-mahjong-ckpts-2026/resolve/main/champion"
for i in 0 1 2; do
  curl -L -o "$DIR/kdens_s${i}_fp16.npz" "$BASE/kdens_s${i}_fp16.npz"
done
ls -la "$DIR"
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_model_loader.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add backend/model_loader.py backend/fetch_weights.sh backend/weights/README.md tests/test_model_loader.py tests/fixtures/empty_weights_dir && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: 模型权重加载与 ensemble"
```

---

### Task 6: analyzer.py — prepare/step 编排 + LRU 缓存

**Files:**
- Create: `backend/analyzer.py`
- Create: `backend/salasa.py`（平台拉取）
- Test: `tests/test_analyzer.py`

**Interfaces:**
- Consumes: `parse_record`、`replay_round`、`DiscardNode`、`load_model`、`ModelMissingError`
- Produces:
  - `salasa.fetch_record(game_id: str, platform: str) -> dict` — GET `{platform}/api/platform/record/{game_id}`，返回 `{game_id, rule, players, record}`（players 元素含 `user_id`/`username`；`original` 由 `original_player_index` 或列表序推导）；非 200 抛 `RuntimeError`
  - `prepare(record: dict, game_id: str, rule: str, players: list) -> dict` — 解析 + 逐视角 `replay_round` 全量预重放（无 AI），返回 `meta`（players、rounds 含每视角 nodes 的静态快照：step/player/seat/actual_tile/hand/melds/river/draw，**不含 obs**）
  - `class Analyzer`：`__init__(model, cache_cap=2000)`；`analyze_step(prep, round_index, step, viewer) -> dict` — 找到该节点缓存 obs → `model.logits` → softmax → mask 内打牌 top-k（≥3 个）→ `{step, player, actual_tile, ai_top: [{tile, prob}], agree}`；LRU 缓存键 `(id, round_index, step, viewer)`
  - `class LRU`（简单 dict + 有序性，cap 淘汰）

- [ ] **Step 1: 写失败测试（用 stub 模型）**

```python
# tests/test_analyzer.py
import json, math
import numpy as np
from converter import parse_record
from analyzer import prepare, Analyzer

class StubModel:
    def logits(self, obs, mask):
        lg = np.zeros(235)
        lg[2:36] = np.arange(34, dtype=np.float32) / 34.0   # Play 概率递增
        ht = np.flatnonzero(obs[2])                          # 手牌位置 (4,9) 扁平索引
        lg[2 + ht] += 5.0                                    # 手牌中的牌被拔高
        return lg

def _load():
    with open('tests/fixtures/guobiao_example.json') as f:
        return json.load(f)

def test_prepare_meta():
    data = _load()
    prep = prepare(data['record'], 'demo1', 'guobiao', [])
    assert prep['game_id'] == 'demo1'
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    vw = r2['viewers'][1]                        # original 1 = player_index 0，本局摸打者
    assert vw['error'] is None
    node = vw['nodes'][0]
    assert node['actual_tile'] == 'W3'
    assert 'obs' not in node

def test_analyze_step_topk():
    data = _load()
    prep = prepare(data['record'], 'demo1', 'guobiao', [])
    a = Analyzer(StubModel())
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    out = a.analyze_step(prep, round_index=2, step=r2['viewers'][1]['nodes'][0]['step'], viewer=1)
    assert out['actual_tile'] == 'W3'
    assert len(out['ai_top']) >= 3
    probs = [p for _, p in out['ai_top']]
    assert all(0 <= p <= 1 for p in probs)
    assert out['ai_top'][0]['prob'] >= probs[1]
    assert out['agree'] is True or out['agree'] is False

def test_cache_hit():
    data = _load()
    prep = prepare(data['record'], 'demo1', 'guobiao', [])
    a = Analyzer(StubModel())
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    step = r2['viewers'][1]['nodes'][0]['step']
    a.analyze_step(prep, 2, step, 1)
    n_calls = [0]
    orig = a.model.logits
    a.model.logits = lambda o, m: (n_calls.__setitem__(0, n_calls[0] + 1) or orig(o, m))
    a.analyze_step(prep, 2, step, 1)
    assert n_calls[0] == 0                        # 命中缓存不再推理
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_analyzer.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 salasa.py**

```python
# backend/salasa.py
import urllib.request, json

def fetch_record(game_id, platform='https://salasasa.cn'):
    url = '%s/api/platform/record/%s' % (platform.rstrip('/'), game_id)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    if not data.get('success'):
        raise RuntimeError('平台返回失败: %r' % data)
    d = data['data']
    players = []
    for i, p in enumerate(d.get('players') or []):
        orig = p.get('original_player_index')
        players.append({'original': orig if orig is not None else i,
                        'user_id': p.get('user_id'), 'username': p.get('username')})
    return {'game_id': d['game_id'], 'rule': d.get('rule'), 'players': players,
            'record': d['record']}
```

- [ ] **Step 4: 实现 analyzer.py**

```python
# backend/analyzer.py
import math, time
from collections import OrderedDict
import numpy as np
from converter import parse_record, replay_round

class LRU:
    def __init__(self, cap):
        self.cap = cap
        self.d = OrderedDict()
    def get(self, k):
        if k not in self.d:
            return None
        self.d.move_to_end(k)
        return self.d[k]
    def put(self, k, v):
        self.d[k] = v
        self.d.move_to_end(k)
        while len(self.d) > self.cap:
            self.d.popitem(last=False)

def prepare(record, game_id, rule, players):
    g = parse_record(record, game_id, players, rule)
    rounds = []
    for r in g.rounds:
        per_viewer = {}
        for v in range(4):
            ra = replay_round(r, v)
            per_viewer[v] = ({
                'error': ra.error,
                'nodes': [{'step': n.step, 'player': n.player, 'seat': n.seat,
                           'actual_tile': n.actual_tile, 'hand': n.hand,
                           'melds': n.melds, 'river': n.river, 'draw': n.draw,
                           'obs': n.obs}
                          for n in ra.nodes],
            } if ra.error is None else {'error': ra.error, 'nodes': []})
        rounds.append({'round_index': r.round_index, 'current_round': r.current_round,
                       'seats': r.seats, 'dealer_index': r.dealer_index,
                       'viewers': per_viewer})
    return {'game_id': game_id, 'players': players, 'rounds': rounds}

class Analyzer:
    def __init__(self, model, cache_cap=2000):
        self.model = model
        self.cache = LRU(cache_cap)

    def _node_meta(self, prep, round_index, step, viewer):
        for r in prep['rounds']:
            if r['round_index'] == round_index:
                vw = r['viewers'].get(viewer)
                if vw is None or vw['error'] is not None:
                    return None, r
                for n in vw['nodes']:
                    if n['step'] == step:
                        return n, r
                return None, r
        return None, None

    def analyze_step(self, prep, round_index, step, viewer):
        key = (prep['game_id'], round_index, step, viewer)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        node, rnd = self._node_meta(prep, round_index, step, viewer)
        if node is None:
            return {'error': 'no such node', 'step': step}
        obs, mask = node['obs']['observation'], node['obs']['action_mask']
        lg = self.model.logits(obs, mask)
        lg = np.asarray(lg).flatten()
        ex = np.exp(lg - lg.max())
        probs = ex / ex.sum()
        po = 2  # OFFSET_ACT['Play']
        legal = [(i, float(probs[i])) for i in range(po, po + 34) if mask[i] > 0]
        legal.sort(key=lambda t: -t[1])
        top = [{'tile': _TILE_NAMES[i - po], 'prob': round(p, 4)} for i, p in legal[:3]]
        agree = top[0]['tile'] == node['actual_tile']
        out = {'step': node['step'], 'player': node['player'], 'seat': node['seat'],
               'actual_tile': node['actual_tile'], 'ai_top': top, 'agree': agree}
        self.cache.put(key, out)
        return out

_TILE_NAMES = [*['W%d' % i for i in range(1, 10)],
               *['T%d' % i for i in range(1, 10)],
               *['B%d' % i for i in range(1, 10)],
               *['F%d' % i for i in range(1, 5)],
               *['J%d' % i for i in range(1, 4)]]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_analyzer.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add backend/analyzer.py backend/salasa.py tests/test_analyzer.py && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: prepare/step 编排与 LRU 缓存"
```

---

### Task 7: main.py — FastAPI 路由 + 静态托管

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `prepare`、`Analyzer`、`salasa.fetch_record`、`load_model`、`ModelMissingError`
- Produces: 路由
  - `POST /api/analyze/prepare` — body `{"game_id": "...", "platform": "..."}` 或 `{"record": {...}}` → 200 `{analysis_id, meta}`（无 AI）；模型缺失不阻塞 prepare；非法 body → 400
  - `GET /api/analysis/{aid}/step?round=&step=&viewer=` — 404（未知 aid / 无此节点）、503（模型缺失）、200 `{...ai_top}`；模型加载一次全局复用
  - `GET /` 与静态托管 `web/dist/`（不存在时 404 提示）
- `analysis_id` = `uuid4().hex[:12]`；`prep_cache: dict[str, prep]` LRU cap 20

- [ ] **Step 1: 写失败测试**

```python
# tests/test_api.py
import json
from fastapi.testclient import TestClient
import main

def _load():
    with open('tests/fixtures/guobiao_example.json') as f:
        return json.load(f)

class _StubModel:
    def logits(self, obs, mask):
        import numpy as np
        lg = np.zeros(235); lg[2:36] = 0.1; lg[2 + 2] = 1.0   # 偏好 W3
        return lg

def _patch(monkeypatch):
    monkeypatch.setattr(main, '_MODEL', _StubModel())

def test_prepare_then_step(monkeypatch):
    _patch(monkeypatch)
    client = TestClient(main.app)
    data = _load()
    r = client.post('/api/analyze/prepare', json={'record': data['record']})
    assert r.status_code == 200
    meta = r.json()['meta']
    aid = r.json()['analysis_id']
    assert meta['game_id'] == 'upload'
    node = meta['rounds'][1]['viewers']['1']['nodes'][0]     # JSON 后 viewers 键为 str
    r2 = client.get('/api/analysis/%s/step' % aid,
                    params={'round': node and meta['rounds'][1]['round_index'],
                            'step': node['step'], 'viewer': 1})
    assert r2.status_code == 200
    assert r2.json()['actual_tile'] == 'W3'
    assert r2.json()['ai_top'][0]['tile'] == 'W3'

def test_unknown_aid_404(monkeypatch):
    _patch(monkeypatch)
    client = TestClient(main.app)
    r = client.get('/api/analysis/nope/step', params={'round': 2, 'step': 1, 'viewer': 0})
    assert r.status_code == 404

def test_bad_body_400():
    client = TestClient(main.app)
    r = client.post('/api/analyze/prepare', json={})
    assert r.status_code == 400
```

（需要 `pip install httpx` 作为 TestClient 依赖）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 main.py**

```python
# backend/main.py
import os, uuid
from collections import OrderedDict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from analyzer import prepare, Analyzer
from salasa import fetch_record
from model_loader import load_model, ModelMissingError

app = FastAPI(title='mcr-ai-analyzer')

class PrepareBody(BaseModel):
    game_id: str | None = None
    platform: str = 'https://salasasa.cn'
    record: dict | None = None

_MODEL = None
_MODEL_ERR = None
_ANALYZER = None
_prep_cache = OrderedDict()
_PREP_CAP = 20

def _get_model():
    global _MODEL, _MODEL_ERR
    if _MODEL is None and _MODEL_ERR is None:
        try:
            _MODEL = load_model(os.path.join(os.path.dirname(__file__), 'weights'))
        except ModelMissingError as e:
            _MODEL_ERR = str(e)
    if _MODEL is None:
        raise HTTPException(status_code=503, detail=_MODEL_ERR or 'model not ready')
    return _MODEL

@app.post('/api/analyze/prepare')
def api_prepare(body: PrepareBody):
    if body.record is not None:
        record, game_id, players, rule = body.record, body.record.get('game_id', 'upload'), [], body.record.get('rule', 'guobiao')
        if 'record' not in body.record and 'game_round' not in body.record:
            raise HTTPException(status_code=400, detail='record 字段需为牌谱 JSON')
        record = body.record.get('record', body.record)
    elif body.game_id:
        try:
            fetched = fetch_record(body.game_id, body.platform)
        except Exception as e:
            raise HTTPException(status_code=502, detail='拉取牌谱失败: %r' % e)
        record, game_id, players, rule = fetched['record'], fetched['game_id'], fetched['players'], fetched['rule']
    else:
        raise HTTPException(status_code=400, detail='需要 game_id 或 record')
    aid = uuid.uuid4().hex[:12]
    _prep_cache[aid] = prepare(record, game_id, rule, players)
    _prep_cache.move_to_end(aid)
    while len(_prep_cache) > _PREP_CAP:
        _prep_cache.popitem(last=False)
    meta = _prep_cache[aid]
    return {'analysis_id': aid, 'meta': meta}

@app.get('/api/analysis/{aid}/step')
def api_step(aid: str, round: int, step: int, viewer: int = 0):
    prep = _prep_cache.get(aid)
    if prep is None:
        raise HTTPException(status_code=404, detail='analysis_id 不存在或已过期')
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = Analyzer(_get_model())       # 全局复用：LRU 缓存跨请求生效
    return _ANALYZER.analyze_step(prep, round, step, viewer)

_web_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'dist')
if os.path.isdir(_web_dir):
    app.mount('/', StaticFiles(directory=_web_dir, html=True), name='web')
```

（注：`Analyzer` 实例需全局复用——用 `_analyzer_slot.obj` 惰性创建，保证缓存跨请求生效）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add backend/main.py tests/test_api.py && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: FastAPI prepare/step 路由"
```

---

### Task 8: 前端工程骨架（复制 game2d 回放引擎）

**Files:**
- Create: `web/`（Vite + Vue3 + TS 工程）
- Copy from `~/project/open_mahjong_unity/open_mahjong_web/client/`:
  - `views/game2d/Replay.vue` → `web/src/views/Replay.vue`
  - `game2d/` 全目录 → `web/src/game2d/`
  - `api/`（仅牌谱相关部分）、`composables/`、`i18n/`、`layouts/`、`stores/`、`utils/`、`styles/`、`constants/` 中 Replay.vue 及其依赖链引用到的文件（用 vite 构建报错驱动逐个补齐）
  - `package.json`（依赖与脚本，去掉平台特有的）
- Create: `web/vite.config.js`、`web/tsconfig.json`、`web/index.html`

**Interfaces:**
- Produces: `web/dist/`（`npm run build` 产物，Task 7 的静态托管目录）

- [ ] **Step 1: 复制与初始化**

```bash
mkdir -p ~/project/mahjong-ai-analyzer/web && cd ~/project/mahjong-ai-analyzer/web
npm create vite@latest . -- --template vue-ts 2>&1 | tail -5
# 复制 Replay.vue 与 game2d/
cp -r ~/project/open_mahjong_unity/open_mahjong_web/client/src/views/game2d/Replay.vue src/views/
cp -r ~/project/open_mahjong_unity/open_mahjong_web/client/src/game2d src/
# 按构建错误补齐依赖（i18n 等最小集）
```

- [ ] **Step 2: 构建驱动补齐依赖**

```bash
cd ~/project/mahjong-ai-analyzer/web && npm install && npm run build
```

反复修复缺失 import/依赖（`@/` 别名、i18n 语言包、PixiJS 版本等）直到构建成功。Replay.vue 的牌谱加载入口暂时改为本地 fixture JSON（`tests/fixtures/guobiao_example.json` 复制到 `web/public/`），验证回放可渲染。

- [ ] **Step 3: 验证构建产物可被后端托管**

```bash
cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/python -m uvicorn main:app --port 8000 &
curl -s http://127.0.0.1:8000/ | grep -i '<div id="app"' && echo STATIC_OK
```

Expected: `STATIC_OK`

- [ ] **Step 4: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add web/ && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: 前端工程骨架（复制 game2d 回放引擎）"
```

---

### Task 9: 前端改造 — 后端 API 对接 + AI 面板

**Files:**
- Modify: `web/src/views/Replay.vue`（加 AI 面板 DOM overlay、api 调用）
- Create: `web/src/game2d/ai/api.ts`（prepare/step 调用）
- Modify: `web/src/views/Replay.vue` 牌谱加载逻辑（输入 game_id 或粘贴 JSON → 调 prepare → 用返回 record 构造 RecordReplay）

**Interfaces:**
- Consumes: 后端 `POST /api/analyze/prepare`、`GET /api/analysis/{aid}/step`
- Produces: AI 面板展示当前 xunmu 节点的 `{ai_top, actual_tile, agree}`

**实现要点（基于已确认的现有接口）：**
- Replay.vue 已有 `viewerOriginal`（视角切换）、`xunmuNodes`（打牌节点列表）、`step()`/`selectRound()`、`onBoardStep(1)`（滚轮步进）
- 新增：`aiPanel` 状态（`{loading, data}`）；`currentXunmuIndex` 由当前步推导；`requestAi()` 在 viewer/round/step 变化时触发（仅当当前步是 xunmu 节点）；AI 面板为固定位置 DOM 卡片（左上），显示 top-3 概率条 + agree 标记
- 分歧列表（可选，MVP 后可加）：不阻塞本次交付

- [ ] **Step 1: 写 ai/api.ts**

```typescript
// web/src/game2d/ai/api.ts
export interface AiTopEntry { tile: string; prob: number }
export interface AiStepResult {
  step: number; player: number; seat: number
  actual_tile: string; ai_top: AiTopEntry[]; agree: boolean
  error?: string
}

export async function prepareAnalysis(
  payload: { game_id?: string; platform?: string; record?: unknown },
): Promise<{ analysis_id: string; meta: unknown }> {
  const resp = await fetch('/api/analyze/prepare', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!resp.ok) throw new Error(`prepare failed: ${resp.status}`)
  return resp.json()
}

export async function fetchStep(
  analysisId: string, round: number, step: number, viewer: number,
): Promise<AiStepResult> {
  const q = new URLSearchParams({ round: String(round), step: String(step), viewer: String(viewer) })
  const resp = await fetch(`/api/analysis/${analysisId}/step?${q}`)
  if (!resp.ok) throw new Error(`step failed: ${resp.status}`)
  return resp.json()
}
```

- [ ] **Step 2: Replay.vue 接入**

在 `Replay.vue` 中：
1. 模板加 AI 面板块（`v-if="aiData"`）：顶部横条或左上卡片，列出 `aiData.ai_top`（每项 tile 名 + 百分比条）与 `actual_tile`（agree 时绿色、分歧时红色高亮）。
2. script：`const analysisId = ref<string|null>(null)`、`const aiData = ref<AiStepResult|null>(null)`、`const aiLoading = ref(false)`；`watch([viewerOriginal, currentRound, currentStep], requestAi)`。
3. 牌谱加载入口改造：页面顶部输入框（game_id + 可选 platform）或粘贴 JSON → `prepareAnalysis` → `analysisId` 存下、用返回的 record 构造 RecordReplay（替换原平台加载逻辑）。
4. `requestAi()`：计算当前 xunmu 节点 step（`replay.xunmuNodes(currentRound, viewerOriginal)` 二分查找当前步）；若是节点 → `fetchStep`；非节点 → 清空面板。**服务端 503（模型缺失）时显示提示文案，不阻塞回放。**
5. 移除平台相关的"返回 2D 大厅"按钮（改为返回输入页）。

- [ ] **Step 3: 构建与人工验证**

```bash
cd ~/project/mahjong-ai-analyzer/web && npm run build
cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/python -m uvicorn main:app --port 8000
```

浏览器打开 `http://127.0.0.1:8000/`：粘贴 fixture JSON → 回放渲染 → 翻到 xunmu 节点 → AI 面板出现 top-3；切换视角后面板数据随视角变化。（模型权重未下载时面板显示 503 提示。）

- [ ] **Step 4: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add web/ && git -c user.name="a314" -c user.email="a314@localhost" commit -m "feat: AI 面板与后端对接"
```

---

### Task 10: 端到端验证 + README 完善

**Files:**
- Modify: `README.md`（完整：运行方式、依赖、权重下载、许可注明、架构图）
- Create: `tests/test_e2e.py`（权重存在时跑真实推理；权重缺失时 skip）

**Interfaces:**
- Consumes: 全部

- [ ] **Step 1: 写 e2e 测试（权重存在时）**

```python
# tests/test_e2e.py
import json, os
import pytest
import numpy as np
from model_loader import load_model
from analyzer import prepare, Analyzer

pytestmark = pytest.mark.skipif(
    not os.path.exists('backend/weights/kdens_s0_fp16.npz'),
    reason='weights not downloaded')

def test_real_model_roundtrip():
    with open('tests/fixtures/guobiao_example.json') as f:
        record = json.load(f)['record']
    model = load_model('backend/weights')
    prep = prepare(record, 'e2e', 'guobiao', [])
    a = Analyzer(model)
    out = a.analyze_step(prep, round_index=2, step=1, viewer=0)
    assert out['ai_top']
    assert all(np.isfinite(p) for _, p in out['ai_top'])
    assert out['ai_top'][0]['tile'] in ('W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8', 'W9',
                                        'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9',
                                        'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9',
                                        'F1', 'F2', 'F3', 'F4', 'J1', 'J2', 'J3')
```

- [ ] **Step 2: 运行全部测试 + 权重下载**

```bash
cd ~/project/mahjong-ai-analyzer && bash backend/fetch_weights.sh   # 若尚未下载
PYTHONPATH=backend .venv/bin/pytest tests/ -v
```

Expected: 全部 PASS（含 test_e2e 真实模型）

- [ ] **Step 3: 真实牌谱端到端（需网络）**

```bash
cd ~/project/mahjong-ai-analyzer && PYTHONPATH=backend .venv/bin/python -c "
from salasa import fetch_record
from analyzer import prepare, Analyzer
from model_loader import load_model
# 用平台最近天梯牌谱 game_id（先手动从平台页面获取一个真实 game_id）
r = fetch_record('<真实 game_id>')
prep = prepare(r['record'], r['game_id'], r['rule'], r['players'])
a = Analyzer(load_model('backend/weights'))
print('rounds:', len(prep['rounds']))
n_nodes = sum(len(v['nodes']) for rd in prep['rounds'] for v in rd['viewers'].values())
print('total discard nodes:', n_nodes)
out = a.analyze_step(prep, prep['rounds'][0]['round_index'], prep['rounds'][0]['viewers'][0]['nodes'][0]['step'], 0)
print('sample:', out)
"
```

Expected: 输出总决策点数（≥1）与一条样例分析；若真实牌谱暴露转换问题，回到 Task 4 修正并在 fixture 补测试。

- [ ] **Step 4: 完善 README**

README 含：项目简介、架构图（spec §2）、运行步骤（venv、pip install、fetch_weights、uvicorn、npm build）、API 说明、牌谱格式转换说明（花牌剔除等）、许可与出处注明（engine/ 来自 IJCAI-mahjong 无 LICENSE；前端来自 open_mahjong_unity MIT）、已知限制（单学生/3 学生切换 `ENSEMBLE=1`）。

- [ ] **Step 5: 提交**

```bash
cd ~/project/mahjong-ai-analyzer && git add README.md tests/test_e2e.py && git -c user.name="a314" -c user.email="a314@localhost" commit -m "docs: README 与端到端验证"
```

---

## 自审记录

- **Spec 覆盖**：§3 转换器 → Task 3/4；§4 懒分析 API → Task 6/7；§5 前端 → Task 8/9；§6 验证 → Task 4/10；§7 部署 → Task 1/10；§8 待办资产 → Task 5（fetch_weights.sh）与 Task 10。
- **已知开放项**（实现时验证，不阻塞）：`bh` 双格式已兼容；`ag` 他人无 tile 语义按 `__main__.py`；示例 fixture 的期望值以真实 c 事件数修正；Task 8 前端依赖链以 vite 报错驱动补齐。

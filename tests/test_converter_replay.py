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
    g = parse_record(data, 'demo1', [], 'guobiao')
    r = g.rounds[1]                          # 第 2 局: seats=[3,0,1,2]（seats[original]=player_index）
    # 事件: bh(53/0) bd(43) d(21) c(21) d(35) c(35) d(42) c(42) hu_first(1)
    # 牌谱语义（game_record_format.md:60）：pX_tiles 与 tick 玩家字段均为 player_index。
    # start_player_index=0（player_index 0 = original 1，坐东位=庄）→ 摸 21、打 21
    ra = replay_round(r, viewer=1)           # original 1 = player_index 0（本局摸打者）
    assert ra.error is None
    assert ra.quan == 0
    assert ra.seat_wind == 0
    assert len(ra.nodes) == 1
    n = ra.nodes[0]
    assert n.actual_tile == 'T1'             # 21 -> T1（万11-19/筒21-29，见 test_tiles.CASES）
    assert n.ok

def test_replay_other_viewer_no_node():
    data = _load()
    g = parse_record(data, 'demo1', [], 'guobiao')
    # original 0 = player_index 3（北位）、original 3 = player_index 2（西位），本局未摸打即结束
    for viewer in (0, 3):
        ra = replay_round(g.rounds[1], viewer=viewer)
        assert ra.nodes == []

def test_round1_hu_terminates():
    data = _load()
    g = parse_record(data, 'demo1', [], 'guobiao')
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

def test_own_discard_claimed_by_next_does_not_crash():
    # 自己打 W4 被下家 cl 吃：c 事件已 'Player 0 Play W4' 移除手牌，cl 补喂若再次
    # remove 会 ValueError 崩掉整局。应防御跳过补喂，保留 viewer 打 W4 的决策点。
    from converter import RoundRecord
    ticks = [
        ['d', 21],                 # step0: viewer 摸 T1
        ['c', 14, 'T'],            # step1: viewer 打 W4 -> 决策点(step0)
        ['cl', 14, 1, 12, 13],     # step2: 下家(1) cl 吃 W4（中间张 W3）
        ['c', 21, 'T'],            # step3: 玩家1 打 T1
        ['d', 31], ['c', 31, 'B'], # 玩家2 摸打 B1
        ['d', 41], ['c', 41, 'F'], # 玩家3 摸打 F1
        ['d', 42], ['c', 42, 'F'], # step8/9: viewer 摸 F2 打 F2 -> 决策点(step8)
        ['liuju'],
    ]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0,1,2,3], dealer_index=0,
        start_player_index=0,
        hands=[[11,11,11,12,12,12,13,13,13,14,21,22,23], [21]*13, [31]*13, [41]*13],
        action_ticks=ticks)
    ra = replay_round(fake, viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 2
    n0, n1 = ra.nodes
    assert n0.step == 0 and n0.actual_tile == 'W4'
    assert n1.step == 8 and n1.actual_tile == 'F2'
    assert ra.nodes[0].ok

def test_bd_buflower_draw_to_claimant():
    # bh 的补花者(2) 非 start_player(0)：bh 不改变摸/打轮转；bd 补摸给补花者本人，
    # 打牌仍按 original 轮转（轮到 2 打时产生决策点）。
    from converter import RoundRecord
    ticks = [
        ['bh', 53, 2],             # step0: 玩家2 补花（轮转仍从 start_player 0 开始）
        ['bd', 21, 2],             # step1: 玩家2 补摸 T1
        ['d', 31],                 # step2: 玩家0 摸 B1
        ['c', 31, 'T'],            # step3: 玩家0 打 B1
        ['d', 42],                 # step4: 玩家1 摸 F2
        ['c', 42, 'T'],            # step5: 玩家1 打 F2
        ['d', 21],                 # step6: 玩家2 摸 T1
        ['c', 21, 'T'],            # step7: 玩家2 打 T1 -> 决策点(step1, draw=T1)
        ['liuju'],
    ]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0,1,2,3], dealer_index=0,
        start_player_index=0,
        hands=[[11]*13, [21]*13, [31,32,33,34,35,36,37,38,39,41,42,43,44], [41]*13],
        action_ticks=ticks)
    ra = replay_round(fake, viewer=2)
    assert ra.error is None
    assert len(ra.nodes) == 1
    assert ra.nodes[0].seat == 2
    assert ra.nodes[0].step == 6
    assert ra.nodes[0].actual_tile == 'T1'

# ---------- 吃牌（cl/cm/cr）顺子中间张换算 ----------

def _chi_fake(ticks):
    from converter import RoundRecord
    return RoundRecord(
        round_index=1, current_round=1, seats=[0,1,2,3], dealer_index=0,
        start_player_index=0,
        hands=[[11,11,11,12,12,12,13,13,13,14,17,18,21], [21]*13, [31]*13, [41]*13],
        action_ticks=ticks)

def _chi_789_ticks(claim):
    # viewer 手牌含 7/8（万）；玩家1 弃 9（万）后 viewer cl 吃（弃 9 是顺子右端）。
    return [
        ['d', 22],                 # step0: viewer 摸 T2
        ['c', 22, 'T'],            # step1: viewer 打 T2 -> 决策点(step0)
        ['d', 19],                 # step2: 玩家1 摸 W9
        ['c', 19, 'T'],            # step3: 玩家1 弃 W9
        [claim, 19, 0],            # step4: viewer 吃 9
        ['c', 21, 'T'],            # step5: viewer 打 T1 -> 决策点(step4)
        ['liuju'],
    ]

def test_chi_cl_discard9_boundary():
    # cl 弃 9（边界）：中间张 = 9-1 = W8，顺子展开 W7W8W9，无 B10 越界崩溃。
    ra = replay_round(_chi_fake(_chi_789_ticks('cl')), viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 2
    n = ra.nodes[1]
    assert n.step == 4 and n.actual_tile == 'T1'
    assert n.melds == [['CHI', 'W8', 3]]     # offer 3 = cl（弃牌是右端）
    assert n.draw is None

def test_chi_normalized_discard_id():
    # tick[1]=109（归一化 9）与 9、19（W9）等价：同一中间张 W8。
    base = _chi_789_ticks('cl')
    melds = []
    for claim_id in (19, 109, 9):
        ticks = base[:4] + [['cl', claim_id, 0]] + base[5:]
        ra = replay_round(_chi_fake(ticks), viewer=0)
        assert ra.error is None
        melds.append(ra.nodes[1].melds)
    assert melds[0] == melds[1] == melds[2] == [['CHI', 'W8', 3]]

def test_chi_cr_discard1_boundary():
    # cr 弃 1（吃 123 边界）：中间张 = 1+1 = W2，顺子展开 W1W2W3。
    ticks = [
        ['d', 22],                 # step0: viewer 摸 T2
        ['c', 22, 'T'],            # step1: viewer 打 T2
        ['d', 11],                 # step2: 玩家1 摸 W1
        ['c', 11, 'T'],            # step3: 玩家1 弃 W1
        ['cr', 11, 0],             # step4: viewer cr 吃 1
        ['c', 21, 'T'],            # step5: viewer 打 T1 -> 决策点(step4)
        ['liuju'],
    ]
    ra = replay_round(_chi_fake(ticks), viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 2
    n = ra.nodes[1]
    assert n.step == 4 and n.actual_tile == 'T1'
    assert n.melds == [['CHI', 'W2', 1]]     # offer 1 = cr（弃牌是左端）

def test_chi_cr_discard9_boundary_defense():
    # cr 弃 9 -> 中间张 10 越界：抛 ValueError 走 error 路径（标记失败而非崩溃）。
    ticks = _chi_789_ticks('cr')
    ra = replay_round(_chi_fake(ticks), viewer=0)
    assert ra.error is not None
    assert 'out of 1..9' in ra.error

def test_meld_branch_no_duplicate_discard_feed():
    # 玩家1 弃 W9、玩家2 cl 吃：c 事件已无条件喂 'Player 1 Play W9'，鸣牌分支不得再补喂。
    # 补喂会让 history 中 W9 出现 2 次 -> DISCARD 平面计数 2（污染 is4thTile/胡判定）。
    # 修复后 W9 在玩家1 弃牌段只计 1 次。
    from converter import RoundRecord
    ticks = [
        ['d', 22],                  # step0: viewer(0) 摸 T2
        ['c', 22, 'T'],             # step1: viewer 打 T2 -> 决策点(step0)
        ['d', 19],                  # step2: 玩家1 摸 W9
        ['c', 19, 'T'],             # step3: 玩家1 弃 W9
        ['cl', 19, 2, 17, 18],      # step4: 玩家2 cl 吃 W9（中间张 W8）
        ['c', 21, 'T'],             # step5: 玩家2 打 T1
        ['d', 31], ['c', 31, 'B'],  # step6/7: 玩家3 摸打 B1
        ['d', 22], ['c', 21, 'T'],  # step8/9: viewer 摸 T2 打 T1 -> 决策点(step8)
        ['liuju'],
    ]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0, 1, 2, 3], dealer_index=0,
        start_player_index=0,
        hands=[[11, 11, 11, 12, 12, 12, 13, 13, 13, 14, 17, 18, 21],
               [21] * 13, [31] * 13, [41] * 13],
        action_ticks=ticks)
    ra = replay_round(fake, viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 2
    obs = ra.nodes[1].obs['observation']     # 决策点(step8)：W9 已弃、已被玩家2 吃
    w9 = 8                                    # OFFSET_TILE['W9']（W1 起 0..8）
    disc = obs[6 + 4 * 1: 6 + 4 * 1 + 4, :, w9]  # DISCARD 平面 6 起，玩家1 相对座位 p=1
    assert int(disc.sum()) == 1


def test_flower_discard_does_not_crash():
    """玩家摸切打出花牌：不崩溃、不产生决策点、轮转继续。"""
    from converter import RoundRecord
    ticks = [['d', 53], ['c', 53, 'T'], ['d', 21], ['c', 21, 'T']]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0, 1, 2, 3], dealer_index=0,
        start_player_index=0,
        hands=[[11] * 13, [21] * 13, [31] * 13, [41] * 13], action_ticks=ticks)
    # viewer 0 摸切花牌（无决策点）；player 1 随后摸打 21 是决策点
    ra0 = replay_round(fake, viewer=0)
    assert ra0.error is None
    assert ra0.nodes == []
    ra1 = replay_round(fake, viewer=1)
    assert ra1.error is None
    assert len(ra1.nodes) == 1
    assert ra1.nodes[0].actual_tile == 'T1'


def test_flower_kept_then_discard_numeral_is_decision():
    """摸花不补、随后打手牌数牌：该次打牌是决策点（观测=13 张数牌）。"""
    from converter import RoundRecord
    ticks = [['d', 53], ['c', 11, 'F'], ['d', 21], ['c', 21, 'T']]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0, 1, 2, 3], dealer_index=0,
        start_player_index=0,
        hands=[[11] * 13, [21] * 13, [31] * 13, [41] * 13], action_ticks=ticks)
    ra = replay_round(fake, viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 1
    n0 = ra.nodes[0]
    assert n0.step == 0 and n0.actual_tile == 'W1'   # 摸花后打 W1（决策点，draw=None）
    assert n0.draw is None
    ra1 = replay_round(fake, viewer=1)
    assert len(ra1.nodes) == 1
    assert ra1.nodes[0].actual_tile == 'T1'          # player 1 正常摸打


def test_cuohe_round_continues():
    """错和（fan 含「错和」）不是局终点：对局继续，后续决策点保留。"""
    from converter import RoundRecord
    ticks = [['d', 21], ['c', 21, 'T'], ['d', 19], ['c', 19, 'T'],
             ['hu_first', 1, 0, ['错和'], [0, 0, 0, 0]],
             ['d', 22], ['c', 22, 'T'], ['d', 23], ['c', 23, 'T']]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0, 1, 2, 3], dealer_index=0,
        start_player_index=0,
        hands=[[11] * 13, [21] * 13, [31] * 13, [41] * 13], action_ticks=ticks)
    # 错和者 player1（原应和牌者），对局继续：player2/player3 的摸打保留
    ra2 = replay_round(fake, viewer=2)
    assert ra2.error is None
    assert len(ra2.nodes) == 1            # player2 打 22 的决策点（错和后续）
    assert ra2.nodes[0].actual_tile == 'T2'

def test_normalized_tile_id_in_draw_and_discard():
    """归一化 id（≥100，赤五）在 d/c 事件中不崩溃（105→15 万5）。"""
    from converter import RoundRecord
    ticks = [['d', 105], ['c', 105, 'T'], ['d', 11], ['c', 11, 'T']]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0, 1, 2, 3], dealer_index=0,
        start_player_index=0,
        hands=[[11] * 13, [21] * 13, [31] * 13, [41] * 13], action_ticks=ticks)
    ra0 = replay_round(fake, viewer=0)
    assert ra0.error is None
    # 摸 105（万5）后打 105：打牌决策点（实际打的是 W5）
    assert len(ra0.nodes) == 1
    assert ra0.nodes[0].actual_tile == 'W5'


def test_dealer_first_discard_is_decision():
    """庄家起手 14 张（无花）：首打（无 d 事件）也是决策点，观测 14 张。"""
    from converter import RoundRecord
    ticks = [['c', 11, 'F'], ['d', 21], ['c', 21, 'T']]
    dealer14 = [11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0, 1, 2, 3], dealer_index=0,
        start_player_index=0,
        hands=[dealer14, [31] * 13, [41] * 13, [21] * 13], action_ticks=ticks)
    ra = replay_round(fake, viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 1
    n0 = ra.nodes[0]
    assert n0.step == 0 and n0.actual_tile == 'W1'
    import numpy as np
    o = n0.obs['observation']
    assert int((o[2:6, :, :] > 0).sum()) == 14     # 观测 14 张（Botzone 摸后状态）

def test_dealer_with_flower_buys_pending_via_bd():
    """庄家起手含花（补花）时：bd 补摸覆盖初始 pending，首打节点 step=bd 下标。"""
    from converter import RoundRecord
    ticks = [['bh', 51, 0], ['bd', 21, 0], ['c', 11, 'F']]
    fake = RoundRecord(
        round_index=1, current_round=1, seats=[0, 1, 2, 3], dealer_index=0,
        start_player_index=0,
        hands=[[11] * 13 + [51], [21] * 13, [31] * 13, [41] * 13], action_ticks=ticks)
    ra = replay_round(fake, viewer=0)
    assert ra.error is None
    assert len(ra.nodes) == 1
    assert ra.nodes[0].step == 1 and ra.nodes[0].actual_tile == 'W1'

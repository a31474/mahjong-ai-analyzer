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
    # 事件: bd(43) d(21) c(21) d(35) c(35) d(42) c(42) hu_first(1)
    # original 1 = player_index 0（start_player_index=0，第 1 个摸打者）→ 摸 43/21、打 21(W3)
    ra = replay_round(r, viewer=1)
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
    ra = replay_round(g.rounds[1], viewer=0) # original 0 = player_index 3，本局未摸打即结束
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
    # 自己打 T1 被下家 cl 吃：c 事件已 'Player 0 Play T1' 移除手牌，cl 补喂若再次
    # remove 会 ValueError 崩掉整局。应防御跳过补喂，保留 viewer 打 T1 的决策点。
    from converter import RoundRecord
    ticks = [
        ['d', 21],                 # step0: viewer 摸 T1
        ['c', 21, 'T'],            # step1: viewer 打 T1 -> 决策点(step0)
        ['cl', 22, 1, 20, 21],     # step2: 下家(1) 吃 T1
        ['c', 22, 'T'],            # step3: 玩家1 打 T2
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
    assert n0.step == 0 and n0.actual_tile == 'T1'
    assert n1.step == 8 and n1.actual_tile == 'F2'
    assert ra.nodes[0].ok

def test_bh_updates_current_to_flower_claimant():
    # bh 的补花者(2) 非 start_player(0)，其后的 d 摸牌者应为补花者本人。
    from converter import RoundRecord
    ticks = [
        ['bh', 53, 2],             # step0: 玩家2 补花
        ['d', 21],                 # step1: 玩家2（viewer）摸 T1
        ['c', 21, 'T'],            # step2: viewer 打 T1 -> 决策点(step1)
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
    assert ra.nodes[0].step == 1
    assert ra.nodes[0].actual_tile == 'T1'

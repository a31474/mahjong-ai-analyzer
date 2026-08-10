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

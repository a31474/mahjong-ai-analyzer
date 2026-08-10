import json
from converter import parse_record, RoundRecord, GameRecord

def _load():
    with open('tests/fixtures/guobiao_example.json') as f:
        data = json.load(f)
    return data

def test_parse_rounds():
    data = _load()
    g = parse_record(data, 'demo1', [], 'guobiao')
    assert isinstance(g, GameRecord)
    assert len(g.rounds) == 2
    r1 = g.rounds[0]
    assert r1.current_round == 1
    assert r1.seats == [0, 1, 2, 3]
    assert len(r1.hands[0]) == 13

def test_hands_contain_flower():
    data = _load()
    g = parse_record(data, 'demo1', [], 'guobiao')
    assert 53 in g.rounds[0].hands[0]      # p0 起手含花 53

def test_bh_variants():
    data = _load()
    g = parse_record(data, 'demo1', [], 'guobiao')
    bh3 = [t for t in g.rounds[0].action_ticks if t[0] == 'bh']
    assert bh3 and bh3[0][0] == 'bh'       # 3 元素 bh 可解析

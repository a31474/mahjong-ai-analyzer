import json, math
import numpy as np
from converter import parse_record
from analyzer import prepare, Analyzer

class StubModel:
    """契约同 ModelHandle：返回 mask 内归一化的概率分布（各学生 softmax 平均的等价物）。"""
    def logits(self, obs, mask):
        lg = np.zeros(235)
        lg[2:36] = np.arange(34, dtype=np.float32) / 34.0   # Play 概率递增
        ht = np.flatnonzero(obs[2])                          # 手牌位置 (4,9) 扁平索引
        lg[2 + ht] += 5.0                                    # 手牌中的牌被拔高
        m = np.asarray(mask, dtype=np.float32)
        lg = np.where(m > 0, lg, -1e30)
        lg = lg - lg.max()
        p = np.exp(lg) * (m > 0)
        return p / p.sum()

def _load():
    with open('tests/fixtures/guobiao_example.json') as f:
        return json.load(f)

def test_prepare_meta():
    data = _load()
    prep = prepare(data, 'demo1', 'guobiao', [])
    assert prep['game_id'] == 'demo1'
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    vw = r2['viewers'][0]                        # original 0 = start_player_index，本局摸打者
    assert vw['error'] is None
    node = vw['nodes'][0]
    assert node['actual_tile'] == 'T1'
    assert 'obs' not in node

def test_analyze_step_topk():
    data = _load()
    prep = prepare(data, 'demo1', 'guobiao', [])
    a = Analyzer(StubModel())
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    out = a.analyze_step(prep, round_index=2, step=r2['viewers'][0]['nodes'][0]['step'], viewer=0)
    assert out['actual_tile'] == 'T1'
    assert len(out['ai_top']) >= 3
    probs = [x['prob'] for x in out['ai_top']]
    assert all(0 <= p <= 1 for p in probs)
    assert out['ai_top'][0]['prob'] >= probs[1]
    assert out['agree'] is True or out['agree'] is False

def test_cache_hit():
    data = _load()
    prep = prepare(data, 'demo1', 'guobiao', [])
    a = Analyzer(StubModel())
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    step = r2['viewers'][0]['nodes'][0]['step']
    a.analyze_step(prep, 2, step, 0)
    n_calls = [0]
    orig = a.model.logits
    a.model.logits = lambda o, m: (n_calls.__setitem__(0, n_calls[0] + 1) or orig(o, m))
    a.analyze_step(prep, 2, step, 0)
    assert n_calls[0] == 0                        # 命中缓存不再推理

import json
import os

from cache_store import DiskCache, safe_key


def test_roundtrip(tmp_path):
    dc = DiskCache(str(tmp_path))
    dc.put('game|2|5|0', {'tile': 'W3', 'prob': 0.9})
    assert dc.get('game|2|5|0') == {'tile': 'W3', 'prob': 0.9}


def test_key_hashed(tmp_path):
    dc = DiskCache(str(tmp_path))
    dc.put('upload|1|2|3', {'ok': True})
    assert safe_key('upload|1|2|3') != 'upload|1|2|3'   # 不落原始键（路径安全）
    assert len(os.listdir(str(tmp_path))) == 1


def test_missing_returns_none(tmp_path):
    dc = DiskCache(str(tmp_path))
    assert dc.get('nope') is None


def test_corrupt_file_returns_none(tmp_path):
    dc = DiskCache(str(tmp_path))
    dc.put('k', {'ok': True})
    with open(dc._path('k'), 'w') as f:
        f.write('{broken json')
    assert dc.get('k') is None


def test_trim_cap(tmp_path):
    dc = DiskCache(str(tmp_path), file_cap=3)
    for i in range(6):
        dc.put('key%d' % i, {'i': i})
    remaining = [n for n in os.listdir(str(tmp_path)) if n.endswith('.json')]
    assert len(remaining) <= 3
    # 最新的键仍可命中
    assert dc.get('key5') == {'i': 5}


def test_analyzer_disk_hit_no_inference(tmp_path):
    """磁盘命中时不调模型（重启/新会话后同一牌谱免重复推理）。"""
    import numpy as np
    from analyzer import prepare, Analyzer

    with open('tests/fixtures/guobiao_example.json') as f:
        record = json.load(f)

    calls = []

    class StubModel:
        def logits(self, obs, mask):
            calls.append(1)
            lg = np.zeros(235)
            lg[2:36] = 0.1
            lg[2 + 9] = 1.0    # 偏好 T1
            return lg

    disk = DiskCache(str(tmp_path))
    prep = prepare(record, 'demo1', 'guobiao', [], cache_key='ck1')
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    step = r2['viewers'][1]['nodes'][0]['step']

    a1 = Analyzer(StubModel(), disk=disk)
    out1 = a1.analyze_step(prep, 2, step, 1)
    assert calls == [1]

    # 新 Analyzer 实例（模拟服务重启，内存缓存清空）——磁盘命中，不再推理
    a2 = Analyzer(StubModel(), disk=disk)
    out2 = a2.analyze_step(prep, 2, step, 1)
    assert calls == [1]
    assert out1 == out2

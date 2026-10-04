import json
import os

from cache_store import DiskCache, RoundCache, safe_key


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
            lg[2 + 18] = 1.0    # 偏好 B1（21=筒1，B 段起始索引 18）
            return lg

    disk = RoundCache(DiskCache(str(tmp_path)))
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


# ---------- RoundCache：按局聚合 ----------

def test_round_cache_one_file_per_round(tmp_path):
    """同一局所有 (step, viewer) 结果共用一个文件；不同局分开。"""
    rc = RoundCache(DiskCache(str(tmp_path)))
    for step, viewer in [(3, 0), (7, 0), (7, 1)]:
        rc.put('ck1', 2, step, viewer, {'v': '%d|%d' % (step, viewer)})
    rc.put('ck1', 3, 1, 0, {'v': 'round3'})
    files = [n for n in os.listdir(str(tmp_path)) if n.endswith('.json')]
    assert len(files) == 2                                   # 2 局 → 2 个文件
    assert rc.get('ck1', 2, 3, 0) == {'v': '3|0'}
    assert rc.get('ck1', 2, 7, 1) == {'v': '7|1'}
    assert rc.get('ck1', 3, 1, 0) == {'v': 'round3'}
    assert rc.get('ck1', 2, 8, 0) is None


def test_round_cache_survives_new_instance(tmp_path):
    """新实例（模拟重启）从文件恢复，同局多步仍命中。"""
    rc1 = RoundCache(DiskCache(str(tmp_path)))
    rc1.put('ck', 1, 5, 2, {'a': 1})
    rc1.put('ck', 1, 6, 2, {'a': 2})
    rc2 = RoundCache(DiskCache(str(tmp_path)))
    assert rc2.get('ck', 1, 5, 2) == {'a': 1}
    assert rc2.get('ck', 1, 6, 2) == {'a': 2}
    assert rc2.get('ck', 1, 99, 2) is None


def test_round_cache_migrates_legacy_single_step(tmp_path):
    """旧「单步一文件」缓存命中后写入新布局（读到即迁移）。"""
    legacy = DiskCache(str(tmp_path))
    legacy.put(RoundCache.legacy_key('ck', 4, 9, 0), {'legacy': True})
    new_dir = str(tmp_path / 'round')
    rc = RoundCache(DiskCache(new_dir), legacy=legacy)
    assert rc.get('ck', 4, 9, 0) == {'legacy': True}
    assert len(os.listdir(new_dir)) == 1                     # 已迁移到新布局
    fresh = RoundCache(DiskCache(new_dir))                   # 不依赖 legacy 也能命中
    assert fresh.get('ck', 4, 9, 0) == {'legacy': True}


def test_round_cache_mem_lru_bounded(tmp_path):
    """内存只保留最近若干局，超限时淘汰最旧的（磁盘仍在）。"""
    rc = RoundCache(DiskCache(str(tmp_path)), mem_cap=2)
    for rnd in (1, 2, 3):
        rc.put('ck', rnd, 0, 0, {'r': rnd})
    assert len(rc.mem) == 2
    assert rc.get('ck', 1, 0, 0) == {'r': 1}                 # 从磁盘回读

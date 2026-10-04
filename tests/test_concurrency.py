"""并发安全：FastAPI 同步路由跑在线程池里，多用户 / 多开同一局会真并发。

覆盖三层：
1. LRU / RoundCache 的容器竞态（move_to_end vs popitem，修复前可复现 KeyError）
2. 并发写同一局不同 step：整局文件不能互相覆盖丢条目
3. Analyzer 并发分析同一局的同一步：结果一致、无异常
"""
import json
import sys
import threading

import numpy as np

from analyzer import LRU, Analyzer, prepare
from cache_store import DiskCache, RoundCache


def _run_threads(target, n=8):
    errs = []

    def wrapped(tid):
        try:
            target(tid)
        except Exception as e:                     # noqa: BLE001 - 收集任意异常用于断言
            errs.append('%s: %s' % (type(e).__name__, e))

    threads = [threading.Thread(target=wrapped, args=(t,)) for t in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errs


def _fast_switch():
    """减小切换间隔以放大竞态窗口；返回原值供调用方恢复。"""
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    return old


def test_lru_concurrent_no_keyerror():
    old = _fast_switch()
    try:
        lru = LRU(4)
        errs = _run_threads(lambda tid: [
            (lru.put('k%d' % ((i + tid) % 6), i) if i % 2 else lru.get('k%d' % ((i + tid) % 6)))
            for i in range(30000)
        ])
    finally:
        sys.setswitchinterval(old)
    assert errs == []


def test_round_cache_concurrent_keeps_all_entries(tmp_path):
    """并发写同一局的不同 step：落盘的整局文件应包含全部条目。"""
    rc = RoundCache(DiskCache(str(tmp_path)), mem_cap=4)
    per_thread, workers = 50, 4
    errs = _run_threads(
        lambda tid: [rc.put('ck', 1, tid * 100 + i, 0, {'v': tid * 100 + i})
                     for i in range(per_thread)],
        n=workers)
    assert errs == []
    fresh = RoundCache(DiskCache(str(tmp_path)))        # 只信磁盘
    for tid in range(workers):
        for i in range(per_thread):
            key = tid * 100 + i
            assert fresh.get('ck', 1, key, 0) == {'v': key}, 'step %d 丢失' % key


class _StubModel:
    """确定性的假模型：偏好 B1（21=筒1，B 段起始索引 18）。"""

    def __init__(self):
        self.calls = []

    def logits(self, obs, mask):
        self.calls.append(1)
        lg = np.zeros(235)
        lg[2:36] = 0.1
        lg[2 + 18] = 1.0
        return lg


def test_analyzer_concurrent_same_step_same_round(tmp_path):
    """多个请求同时分析「同一局同一步」（多用户 / 多开同一牌谱）：结果一致且无异常。"""
    with open('tests/fixtures/guobiao_example.json') as f:
        record = json.load(f)
    prep = prepare(record, 'demo1', 'guobiao', [], cache_key='ck1')
    r2 = [r for r in prep['rounds'] if r['round_index'] == 2][0]
    step = r2['viewers'][1]['nodes'][0]['step']

    analyzer = Analyzer(_StubModel(), disk=RoundCache(DiskCache(str(tmp_path))))
    results = []
    errs = _run_threads(lambda _tid: results.append(analyzer.analyze_step(prep, 2, step, 1)))
    assert errs == []
    assert len(results) == 8
    assert all(r == results[0] for r in results)
    assert results[0]['ai_top'][0]['tile'] == 'B1'


def test_analyzer_concurrent_distinct_steps_same_round(tmp_path):
    """并发分析同一局的不同步：都能拿到结果，且整局文件最终条目齐全。"""
    with open('tests/fixtures/guobiao_example.json') as f:
        record = json.load(f)
    prep = prepare(record, 'demo1', 'guobiao', [], cache_key='ck1')
    targets = []
    for r in prep['rounds']:
        for viewer, vw in r['viewers'].items():
            if vw['error']:
                continue
            for node in vw['nodes']:
                targets.append((r['round_index'], node['step'], viewer))
    assert len(targets) >= 3

    disk = RoundCache(DiskCache(str(tmp_path)))
    analyzer = Analyzer(_StubModel(), disk=disk)
    outputs = {}
    lock = threading.Lock()

    def worker(tid):
        rnd, step, viewer = targets[tid % len(targets)]
        out = analyzer.analyze_step(prep, rnd, step, viewer)
        with lock:
            outputs.setdefault((rnd, step, viewer), []).append(out)

    assert _run_threads(worker) == []
    # 每个目标节点的多次并发结果一致
    for key, outs in outputs.items():
        assert all(o == outs[0] for o in outs), '%s 结果不一致' % (key,)
    # 磁盘上这些条目齐全
    fresh = RoundCache(DiskCache(str(tmp_path)))
    for rnd, step, viewer in targets:
        assert fresh.get('ck1', rnd, step, viewer) is not None, '%s 未落盘' % ((rnd, step, viewer),)

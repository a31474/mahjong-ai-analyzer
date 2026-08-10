import json
from fastapi.testclient import TestClient
import main

def _load():
    with open('tests/fixtures/guobiao_example.json') as f:
        return json.load(f)

class _StubModel:
    def logits(self, obs, mask):
        import numpy as np
        lg = np.zeros(235); lg[2:36] = 0.1; lg[2 + 9] = 1.0  # 偏好 T1（tile_id 21=筒1，模型 Play 段索引 9）
        m = np.asarray(mask, dtype=np.float32)
        lg = np.where(m > 0, lg, -1e30)
        lg = lg - lg.max()
        p = np.exp(lg) * (m > 0)
        return p / p.sum()

def _patch(monkeypatch):
    monkeypatch.setattr(main, '_MODEL', _StubModel())

def test_prepare_then_step(monkeypatch):
    _patch(monkeypatch)
    client = TestClient(main.app)
    data = _load()
    r = client.post('/api/analyze/prepare', json={'record': data})
    assert r.status_code == 200
    body = r.json()
    meta = body['meta']
    aid = body['analysis_id']
    assert meta['game_id'] == 'upload'
    assert body['record']['game_title']            # record 随响应返回（前端渲染需要）
    node = meta['rounds'][1]['viewers']['1']['nodes'][0]     # JSON 后 viewers 键为 str
    r2 = client.get('/api/analysis/%s/step' % aid,
                    params={'round': node and meta['rounds'][1]['round_index'],
                            'step': node['step'], 'viewer': 1})
    assert r2.status_code == 200
    assert r2.json()['actual_tile'] == 'T1'
    assert r2.json()['ai_top'][0]['tile'] == 'T1'

def test_unknown_aid_404(monkeypatch):
    _patch(monkeypatch)
    client = TestClient(main.app)
    r = client.get('/api/analysis/nope/step', params={'round': 2, 'step': 1, 'viewer': 0})
    assert r.status_code == 404

def test_bad_body_400():
    client = TestClient(main.app)
    r = client.post('/api/analyze/prepare', json={})
    assert r.status_code == 400


def test_health_ok(monkeypatch):
    _patch(monkeypatch)
    client = TestClient(main.app)
    r = client.get('/api/health')
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'ok'
    assert body['model'] == 'ready'

def test_health_model_missing(monkeypatch):
    monkeypatch.setattr(main, '_MODEL', None)
    monkeypatch.setattr(main, '_MODEL_ERR', '缺少模型权重: /nonexistent')
    client = TestClient(main.app)
    r = client.get('/api/health')
    assert r.status_code == 503
    assert r.json()['status'] == 'degraded'
    assert '缺少模型权重' in r.json()['detail']


def test_record_disk_cache_skips_fetch(monkeypatch, tmp_path):
    """game_id 路径：磁盘缓存命中时不再调用 fetch_record。"""
    import main
    _patch(monkeypatch)
    # 指向临时缓存目录，避免污染真实缓存
    monkeypatch.setattr(main, '_RECORD_DISK', __import__('cache_store').DiskCache(str(tmp_path)))
    calls = []

    def fake_fetch(game_id, platform):
        calls.append(game_id)
        return {'game_id': game_id, 'rule': 'guobiao', 'players': [],
                'record': {'game_title': {}, 'game_round': {}}}

    monkeypatch.setattr(main, 'fetch_record', fake_fetch)
    client = TestClient(main.app)

    r1 = client.post('/api/analyze/prepare', json={'game_id': 'abc123XYZ'})
    assert r1.status_code == 200
    assert calls == ['abc123XYZ']

    r2 = client.post('/api/analyze/prepare', json={'game_id': 'abc123XYZ'})
    assert r2.status_code == 200
    assert calls == ['abc123XYZ']    # 未再拉取

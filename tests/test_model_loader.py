import os
import numpy as np
import pytest
from model_loader import load_model, ModelHandle, ModelMissingError

def test_missing_weights_raises():
    with pytest.raises(ModelMissingError):
        load_model('tests/fixtures/empty_weights_dir')

def test_single_student_fallback_when_others_missing():
    os.environ.pop('ENSEMBLE', None)
    with pytest.raises(ModelMissingError):
        load_model('tests/fixtures/empty_weights_dir', single=True)

def test_real_weights_load():
    """权重存在时真实加载验证：logits 形状 (235,) 且数值有限。"""
    weights_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'weights')
    weights_dir = os.path.abspath(weights_dir)
    if not os.path.exists(os.path.join(weights_dir, 'kdens_s0_fp16.npz')):
        pytest.skip('真实权重不存在，跳过')
    os.environ.pop('ENSEMBLE', None)
    handle = load_model(weights_dir, single=True)
    rng = np.random.RandomState(0)
    obs = rng.randint(0, 2, size=(38, 4, 9)).astype(np.float32)
    mask = np.ones(235, dtype=np.float32)
    lg = handle.logits(obs, mask)
    assert isinstance(lg, np.ndarray)
    assert lg.shape == (235,)
    assert np.isfinite(lg).all()

class FakeStudent:
    def __init__(self, lg):
        self.lg = np.asarray(lg, dtype=np.float64)
    def logits(self, obs, mask):
        return self.lg.copy()

def _mask():
    m = np.zeros(235)
    m[2:6] = 1
    return m

def _logits():
    lg = np.zeros(235)
    lg[2:6] = [1.0, 0.0, 0.0, 0.0]          # 学生 A：偏好 mask 内第一项
    return lg

def test_ensemble_averages_masked_softmax_per_student():
    # 契约（同 IJCAI ensemble_infer.py）：每学生 mask 内 softmax 后算术平均。
    # 学生 B 均匀（0.25 每项）；学生 A logits [1,0,0,0] -> softmax
    # [e/(e+3), 1/(e+3), 1/(e+3), 1/(e+3)]。平均 = [(0.25+e/(e+3))/2, ...]。
    s_uni = FakeStudent(np.zeros(235))
    s_b = FakeStudent(_logits())
    h = ModelHandle([s_uni, s_b])
    p = h.logits(None, _mask())
    assert p.shape == (235,)
    assert np.isclose(p.sum(), 1.0)              # mask 内归一化，和为 1
    expected = np.array([0.25 + np.e / (np.e + 3), 0.25 + 1 / (np.e + 3),
                         0.25 + 1 / (np.e + 3), 0.25 + 1 / (np.e + 3)]) / 2.0
    assert np.allclose(p[2:6], expected)
    assert not np.any(p[6:])                     # mask 外置 0
    assert p[2] > p[3]

def test_ensemble_differs_from_softmax_of_mean_logits():
    # softmax(mean logits) != mean softmax：聚合必须按学生分别 softmax。
    s_uni = FakeStudent(np.zeros(235))
    s_b = FakeStudent(_logits())
    h = ModelHandle([s_uni, s_b])
    p = h.logits(None, _mask())
    naive = np.zeros(235)
    naive[2:6] = 0.5                             # mean of raw logits = [0.5,0,0,0]
    ex = np.exp(naive)
    naive = ex / ex.sum()
    assert not np.allclose(p, naive)

import os
import numpy as np
import pytest
from model_loader import load_model, ModelMissingError

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

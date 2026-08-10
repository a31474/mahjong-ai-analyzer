# tests/test_e2e.py
import json, os
import pytest
import numpy as np
from model_loader import load_model
from analyzer import prepare, Analyzer

pytestmark = pytest.mark.skipif(
    not os.path.exists('backend/weights/kdens_s0_fp16.npz'),
    reason='weights not downloaded')

def test_real_model_roundtrip():
    with open('tests/fixtures/guobiao_example.json') as f:
        record = json.load(f)
    model = load_model('backend/weights')
    prep = prepare(record, 'e2e', 'guobiao', [])
    a = Analyzer(model)
    out = a.analyze_step(prep, round_index=2, step=2, viewer=1)
    assert out['ai_top']
    assert all(np.isfinite(x['prob']) for x in out['ai_top'])
    assert out['ai_top'][0]['tile'] in ('W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8', 'W9',
                                        'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9',
                                        'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9',
                                        'F1', 'F2', 'F3', 'F4', 'J1', 'J2', 'J3')
    assert out['actual_tile'] == 'T1'
    assert isinstance(out['agree'], bool)
    assert 0 <= out['ai_top'][0]['prob'] <= 1

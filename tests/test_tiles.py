import pytest
from tiles import to_csm, is_flower, FLOWER_IDS

CASES = {11: 'W1', 19: 'W9', 21: 'T1', 29: 'T9', 31: 'B1', 39: 'B9',
         41: 'F1', 42: 'F2', 43: 'F3', 44: 'F4', 45: 'J1', 46: 'J2', 47: 'J3'}

def test_suits_and_honors():
    for tid, csm in CASES.items():
        assert to_csm(tid) == csm

def test_flowers():
    assert is_flower(51) and is_flower(58)
    assert not is_flower(47)
    assert FLOWER_IDS == frozenset(range(51, 59))

def test_flower_raises():
    with pytest.raises(ValueError):
        to_csm(53)

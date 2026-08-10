import pytest
from tiles import to_csm, is_flower, FLOWER_IDS

CASES = {11: 'W1', 19: 'W9', 21: 'T1', 29: 'T9', 31: 'B1', 39: 'B9',
         41: 'F1', 42: 'F2', 43: 'F3', 44: 'F4', 45: 'J1', 46: 'J3', 47: 'J2'}

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

def test_honor_swap_contract():
    # salasasa 45=中 46=白 47=发（gbHepai 推不倒含 46=白、绿一色含 47=发）;
    # IJCAI J1=中 J2=发 J3=白（dragon_aug.py）。45->J1 46->J3 47->J2。
    assert to_csm(45) == 'J1'
    assert to_csm(46) == 'J3'
    assert to_csm(47) == 'J2'
    assert to_csm(41) == 'F1' and to_csm(44) == 'F4'

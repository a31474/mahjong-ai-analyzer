"""open_mahjong tile_id <-> IJCAI CSM string code."""

FLOWER_IDS = frozenset(range(51, 59))  # 51-58 春夏秋冬梅兰竹菊

# 字牌（41-44 风牌，45-47 三元牌）。salasasa 平台：45=中、46=白、47=发
# （gbHepai 推不倒含 46=白、绿一色含 47=发，双重印证）；IJCAI 编码：J1=中、J2=发、J3=白
# （IJCAI-mahjong/train/caiest_repro/dragon_aug.py 中/發/白 = J1/J2/J3）。
HONOR_CSM = {45: 'J1', 46: 'J3', 47: 'J2'}

def is_flower(tile_id: int) -> bool:
    return tile_id in FLOWER_IDS

def _normalize(tile_id: int) -> int:
    """归一化 id（≥100，赤五编码：105=万5/205=筒5/305=索5）转标准 id（15/25/35）。"""
    if tile_id >= 100:
        return (tile_id // 100) * 10 + tile_id % 100
    return tile_id

def to_csm(tile_id: int) -> str:
    tile_id = _normalize(tile_id)
    if is_flower(tile_id):
        raise ValueError('flower tile %d is excluded from CSM view' % tile_id)
    if tile_id in HONOR_CSM:
        return HONOR_CSM[tile_id]
    suit, num = divmod(tile_id, 10)          # 11..47
    table = {1: 'W', 2: 'T', 3: 'B', 4: 'F'}
    if suit not in table or not (1 <= num <= (7 if suit == 4 else 9)):
        raise ValueError('invalid tile_id %d' % tile_id)
    return table[suit] + str(num)            # 11->W1, 31->B1

"""open_mahjong tile_id <-> IJCAI CSM string code.

字母约定与 Botzone 官方协议、PyMahjongGB（本仓库 engine 依赖的算番库）一致：
    W = 万（11-19）、B = 筒/饼（21-29）、T = 索/条（31-39）

依据：PyMahjongGB `mahjong-algorithm/tile.h`（TILE_1s=0x21 索、TILE_1p=0x31 筒）配合
`mahjong.cpp` 的字符串表 "W1..W9","T1..T9","B1..B9"；Botzone wiki 亦为「B6=六筒、T8=8条」。
实验复核：234/234/666/888+发发 全用 T 算得「绿一色」，全用 B 只得「混一色」。
详见 docs/salasasa-botzone-conversion.md。
"""

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
    table = {1: 'W', 2: 'B', 3: 'T', 4: 'F'}  # 2=筒(21-29)->B、3=索(31-39)->T
    if suit not in table or not (1 <= num <= (7 if suit == 4 else 9)):
        raise ValueError('invalid tile_id %d' % tile_id)
    return table[suit] + str(num)            # 11->W1, 21->B1, 31->T1

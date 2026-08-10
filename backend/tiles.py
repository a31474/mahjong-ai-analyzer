"""open_mahjong tile_id <-> IJCAI CSM string code."""

FLOWER_IDS = frozenset(range(51, 59))  # 51-58 春夏秋冬梅兰竹菊

def is_flower(tile_id: int) -> bool:
    return tile_id in FLOWER_IDS

def to_csm(tile_id: int) -> str:
    if is_flower(tile_id):
        raise ValueError('flower tile %d is excluded from CSM view' % tile_id)
    suit, num = divmod(tile_id, 10)          # 11..47
    table = {1: 'W', 2: 'T', 3: 'B', 4: 'F'}
    if suit not in table or not (1 <= num <= (7 if suit == 4 else 9)):
        raise ValueError('invalid tile_id %d' % tile_id)
    if suit == 4 and num > 4:                # 45-47 -> J1-J3（中发白）
        return 'J' + str(num - 4)
    return table[suit] + str(num)            # 11->W1, 31->B1

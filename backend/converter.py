from dataclasses import dataclass, field

@dataclass
class RoundRecord:
    round_index: int
    current_round: int
    seats: list
    dealer_index: int
    start_player_index: int
    hands: list          # hands[original_player] -> 起手牌 list（含花）
    action_ticks: list

@dataclass
class GameRecord:
    game_id: str
    rule: str
    players: list        # [{original, username}, ...]
    rounds: list

def normalize_tick(tick):
    out = []
    for v in tick:
        if isinstance(v, str) and v.isdigit():
            out.append(int(v))
        else:
            out.append(v)
    return out

def parse_record(record, game_id, players, rule):
    game_round = record.get('game_round') or {}
    rounds = []
    for key in sorted(game_round.keys(), key=lambda k: int(k.rsplit('_', 1)[-1])):
        r = game_round[key]
        hands = []
        for p in range(4):
            hands.append(list(r.get('p%d_tiles' % p) or []))
        rounds.append(RoundRecord(
            round_index=r.get('round_index'),
            current_round=r.get('current_round'),
            seats=list(r.get('seats') or []),
            dealer_index=r.get('dealer_index'),
            start_player_index=r.get('start_player_index'),
            hands=hands,
            action_ticks=[normalize_tick(t) for t in (r.get('action_ticks') or [])],
        ))
    return GameRecord(game_id=game_id, rule=rule, players=players, rounds=rounds)

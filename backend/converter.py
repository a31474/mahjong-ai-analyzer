import sys, os
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'engine'))
from engine.feature import FeatureAgent
from tiles import to_csm, is_flower

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

# cl/cm/cr 被吃的弃牌在顺子中的位置 -> 中间张相对弃牌的偏移
_CHI_DELTA = {'cl': -1, 'cm': 0, 'cr': 1}

def chi_middle_tile(tile_id, action):
    """cl/cm/cr 的 tick[1] 是被吃的弃牌 id（open_mahjong 编码 11..39；≥100 为
    归一化 id，如 105=5万/205=5筒/305=5条赤五，与 15/25/35 等价）。FeatureAgent
    的 Chi 把传入 tile 当顺子中间张展开为 [tile-1, tile, tile+1]，故按吃法换算
    中间张：cl 弃牌是顺子右端(-1)、cm 是中间(0)、cr 是左端(+1)。换算后点数不在
    1..9（如 cr 弃 9 -> 10）抛 ValueError，走 replay 的 error 路径。"""
    if isinstance(tile_id, str):
        tile_id = int(tile_id)
    if tile_id >= 100:
        suit, rank = divmod(tile_id, 100)      # 赤五: 105 -> (1,5) 万5
    else:
        suit, rank = divmod(tile_id, 10)       # 普通: 19 -> (1,9) 万9
    if suit == 0:
        suit = 1                               # 归一化裸点无花色: 仅万（105=5万）
    mid_rank = rank + _CHI_DELTA[action]
    if not 1 <= mid_rank <= 9:
        raise ValueError('Chi %s discard %d -> middle rank %d out of 1..9'
                         % (action, tile_id, mid_rank))
    return to_csm(suit * 10 + mid_rank)

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

@dataclass
class DiscardNode:
    step: int
    player: int
    seat: int
    actual_tile: str
    hand: list
    melds: list
    river: list
    draw: str
    obs: dict
    ok: bool = True

@dataclass
class RoundAnalysis:
    round_index: int
    viewer: int
    seat_wind: int
    quan: int
    nodes: list
    error: str = None

def quan_of(current_round):
    return (current_round - 1) // 4

def replay_round(round_rec, viewer):
    seats = round_rec.seats
    seat_wind = seats[viewer] if viewer < len(seats) else viewer
    quan = quan_of(round_rec.current_round)
    agent = FeatureAgent(seat_wind)
    agent.request2obs('Wind %d' % quan)
    # 牌谱语义（game_record_format.md:60）：pX_tiles 的 X 与 action_ticks 的 action_player
    # 均为当局 player_index（门风位）；viewer 是 original，需经 seats[original] 映射取手牌。
    pi = seat_wind
    hand = [t for t in round_rec.hands[pi] if not is_flower(t)]
    if not hand or len(hand) > 14:
        # 起手 13（庄家 14）张，剔花后 1..14 均合法（庄家 14 张 = 13+首摸 1，无花时保留 14）；
        # >14 或空则数据异常
        return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, [],
                             error='viewer%d 起手 %d 张(剔花后), 需要 1..14' % (viewer, len(hand)))
    try:
        agent.request2obs('Deal ' + ' '.join(to_csm(t) for t in hand))
    except Exception as e:
        return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, [],
                             error='Deal 失败: %r' % e)

    nodes = []
    current = round_rec.start_player_index   # player_index 域：摸/打轮转按 player_index
    last_discarder = None
    last_discard_tile = None
    last_fed = None              # 最近一次成功喂入的 (player, tile)
    pending = None               # 待定决策点: (obs, step, draw_tile) —— 自己摸牌/鸣牌后尚未打牌
    flower_claimant = None       # 最近 bh 的补花者（player_index 域），bd 补摸给此人

    def mine(p):
        return p == seat_wind

    def is_draw_action(a):
        return a in ('d', 'gd', 'bd')

    def feed_play(player, tile):
        """喂 'Player N Play XX'。自己打牌而 tile 已不在手牌时（补喂时该牌早在
        c 事件移除、或状态漂移/非法流），跳过喂食避免 FeatureAgent 对 p==0
        无条件 hand.remove 崩溃；返回是否实际喂入。"""
        if mine(player) and tile not in agent.hand:
            return False
        agent.request2obs('Player %d Play %s' % (player, tile))
        return True

    try:
        for step, tick in enumerate(round_rec.action_ticks):
            a = tick[0]
            if a == 'bh':
                # 补花不改变摸/打轮转（打牌者由 start_player_index 起轮转），仅记录补花者
                if len(tick) > 2 and isinstance(tick[2], int):
                    flower_claimant = tick[2]
                continue
            if is_draw_action(a):
                tid = tick[1]
                if is_flower(tid):
                    # 花牌 Draw 吞掉（bd 才是真实补摸）。但摸花后玩家仍要打一张牌——
                    # 若是不补花而打手牌数牌，该次打牌是打牌决策点，需建立 pending
                    # （观测 = 当前 13 张数牌手牌，与真实数牌一致）。
                    # valid 手动构造：摸花后只能打手牌（花非成和张，不能胡；杠需摸牌时机，
                    # 此处不展开）——Play 合法集 = 手牌去重即可。
                    if mine(current) and a in ('d', 'gd'):
                        agent.valid = [agent.OFFSET_ACT['Play'] + agent.OFFSET_TILE[t]
                                       for t in set(agent.hand)]
                        pending = (agent._obs(), step, None)
                    continue
                tile = to_csm(tid)
                p = flower_claimant if (a == 'bd' and flower_claimant is not None) else current
                if mine(p):
                    obs = agent.request2obs('Draw ' + tile)
                    pending = (obs, step, tile)     # 摸牌后待打牌（含摸到的牌）
                else:
                    agent.request2obs('Player %d Draw' % p)
                continue
            if a == 'c':
                tid = tick[1]
                if is_flower(tid):
                    # 花牌打出（可摸切/手切）：花不进引擎（IJCAI 牌墙 136 无花），
                    # 牌河无吃碰杠可能，仅轮转；防御性清 pending（摸花本就吞掉）。
                    pending = None
                    last_discarder, last_discard_tile = current, tid
                    current = (current + 1) % 4
                    continue
                tile = to_csm(tid)
                fed = feed_play(current, tile)
                if fed:
                    last_fed = (current, tile)
                if mine(current):
                    # 只有自己打牌时消费/清空 pending；别人的 c 不清（补花者补摸后
                    # pending 需保留到轮转回自己打牌）
                    if pending is not None and fed:
                        obs, dstep, draw_tile = pending
                        po = agent.OFFSET_ACT['Play']
                        if obs['action_mask'][po:po+34].any():
                            nodes.append(DiscardNode(
                                step=dstep, player=viewer, seat=seat_wind,
                                actual_tile=tile,
                                hand=[str(t) for t in agent.hand],
                                melds=[list(m) for m in agent.packs[0]],
                                river=list(agent.history[0]),
                                draw=draw_tile,
                                obs=obs))
                    pending = None
                last_discarder, last_discard_tile = current, tile
                current = (current + 1) % 4
                continue
            if a in ('cl', 'cm', 'cr'):
                actor = tick[2] if 0 <= tick[2] < len(seats) else current
                if last_discarder is not None and last_fed != (last_discarder, last_discard_tile):
                    feed_play(last_discarder, last_discard_tile)
                tile = chi_middle_tile(tick[1], a)
                obs = agent.request2obs('Player %d Chi %s' % (actor, tile))
                if obs is not None:
                    pending = (obs, step, None)     # 自己吃后待打牌（无摸牌）
                current = actor
                last_discarder = last_discard_tile = None
                continue
            if a == 'p':
                actor = tick[2] if 0 <= tick[2] < len(seats) else current
                if last_discarder is not None and last_fed != (last_discarder, last_discard_tile):
                    feed_play(last_discarder, last_discard_tile)
                obs = agent.request2obs('Player %d Peng' % actor)
                if obs is not None:
                    pending = (obs, step, None)     # 自己碰后待打牌
                current = actor
                last_discarder = last_discard_tile = None
                continue
            if a == 'g':
                actor = tick[2] if 0 <= tick[2] < len(seats) else current
                if last_discarder is not None and last_fed != (last_discarder, last_discard_tile):
                    feed_play(last_discarder, last_discard_tile)
                agent.request2obs('Player %d Gang' % actor)
                current = actor
                last_discarder = last_discard_tile = None
                continue
            if a == 'ag':
                if mine(current):
                    agent.request2obs('Player %d AnGang %s' % (current, to_csm(tick[1])))
                else:
                    agent.request2obs('Player %d AnGang' % current)
                pending = None                      # 杠了，没有打牌决策
                continue
            if a == 'jg':
                agent.request2obs('Player %d BuGang %s' % (current, to_csm(tick[1])))
                pending = None
                continue
            if a.startswith('hu'):
                if len(tick) > 1 and isinstance(tick[1], int):
                    # tick[1] = hepai_player_index（player_index 域，真实牌谱验证）
                    agent.request2obs('Player %d Hu' % tick[1])
                break
            if a == 'liuju':
                agent.request2obs('Huang')
                break
            # ask_hand/ask_other/ca/end 等: 跳过
    except Exception as e:
        return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, nodes,
                             error='step%d %r: %r' % (step, tick, e))
    return RoundAnalysis(round_rec.round_index, viewer, seat_wind, quan, nodes)

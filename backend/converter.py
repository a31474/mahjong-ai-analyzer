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

def claim_options(agent):
    """把 FeatureAgent 在「别人打牌」后构造的 valid 解码成候选动作列表。

    动作空间（与 deploy/caiest_cnn/feature.py 的 OFFSET_ACT 一致）：
        Pass=0, Hu=1, Play=2..35, Chi=36..98, Peng=99..132, Gang=133..166,
        AnGang=167..200, BuGang=201..234
    Chi 段每 3 个索引一组，对应一个顺子中间张（'WTB'[t//7] + (t%7+2)）；
    Peng/Gang 段按 34 张牌逐一编码。AnGang/BuGang 不会出现在 claim 场景，忽略。
    """
    oa = agent.OFFSET_ACT
    out = []
    for idx in sorted(set(agent.valid or [])):
        if idx == oa['Pass']:
            out.append({'index': idx, 'action': 'pass', 'tile': None})
        elif idx == oa['Hu']:
            out.append({'index': idx, 'action': 'hu', 'tile': None})
        elif idx < oa['Peng']:                      # Chi 段
            t = (idx - oa['Chi']) // 3
            out.append({'index': idx, 'action': 'chi',
                        'tile': 'WTB'[t // 7] + str(t % 7 + 2)})
        elif idx < oa['Gang']:
            out.append({'index': idx, 'action': 'peng',
                        'tile': agent.TILE_LIST[idx - oa['Peng']]})
        elif idx < oa['AnGang']:
            out.append({'index': idx, 'action': 'gang',
                        'tile': agent.TILE_LIST[idx - oa['Gang']]})
    return out

# 出现这些事件说明 claim 窗口已关闭（本家没有鸣牌/和牌 → 判为「过」）
_CLAIM_CLOSERS = frozenset(['d', 'gd', 'bd', 'c', 'liuju', 'end', 'ag', 'jg'])

def _claim_resolution(a, tick, seat_wind, seats, current):
    """判断该 tick 是否揭晓了挂起的 claim。

    返回 (action, tile, cuohe)：action ∈ {chi,peng,gang,hu,pass}；tile 由调用方补
    （chi 需要 chi_middle_tile 换算）。返回 None 表示事件与该决策无关，继续等待。
    """
    def actor_of():
        if len(tick) > 2 and isinstance(tick[2], int) and 0 <= tick[2] < len(seats):
            return tick[2]
        return current

    if a in ('cl', 'cm', 'cr', 'p', 'g'):
        act = {'cl': 'chi', 'cm': 'chi', 'cr': 'chi', 'p': 'peng', 'g': 'gang'}[a]
        return (act, None, False) if actor_of() == seat_wind else ('pass', None, False)
    if a.startswith('hu'):
        winner = tick[1] if len(tick) > 1 and isinstance(tick[1], int) else None
        if winner == seat_wind:
            cuohe = len(tick) > 3 and isinstance(tick[3], list) and '错和' in tick[3]
            return ('hu', None, cuohe)
        return ('pass', None, False)
    if a in _CLAIM_CLOSERS:
        return ('pass', None, False)
    return None

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
    kind: str = 'discard'

@dataclass
class ClaimNode:
    """吃/碰/杠/和/过 的决策点：别人打出牌后、本家可鸣牌（或过）时的观测。

    step = 别人打牌那一 tick 的索引（与 DiscardNode 的 step 不冲突：同一 tick
    对同一 viewer 只会是二者之一）。实际选择由后续 tick 揭晓，见 _claim_resolution。
    """
    step: int
    player: int                 # viewer（original）
    seat: int                   # viewer 的门风（player_index）
    claim_tile: str             # 被鸣/被和的弃牌（CSM，如 'T5'）
    options: list               # [{'index','action','tile'}]，含 pass
    obs: dict
    actual_action: str = None   # 'pass'/'hu'/'chi'/'peng'/'gang'
    actual_tile: str = None     # chi 为顺子中间张；peng/gang 为牌；pass/hu 为 None
    cuohe: bool = False         # 实际选择了和牌但为错和
    ok: bool = True
    kind: str = 'claim'

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
    pending_claim = None         # 待揭晓的 claim 决策点（吃/碰/杠/和/过），由后续 tick 回填实际选择
    flower_claimants = []        # 补花者队列（bh 顺序 append，bd 消费）——多花/交错补花安全

    # 庄家起手 14 张（13 + 跳牌 1，开牌所得无 d 事件）：首打是打牌决策点。
    # Deal 后直接建立 pending（观测 = 14 张 = Botzone 摸后状态，与训练分布一致）；
    # step=0（全局首个 c 前），若随后有 bd 补摸会覆盖为更精确的 step。
    if len(hand) == 14:
        agent.valid = [agent.OFFSET_ACT['Play'] + agent.OFFSET_TILE[to_csm(t)] for t in set(hand)]
        pending = (agent._obs(), 0, None)

    def mine(p):
        return p == seat_wind

    def is_draw_action(a):
        return a in ('d', 'gd', 'bd')

    def feed_play(player, tile):
        """喂 'Player N Play XX'，返回 (是否喂入, obs)。

        自己打牌而 tile 已不在手牌时（补喂时该牌早在 c 事件移除、或状态漂移/非法流），
        跳过喂食避免 FeatureAgent 对 p==0 无条件 hand.remove 崩溃。
        obs 只在「别人打牌」时非空——那正是本家可吃/碰/杠/和/过的观测。
        """
        if mine(player) and tile not in agent.hand:
            return False, None
        return True, agent.request2obs('Player %d Play %s' % (player, tile))

    try:
        for step, tick in enumerate(round_rec.action_ticks):
            a = tick[0]
            if pending_claim is not None:
                # 先看这一 tick 有没有揭晓挂起的 claim（吃/碰/杠/和/过）
                res = _claim_resolution(a, tick, seat_wind, seats, current)
                if res is not None:
                    act, mid, cuohe = res
                    if act == 'chi':
                        try:
                            mid = chi_middle_tile(tick[1], a)
                        except ValueError:
                            mid = None
                    pending_claim.actual_action = act
                    pending_claim.actual_tile = mid
                    pending_claim.cuohe = cuohe
                    nodes.append(pending_claim)
                    pending_claim = None
            if a == 'reset':
                # 重置事件（开局补花结束后/跳转）：显式声明当前行动者（player_index 域）。
                # 前端回放引擎同样以 tick[1] 为准；实测 48/48 局与 start_player_index 相等，
                # 以 reset 为准可兼容二者不一致的牌谱（寻摸/跳转类）。
                if len(tick) > 1 and isinstance(tick[1], int):
                    current = tick[1]
                continue
            if a == 'bh':
                # 补花不改变摸/打轮转（打牌者由 start_player_index 起轮转），仅记录补花者
                if len(tick) > 2 and isinstance(tick[2], int):
                    flower_claimants.append(tick[2])
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
                if a == 'bd':
                    # bd 优先用自身 tick[2]（若存在），否则消费补花者队列
                    if len(tick) > 2 and isinstance(tick[2], int):
                        p = tick[2]
                    elif flower_claimants:
                        p = flower_claimants.pop(0)
                    else:
                        p = current
                else:
                    p = current
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
                    last_discarder, last_discard_tile = None, None   # 花不进入鸣牌配对链
                    current = (current + 1) % 4
                    continue
                tile = to_csm(tid)
                fed, play_obs = feed_play(current, tile)
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
                elif play_obs is not None:
                    # 别人打出的牌 → 本家可能有吃/碰/杠/和/过 的决策点。引擎此时已把
                    # 该弃牌计入牌河并构造好 valid（含 Pass），play_obs 就是该决策点观测。
                    # 只有 Pass 的情况没有分析价值，跳过。
                    opts = claim_options(agent)
                    if any(o['action'] != 'pass' for o in opts):
                        pending_claim = ClaimNode(step=step, player=viewer, seat=seat_wind,
                                                  claim_tile=tile, options=opts, obs=play_obs)
                last_discarder, last_discard_tile = current, tile
                current = (current + 1) % 4
                continue
            if a in ('cl', 'cm', 'cr'):
                actor = tick[2] if 0 <= tick[2] < len(seats) else current
                if last_discarder is not None and last_fed != (last_discarder, last_discard_tile):
                    # 状态漂移防御：补喂失败（弃牌不在手牌等）说明事件流已不一致，
                    # 继续喂会拿过期 curTile 错乱，显式走 error 路径
                    fed_ok, _obs = feed_play(last_discarder, last_discard_tile)
                    if not fed_ok:
                        raise ValueError('鸣牌前弃牌喂入失败（状态漂移）: %s' % (last_discard_tile,))
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
                    # 状态漂移防御：补喂失败（弃牌不在手牌等）说明事件流已不一致，
                    # 继续喂会拿过期 curTile 错乱，显式走 error 路径
                    fed_ok, _obs = feed_play(last_discarder, last_discard_tile)
                    if not fed_ok:
                        raise ValueError('鸣牌前弃牌喂入失败（状态漂移）: %s' % (last_discard_tile,))
                obs = agent.request2obs('Player %d Peng' % actor)
                if obs is not None:
                    pending = (obs, step, None)     # 自己碰后待打牌
                current = actor
                last_discarder = last_discard_tile = None
                continue
            if a == 'g':
                actor = tick[2] if 0 <= tick[2] < len(seats) else current
                if last_discarder is not None and last_fed != (last_discarder, last_discard_tile):
                    # 状态漂移防御：补喂失败（弃牌不在手牌等）说明事件流已不一致，
                    # 继续喂会拿过期 curTile 错乱，显式走 error 路径
                    fed_ok, _obs = feed_play(last_discarder, last_discard_tile)
                    if not fed_ok:
                        raise ValueError('鸣牌前弃牌喂入失败（状态漂移）: %s' % (last_discard_tile,))
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
                # 错和（fan 列表含「错和」）不是局终点：玩家失去和牌权、对局继续
                # （前端 isCuoheTick 同约定）；不喂 Hu、不 break。
                if len(tick) > 3 and isinstance(tick[3], list) and '错和' in tick[3]:
                    continue
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

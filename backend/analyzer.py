import math, time
from collections import OrderedDict
import numpy as np
from converter import parse_record, replay_round, RoundRecord

class LRU:
    def __init__(self, cap):
        self.cap = cap
        self.d = OrderedDict()
    def get(self, k):
        if k not in self.d:
            return None
        self.d.move_to_end(k)
        return self.d[k]
    def put(self, k, v):
        self.d[k] = v
        self.d.move_to_end(k)
        while len(self.d) > self.cap:
            self.d.popitem(last=False)

def _dump_node(n):
    """节点 → JSON 可序列化 dict（obs 不入 meta，需要时由 Analyzer._obs_for 重放取）。

    两类节点：discard（自己摸/鸣牌后待打牌）与 claim（别人打牌后本家可吃/碰/杠/和/过）。
    """
    if getattr(n, 'kind', 'discard') == 'claim':
        return {'kind': 'claim', 'step': n.step, 'player': n.player, 'seat': n.seat,
                'claim_tile': n.claim_tile, 'options': n.options,
                'actual_action': n.actual_action, 'actual_tile': n.actual_tile,
                'cuohe': n.cuohe}
    return {'kind': 'discard', 'step': n.step, 'player': n.player, 'seat': n.seat,
            'actual_tile': n.actual_tile, 'hand': n.hand, 'melds': n.melds,
            'river': n.river, 'draw': n.draw}

def prepare(record, game_id, rule, players, cache_key=None):
    g = parse_record(record, game_id, players, rule)
    rounds = []
    for r in g.rounds:
        per_viewer = {}
        for v in range(4):
            ra = replay_round(r, v)
            per_viewer[v] = ({
                'error': ra.error,
                'nodes': [_dump_node(n) for n in ra.nodes],
            } if ra.error is None else {'error': ra.error, 'nodes': []})
        rounds.append({'round_index': r.round_index, 'current_round': r.current_round,
                       'seats': r.seats, 'dealer_index': r.dealer_index,
                       'start_player_index': r.start_player_index,
                       'hands': r.hands, 'action_ticks': r.action_ticks,
                       'viewers': per_viewer})
    return {'game_id': game_id, 'cache_key': cache_key or game_id,
            'players': players, 'rounds': rounds}

class Analyzer:
    def __init__(self, model, cache_cap=2000, disk=None):
        self.model = model
        self.cache = LRU(cache_cap)
        self.disk = disk        # RoundCache 实例（可选）：同一局的所有单步结果聚合持久化

    def _node_meta(self, prep, round_index, step, viewer):
        for r in prep['rounds']:
            if r['round_index'] == round_index:
                vw = r['viewers'].get(viewer)
                if vw is None or vw['error'] is not None:
                    return None, r
                for n in vw['nodes']:
                    if n['step'] == step:
                        return n, r
                return None, r
        return None, None

    def _obs_for(self, rnd, viewer, step):
        """静态快照不含 obs；由 round 级重建数据（hands/action_ticks）重放取观测。"""
        rec = RoundRecord(rnd['round_index'], rnd['current_round'], rnd['seats'],
                          rnd['dealer_index'], rnd['start_player_index'],
                          rnd['hands'], rnd['action_ticks'])
        ra = replay_round(rec, viewer)
        if ra.error is not None:
            return None
        for n in ra.nodes:
            if n.step == step:
                return n.obs
        return None

    def analyze_step(self, prep, round_index, step, viewer):
        key = (prep['cache_key'], round_index, step, viewer)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        if self.disk is not None:
            hit = self.disk.get(prep['cache_key'], round_index, step, viewer)
            if hit is not None:
                self.cache.put(key, hit)
                return hit
        node, rnd = self._node_meta(prep, round_index, step, viewer)
        if node is None:
            return {'error': 'no such node', 'step': step}
        obs = self._obs_for(rnd, viewer, step)
        if obs is None:
            return {'error': 'no obs for node', 'step': step}
        observation, mask = obs['observation'], obs['action_mask']
        probs = np.asarray(self.model.logits(observation, mask)).flatten()
        out = self._claim_result(node, probs, mask) if node.get('kind') == 'claim' \
            else self._discard_result(node, probs, mask)
        self.cache.put(key, out)
        if self.disk is not None:
            self.disk.put(prep['cache_key'], round_index, step, viewer, out)
        return out

    @staticmethod
    def _discard_result(node, probs, mask):
        """打牌决策点：给出 34 张牌里合法的 top3 与是否与玩家实际打牌一致。"""
        po = 2  # OFFSET_ACT['Play']
        legal = [(i, float(probs[i])) for i in range(po, po + 34) if mask[i] > 0]
        legal.sort(key=lambda t: -t[1])
        top = [{'tile': _TILE_NAMES[i - po], 'prob': round(p, 4)} for i, p in legal[:3]]
        return {'kind': 'discard', 'step': node['step'], 'player': node['player'],
                'seat': node['seat'], 'actual_tile': node['actual_tile'],
                'ai_top': top, 'agree': bool(top) and top[0]['tile'] == node['actual_tile']}

    @staticmethod
    def _claim_result(node, probs, mask):
        """鸣牌决策点：给出吃/碰/杠/和/过 各候选的概率，并与玩家实际选择对比。

        actual_action ∈ {pass, hu, chi, peng, gang}；chi 的 tile 是顺子中间张，
        peng/gang 的 tile 是被鸣的牌，pass/hu 无 tile。agree 同时比较动作与牌。
        """
        actions = [{'action': o['action'], 'tile': o['tile'], 'index': o['index'],
                    'prob': round(float(probs[o['index']]), 4)}
                   for o in (node.get('options') or [])]
        actions.sort(key=lambda x: -x['prob'])
        top = actions[0] if actions else None
        actual_action = node.get('actual_action')
        actual_tile = node.get('actual_tile')
        agree = bool(top) and top['action'] == actual_action and (
            top['tile'] is None or actual_tile is None or top['tile'] == actual_tile)
        return {'kind': 'claim', 'step': node['step'], 'player': node['player'],
                'seat': node['seat'], 'claim_tile': node.get('claim_tile'),
                'actual_action': actual_action, 'actual_tile': actual_tile,
                'cuohe': bool(node.get('cuohe')), 'ai_actions': actions, 'agree': agree}

_TILE_NAMES = [*['W%d' % i for i in range(1, 10)],
               *['T%d' % i for i in range(1, 10)],
               *['B%d' % i for i in range(1, 10)],
               *['F%d' % i for i in range(1, 5)],
               *['J%d' % i for i in range(1, 4)]]

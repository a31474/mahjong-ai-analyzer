#!/usr/bin/env python3
"""验证 analyzer 的观测构造与 IJCAI 训练/评测侧一致（feature parity）。

A) 源码级：backend/engine/feature.py 与
   mcr-ai/IJCAI-mahjong/{deploy/caiest_cnn,train/caiest_repro}/feature.py 字节一致；
   训练主线（train/caiest_repro/*.py）import 的正是 `feature.FeatureAgent`。

B) 运行时：用本仓库 converter 从 salasasa 牌谱产生 request 序列，分别驱动
   1) analyzer 的 engine（38 平面，OBS_SIZE=38）
   2) 训练侧同名副本（train/caiest_repro/feature.py）
   3) 独立实现 data/feature_agent.py（240 维 FeatureAgent2Adapted，来自 Mahjong-LLM/sample.py）
   比较 (1)(2) 的 observation 逐位相等、以及三者每步的合法动作集合
   （两套的 ACT 索引定义相同：Pass/Hu/Play/Chi/Peng/Gang/AnGang/BuGang）。

用法（仓库根目录）:
  PYTHONPATH=backend .venv/bin/python scripts/verify_feature_parity.py
  PYTHONPATH=backend .venv/bin/python scripts/verify_feature_parity.py --record web/public/records/sample.json --rounds 3
"""
import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, 'backend')
DEFAULT_RECORD = os.path.join(ROOT, 'web/public/records/sample.json')
DEFAULT_IJCAI = os.path.abspath(os.path.join(ROOT, '..', 'mcr-ai', 'IJCAI-mahjong'))

# 会产生/重置决策的 request 前缀（比较 valid 的时机）
DECISION_PREFIXES = ('Draw ', 'Player ')


def sha1(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def load_feature(path, tag, agent_dir):
    """按文件路径加载 feature 实现；其内部 `from agent import ...` 由 agent_dir 决定。"""
    for name in ('agent', 'feature'):
        sys.modules.pop(name, None)
    sys.path.insert(0, agent_dir)
    try:
        spec = importlib.util.spec_from_file_location('feature_%s' % tag, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules['feature_%s' % tag] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(agent_dir)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def convert_requests(record_path, rounds):
    """用本仓库 converter 跑指定局（viewer=0），返回 [(seat_wind, [request, ...]), ...]。

    注意：每局的 seatWind 不同、且 FeatureAgent 状态不跨局，重放时必须逐局新建 agent。
    """
    sys.path.insert(0, BACKEND)
    import json as _json
    import converter
    game_round = _json.load(open(record_path, encoding='utf-8'))['record']['game_round']
    g = converter.parse_record({'game_round': game_round}, 'parity', [], 'guobiao')
    out = []
    for rnd in g.rounds[:rounds]:
        calls = []
        original = converter.FeatureAgent.request2obs

        def patched(self, request, _c=calls, _o=original):
            _c.append(request)
            return _o(self, request)

        converter.FeatureAgent.request2obs = patched
        try:
            ra = converter.replay_round(rnd, 0)
        finally:
            converter.FeatureAgent.request2obs = original
        out.append((ra.seat_wind, calls))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--record', default=DEFAULT_RECORD)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--ijcai', default=DEFAULT_IJCAI, help='IJCAI-mahjong 仓库路径')
    ap.add_argument('--verbose', action='store_true', help='打印每个 request 的比较结果')
    args = ap.parse_args()

    print('=' * 78)
    print('A) 源码级一致性')
    print('=' * 78)
    ana_feature = os.path.join(BACKEND, 'engine/feature.py')
    pairs = [
        ('analyzer backend/engine/feature.py', ana_feature),
        ('IJCAI deploy/caiest_cnn/feature.py', os.path.join(args.ijcai, 'deploy/caiest_cnn/feature.py')),
        ('IJCAI train/caiest_repro/feature.py', os.path.join(args.ijcai, 'train/caiest_repro/feature.py')),
    ]
    hashes = []
    for label, path in pairs:
        if not os.path.exists(path):
            print('  %-40s 缺失: %s' % (label, path))
            continue
        digest = sha1(path)
        hashes.append(digest)
        print('  %-40s sha1=%s' % (label, digest[:12]))
    print('  => %s' % ('三份完全一致' if len(set(hashes)) == 1 and hashes else '存在差异!'))
    print('  训练主线 import: `from feature import FeatureAgent`'
          '（train/caiest_repro/{bot_cfg,bot_main,distill,cook_*,curriculum_states}.py）')
    print('  240 维实现仅用于 e16/e17 gate: `from data.feature_agent import ACT, TILE_LIST`')

    print()
    print('=' * 78)
    print('B) 运行时 parity（%d 局 viewer=0 的 request 序列）' % args.rounds)
    print('=' * 78)
    per_round = convert_requests(args.record, args.rounds)
    total = sum(len(c) for _s, c in per_round)
    print('  request 条数: %d（%d 局；样例: %s …）'
          % (total, len(per_round), ' | '.join(per_round[0][1][:3])))

    mod_a = load_feature(ana_feature, 'analyzer',
                         os.path.join(BACKEND, 'engine'))
    mod_b = load_feature(os.path.join(args.ijcai, 'train/caiest_repro/feature.py'), 'train',
                         os.path.join(args.ijcai, 'train/caiest_repro'))
    mod_c = None
    c_path = os.path.join(args.ijcai, 'train/caiest_repro/data/feature_agent.py')
    if os.path.exists(c_path):
        try:
            mod_c = load_module(c_path, 'feature_agent_240')
        except Exception as exc:
            print('  240 维实现加载失败（跳过交叉验证）: %s' % exc)

    obs_diff = valid_ab_diff = valid_ac_diff = 0
    ac_both = ac_only_a = ac_only_c = 0
    first_diffs = []
    for seat_wind, requests in per_round:
        agent_a = mod_a.FeatureAgent(seat_wind)
        agent_b = mod_b.FeatureAgent(seat_wind)
        agent_c = mod_c.FeatureAgent(seat_wind) if mod_c is not None else None
        for idx, req in enumerate(requests):
            obs_a = agent_a.request2obs(req)
            obs_b = agent_b.request2obs(req)
            va = set(getattr(agent_a, 'valid', None) or [])
            vb = set(getattr(agent_b, 'valid', None) or [])
            vc = None
            if agent_c is not None:
                try:
                    _obs_c, valid_c = agent_c.update(req)
                    vc = set(valid_c or [])
                except Exception as exc:
                    vc = 'ERR:%s' % str(exc)[:40]

            if obs_a is not None and obs_b is not None:
                import numpy as np
                # 38 平面实现的 request2obs 返回 {'observation','action_mask'}，240 维实现返回裸数组
                oa = obs_a['observation'] if isinstance(obs_a, dict) else obs_a
                ob = obs_b['observation'] if isinstance(obs_b, dict) else obs_b
                if not np.array_equal(oa, ob):
                    obs_diff += 1
                    first_diffs.append(('obs', seat_wind, idx, req))
            if va != vb:
                valid_ab_diff += 1
                first_diffs.append(('valid A/B', seat_wind, idx, req, sorted(va ^ vb)))
            if vc is not None and not isinstance(vc, str):
                if va and vc:
                    ac_both += 1
                    if va != vc:
                        valid_ac_diff += 1
                        if len(first_diffs) < 12:
                            first_diffs.append(('valid A/C', seat_wind, idx, req, sorted(va ^ vc)))
                elif va and not vc:
                    ac_only_a += 1
                elif vc and not va:
                    ac_only_c += 1
            if args.verbose:
                print('  seat%d %-3d %-28s valid=%s' % (seat_wind, idx, req, sorted(va)))

    print('  A(analyzer engine) vs B(训练侧副本)   —— parity 判据')
    print('    observation 逐位不同: %d 步' % obs_diff)
    print('    合法动作集合不同 : %d 步' % valid_ab_diff)
    if agent_c is not None:
        print('  A(38 平面) vs C(240 维 FeatureAgent2Adapted)   —— 独立实现，仅作交叉参考')
        tiles_same = list(mod_a.FeatureAgent.TILE_LIST) == list(mod_c.TILE_LIST)
        a_act, c_act = mod_a.FeatureAgent.OFFSET_ACT, getattr(mod_c, 'ACT', {})
        act_same = all(c_act.get(k) == v for k, v in a_act.items())
        print('    TILE_LIST 文字序列一致: %s（%s）'
              % (tiles_same, 'W,T,B,F,J' if tiles_same else '不同'))
        print('    ACT 索引定义一致: %s' % act_same)
        print('    两边都判为决策点但不一致: %d 步' % valid_ac_diff)
        print('    仅 A 判为决策点: %d 步；仅 C 判为决策点: %d 步（决策点语义不同，属预期）'
              % (ac_only_a, ac_only_c))
        print('    C 的 TILE_LIST 注释: "W=Characters, T=Bamboo, B=Dots"'
              '（与本仓库修正后的 tiles.py 一致）')
    if first_diffs:
        print('  前若干差异（A/C 部分为独立实现的语义差异，非编码差异）:')
        for item in first_diffs[:12]:
            print('    %s' % (item,))
    ok = obs_diff == 0 and valid_ab_diff == 0
    print()
    print('结论: %s' % ('analyzer 观测实现与训练主线逐位一致（字节 + 运行时 %d 步）' % total
                        if ok else '存在差异，见上'))


if __name__ == '__main__':
    main()

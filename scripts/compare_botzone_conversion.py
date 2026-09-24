#!/usr/bin/env python3
"""对比 salasasa → Botzone 的两种转换实现，并复核牌面编码约定。

上游: open_mahjong_unity/open_mahjong_web/client/src/utils/recordConvert/botzoneGuobiao.js
      （salasasaToBotzone，输出 Botzone 协议文本行）
本仓库: backend/converter.py + backend/tiles.py（输出 FeatureAgent request 流，供 AI 推理）

用法（在仓库根目录）:
  PYTHONPATH=backend .venv/bin/python scripts/compare_botzone_conversion.py
  PYTHONPATH=backend .venv/bin/python scripts/compare_botzone_conversion.py --record web/public/records/sample.json --round 1
  PYTHONPATH=backend .venv/bin/python scripts/compare_botzone_conversion.py --no-ab     # 跳过推理对比（无需权重）

做三件事:
  1) reset tick 统计: reset[1] 是否等于 start_player_index、是否出现在首个 c 之前
  2) 双跑对比: 上游 Botzone 行 vs 本仓库 converter 的 FeatureAgent request
  3) A/B 推理: 现状映射(21-29→T) 与修正映射(21-29→B) 下模型对同一决策点的建议对比
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, 'backend')
sys.path.insert(0, BACKEND)

DEFAULT_RECORD = os.path.join(ROOT, 'web/public/records/sample.json')


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--record', default=DEFAULT_RECORD, help='salasasa 牌谱 JSON（默认 sample.json）')
    p.add_argument('--round', type=int, default=1, help='小局序号，从 1 开始')
    p.add_argument('--lines', type=int, default=24, help='双跑各打印多少条')
    p.add_argument('--no-ab', action='store_true', help='跳过 A/B 推理对比')
    p.add_argument('--cache-dir', default=os.path.join(BACKEND, 'cache/record'),
                   help='额外扫描 reset tick 的牌谱缓存目录')
    return p.parse_args()


def loads_record(path):
    src = json.load(open(path, encoding='utf-8'))
    rec = src.get('record') or src
    return src, rec


def round_keys(game_round):
    return sorted(game_round.keys(), key=lambda k: int(k.rsplit('_', 1)[-1]))


# ---------------------------------------------------------------- 1) reset 统计
def reset_stats(record_paths):
    total = without = eq = before_first_c = 0
    for path in record_paths:
        try:
            _, rec = loads_record(path)
        except Exception:
            continue
        for _key, r in (rec.get('game_round') or {}).items():
            ticks = r.get('action_ticks') or []
            resets = [(i, t) for i, t in enumerate(ticks) if t and t[0] == 'reset']
            if not resets:
                without += 1
                continue
            first_c = next((j for j, x in enumerate(ticks) if x and x[0] == 'c'), None)
            for i, t in resets:
                total += 1
                if len(t) > 1 and t[1] == r.get('start_player_index'):
                    eq += 1
                if first_c is None or i < first_c:
                    before_first_c += 1
    return total, without, eq, before_first_c


# ---------------------------------------------------------------- 2) 双跑对比
def analyzer_requests(record_path, round_index):
    """用本仓库 converter 跑指定小局（viewer=0），返回喂给 FeatureAgent 的 request 序列。"""
    import converter
    src, rec = loads_record(record_path)
    g = converter.parse_record({'game_round': rec['game_round']}, src.get('game_id', ''),
                               src.get('players') or [], src.get('rule', 'guobiao'))
    round_rec = g.rounds[round_index - 1]
    calls = []
    original = converter.FeatureAgent.request2obs

    def patched(self, request):
        calls.append(request)
        return original(self, request)

    converter.FeatureAgent.request2obs = patched
    try:
        ra = converter.replay_round(round_rec, 0)
    finally:
        converter.FeatureAgent.request2obs = original
    return calls, ra, round_rec


def upstream_lines(record_path, round_index):
    script = os.path.join(ROOT, 'scripts/upstream_botzone_lines.mjs')
    proc = subprocess.run(['node', script, record_path, str(round_index)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    return proc.stdout.strip().splitlines(), None


# ---------------------------------------------------------------- 3) A/B 推理
def to_csm_fixed(tile_id):
    """修正映射：B=筒(21-29)、T=索(31-39)，与 Botzone 官方 / PyMahjongGB 一致。"""
    import tiles
    tile_id = tiles._normalize(tile_id)
    if tiles.is_flower(tile_id):
        raise ValueError('flower tile %d' % tile_id)
    if tile_id in tiles.HONOR_CSM:
        return tiles.HONOR_CSM[tile_id]
    suit, num = divmod(tile_id, 10)
    return {1: 'W', 2: 'B', 3: 'T', 4: 'F'}[suit] + str(num)


def salasasa_id(name, fixed):
    kind, num = name[0], int(name[1:])
    if kind == 'W':
        return 10 + num
    if kind == 'F':
        return 40 + num
    if kind == 'J':
        return {1: 45, 2: 47, 3: 46}[num]
    if fixed:
        return (20 + num) if kind == 'B' else (30 + num)
    return (20 + num) if kind == 'T' else (30 + num)


CN = {41: '东', 42: '南', 43: '西', 44: '北', 45: '中', 46: '白', 47: '发'}


def cn_name(tid):
    if 11 <= tid <= 19:
        return '%d万' % (tid - 10)
    if 21 <= tid <= 29:
        return '%d筒' % (tid - 20)
    if 31 <= tid <= 39:
        return '%d索' % (tid - 30)
    return CN.get(tid, str(tid))


def ab_compare(record_path, round_index):
    import numpy as np
    import converter
    from analyzer import _TILE_NAMES
    from model_loader import load_model

    src, rec = loads_record(record_path)
    g = converter.parse_record({'game_round': rec['game_round']}, src.get('game_id', ''),
                               src.get('players') or [], src.get('rule', 'guobiao'))
    round_rec = g.rounds[round_index - 1]
    original = converter.to_csm

    def replay(fixed):
        converter.to_csm = to_csm_fixed if fixed else original
        try:
            return converter.replay_round(round_rec, 0)
        finally:
            converter.to_csm = original

    model = load_model(os.path.join(BACKEND, 'weights'))
    ra_now, ra_fix = replay(False), replay(True)

    def top3(node):
        obs = node.obs
        probs = np.asarray(model.logits(obs['observation'], obs['action_mask'])).flatten()
        legal = [(i, float(probs[i])) for i in range(2, 36) if obs['action_mask'][i] > 0]
        legal.sort(key=lambda x: -x[1])
        return [(_TILE_NAMES[i - 2], v) for i, v in legal[:3]]

    rows, same_top1 = [], 0
    for na, nb in zip(ra_now.nodes, ra_fix.nodes):
        ia = [(salasasa_id(t, False), p) for t, p in top3(na)]
        ib = [(salasasa_id(t, True), p) for t, p in top3(nb)]
        same_top1 += ia[0][0] == ib[0][0]
        rows.append((na.step, salasasa_id(na.actual_tile, False), ia, ib))
    return ra_now, ra_fix, rows, same_top1, model


# ---------------------------------------------------------------- main
def main():
    args = parse_args()
    print('=' * 78)
    print('1) reset tick 统计')
    print('=' * 78)
    paths = sorted(glob.glob(os.path.join(args.cache_dir, '*.json')))
    if os.path.abspath(args.record) not in [os.path.abspath(p) for p in paths]:
        paths.append(args.record)
    total, without, eq, before = reset_stats(paths)
    print('扫描牌谱: %d 份' % len(paths))
    if total:
        print('含 reset 的局: %d，不含: %d' % (total, without))
        print('reset[1] == start_player_index: %d/%d' % (eq, total))
        print('reset 出现在首个 c 之前: %d/%d' % (before, total))
    else:
        print('未发现 reset tick')

    print()
    print('=' * 78)
    print('2) 双跑对比（第 %d 局）' % args.round)
    print('=' * 78)
    lines, err = upstream_lines(args.record, args.round)
    if lines is None:
        print('跳过上游对比: %s' % err)
    else:
        print('--- 上游 salasasaToBotzone（前 %d 行）---' % args.lines)
        for i, line in enumerate(lines[:args.lines]):
            print('%3d  %s' % (i, line))
    calls, ra, round_rec = analyzer_requests(args.record, args.round)
    print('--- 本仓库 converter 的 FeatureAgent request（viewer=0，前 %d 条）---' % args.lines)
    for i, line in enumerate(calls[:args.lines]):
        print('%3d  %s' % (i, line))
    print('决策点: %d  error: %s' % (len(ra.nodes), ra.error))

    if args.no_ab:
        return
    print()
    print('=' * 78)
    print('3) A/B 推理对比（现状映射 21-29→T  vs  修正映射 21-29→B）')
    print('=' * 78)
    try:
        ra_now, ra_fix, rows, same_top1, _model = ab_compare(args.record, args.round)
    except Exception as exc:                                     # 权重缺失等
        print('跳过 A/B（%s）' % exc)
        return
    print('节点数 现状=%d 修正=%d' % (len(ra_now.nodes), len(ra_fix.nodes)))
    for step, actual, ia, ib in rows:
        mark = '' if ia[0][0] == ib[0][0] else '  <-- 首选不同'
        print('step %-4d 实际 %-4s | 现状 %s | 修正 %s%s' % (
            step, cn_name(actual),
            ' '.join('%s %.3f' % (cn_name(i), p) for i, p in ia),
            ' '.join('%s %.3f' % (cn_name(i), p) for i, p in ib), mark))
    print('首选一致: %d/%d' % (same_top1, len(rows)))


if __name__ == '__main__':
    main()

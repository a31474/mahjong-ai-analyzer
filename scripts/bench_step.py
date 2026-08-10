#!/usr/bin/env python3
"""单步分析性能基准。

衡量一次"单局面分析"各环节耗时（单核 CPU 视角）：
  - prepare       ：牌谱解析 + 全部视角/回合重放（无 AI）
  - step 冷缓存   ：重放到目标步 + 3 学生 ensemble 推理（真实用户首次翻到该步）
  - step 热缓存   ：LRU 命中（用户翻回已分析过的步）
  - 纯推理        ：ModelHandle.logits 单次（重放之外的部分）

用法：
  PYTHONPATH=backend .venv/bin/python scripts/bench_step.py
  PYTHONPATH=backend .venv/bin/python scripts/bench_step.py --record web/public/records/sample.json --round 2 --viewer 0 --iterations 20

依赖：backend/weights/ 下已下载模型权重（fetch_weights.sh）。
"""
import argparse
import json
import time

from analyzer import prepare, Analyzer
from model_loader import load_model

DEFAULT_RECORD = 'web/public/records/sample.json'


def _ms(seconds):
    return seconds * 1000.0


def main():
    ap = argparse.ArgumentParser(description='单步分析性能基准')
    ap.add_argument('--record', default=DEFAULT_RECORD, help='牌谱 JSON 路径')
    ap.add_argument('--round', type=int, default=None, help='基准用局号（默认取第一局）')
    ap.add_argument('--viewer', type=int, default=0, help='视角 (original id)')
    ap.add_argument('--iterations', type=int, default=20, help='推理计时迭代次数')
    args = ap.parse_args()

    with open(args.record) as f:
        raw = json.load(f)
    record = raw.get('record', raw)
    players = raw.get('players', [])
    game_id = raw.get('game_id', 'bench')

    t0 = time.perf_counter()
    prep = prepare(record, game_id, 'guobiao', players)
    t_prepare = time.perf_counter() - t0
    print('prepare（解析+全视角重放）: %.1f ms' % _ms(t_prepare))

    target = None
    if args.round is not None:
        target = next((r for r in prep['rounds'] if r['round_index'] == args.round), None)
    if target is None:
        target = prep['rounds'][0]
    vw = target['viewers'][args.viewer]
    if vw['error'] is not None:
        print('该视角转换失败: %s' % vw['error'])
        return 1
    if not vw['nodes']:
        print('该视角无打牌决策点（round=%d viewer=%d）' % (target['round_index'], args.viewer))
        return 1
    node = vw['nodes'][0]
    round_index = target['round_index']
    print('基准节点: round=%d viewer=%d step=%d actual_tile=%s' % (
        round_index, args.viewer, node['step'], node['actual_tile']))
    print('该视角全部节点数: %d' % len(vw['nodes']))

    model = load_model('backend/weights')
    analyzer = Analyzer(model)

    # 预热（模型加载后的首次调用含 numpy/缓存初始化开销）
    for _ in range(3):
        analyzer.analyze_step(prep, round_index, node['step'], args.viewer)
    analyzer.cache.d.clear()

    # 1) 冷缓存单步（重放 + 推理），取前几个节点的均值
    n_cold = min(5, len(vw['nodes']))
    t_cold_vals = []
    for i, nd in enumerate(vw['nodes'][:n_cold]):
        t0 = time.perf_counter()
        out = analyzer.analyze_step(prep, round_index, nd['step'], args.viewer)
        t_cold_vals.append(time.perf_counter() - t0)
        if i == 0:
            print('step 冷缓存首个节点: %.1f ms → top1=%s(%.1f%%) agree=%s' % (
                _ms(t_cold_vals[0]), out['ai_top'][0]['tile'],
                out['ai_top'][0]['prob'] * 100, out['agree']))
    t_cold = sum(t_cold_vals) / len(t_cold_vals)
    print('step 冷缓存均值（%d 节点）: %.1f ms' % (n_cold, _ms(t_cold)))

    # 2) 热缓存单步（LRU 命中）
    t0 = time.perf_counter()
    out2 = analyzer.analyze_step(prep, round_index, node['step'], args.viewer)
    t_hot = time.perf_counter() - t0
    print('step 热缓存（LRU 命中）: %.2f ms' % _ms(t_hot))

    # 3) 纯推理（logits，多次取均值；obs/mask 由 Analyzer 重建重放获得）
    _meta, rnd = analyzer._node_meta(prep, round_index, node['step'], args.viewer)
    obs_ = analyzer._obs_for(rnd, args.viewer, node['step'])
    obs = obs_['observation']
    mask = obs_['action_mask']
    for _ in range(5):  # 预热（numpy 首次调用含初始化开销）
        model.logits(obs, mask)
    t0 = time.perf_counter()
    for _ in range(args.iterations):
        model.logits(obs, mask)
    t_infer = (time.perf_counter() - t0) / args.iterations
    print('纯推理均值（%d 次，3 学生）: %.2f ms' % (args.iterations, _ms(t_infer)))

    # 4) 估算
    n_nodes = len(vw['nodes'])
    est_cold = t_cold * n_nodes
    est_infer = t_infer * n_nodes
    print('---')
    print('估算该视角整局全部决策点:')
    print('  全冷缓存: %.1f s（%d 节点 × %.1f ms）' % (est_cold, n_nodes, _ms(t_cold)))
    print('  纯推理叠加: %.1f s（不考虑重放与缓存命中）' % est_infer)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

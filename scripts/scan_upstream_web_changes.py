#!/usr/bin/env python3
"""扫描 open_mahjong_unity 的 web 界面更新，辅助决定「哪些需要同步到本项目」。

做三件事：
  1) 列出基线 → 目标（默认 HEAD）之间、落在本项目同步路径内的变更文件（A/M/D）
  2) 对目标版本的文件解析 import，找出**本项目缺失的依赖模块**（这是能否整文件同步的关键）
  3) 按启发式给缺失依赖打标：站点专属 / 其他麻将规则 / 可移植

用法（仓库根目录）:
  .venv/bin/python scripts/scan_upstream_web_changes.py --from 4db27ac0
  .venv/bin/python scripts/scan_upstream_web_changes.py --from 4db27ac0 --to HEAD
  # --from 省略时，从 docs/upstream-sync.md 解析「当前同步点」

判定原则见 docs/upstream-sync.md。
"""
import argparse
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = 'open_mahjong_web/client/src'
SYNC_PATHS = [
    f'{CLIENT}/game2d',
    f'{CLIENT}/views/game2d',
    f'{CLIENT}/constants',
    f'{CLIENT}/i18n',
    'open_mahjong_web/client/public/game2d-assets',
]

# 依赖打标：命中即视为「本项目不该引入」
SITE_HINTS = [
    (r'stores/', '站点 store（登录态/对局会话）'),
    (r'api/playerClient', '站点登录接口'),
    (r'localGameRecordStore', 'Unity 客户端本地牌谱库'),
    (r'recordShareLink', '站点分享链接'),
    (r'recordConvert/externalPlayers', '外部牌谱导入'),
    (r'ptChange|rankTable|libraryRules', '数据站/规则书页面'),
    (r'components/', '站点组件'),
]
OTHER_RULE_HINTS = [
    (r'sichuan|guangdong|hangzhou|guizhou|wenzhou|yixing|changchun|hongzhong|shanxi|taiwan|qingque|jiandan|changsha',
     '其他麻将规则'),
    (r'duplicateWall|duplicateReplayWall', '复式赛制'),
    (r'hongKong', '香港麻将规则书'),
]


def sh(args, cwd, check=True):
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError('%s -> %s' % (' '.join(args), (proc.stderr or proc.stdout).strip()))
    return proc.stdout


def current_sync_point():
    """从 docs/upstream-sync.md 里读「当前同步点」。"""
    path = os.path.join(REPO, 'docs/upstream-sync.md')
    if not os.path.exists(path):
        return None
    for line in open(path, encoding='utf-8'):
        m = re.search(r'当前同步点[:：]\s*`?([0-9a-f]{7,40})`?', line)
        if m:
            return m.group(1)
    return None


def changed_files(unity, frm, to):
    out = sh(['git', 'diff', '--name-status', frm, to, '--'] + SYNC_PATHS, unity)
    rows = []
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1]))
    return rows


def stat_lines(unity, frm, to, path):
    out = sh(['git', 'diff', '--numstat', frm, to, '--', path], unity).strip()
    if not out:
        return (0, 0)
    a, b, _ = out.split('\t', 2)
    return (int(a) if a.isdigit() else 0, int(b) if b.isdigit() else 0)


def file_text(unity, rev, path):
    try:
        return sh(['git', 'show', f'{rev}:{path}'], unity)
    except RuntimeError:
        return ''


def to_analyzer_path(up_path, analyzer_root):
    """把上游仓库路径映射到本项目对应路径（用于解析相对 import）。"""
    for prefix, target in (('open_mahjong_web/client/src/', 'web/src/'),
                           ('open_mahjong_web/client/public/', 'web/public/')):
        if up_path.startswith(prefix):
            return os.path.join(analyzer_root, target + up_path[len(prefix):])
    return None


def is_maintained(up_path, analyzer_root):
    """该上游文件在本项目里是否也存在（即我们也在维护它）。"""
    p = to_analyzer_path(up_path, analyzer_root)
    return bool(p and os.path.exists(p))


def resolve(spec, up_path, analyzer_root):
    """spec 解析到本项目文件；不存在返回 'MISSING'，第三方包返回 None。"""
    src_root = os.path.join(analyzer_root, 'web/src')
    if spec.startswith('@/'):
        base = os.path.join(src_root, spec[2:])
    elif spec.startswith('.'):
        local = to_analyzer_path(up_path, analyzer_root)
        if local is None:
            return None
        base = os.path.normpath(os.path.join(os.path.dirname(local), spec))
    else:
        return None
    for cand in (base, base + '.ts', base + '.js', base + '.vue',
                 os.path.join(base, 'index.ts'), os.path.join(base, 'index.js')):
        if os.path.exists(cand):
            return cand
    return 'MISSING'


def tag(spec):
    for pat, why in SITE_HINTS:
        if re.search(pat, spec, re.I):
            return '站点专属：' + why
    for pat, why in OTHER_RULE_HINTS:
        if re.search(pat, spec, re.I):
            return '其他规则：' + why
    return '需人工判断'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--unity', default=os.path.join(REPO, '..', 'open_mahjong_unity'))
    ap.add_argument('--from', dest='frm', default=None, help='上次同步点（省略时读 docs/upstream-sync.md）')
    ap.add_argument('--to', default='HEAD')
    args = ap.parse_args()

    unity = os.path.abspath(args.unity)
    if not os.path.isdir(os.path.join(unity, '.git')):
        print('找不到上游仓库: %s' % unity, file=sys.stderr)
        return 2
    frm = args.frm or current_sync_point()
    if not frm:
        print('请用 --from 指定同步点，或在 docs/upstream-sync.md 写明「当前同步点」', file=sys.stderr)
        return 2

    head = sh(['git', 'rev-parse', '--short', args.to], unity).strip()
    desc = sh(['git', 'log', '-1', '--format=%ad %s', '--date=short', args.to], unity).strip()
    commits = sh(['git', 'log', '--oneline', f'{frm}..{args.to}', '--'] + SYNC_PATHS, unity).strip()
    n_commits = len(commits.splitlines()) if commits else 0

    print('=' * 78)
    print('上游同步扫描：%s → %s (%s)' % (frm, head, desc))
    print('=' * 78)
    print('落在同步路径内的提交: %d 个' % n_commits)
    for line in (commits.splitlines()[:10]):
        print('   ', line)

    rows = changed_files(unity, frm, args.to)
    added = [p for s, p in rows if s.startswith('A')]
    deleted = [p for s, p in rows if s.startswith('D')]
    modified = [(s, p) for s, p in rows if s.startswith('M')]
    print()
    print('变更文件 %d（新增 %d / 修改 %d / 删除 %d）'
          % (len(rows), len(added), len(modified), len(deleted)))
    for p in added:
        print('  A  %s' % p.replace(CLIENT + '/', ''))
    for p in deleted:
        print('  D  %s' % p.replace(CLIENT + '/', ''))
    for _s, p in sorted(modified, key=lambda x: -sum(stat_lines(unity, frm, args.to, x[1]))):
        a, b = stat_lines(unity, frm, args.to, p)
        print('  M  %-58s +%d/-%d' % (p.replace(CLIENT + '/', ''), a, b))

    # 依赖缺口：只看本项目也有的文件 + 新增文件
    print()
    print('本项目缺失的依赖模块（决定能否整文件覆盖）:')
    missing = {}
    for _s, path in rows:
        if not path.endswith(('.ts', '.js', '.vue')):
            continue
        maintained = is_maintained(path, REPO)   # 该文件本项目是否也在维护
        text = file_text(unity, args.to, path)
        for spec in re.findall(r"from\s+'([^']+)'", text) + re.findall(r"import\('([^']+)'\)", text):
            if resolve(spec, path, REPO) == 'MISSING':
                missing.setdefault(spec, set()).add(
                    (path.replace(CLIENT + '/', ''), maintained))
    if not missing:
        print('  （无 —— 变更文件都可整文件同步）')
    for spec, sources in sorted(missing.items()):
        maintained = [s for s, m in sources if m]
        note = tag(spec) if maintained else '引用方未同步 → 可忽略'
        print('  %-46s %-24s <- %s%s' % (
            spec, '[%s]' % note,
            ', '.join(sorted(s for s, _m in sources))[:52],
            '' if maintained else '（本项目无此文件）'))
    need = [s for s in missing
            if any(m for _p, m in missing[s]) and tag(s).startswith('需人工')]
    print()
    print('提示：站点专属/其他规则的缺失依赖应跳过（本项目不需要）；'
          '「需人工判断」且引用方已同步的才要逐个确认。')
    if need:
        print('需人工判断 %d 个: %s' % (len(need), ', '.join(need)))
    else:
        print('需人工判断: 无')
    return 0


if __name__ == '__main__':
    sys.exit(main())

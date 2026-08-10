import urllib.request, urllib.error, json

def fetch_record(game_id, platform='https://salasasa.cn'):
    url = '%s/api/platform/record/%s' % (platform.rstrip('/'), game_id)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError('HTTP %d: %s' % (e.code, url)) from e
    if not data.get('success'):
        raise RuntimeError('平台返回失败: %r' % data)
    d = data['data']
    players = []
    for i, p in enumerate(d.get('players') or []):
        orig = p.get('original_player_index')
        players.append({'original': orig if orig is not None else i,
                        'user_id': p.get('user_id'), 'username': p.get('username'),
                        'score': p.get('score'), 'rank': p.get('rank')})
    return {'game_id': d['game_id'], 'rule': d.get('rule'), 'players': players,
            'record': d['record']}

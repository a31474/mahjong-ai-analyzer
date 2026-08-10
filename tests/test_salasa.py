import json
import urllib.request

import pytest

from salasa import fetch_record


def _mock_response(payload: dict):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode('utf-8')

    return FakeResp()


def test_fetch_record_keeps_score_rank(monkeypatch):
    """fetch_record 返回的 players 必须保留平台最终 score/rank（前端反推起始分依赖）。"""
    platform_payload = {
        'success': True,
        'data': {
            'game_id': 'abc123',
            'rule': 'guobiao',
            'players': [
                {'user_id': 1, 'username': '甲', 'score': 71, 'rank': 1, 'original_player_index': 0},
                {'user_id': 2, 'username': '乙', 'score': 55, 'rank': 2, 'original_player_index': 1},
                {'user_id': 3, 'username': '丙', 'score': -12, 'rank': 3, 'original_player_index': 2},
                {'user_id': 4, 'username': '丁', 'score': -114, 'rank': 4, 'original_player_index': 3},
            ],
            'record': {'game_title': {}, 'game_round': {}},
        },
    }
    monkeypatch.setattr(
        urllib.request, 'urlopen',
        lambda url, timeout: _mock_response(platform_payload),
    )
    out = fetch_record('abc123', 'https://salasasa.cn')
    scores = {p['original']: p['score'] for p in out['players']}
    ranks = {p['original']: p['rank'] for p in out['players']}
    assert scores == {0: 71, 1: 55, 2: -12, 3: -114}
    assert ranks == {0: 1, 1: 2, 2: 3, 3: 4}

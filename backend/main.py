import hashlib
import json
import os
import re
import threading
import uuid
from collections import OrderedDict
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from analyzer import prepare, Analyzer
from cache_store import DiskCache, RoundCache
from salasa import fetch_record
from model_loader import load_model, ModelMissingError

app = FastAPI(title='mcr-ai-analyzer')

class PrepareBody(BaseModel):
    game_id: str | None = None
    platform: str = 'https://salasasa.cn'
    record: dict | None = None

_MODEL = None
_MODEL_ERR = None
_ANALYZER = None
_prep_cache = OrderedDict()
_PREP_CAP = 20
# 同步路由跑在线程池里（真并发）：_prep_cache 的插入/淘汰/读回需要互斥，否则可能
# 读到被其他请求淘汰的 aid（KeyError → 500）。prepare 本身耗时，放在锁外执行，
# 只在插入+淘汰时持锁。模型首次加载同理，避免并发请求各加载一份（内存翻倍）。
_PREP_LOCK = threading.Lock()
_MODEL_LOCK = threading.Lock()
# 磁盘持久化（backend/cache/，gitignore）：重启后同一牌谱免重复推理/拉取
_CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
# 分析结果按「局」聚合：一个文件存该局所有 (step, viewer) 的结果（原为每步一个文件）
_ROUND_DISK = DiskCache(os.path.join(_CACHE_DIR, 'round'), file_cap=2000)
_STEP_CACHE = RoundCache(_ROUND_DISK)          # 旧的「单步一文件」缓存（cache/*.json）已废弃，可删
_RECORD_DISK = DiskCache(os.path.join(_CACHE_DIR, 'record'), file_cap=200)  # 牌谱原始 JSON

# 转换/结果指纹：tiles.py / converter.py（观测与节点提取）/ analyzer.py（结果结构）
# 的内容变化会让磁盘缓存自动失效。
# 曾经用手工版本号，结果"改了牌面映射却忘了递增"时读到按旧约定算出的缓存结果
# （表现为测试里 actual_tile 是新的、ai_top 却还是旧的牌名）。
def _transform_fingerprint():
    digest = hashlib.sha1()
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ('tiles.py', 'converter.py', 'analyzer.py'):
        try:
            with open(os.path.join(here, name), 'rb') as f:
                digest.update(f.read())
        except OSError:
            pass
    return digest.hexdigest()[:8]

_TRANSFORM_VERSION = 'enc' + _transform_fingerprint()

def _record_cache_key(record, game_id):
    """持久化缓存键：game_id 路径加 'gid:' 前缀（防与上传 sha1 键碰撞）；上传路径用内容 sha1。"""
    if game_id and game_id != 'upload':
        base = 'gid:' + game_id
    else:
        base = 'sha1:' + hashlib.sha1(
            json.dumps(record, sort_keys=True, ensure_ascii=False).encode('utf-8')
        ).hexdigest()
    return _TRANSFORM_VERSION + '|' + base

def _load_record(game_id, platform):
    """牌谱磁盘缓存：命中直接返回（跳过平台拉取），未命中拉取并存盘。"""
    key = 'gid:' + game_id
    hit = _RECORD_DISK.get(key)
    if hit is not None:
        return hit
    fetched = fetch_record(game_id, platform)
    entry = {'record': fetched['record'], 'players': fetched['players'],
             'rule': fetched.get('rule')}
    _RECORD_DISK.put(key, entry)
    return entry

def _get_model():
    global _MODEL, _MODEL_ERR
    with _MODEL_LOCK:
        if _MODEL is None and _MODEL_ERR is None:
            try:
                _MODEL = load_model(os.path.join(os.path.dirname(__file__), 'weights'))
            except ModelMissingError as e:
                _MODEL_ERR = str(e)
        if _MODEL is None:
            raise HTTPException(status_code=503, detail=_MODEL_ERR or 'model not ready')
        return _MODEL

@app.get('/api/health')
def api_health():
    """启动自检/存活探针：主动触发模型加载，就绪 200，模型缺失 503（附原因）。"""
    try:
        model = _get_model()
    except HTTPException as e:
        return JSONResponse({'status': 'degraded', 'model': 'missing', 'detail': e.detail}, status_code=503)
    return {'status': 'ok', 'model': 'ready', 'students': len(getattr(model, 'students', []))}

@app.post('/api/analyze/prepare')
def api_prepare(body: PrepareBody):
    if body.record is not None:
        record, game_id, players, rule = body.record, body.record.get('game_id', 'upload'), [], body.record.get('rule', 'guobiao')
        if 'record' not in body.record and 'game_round' not in body.record:
            raise HTTPException(status_code=400, detail='record 字段需为牌谱 JSON')
        record = body.record.get('record', body.record)
        # 上传路径也入盘（键 = 内容 sha1）：重启后同一牌谱再次上传免解析；
        # 写盘失败仅降级（不阻断 200 响应）
        ckey = _record_cache_key(record, game_id)
        try:
            _RECORD_DISK.put(ckey, {'record': record, 'players': players, 'rule': rule})
        except Exception:
            pass
    elif body.game_id:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', body.game_id):
            raise HTTPException(status_code=400, detail='非法 game_id（仅字母数字_-）')
        try:
            entry = _load_record(body.game_id, body.platform)   # 磁盘缓存优先，未命中拉取
        except Exception as e:
            raise HTTPException(status_code=502, detail='拉取牌谱失败: %r' % e)
        record = entry['record']
        game_id = body.game_id
        players = entry.get('players') or []
        rule = entry.get('rule')
    else:
        raise HTTPException(status_code=400, detail='需要 game_id 或 record')
    aid = uuid.uuid4().hex[:12]
    ckey = _record_cache_key(record, game_id)
    meta = prepare(record, game_id, rule, players, cache_key=ckey)
    with _PREP_LOCK:
        _prep_cache[aid] = meta
        _prep_cache.move_to_end(aid)
        while len(_prep_cache) > _PREP_CAP:
            _prep_cache.popitem(last=False)
    # record 随响应返回：前端渲染回放需要完整牌谱（上传时前端已有，game_id 拉取时没有）
    return {'analysis_id': aid, 'meta': meta, 'record': record}

@app.get('/api/analysis/{aid}/step')
def api_step(aid: str, round: int, step: int, viewer: int = 0):
    prep = _prep_cache.get(aid)
    if prep is None:
        raise HTTPException(status_code=404, detail='analysis_id 不存在或已过期')
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = Analyzer(_get_model(), disk=_STEP_CACHE)   # 全局复用：LRU + 磁盘缓存跨请求生效
    return _ANALYZER.analyze_step(prep, round, step, viewer)

_web_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'dist')
if os.path.isdir(_web_dir):
    app.mount('/', StaticFiles(directory=_web_dir, html=True), name='web')

import hashlib
import json
import os
import uuid
from collections import OrderedDict
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from analyzer import prepare, Analyzer
from cache_store import DiskCache
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
# 单步分析结果磁盘持久化（backend/cache/，gitignore）；重启后同一牌谱的已分析步免重复推理
_STEP_DISK = DiskCache(os.path.join(os.path.dirname(__file__), 'cache'))

def _record_cache_key(record, game_id):
    """持久化缓存键：game_id 路径直接用 game_id；上传路径用 record 内容 sha1
    （多个上传牌谱的 game_id 可能都是 'upload'，不能作键）。"""
    if game_id and game_id != 'upload':
        return game_id
    return 'sha1:' + hashlib.sha1(
        json.dumps(record, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()

def _get_model():
    global _MODEL, _MODEL_ERR
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
    elif body.game_id:
        try:
            fetched = fetch_record(body.game_id, body.platform)
        except Exception as e:
            raise HTTPException(status_code=502, detail='拉取牌谱失败: %r' % e)
        record, game_id, players, rule = fetched['record'], fetched['game_id'], fetched['players'], fetched['rule']
    else:
        raise HTTPException(status_code=400, detail='需要 game_id 或 record')
    aid = uuid.uuid4().hex[:12]
    ckey = _record_cache_key(record, game_id)
    _prep_cache[aid] = prepare(record, game_id, rule, players, cache_key=ckey)
    _prep_cache.move_to_end(aid)
    while len(_prep_cache) > _PREP_CAP:
        _prep_cache.popitem(last=False)
    meta = _prep_cache[aid]
    # record 随响应返回：前端渲染回放需要完整牌谱（上传时前端已有，game_id 拉取时没有）
    return {'analysis_id': aid, 'meta': meta, 'record': record}

@app.get('/api/analysis/{aid}/step')
def api_step(aid: str, round: int, step: int, viewer: int = 0):
    prep = _prep_cache.get(aid)
    if prep is None:
        raise HTTPException(status_code=404, detail='analysis_id 不存在或已过期')
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = Analyzer(_get_model(), disk=_STEP_DISK)   # 全局复用：LRU + 磁盘缓存跨请求生效
    return _ANALYZER.analyze_step(prep, round, step, viewer)

_web_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'dist')
if os.path.isdir(_web_dir):
    app.mount('/', StaticFiles(directory=_web_dir, html=True), name='web')

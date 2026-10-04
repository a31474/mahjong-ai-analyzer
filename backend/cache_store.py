"""磁盘 JSON 缓存（单核小服务用，原子写 + 文件数上限清理）。

- `DiskCache`：一个键一个文件（牌谱原始 JSON、按局聚合的分析结果等）
- `RoundCache`：分析结果的「按局聚合」视图——同一局所有 (step, viewer) 结果
  存在同一个文件里，底层复用 DiskCache 的原子写与清理

键要求：str，仅 [a-zA-Z0-9_-]（防路径注入）；RoundCache 内部自行哈希。
值要求：JSON 可序列化（无 numpy/对象）。
"""
import hashlib
import json
import os
import tempfile
import threading
from collections import OrderedDict


def safe_key(key):
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:24]


class DiskCache:
    def __init__(self, directory, file_cap=5000):
        self.dir = directory
        self.file_cap = file_cap
        os.makedirs(directory, exist_ok=True)

    def _path(self, key):
        return os.path.join(self.dir, safe_key(key) + '.json')

    def get(self, key):
        try:
            with open(self._path(key), 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def put(self, key, value):
        path = self._path(key)
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._trim()

    def _trim(self):
        """文件数超上限时，按 mtime 删除最旧的，直到回到上限内。"""
        try:
            files = [os.path.join(self.dir, n) for n in os.listdir(self.dir)
                     if n.endswith('.json')]
            excess = len(files) - self.file_cap
            if excess <= 0:
                return
            files.sort(key=lambda p: os.path.getmtime(p))
            for p in files[:excess]:
                try:
                    os.unlink(p)
                except OSError:
                    pass
        except OSError:
            pass


class RoundCache:
    """分析结果的「按局聚合」缓存：一个牌谱的一局 → 一个文件。

    文件内容形如 {"<step>|<viewer>": <单步结果>, ...}。文件数从「每步一个」
    （多牌谱下会堆到上千个）降为「每局一个」（典型牌谱 16 局 → 16 个文件）。

    内存里保留最近 mem_cap 局的整局字典：analyze_step 是「先 get 再 put」，
    没有它每一步都要读+写整个文件两次。

    注意：写回是「整个局文件」，因此**只适合单进程**（多 worker 会互相覆盖同一局
    的结果）——本项目按 README 约定以单 worker 运行。
    """

    def __init__(self, disk, mem_cap=32):
        self.disk = disk
        self.mem_cap = mem_cap
        self.mem = OrderedDict()
        # 并发保护：FastAPI 同步路由在线程池里真并发。get/put 全程持锁（含磁盘
        # 读写的毫秒级开销）——单核服务无感，但避免 mem 的 move_to_end/popitem
        # 交错抛 KeyError，也避免「读到 bucket 后被淘汰」导致整局文件互相覆盖。
        self.lock = threading.Lock()

    @staticmethod
    def bucket_key(cache_key, round_index):
        """局级文件键（DiskCache 会再哈希成文件名）。"""
        return '%s|r%d' % (cache_key, round_index)

    @staticmethod
    def entry_key(step, viewer):
        return '%d|%d' % (step, viewer)

    def _bucket(self, cache_key, round_index):
        """（调用方需持锁）取该局的整局字典，未命中时从磁盘加载。"""
        key = self.bucket_key(cache_key, round_index)
        bucket = self.mem.get(key)
        if bucket is None:
            loaded = self.disk.get(key)
            bucket = loaded if isinstance(loaded, dict) else {}
            self.mem[key] = bucket
            self._trim_mem()
        else:
            self.mem.move_to_end(key)
        return key, bucket

    def _trim_mem(self):
        while len(self.mem) > self.mem_cap:
            self.mem.popitem(last=False)

    def get(self, cache_key, round_index, step, viewer):
        with self.lock:
            _key, bucket = self._bucket(cache_key, round_index)
            return bucket.get(self.entry_key(step, viewer))

    def put(self, cache_key, round_index, step, viewer, value):
        with self.lock:
            self._write(cache_key, round_index, step, viewer, value)

    def _write(self, cache_key, round_index, step, viewer, value):
        """（调用方需持锁）写入 bucket 并落盘整局。"""
        key, bucket = self._bucket(cache_key, round_index)
        bucket[self.entry_key(step, viewer)] = value
        self.disk.put(key, bucket)

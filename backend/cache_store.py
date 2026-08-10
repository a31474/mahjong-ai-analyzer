"""磁盘 JSON 缓存（单核小服务用，原子写 + 文件数上限清理）。

键要求：str，仅 [a-zA-Z0-9_-]（防路径注入）。
值要求：JSON 可序列化（无 numpy/对象）。
"""
import hashlib
import json
import os
import tempfile


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

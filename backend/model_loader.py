import os
import numpy as np

N_STUDENTS = 3
STUDENT_FILES = ['kdens_s%d_fp16.npz' % i for i in range(N_STUDENTS)]
PRIMARY = STUDENT_FILES[0]


class ModelMissingError(Exception):
    pass


class ModelHandle:
    def __init__(self, students):
        self.students = students

    def logits(self, obs, mask):
        lg = sum(s.logits(obs, mask) for s in self.students) / len(self.students)
        return lg


def _load_one(path):
    from engine.numpy_resfused import NumpyResFused
    return NumpyResFused(path)


def load_model(weights_dir, single=False):
    """默认 3 学生 ensemble；ENSEMBLE=1 环境变量或 single=True 时只加载 s0 单学生。"""
    names = [PRIMARY] if (single or os.environ.get('ENSEMBLE') == '1') else STUDENT_FILES
    paths = []
    missing = []
    for n in names:
        p = os.path.join(weights_dir, n)
        if os.path.exists(p):
            paths.append(p)
        else:
            missing.append(n)
    if not paths:
        raise ModelMissingError('缺少模型权重: %s（从 HF Dannibal/ijcai-mahjong-ckpts-2026 champion/ 下载 %s）'
                                % (weights_dir, ', '.join(names)))
    students = [_load_one(p) for p in paths]
    return ModelHandle(students)

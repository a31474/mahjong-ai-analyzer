import os
import numpy as np

N_STUDENTS = 3
STUDENT_FILES = ['kdens_s%d_fp16.npz' % i for i in range(N_STUDENTS)]
PRIMARY = STUDENT_FILES[0]


class ModelMissingError(Exception):
    pass


class ModelHandle:
    """3 学生 ensemble：与 IJCAI deploy/caiest_cnn/ensemble_infer.py 一致——
    每个学生 mask 内 softmax（mask=0 置 0）后算术平均，返回已是概率分布（和为 1）。
    注：softmax(mean logits) != mean softmax，不得再在调用方做二次 softmax。"""

    def __init__(self, students):
        self.students = students

    def logits(self, obs, mask):
        m = np.asarray(mask, dtype=np.float32)
        acc = None
        for s in self.students:
            lg = np.asarray(s.logits(obs, mask)).flatten()
            lg = np.where(m > 0, lg, -1e30)
            lg = lg - lg.max()                 # 数值稳定
            p = np.exp(lg) * (m > 0)
            s_sum = p.sum()
            p = p / s_sum if s_sum > 0 else (m / max(1.0, m.sum()))
            acc = p if acc is None else acc + p
        return acc / len(self.students)


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

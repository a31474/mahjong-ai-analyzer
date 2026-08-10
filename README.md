# mahjong-ai-analyzer

国标麻将 AI 牌谱分析服务（后端 Python + numpy 推理）。

## 项目结构

```
backend/            # 后端服务（FastAPI）
  engine/           # IJCAI 推理引擎（来自 mcr-ai/IJCAI-mahjong/deploy/caiest_cnn，原样复制）
  weights/          # 模型权重（.npz，git 忽略）
  tiles.py          # 牌型工具（Task 2）
  converter.py      # 牌谱转换（Task 3）
  analyzer.py       # 分析逻辑（Task 6）
  main.py           # FastAPI 入口（Task 7）
tests/              # pytest 测试
web/                # 前端（待建）
```

## 环境搭建

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

## 开发

所有 python/pytest 命令使用 `.venv/bin/` 前缀。

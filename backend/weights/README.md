# backend/weights/ — kdens3 三学生权重

权重文件**不入库**（.gitignore 排除），需手动下载或运行：

```bash
bash backend/fetch_weights.sh
```

或从 HuggingFace 手动放置到本目录：

- 来源：`Dannibal/ijcai-mahjong-ckpts-2026`（champion/ 目录）
- 文件：
  - `kdens_s0_fp16.npz`（约 26MB，单学生模式必选）
  - `kdens_s1_fp16.npz`（约 26MB）
  - `kdens_s2_fp16.npz`（约 26MB）

## 运行模式

- 默认：3 学生 ensemble（mean logits）
- 环境变量 `ENSEMBLE=1`：仅加载 `kdens_s0_fp16.npz`（单学生）

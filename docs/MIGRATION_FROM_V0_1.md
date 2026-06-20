# MIGRATION_FROM_V0_1

**Date**: 2026-06-19
**From**: `auto_coding_v0_1` (legacy dual-agent coding system)
**To**: `auto_coding_v0_2` (agentic coding system)

---

## 1. 迁移目的

v0_1 已验证了大量工程能力（DeepSeek API、JSON 解析、A/B 编码、Kappa、分歧表、resume、并行），但整体架构不是完整的 Agent 化人工编码流程。v0_2 重新按人工编码流程组织项目，复用 v0_1 中已验证的模块，废弃旧的自循环/prompt_optimizer 逻辑。

---

## 2. v0_1 旧系统审查结果

v0_1 累计完成：
- 18 个 group 全量编码（g01-g18，~3439 条）
- A/B Kappa 跨 group 平均 ~0.76
- 0 prompt_rule_gap across all groups
- 工程成熟度：实时 JSONL、resume、并行、进度显示
- v1.2 locked prompt 经人工确认

问题：
- `prompt_optimizer.py` 的自动 prompt 修订逻辑从未实际触发
- `loop_runner.py` 的 `no_change` 决策是正确结果但架构混乱
- 旧 batch runner 混合了编码执行和质量判断
- 没有 Agent 抽象层

---

## 3. 已迁移模块（直接复用）

| v0_1 路径 | v0_2 路径 | 迁移方式 | 是否修改 | 说明 |
|-----------|-----------|---------|---------|------|
| `src/auto_coding/llm_client.py` | 同名 | 直接复制 | 否 | DeepSeek API 底座 + mock |
| `src/auto_coding/parser.py` | 同名 | 直接复制 | 否 | JSON 解析 + repair |
| `src/auto_coding/io_utils.py` | 同名 | 直接复制 | 否 | JSONL/JSON 读写 |
| `src/auto_coding/config.py` | 同名 | 直接复制 | 否 | .env 配置加载 |
| `src/auto_coding/schemas.py` | 同名 | 直接复制 | 否 | Pydantic 模型 |
| `src/auto_coding/codebook_standardizer.py` | 同名 | 直接复制 | 否 | Phase 1 |
| `src/auto_coding/codebook_review.py` | 同名 | 直接复制 | 否 | Phase 1 |
| `src/auto_coding/prompt_renderer.py` | 同名 | 直接复制 | 否 | Phase 1 |
| `src/auto_coding/unit_table_validator.py` | 同名 | 直接复制 | 否 | Phase 1 |
| `src/auto_coding/pilot_sample_review.py` | 同名 | 直接复制 | 否 | Phase 1 |
| `src/auto_coding/preprocess.py` | 同名 | 直接复制 | 否 | Raw CSV → JSONL |
| `src/auto_coding/__init__.py` | 同名 | 直接复制 | 否 | 包初始化 |

---

## 4. 部分迁移模块（重命名或保留子集）

| v0_1 路径 | v0_2 路径 | 保留内容 | 暂不保留内容 | 原因 |
|-----------|-----------|---------|-------------|------|
| `metrics.py` | `reliability.py` | Kappa、confusion matrix、per-label P/R/F1、disagreements | 旧 `build_disagreements` 依赖 `preprocessed_inputs` | 新体系 ReliabilityAgent 工具层 |
| `diagnosis.py` | `disagreement_analysis.py` | 分歧分类、`_classify_boundary` | `good_reference_conflict` 计数逻辑 | 旧 prompt_rule_gap 停止逻辑不适用新体系 |
| `coder.py` | `coder.py` | `code_single`、实时 JSONL append、resume、并行 | `run_coding` 的旧 orchestration | 后续 CoderAgent 重新封装 |

---

## 5. 未迁移模块

| v0_1 内容 | 不迁移原因 | 后续处理 |
|-----------|-----------|---------|
| `prompt_optimizer.py` | 旧自动 prompt 修订逻辑从未触发；基于 prompt_rule_gap≥3 的停止条件不适用新体系 | 归档为历史参考 |
| `loop_runner.py` | `run_full_round` 混合了编码+Kappa+诊断+决策，架构不清晰 | 新 `self_loop_runner.py` 重新设计 |
| `prompt_versioning.py` | 依赖旧 prompt_optimizer 的 candidate 逻辑 | 新体系重新设计版本管理 |
| `evaluate_good.py` | Good-only reference logic | 新体系重新设计对照评估 |
| `report.py` | CLI 打印逻辑耦合旧模块 | 新体系重新设计报告 |
| `cli.py` (旧) | 混合了 code/kappa/loop-run-round 等旧命令 | 新体系只保留 Phase 1 命令 |
| `loop_runner.py` 的 `run_full_round` | 旧 one-command pipeline | 新 `round_controller.py` 重新设计 |
| `_batch_runner.py` (outputs/) | 临时批处理脚本 | 归档 |

---

## 6. 可复用工程能力

以下工程能力已在 v0_1 中验证，保留到 v0_2：

- DeepSeek API 调用 + mock 模式
- JSON 输出解析 + repair
- A/B 双 Agent 并行
- `--resume` 断点续跑
- `--progress-every` 进度显示
- 实时 JSONL append + flush
- unweighted/weighted Cohen's Kappa
- confusion matrix (4×4)
- per-label precision/recall/F1
- disagreements CSV 导出
- parse_ok/invalid 统计
- codebook → YAML 标准化
- codebook 字段完整性审查
- YAML → prompt 渲染
- unit_table 校验增强

---

## 7. 不再沿用的旧逻辑

| 旧逻辑 | 原因 |
|--------|------|
| prompt_rule_gap 作为核心停止条件 | v0_1 中 18 groups 全部 prompt_rule_gap=0，此条件永不会触发 |
| `no_change` 自动决策 | 新体系改为人工审议 + Agent 辅助决策 |
| Good 作为 Kappa 参考目标 | Good 是人工一致参考，不是优化目标 |
| group batch runner 的质量判断逻辑 | 新体系拆分为独立 Agent |
| 旧 `hold_for_review` 批处理标记 | 新体系改为结构化 decision_log |

---

## 8. v0_2 新架构目标

按 20 步人工编码流程重新组织，项目结构对应 Agent 角色。详见 `AGENTIC_CODING_ARCHITECTURE.md`。

---

## 9. 环境配置

- `.env` 已由用户人工复制到 v0_2，本地可用，但不进入版本控制。
- `.env.example` 用于记录所需环境变量，不含真实密钥。
- `.gitignore` 已确保忽略 `.env`、`__pycache__/`、`outputs/`。
- 测试不调用真实 DeepSeek API。
- 新增 `LLM_TEMPERATURE` 环境变量支持（默认 0.0）。

## 10. 当前 pytest 结果

```
56 passed, 4 warnings in 2.48s
```

覆盖模块：parser, reliability, disagreement_analysis, codebook_standardizer, codebook_review, prompt_renderer, unit_table_validator, pilot_sample_review。

---

## 10. 下一步开发建议

1. **Phase 1-real-input-rebuild**: 从真实 CodeFrame / Datas 生成 initial_codebook.md、unit_table.csv、pilot_sample_units.csv
2. **Phase 2-coder-training**: 实现 CoderTrainingAgent
3. 不继续在 v0_1 上叠加功能
4. v0_1 保留为旧实验参考，不再作为主开发项目

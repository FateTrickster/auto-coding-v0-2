# STAGE_REVIEW_SCOPE

本文件用于约束后续审查范围，避免把全项目问题一次性混在一起。

当前采用：

```text
Stage 0 + Stage 1-10
```

作为业务验收单元。旧文档中的 Phase 1-7 只保留为历史结构参考，不再作为当前审查边界。

---

## 当前优先审查范围

先只审查并修复：

```text
Stage 0  项目初始化与输入门控
Stage 1  初始 Codebook 标准化、审查、Prompt 渲染
Stage 2  编码单元确认与验证
Stage 3  试编码样本生成与覆盖审查
```

对应人工流程：

```text
编写初始 codebook
→ 确定编码单元
→ 抽样试编码
```

Stage 0 是软件项目初始化门控，不是人工编码步骤，但必须先稳定。

---

## Stage 0：项目初始化与输入门控

目标：确认人工输入真实存在，再建立项目目录。

模块：

```text
cli.py：init-from-codebook
io_utils.py
```

输入：

```text
initial_codebook.md
unit_table.csv
project_config.yaml（可选）
```

输出：

```text
00_inputs/
01_codebook/
02_prompts/
03_units/
04_pilot/
```

Gate：

- 必需输入存在；
- 显式传入的 config 存在；
- 输入不可读时不得生成半初始化项目；
- 复制后的输入文件可读取。

当前已知问题：

- `init-from-codebook` 对不存在的输入是静默跳过，应改为失败。

---

## Stage 1：初始 Codebook 标准化、审查与 Prompt 渲染

目标：把人工 Codebook 转换成唯一、稳定、可执行的结构化版本。

模块：

```text
codebook_standardizer.py
codebook_schema.py
codebook_review.py
prompt_renderer.py
```

输出：

```text
01_codebook/codebook_v0.1.yaml
01_codebook/codebook_v0.1.md
01_codebook/codebook_review_report_v0.1.md
01_codebook/codebook_missing_fields.json
02_prompts/coder_prompt_v0.1.md
```

Gate：

- 标签完整、唯一、顺序正确；
- 10 个字段完整；
- 字段顺序正确；
- 每个字段恰好出现一次；
- Schema 严格通过；
- Codebook review 允许进入后续阶段；
- Prompt 与 Codebook 版本一致；
- 失败时不覆盖旧产物。

当前已知问题：

- `codebook_standardizer.py` 没有真正检查字段顺序；
- 需要确认重复字段会失败；
- PromptRenderer 负向测试不能被删除或弱化。

---

## Stage 2：编码单元确认与验证

目标：将人工提供的 `unit_table.csv` 转换为可编码的正式单元表。

模块：

```text
unit_table_validator.py
```

输出：

```text
03_units/unit_table_v0.1.csv
03_units/unit_table_validation_report.md
```

Gate：

- 必需字段齐全；
- `unit_id` 非空且唯一；
- `unit_text` 非空；
- 结构标记一致；
- 短文本、长文本等阈值统一；
- Schema 失败时不生成增强表。

当前已知问题：

- `REQUIRED_FIELDS` 已定义但未实际 gate；
- 空文本目前会进入增强表，后续 sampler 再过滤，边界不清；
- 短/长文本阈值在 validator、sampler、report 中不一致；
- `possible_multi_function_flag` 的自动判断对中文问号不敏感。

---

## Stage 3：试编码样本生成与覆盖审查

目标：从经过验证的编码单元中形成当前轮试编码样本。

模块：

```text
pilot_sampler.py
risk_profile_builder.py
```

职责边界：

- `pilot_sampler.py` 负责抽样；
- `risk_profile_builder.py` 只负责从上一轮真实结果生成下一轮风险画像。

输出：

```text
04_pilot/pilot_sample_units.csv
04_pilot/pilot_sample_build_report.md
04_pilot/risk_profiles/risk_config_round_02_candidate.yaml
```

Gate：

- Round 1 不使用 risk profile；
- Round 1 不包含领域关键词；
- Round 2+ 的风险必须来自真实分歧、裁决和修订证据；
- group、speaker、结构类型覆盖可核查；
- 抽样可复现；
- 样本无重复；
- 报告阈值与实际抽样规则一致。

当前已知问题：

- `sample-pilot` 没有显式 round 边界，误传 `--risk-config` 会直接进入 Round 2+ 模式；
- `sample-pilot` 对缺少 `unit_table_v0.1.csv` 的报错应提示先运行 `validate-units`；
- 报告中的文本长度阈值需要与实际抽样规则统一。

---

## 暂不纳入当前审查

以下阶段先不审查，不作为当前修复目标：

```text
Stage 4  A/B 独立试编码
Stage 5  一致性计算与分歧识别
Stage 6  审议裁决、Decision Log、轮次共识
Stage 7  Codebook 修订与下一轮准备
Stage 8  轮次控制、自循环与冻结决策
Stage 9  Codebook 冻结、正式编码、正式信度
Stage 10 最终裁决、最终数据集、归档
```

也就是说，当前不要继续扩展到：

- DeepSeek hard gate；
- self-loop；
- refiner；
- formal coding；
- final dataset；
- archive；
- dev validation。

这些问题保留，但不混入 Stage 0-3 的验收。

---

## 后续审查规则

每次只审查一个 Stage。

每个 Stage 的审查输出必须包含：

```text
1. 当前是否通过；
2. 阻塞问题；
3. 可后置问题；
4. 最小修复清单；
5. 需要保留或恢复的测试。
```

不得用删除测试换取通过。

不得把后续 Stage 的问题提前作为当前 Stage 的失败条件。

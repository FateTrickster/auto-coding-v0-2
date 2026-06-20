# AGENTIC_CODING_ARCHITECTURE

**Version**: v0.2
**Principle**: Each step in the human coding workflow maps to one or more software Agents.
**Status**: Phase 0 (skeleton + reusable assets migrated)

---

## System Overview

```
Human Steps 1-3 (manual): Raw Data → Coding Goal → Initial CodeFrame
                    ↓
            [Phase 1: Codebook Standardization]
                    ↓
   CodebookStandardizationAgent
                    ↓
   CodebookReviewAgent
                    ↓
   PromptRendererAgent
                    ↓
            [Phase 2: Coder Training]
                    ↓
   CoderTrainingAgent ──→ trains ──→ CoderAgentA
                                    CoderAgentB
                    ↓
            [Phase 3: Pilot Coding]
                    ↓
   CoderAgentA  ←── independent ──→  CoderAgentB
        ↓                                  ↓
   ReliabilityAgent (Kappa calculation)
                    ↓
   DisagreementAnalysisAgent
                    ↓
            [Phase 4: Adjudication]
                    ↓
   AdjudicationAgent (3rd-party review)
                    ↓
   DecisionLogAgent
                    ↓
   CodebookRevisionAgent
                    ↓
   RecodingPlannerAgent
                    ↓
   RoundControllerAgent (decides: re-code or freeze)
                    ↓
            [Phase 5: Codebook Freeze]
                    ↓
   CodebookFreezingAgent
                    ↓
            [Phase 6: Formal Coding]
                    ↓
   FormalCodingManagerAgent
                    ↓
   FinalConsensusAgent
                    ↓
   FinalDatasetAgent
                    ↓
   ArchiveAgent
```

---

## Agent Inventory

| # | Agent Module | Human Step Mapping | Status |
|---|-------------|-------------------|--------|
| 1 | `codebook_standardizer.py` | Step 4: Write initial codebook | ✅ Implemented |
| 2 | `codebook_review.py` | Step 4: Review codebook completeness | ✅ Implemented |
| 3 | `prompt_renderer.py` | Step 4: Render codebook → prompt | ✅ Implemented |
| 4 | `unit_table_validator.py` | Step 5: Validate coding units | ✅ Implemented |
| 5 | `pilot_sample_review.py` | Step 6: Review pilot sample coverage | ✅ Implemented |
| 6 | `coder_training.py` | Step 7: Coder training | 🔲 Placeholder |
| 7 | `coder.py` | Step 8: Independent pilot coding | ⚠️ Partially migrated |
| 8 | `reliability.py` | Step 9: Kappa calculation | ⚠️ Partially migrated |
| 9 | `disagreement_analysis.py` | Step 10: Disagreement analysis | ⚠️ Partially migrated |
| 10 | `adjudicator.py` | Step 11: 3rd-party review | 🔲 Placeholder |
| 11 | `decision_log.py` | Step 12: Decision logging | 🔲 Placeholder |
| 12 | `codebook_refiner.py` | Step 13: Codebook revision | 🔲 Placeholder |
| 13 | `recoding_planner.py` | Step 14: Plan next round | 🔲 Placeholder |
| 14 | `round_controller.py` | Step 14: Round control | 🔲 Placeholder |
| 15 | `self_loop_runner.py` | Steps 8-14 loop | 🔲 Placeholder |
| 16 | `codebook_freezer.py` | Step 15: Freeze codebook | 🔲 Placeholder |
| 17 | `formal_coding_manager.py` | Step 16: Formal coding | 🔲 Placeholder |
| 18 | `final_consensus.py` | Step 17: Final consensus | 🔲 Placeholder |
| 19 | `final_dataset_builder.py` | Step 18: Build final dataset | 🔲 Placeholder |
| 20 | `archive_manager.py` | Step 19-20: Archive | 🔲 Placeholder |

---

## Support Modules

| Module | Purpose | Status |
|--------|---------|--------|
| `llm_client.py` | OpenAI-compatible API + mock | ✅ Reusable |
| `parser.py` | Robust JSON parse + repair | ✅ Reusable |
| `io_utils.py` | JSONL/JSON file I/O | ✅ Reusable |
| `config.py` | .env configuration | ✅ Reusable |
| `schemas.py` | Pydantic data models | ✅ Reusable |
| `preprocess.py` | Raw CSV → JSONL | ✅ Reusable |
| `cli.py` | Typer CLI commands | ⚠️ Needs rebuild |

---

## Data Flow

```
CodeFrame.xlsx + Datas/Raw/*.csv
        ↓ (manual steps 1-3)
initial_codebook.md + unit_table.csv + pilot_sample_units.csv
        ↓ (Phase 1)
codebook_v0.1.yaml + coder_prompt_v0.1.md
        ↓ (Phase 2-3)
agent_a_results.jsonl + agent_b_results.jsonl
        ↓ (Phase 3-4)
kappa_report + disagreements.csv + diagnosis
        ↓ (Phase 4-5)
decision_log + codebook_revision + frozen_codebook
        ↓ (Phase 6)
final_coding_table.csv
```

---

## What v0_1 Validated (Retained)

- DeepSeek v4-flash API works reliably for Chinese coding tasks
- Kappa ~0.76 across 18 groups with v1.2 locked prompt
- 0 prompt_rule_gap — boundary rules are sufficient
- Real-time JSONL + resume + parallel agents are production-ready

## What Changes in v0_2

- No auto prompt optimization (old `prompt_optimizer.py` retired)
- No batch runner with inline quality judgment
- Each coding workflow step gets an explicit Agent
- Decision logging replaces `hold_for_review` markers
- Good data is reference only, not optimization target

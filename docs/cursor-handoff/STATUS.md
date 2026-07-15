# Cursor Flow 状态

最后更新：2026-07-15 22:33 CST（UTC+8）

## 当前阶段

- Flow：**B（C006–C010）执行中**
- WaveId：`C006-C010`
- Batch：`BATCH-20260715-001`
- Prompt：`knowledge-v002` / `knowledge-v002-compact`
- HEAD：`723fd44`（本地多提交待 push；GitHub 443 曾失败）

## Flow A（已完成）

| 项 | 结果 |
| --- | --- |
| 测试基线 | `218 passed, 1 skipped` |
| knowledge.db | 232 条；smoke-answer QA=`pass` |
| C001–C005 | 首批 P01–P06 完成标记齐全 |
| 审计提交 | `8b2f5ae` |

## Flow B 进度

### 视频分析

| 课 | 视频阶段 | 归档 | raw QA |
| --- | --- | --- | --- |
| C006 | export completed | `01_raw/RUN-20260715-001-V001` | pass |
| C007 | transcript running | - | - |
| C008–C010 | pending | - | - |

`run-batch --start 6 --end 10` 仍存活，勿重启。

### 知识流水线（WaveId=`C006-C010`）

| 阶段 | 状态 |
| --- | --- |
| P01 | C006 Cursor 进行中（baseline 已生成，`status=started`） |
| P02–P06 / finalize | 守护等待同波次前置 complete 标记 |

波次守护 PID（22:05 启动）：p01=24720, p02=14656, p03=3656, p04=2628, p05=7976, p06=30680, final=21644。

### 已落地工程改动（支持后续 Flow C）

- `index-tidy --output-version`（`9f28bce`）
- `scripts/build_knowledge_quality_report.py` + `docs/evaluation/knowledge-C001-C005.*`
- 波次脚本可配置 `OutputVersion`/`PromptRoot`（`723fd44`）；默认仍为 v002
- `scripts/start_wave_C006_C010.ps1`

## 下一步

1. 完成 C007–C010 视频归档与 raw QA。
2. 串行完成 P01–P06 与波次 finalize；失败按课/案例补跑。
3. 重建索引、检索/回答、pytest → Flow C 质量审查。

## 阻塞

- GitHub push：网络 443（稍后重试）；无凭据阻塞。

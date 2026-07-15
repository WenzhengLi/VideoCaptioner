# Cursor Flow 状态

最后更新：2026-07-15 22:06 CST（UTC+8）

## 当前阶段

- Flow：A 完成 → B（C006–C010）监控/执行中
- WaveId：`C006-C010`
- Batch：`BATCH-20260715-001`
- Prompt：`knowledge-v002` / `knowledge-v002-compact`
- HEAD：`5e02413`（本地 ahead origin/master 1；`git fetch` 因 GitHub 443 超时失败）

## Flow A 审计结论

| 项 | 结果 |
| --- | --- |
| Git | master @ `5e02413 docs: add standalone Cursor Flow handoff prompts`；工作区干净（仅文档新增待后续提交） |
| 资源 | 磁盘 C/D/E 充足；内存约 31.8GB / 空闲 ~13.7GB |
| 测试基线 | `218 passed, 1 skipped`（略优于文档记载的 217/2） |
| knowledge.db | `knowledge_entries=232`；smoke-answer QA=`pass` |
| C001–C005 | 各课有 `01_raw` transcript、`05_tidy` Markdown/JSON、QA；首批 P01–P06 + `knowledge-pipeline-complete.json` 齐全 |
| C006–C010 视频 | **健康运行**，禁止重启副本 |

### 视频批次进程

| PID | 角色 | 命令摘要 |
| --- | --- | --- |
| 3804 / 17096 | run-batch | `run-batch BATCH-20260715-001 --start 6 --end 10 --run-version V001` |
| 20632 / 18444 | analysis_cli | `C006-RUN-20260715-001-V001`（~5GB RSS） |

### C006 job 阶段（`jobs/batch/C006-RUN-20260715-001-V001/job.json`）

| 阶段 | 状态 |
| --- | --- |
| media / transcript / diarization / alignment | completed |
| board_detect / board_track | completed |
| board_ocr | **running**（代表帧目录已增至 ~120+，OCR JSON 持续增长） |
| merge / export | pending |

C007–C010：manifest 仍为 `pending`，等待串行调度。

### 波次守护（已于 22:05 重启，WaveId=`C006-C010`）

| 阶段 | PID | 脚本 |
| --- | --- | --- |
| P01 | 24720 | `wait_then_run_cursor_review.ps1` |
| P02 | 14656 | `wait_then_run_cursor_p02.ps1` |
| P03 | 3656 | `wait_then_run_cursor_p03.ps1` |
| P04 | 2628 | `wait_then_run_cursor_p04.ps1` |
| P05 | 7976 | `wait_then_run_cursor_p05.ps1` |
| P06 | 30680 | `wait_then_run_cursor_p06.ps1` |
| finalize | 21644 | `wait_then_finalize_knowledge.ps1` |

报告：`wave-C006-C010-watchers-20260715T220509.json`。启动器：`scripts/start_wave_C006_C010.ps1`。

P01 实际脚本为 `wait_then_run_cursor_review.ps1`；勿使用硬编码 C001–C005 的 `wait_then_run_cursor_pilot.ps1`。

## 下一步（不询问，直接执行）

1. 监控 C006 board_ocr → merge → export → 归档；逐课检查 raw QA。
2. 守护等待 raw/P 阶段产物；失败则按课/案例补跑。
3. 波次完成后核对 `*-C006-C010-complete.json`、索引、检索/回答、pytest，进入 Flow C。

## 错误 / 阻塞

- GitHub push/fetch：443 连接失败（网络）；本地工作可继续，推送稍后重试。
- 未见凭据类阻塞。

## 完成标记（首批，勿误读为本波次）

- `cursor-p0N-knowledge-v002-complete.json`（无 WaveId 后缀）= C001–C005
- `knowledge-pipeline-complete.json` = 首批 finalize

本波次完成后应存在：`*-C006-C010-complete.json` 与 `knowledge-pipeline-C006-C010-complete.json`。

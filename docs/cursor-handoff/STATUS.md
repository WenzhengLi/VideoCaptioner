# Cursor Flow 状态

最后更新：2026-07-16 08:15 CST（UTC+8）

## 当前阶段

- Flow：**D（C011–C015）视频进行中**；Flow C 质量审查与 v003 Prompt 已落地（回归待排程）
- WaveId（知识）：`C011-C015`（守护已启动，等待各课 raw 归档）

## Flow A / B（已核实完成）

| 项 | 结果 |
| --- | --- |
| C001–C010 知识 | DB 393 条；smoke-answer 可用 |
| C006–C010 | P01–P06 + finalize 完成；36/36 QA pass |
| pytest（此前） | 219 passed / 1 skipped |
| 质量报告 | `docs/evaluation/knowledge-C001-C010.md`（风险 146；高未分配 C003 40.4%） |

## Flow C

- 修复：`scripts/build_knowledge_quality_report.py`（unassigned / safety_flags）
- 测试：`tests/test_knowledge/test_quality_report.py` 通过
- Prompt：已复制 `prompts/knowledge-v003` + `knowledge-v003-compact`；P03 增加宽边界与 >20% 未分配自检
- **未改** v002 产物；v003 全量回归（C001–C010）待 C011–C015 视频高峰过后启动，避免 Cursor 互抢

## Flow D：C011–C015

### 视频

| 项 | 值 |
| --- | --- |
| 命令 PID | 36448（powershell）/ 32544+20268（run-batch） |
| 日志 | `data/batches/BATCH-20260715-001/run-batch-C011-C015.20260716T080922.*.log` |
| C011 job | `jobs/batch/C011-RUN-20260715-001-V001`；media completed；**transcript running** |
| ffmpeg | WinGet Gyan.FFmpeg `ffmpeg-8.1.2-full_build\bin` |

### 知识守护（等待 transcript + raw QA）

| 阶段 | PID | 日志前缀 |
| --- | --- | --- |
| p01 | 44300 | `wave-C011-C015-p01.20260716T081003` |
| p02 | 46184 | `wave-C011-C015-p02.20260716T081003` |
| p03 | 46968 | `wave-C011-C015-p03.20260716T081003` |
| p04 | 17216 | `wave-C011-C015-p04.20260716T081003` |
| p05 | 38276 | `wave-C011-C015-p05.20260716T081003` |
| p06 | 17040 | `wave-C011-C015-p06.20260716T081003` |
| final | 35816 | `wave-C011-C015-final.20260716T081003` |

报告：`wave-C011-C015-watchers-20260716T081003.json`

## 下一动作

1. 监控 C011→C015 逐课归档与 raw QA；失败只补该课  
2. 知识守护自动串行 P01–P06；关注 failures.jsonl  
3. 视频高峰过后启动 WaveId=`C001-C010-v003` 固定集回归（OutputVersion=`knowledge-v003`）  
4. 完成后比较 unassigned / 检索质量，决定是否采用 v003  

## 阻塞

- 无

# Cursor Flow 状态

最后更新：2026-07-16 09:50 CST（UTC+8）  
审计会话：独立读取 `docs/CURSOR-HANDOFF.md` 接管，**未重启任何任务**。

## 平台纠错（重要）

- 目标知识库产品是 **Dify**（官方 Docker Compose + Dataset API），**不是 Tidy**。
- 仓库内 `index-tidy` / `search-tidy` / `data/tidy/knowledge.db` 仅为本地 SQLite 回归索引。
- 截至本审计：`docker ps` 仅有 `cpa`（Up）；**无 Dify 容器**；Dify 未安装、未入库。

## 当前阶段

- 阶段 A：**接管并完成 C011–C015**（监控既有进程）
- WaveId（知识）：`C011-C015` / `knowledge-v002`
- Git：`HEAD=49d61b5`（含 Dify 交接文档）；`origin/master=5bf4999`；本地领先 2 commit，待网络稳定后 push

## 进程审计（09:50，只监控）

| 角色 | PID | 说明 |
| --- | ---: | --- |
| run-batch PS | 36448 | `--start 11 --end 15`，08:09 起 |
| run-batch py | 32544 / 20268 | 健康 |
| analysis_cli C013 | 16948 / 23000 | 09:16 起，job-id=`C013-RUN-20260715-001-V001` |
| P01 watcher | 44300 | `wait_then_run_cursor_review.ps1` WaveId=C011-C015 |
| P02–P06 + final | 46184 / 46968 / 17216 / 38276 / 17040 / 35816 | 均在等待同波次前置 complete |

**判定**：进程存在且 C013 `board_ocr=running` → **禁止重复启动** run-batch / watcher。

## 视频进度

| 课 | manifest | job 阶段 |
| --- | --- | --- |
| C011 | succeeded | 9/9 completed；已归档；raw QA pass |
| C012 | succeeded | 9/9 completed；已归档；raw QA pass |
| C013 | running | media…board_track completed；**board_ocr running**；merge/export pending |
| C014 | pending | 无 job（等 C013 串行结束后由既有 run-batch 启动） |
| C015 | pending | 同上 |

## 知识进度（v002 / WaveId=C011-C015）

| 课 | P01 | P01 QA | P02+ |
| --- | --- | --- | --- |
| C011 | 完成 | pass | 等待整波 P01 complete 标记 |
| C012 | 完成 | pass | 同上 |
| C013–C015 | 等待视频归档 | — | — |

## 已完成基线（C001–C010，不重做）

- 43549 segments / 19 cases / 393 entries / 146 safety flags
- 本地 SQLite 索引可用（**非 Dify**）
- 质量报告：`docs/evaluation/knowledge-C001-C010.md`；v003 Prompt 已创建，固定回归未跑

## 下一动作（不启动副本）

1. 持续监控 C013 OCR→merge→export→归档→raw QA  
2. 既有 run-batch 自动串行 C014、C015；失败才按同 job-id 断点恢复  
3. 整波 P01 pass 后由既有 watcher 进入 P02–P06  
4. OCR 高峰时只写 Dify 部署/适配代码草案，不抢占资源拉起 Dify 容器  
5. push 本地领先提交（含 `CURSOR-HANDOFF.md`）

## 阻塞

- 无凭据阻塞；Dify 真实模型密钥待部署窗口再配置

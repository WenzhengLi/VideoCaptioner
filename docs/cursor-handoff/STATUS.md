# Cursor Flow 状态

最后更新：2026-07-16 09:54 CST（UTC+8）  
审计会话：独立读取 `docs/CURSOR-HANDOFF.md` 接管，**未重启任何任务**。

## 平台纠错（重要）

- 目标知识库产品是 **Dify**（官方 Docker Compose + Dataset API），**不是 Tidy**。
- 仓库内 `index-tidy` / `search-tidy` / `data/tidy/knowledge.db` 仅为本地 SQLite 回归索引（已加别名 `local-index-*`）。
- 截至本审计：`docker ps` 仅有 `cpa`（Up）；**无 Dify 容器**；Dify 未安装、未入库。
- 已新增：`deploy/dify/`（钉选官方 tag `1.15.0`）与 CLI `dify-create-dataset` / `dify-sync-markdown` / `dify-status`（OCR 高峰**未**执行 `compose up`）。

## 当前阶段

- 阶段 A：**接管并完成 C011–C015**（监控既有进程）
- WaveId（知识）：`C011-C015` / `knowledge-v002`
- Git：本地领先 origin（含交接/STATUS/Dify 骨架）；GitHub `443` 连接失败，提交已保留，稍后重试 push

## 进程审计（持续有效，禁止副本）

| 角色 | PID | 说明 |
| --- | ---: | --- |
| run-batch | 36448 / 32544 / 20268 | `--start 11 --end 15` |
| analysis_cli C013 | 16948 / 23000 | `C013-RUN-20260715-001-V001` |
| P01–P06 + final watchers | 44300 等 7 个 | WaveId=`C011-C015` |

## 视频进度（09:53）

| 课 | manifest | 阶段 |
| --- | --- | --- |
| C011 | succeeded | 归档+raw QA pass；P01 pass |
| C012 | succeeded | 归档+raw QA pass；P01 pass |
| C013 | running | **board_ocr running**（产物持续更新） |
| C014–C015 | pending | 等串行 |

## 下一动作

1. 只监控至 C013 export/归档 → C014 → C015  
2. 整波 P01 complete 后由既有 watcher 进 P02–P06  
3. 资源窗口再 `deploy/dify/scripts/bootstrap.ps1` + `up.ps1`  
4. 重试 `git push origin master`

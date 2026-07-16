# Cursor Flow 状态

最后更新：2026-07-16 19:55 CST（UTC+8）

## 平台纠错

- 目标产品：**Dify**（非 Tidy）。本地 SQLite 仅回归索引。
- 无 Dify 容器；`deploy/dify/` 与 `dify-*` CLI 已就绪。

## 本轮任务边界（仅事实与证据层）

- 唯一任务说明：`docs/CURSOR-NEXT-前20课事实与证据层.md`
- 仅执行 P01–P04（含 QA），不启动 P05/P06/finalizer，不启动 Dify
- 不做阿峰方法层、MiMo API、发布分类、忠实度审查
- 不覆盖或删除用户讨论中的既有 Markdown 文件

## 现场审计（续跑 2026-07-16 19:45）

- `git status`：STATUS / 任务说明 / evaluation 报告未跟踪或已改
- HEAD：`c4d52ff feat: 搭建阿峰课程方法层 v001`
- `origin/master...HEAD`：`0 1`（本地落后远端 1）
- 无 `run-batch` / knowledge watcher / VideoCaptioner 分析进程在跑
- Docker daemon 当前不可用；未启动 Dify，未触碰 cpa

## 当前阶段

- 已完成：任务 A（C001–C015 事实与证据层质量汇总）
- 进行中：任务 B（P03 v002/v003 固定回归 C003/C008/C006/C010）
- 待执行：任务 C/D/E/F 与全量测试

## 任务 A 摘要

- 产物：`docs/evaluation/knowledge-C001-C015.md/.json`（schema 1.1，聚焦 raw/P01–P04）
- 补齐：`C001` 缺失的 `P01-knowledge-v002-qa.json`（现为 pass）
- 脚本增强：`scripts/build_knowledge_quality_report.py`（阶段耗时、OCR、P04、flags）
- 标记课：C003/C008/C012/C015 高未分配；C007 高 unknown；C015 OCR 偏高

## C011–C015

| 阶段 | 状态 |
| --- | --- |
| 视频 + P01–P06 + finalizer | **已完成**（`knowledge-pipeline-C011-C015-complete.json` 已存在；STATUS 此前滞后） |

## 下一动作

1. 跑完 P03 v003 固定集并写出 `docs/evaluation/p03-v002-v003-regression.md/.json`
2. 按采用规则确定 evidence baseline（任务 C）
3. 推进 C016–C020 视频与 P01–P04

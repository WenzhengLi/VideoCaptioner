# Cursor 独立任务：最终完成审计、清理和交付

工作区 `D:\Dev\VideoCaptioner`。不要依据已有“complete”文件直接宣布完成。读取总控 Prompt、STATUS、
所有批次 manifest、质量报告、冻结 Prompt、catalog、数据库和 Git，建立逐条验收矩阵。

验证每个唯一视频/PDF：原始 QA、P01/P02/P03、案例覆盖、每案例 P04/P05/P06 QA、Markdown 和索引记录。
确认重复来源映射正确且未重复处理。抽检证据 ID、speaker、讲师观点、观察结果、拒绝/隐私/醉酒/年龄安全。
运行 ruff、类型检查、pytest、真实 FunASR/WeSpeaker/OCR/PDF 冒烟、中文检索和至少 20 问回答 QA。

检查生命周期清理：`benchmarks/results/`、`tmp/`、调试帧、OCR 中间图和已归档 job 的大缓存按规则删除；
最终 TXT/JSON/Markdown、运行元数据和 QA 不得删除。检查没有 secrets、大文件和 data/jobs 被 Git 跟踪。
更新 README、架构、运行恢复、磁盘规划、命名和外部 Tidy 限制。

写 `docs/cursor-handoff/FINAL-REPORT.md`：来源/唯一/重复/PDF/成功失败、segments、案例、知识条目、安全标签、
OCR 缓存和耗时、测试、20 问结果、数据库、提交号、限制。工作区干净后 push。只有验收矩阵全部有直接
证据且失败为零，才可回复完成；否则继续修正和补跑。


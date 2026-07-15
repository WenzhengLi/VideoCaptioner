# Cursor 独立任务：审计现场并恢复 C006–C010

工作区为 `D:\Dev\VideoCaptioner`。你没有此前上下文。C001–C005 已完成，C006–C010 的视频批次曾以
`course-knowledge run-batch BATCH-20260715-001 --start 6 --end 10 --run-version V001` 启动；最后已知
C006 转写完成、WeSpeaker 正在运行。P01–P06 等待进程已被停止，避免重复写入。真实状态必须重新检查。

使用 Flow 完成以下任务，不请求用户授权：

1. 阅读 README、`docs/knowledge-pipeline.md`、knowledge 源码、batch/watcher 脚本。
2. 检查 Git、进程、manifest、status/failures、C006–C010 job.json、归档和 QA。
3. 若视频批次仍运行，记录 PID 并监控，禁止启动副本；若退出，读取日志修复后使用相同 batch/job-id 恢复。
4. 验证首批 `knowledge-pipeline-complete.json`、`knowledge.db`、232 条知识和 smoke answer 可读。
5. 运行 pytest 并记录结果。
6. 创建 `docs/cursor-handoff/STATUS.md`，写清每课当前阶段、最后更新时间、进程和下一动作。
7. 不覆盖 data 中已有结果，不删除有效归档，不改 Prompt 内容。

交付：更新后的 STATUS、健康的视频批次或可复现的恢复命令、测试结果。完成后提交代码/文档变更；运行数据
不提交。


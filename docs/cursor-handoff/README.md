# Cursor Flow 交接任务

本目录中的文件是可以直接复制给 Cursor Agent 的独立 Prompt。Cursor 不需要读取 Codex 会话，
每份任务都包含必要背景、当前已知状态、执行边界、交付物和验收标准。

推荐顺序：

1. 优先把 `00-MASTER-FLOW.md` 整份交给 Cursor，让它作为总控使用 Flow 依次执行全部阶段。
2. Cursor 必须在 `docs/cursor-handoff/STATUS.md` 持续记录状态；该文件由 Cursor 首次运行时创建。
3. 如果总控在某阶段退出，开启一个全新 Cursor 会话，复制对应的 `TASK-*.md` 单独补跑。
4. 不要同时启动两个会写同一课程、同一版本输出的任务。

任务文件：

- `00-MASTER-FLOW.md`：总控任务，覆盖现状审计、5/10/15/20 课迭代、全量课程、PDF、Tidy、问答和最终验收。
- `TASK-01-AUDIT-AND-RESUME.md`：审计现场、进程和数据，恢复 C006–C010。
- `TASK-02-C006-C010.md`：完成第 6–10 课及前 10 课质量回归。
- `TASK-03-C011-C015.md`：完成第 11–15 课并迭代 Prompt。
- `TASK-04-C016-C020.md`：完成第 16–20 课、冻结 Prompt。
- `TASK-05-FULL-CORPUS-PDF.md`：处理全部唯一视频和 PDF。
- `TASK-06-TIDY-AND-ANSWERING.md`：安装并接入 Dify，完成知识库导入、检索和多方案回答验收。
- `DIFY-CORRECTION.md`：重要纠错；说明 Dify 才是目标，SQLite 只可作为本地暂存/回归索引。
- `TASK-07-FINAL-AUDIT.md`：最终逐项审计、清理、测试、提交和推送。

固定工作区：`D:\Dev\VideoCaptioner`。

Cursor Agent 非交互调用固定参数：

```text
-p --force --sandbox disabled --approve-mcps --trust --model auto
```

禁止使用 `--resume` 继承其他课程上下文。每课、每案例、每阶段必须使用独立上下文。

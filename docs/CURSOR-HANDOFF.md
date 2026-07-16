# Cursor 新会话完整交接 Prompt（单文件、无需任何历史上下文）

请把本文件视为用户直接交给你的完整任务。你没有此前 Codex/Cursor 聊天上下文，也不需要读取旧会话。
使用 Cursor Flow 工作方式，从现场状态继续执行，不要只写计划，不要请求用户点击允许，不要等待用户确认。
遇到长任务要持续监控、写状态、检查日志、修复和断点补跑；不要因为某条命令耗时长就重新启动重复进程。

## 1. 用户真正要实现什么

用户有约 97 集聊天课程视频和一份 PDF，希望自动完成：

1. 视频语音转写、WeSpeaker 说话人区分、时间对齐；
2. 自动发现视频中的课板区域，跟踪左右移动/缩放后的课板，减少完整 OCR 次数但保证内容完整；
3. 合并语音、speaker、课板 OCR，保留原始时间、segment ID 和来源；
4. 使用独立 Cursor 上下文完成 P01–P06 清洗：规范化、分类、案例边界、证据提取、安全审查、原子知识；
5. 先做 5/10/15/20 课迭代，回归 Prompt，然后使用冻结版本处理全部唯一课程和 PDF；
6. 最终安装并使用 **Dify** 建知识库、导入知识、建立检索与多方案问答应用。

重要纠错：目标产品是 **Dify**，不是 Tidy。仓库当前的 `index-tidy`、`search-tidy`、
`data/tidy/knowledge.db` 是此前误命名的本地 SQLite 暂存/回归索引。SQLite 可以保留用于离线测试，
但绝不能再把 SQLite 建库描述成“Dify 已安装”或“Dify 已入库”。截至交接时，Dify 尚未安装。

## 2. 固定路径与环境

- 工作区：`D:\Dev\VideoCaptioner`
- GitHub：`https://github.com/WenzhengLi/VideoCaptioner.git`
- 分支：`master`
- Python：`D:\Dev\VideoCaptioner\.venv\Scripts\python.exe`
- 数据：`D:\Dev\VideoCaptioner\data`
- 任务：`D:\Dev\VideoCaptioner\jobs\batch`
- 主批次：`BATCH-20260715-001`
- 课程来源：
  `E:\BaiduNetdiskDownload\绅士派《迷情烽暴2023》已更新97集\绅士派《迷情烽暴2023》已更新97集`
- FFmpeg：
  `C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin`
- 当前稳定清洗结果：`knowledge-v002`
- 新候选 Prompt：`prompts\knowledge-v003`、`prompts\knowledge-v003-compact`
- 状态文件：`docs\cursor-handoff\STATUS.md`
- 10 课报告：`docs\evaluation\knowledge-C001-C010.md`

Docker 已安装，`docker ps` 可用；截至 2026-07-16 检查时只有 `cpa` 容器，没有 Dify 容器。
不要删除或影响现有 `cpa`。Docker Desktop 的 Windows service 可能显示 stopped，但 Docker Engine 仍可能
通过 WSL 工作，必须以 `docker info`/`docker ps` 实测为准。

## 3. 交接时已经完成的工作

### C001–C010

- C001–C010 已完成原始视频分析、P01–P06、逐课/逐案例 QA、Markdown 和本地索引。
- 10 课统计：43,549 segments、19 cases、393 knowledge entries、146 safety flags。
- 类型约为：risk 141、case 132、expression 47、principle 41、counterexample 32。
- `knowledge-pipeline-C006-C010-complete.json` 状态为 complete。
- 当前测试基线：`219 passed, 2 skipped`。
- 质量审查发现：C003 未分配 40.4%、C008 26.0%，因此创建 v003 强化 P03 宽边界和覆盖规则。
- v003 尚未完成 C001–C010 固定回归，不能直接宣称已采用或已冻结。

### 重复来源和 PDF

- `VIDEO001` 与 C012 重复；C078 与 C068 重复。必须用 catalog/hash 证据复核并复用，不能重复做昂贵处理。
- PDF 来源登记为 `PDF001`，尚未完成独立 PDF 入库流程。

### Git

- 最新本地提交：`28a2511 docs: correct knowledge platform target to Dify`。
- 该提交因 GitHub 网络重置尚未推送，交接时本地领先远端 1 commit。
- `docs/cursor-handoff/STATUS.md` 可能存在 Cursor 尚未提交的进度修改，属于有效用户工作，不能丢弃。
- 开始前执行 `git status --short`，保留所有已有改动，禁止 reset/checkout 覆盖。

## 4. 交接瞬间正在进行的工作（必须重新检查，不能盲信）

交接前最后一次现场检查：

- C011：视频 9/9 阶段完成、已归档、raw QA pass、P01 v002 和 P01 QA pass；P02 尚未开始。
- C012：同上。
- C013：media/transcript/diarization/alignment/board_detect/board_track 已完成，`board_ocr` 正在运行；
  merge/export 未开始。
- C014、C015：尚未开始。
- C011–C015 的视频批次进程、P01–P06 watcher 和 finalizer 在运行/等待。

用户会打断旧 Cursor，会话结束不一定会终止这些独立 PowerShell/Python 进程。新会话第一件事必须执行：

```powershell
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -match 'run-batch.*--start 11|C011-C015|analysis_cli.*C01[3-5]'
} | Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine
```

再检查：

```powershell
Get-Content data\batches\BATCH-20260715-001\manifest.json -Raw -Encoding utf8
Get-Content data\batches\BATCH-20260715-001\status.jsonl -Tail 20 -Encoding utf8
Get-Content jobs\batch\C013-RUN-20260715-001-V001\job.json -Raw -Encoding utf8
```

判断规则：

- 进程存在、CPU/日志/job.json 时间在变化：只监控，不启动副本。
- 进程不存在但 job 未完成：读取错误日志，使用相同 batch、run-version 和 job-id 断点恢复。
- watcher 仍存在：不要再启动相同 WaveId 的 watcher。
- watcher 被打断：确认没有同名进程后，再用 `WaveId=C011-C015` 恢复。
- 不得创建新的 run-id 来绕过失败，否则会重做并产生重复归档。

## 5. 立即执行顺序

### 阶段 A：接管 C011–C015

1. 更新 `docs/cursor-handoff/STATUS.md`，写明真实 PID、课程阶段和检查时间。
2. 让 C013 完成 OCR/merge/export/归档/QA，然后串行完成 C014、C015。
3. P01 必须逐课完成并 QA pass；整波 P01 complete 后，现有 watcher 会依次进入 P02–P06。
4. 每课 P01/P02/P03 QA 必须 pass；每案例 P04/P05/P06 QA 必须 pass。单个失败只补跑该课/案例。
5. 生成 C001–C015 质量报告，抽检新增每课至少 2 个案例、每案例至少 3 条知识。

### 阶段 B：v003 回归与前 20 课

1. 使用 v003 回归 C001–C010，旧 v002 产物不得覆盖。
2. 比较完整度、P03 未分配比例、证据、speaker、安全和检索；只有不退化才采用 v003。
3. 完成 C016–C020 独立 Wave，生成 20 课报告。
4. 修正后回归 C001–C020，冻结 Prompt；写 README/CHANGELOG/冻结证据。

### 阶段 C：全量唯一课程和 PDF

1. 按小 Wave 串行处理剩余唯一视频；每课独立进程和 Cursor 上下文，失败断点补跑。
2. 每课输出后立即 QA，不要等全量完成才发现某课缺失。
3. PDF001 使用独立 PDF 处理：保留页码、文本块、图片/OCR、来源定位；不能当视频处理。
4. 重复来源只建立映射，禁止重复转写/OCR。

### 阶段 D：真正接入 Dify

不要等到最后才发现 Dify 无法部署，但也不要在视频 OCR 高负载时抢占资源。先完成部署脚本和适配代码，
在合适的资源窗口启动。

必须交付：

1. 使用 Dify 官方 Docker Compose，固定版本，不用来源不明的一键镜像。
2. 独立目录（建议 `deploy/dify/` 或工作区外持久目录）、`.env.example`、数据卷、健康检查、启动/停止、
   备份和升级文档。真实 `.env` 和密钥不得提交。
3. 创建课程 Dataset，记录 dataset_id。
4. 新增 `dify-*` CLI 或独立同步程序，通过官方 Dataset/Document API 导入通过 P06 QA 的 Markdown。
5. 建立本地 knowledge ID ↔ Dify document_id 映射；幂等新增、更新、删除、失败重试和 indexing 状态轮询。
6. 元数据至少包含 course_id、case_id、type、source_ids、evidence_spans、confidence、prompt_version、
   safety_flags、视频时间或 PDF 页码。
7. 配置 embedding 和 LLM provider。优先检查本机已有、用户已授权的兼容服务；不得在日志或提交中打印
   token。没有可用密钥时，完成除真实模型调用外的所有工作并把唯一凭据步骤明确记录，不能用 SQLite
   冒充 Dify。
8. 在 Dify 创建 Chatflow/Workflow：用户问题 → 知识检索 → 多解释/多方案回答 → 引用与安全检查。
9. 使用 Dify 的真实检索/API 测试不少于 20 个问题；本地 SQLite 测试不能替代。

历史 `index-tidy`/`search-tidy` 可保留兼容，但应逐步改名为 `local-index-*`，新增兼容别名和迁移说明。
SQLite 原始字段曾发现乱码、表中缺少 prompt_version；作为本地工具也必须修复，但这不是 Dify 交付本身。

## 6. 清洗与安全硬约束

1. 完整度优先，不以减少重复、缩短文本或降低案例数代替完整性。
2. 保留 segment ID、时间、speaker cluster、原文、OCR、来源和不确定项。
3. 未知身份仍保留 `speaker_0/speaker_1`，禁止整课降级为 `unknown`。
4. P03 案例区间与 unassigned 必须无重叠、无遗漏覆盖全课。
5. P04/P05/P06 evidence 必须位于所属案例范围。
6. 讲师观点只能是 instructor claim，模拟结果不能写成 observed outcome。
7. 明确拒绝、不适、恐惧、醉酒、撤回同意、隐私、年龄不明、欺骗和施压必须作为风险/停止信号；
   禁止包装成测试、窗口或推进技巧。
8. 视觉优化允许大量抽帧和图像比较，真正减少的是完整 OCR 调用；同一帧 OCR 必须缓存。
9. 不覆盖历史版本。Prompt 变更提升版本并回归固定集。

## 7. Cursor 执行规则

- 使用 Flow，不只写计划。
- 每课、每案例、每阶段使用独立上下文；禁止 `--resume` 混课。
- 非交互 Cursor Agent 参数固定：
  `-p --force --sandbox disabled --approve-mcps --trust --model auto`。
- 不硬编码 composer/Kimi/GLM 等不可用模型。
- 输出 JSON 后重新解析并运行确定性 QA；QA 未通过不进入下游。
- 每 30–60 分钟或每课完成后更新 STATUS，不能数小时无记录。
- 临时诊断用 `tmp/`，完成后清理；data/jobs/output/模型/视频不提交。
- 稳定阶段独立 commit，检查 secrets/大文件后 push。GitHub 网络失败保留本地提交并重试，不重复改写提交。

## 8. 最终完成标准

只有以下全部有直接证据才可回复完成：

- 所有唯一视频和 PDF 处理成功，重复映射正确，失败为零；
- 逐课原始 QA、P01–P03 和逐案例 P04–P06 QA 全通过；
- 冻结 Prompt 已完成 C001–C020 回归并用于全量；
- Dify 官方容器健康运行；全量知识真实导入 Dify 且 indexing 完成；
- Dify Dataset/Document 映射完整，真实 Dify 检索和 20 问 Chatflow/Workflow QA 通过；
- README、运行恢复、Dify 部署、备份、数据命名和最终报告完成；
- 全量测试通过，Git 工作区干净并推送。

现在开始：先重新审计进程、manifest、job.json、Git 和 STATUS。不要依据交接时间点盲目重启；接管健康
任务后继续完成 C011–C015。同时把“Dify 而不是 Tidy”的纠错写进 STATUS，后续所有报告使用正确名称。


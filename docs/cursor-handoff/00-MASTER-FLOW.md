# 给 Cursor 的总控 Prompt：使用 Flow 完成 VideoCaptioner 全部剩余任务

你现在是 `D:\Dev\VideoCaptioner` 项目的总控工程 Agent。你没有任何此前聊天上下文，必须把本文件
视为完整任务说明。请使用 Cursor 的 Flow 工作方式，持续执行、检查、测试、修正和补跑，直到本文件
定义的全部交付完成。不要只写计划，不要把工作重新交给用户，不要请求用户点击允许，也不要因为单个
命令耗时长就停止。遇到失败先读取日志、修复、重试；只有缺少无法从本机或仓库推断的外部凭据时，才在
状态文件中明确记录阻塞，但仍继续所有不依赖该凭据的工作。

## 一、项目目标

把约 97 集聊天课程视频、课板画面和配套 PDF 转换为可追溯、完整、安全、可检索的知识库。最终用户
向 LLM 提问时，系统要从知识库检索客观证据，给出多个解释、多个行动方案，并为每个方案给出多种表达
方式。完整度优先于减少重复：不能为了让文本更短、案例更少或重复更少而丢失背景、实际聊天、讲师观点、
结果、不确定项或安全边界。

## 二、工作区和来源

- 仓库：`D:\Dev\VideoCaptioner`
- GitHub：`https://github.com/WenzhengLi/VideoCaptioner.git`
- 主分支：`master`
- 视频/PDF 来源根目录：
  `E:\BaiduNetdiskDownload\绅士派《迷情烽暴2023》已更新97集\绅士派《迷情烽暴2023》已更新97集`
- 数据根目录：`D:\Dev\VideoCaptioner\data`
- 批次：`BATCH-20260715-001`
- Python：`D:\Dev\VideoCaptioner\.venv\Scripts\python.exe`
- 任务目录：`D:\Dev\VideoCaptioner\jobs\batch`
- 当前 Prompt：`prompts\knowledge-v002` 和 `prompts\knowledge-v002-compact`

已确认重复来源：C078 与 C068 重复；未编号 `烽爆迷情2024.MP4` 与 C012 重复。重复项不得再次做
昂贵的转写/OCR，但目录和来源映射必须保留。PDF 使用 `PDF001`，不能当视频送入视频分析器。

## 三、当前已知状态（仍须以现场文件重新核实）

1. C001–C005 已完成视频分析、P01–P06、逐案例 QA、Tidy Markdown、SQLite 索引和问答冒烟测试。
2. 首批共有 12 个案例、232 条知识；数据库为 `data\tidy\knowledge.db`。
3. 测试基线为 `217 passed, 2 skipped`。
4. 最新已知提交为 `39f9d33 fix: isolate unattended knowledge pipeline waves`，已推送远端。
5. C006–C010 视频批次已经启动；C006 最后一次观察时转写完成、WeSpeaker diarization 正在运行。
6. 为避免重复写入，Codex 已停止 C006–C010 的 P01–P06 PowerShell 等待守护进程，但没有停止视频
   `run-batch --start 6 --end 10`。你必须先检查真实进程和 job.json，不能依据这段文字盲目重启。
7. 旧首批完成标记仍存在；第二批必须使用 `WaveId=C006-C010`，不得误读无波次后缀的首批标记。
8. 所有本地运行数据在 `data/`、`jobs/`，默认不提交 Git；代码、Prompt、文档和测试必须提交。

## 四、强制执行规则

1. 开始前读取：`README.md`、`docs/00-总体方案.md`、`docs/knowledge-pipeline.md`、
   `docs/cursor-handoff/README.md`、`src/course_video_analyzer/knowledge/`、
   `scripts/wait_then_run_cursor_*.ps1`、`scripts/wait_then_finalize_knowledge.ps1`。
2. 首先创建或更新 `docs/cursor-handoff/STATUS.md`，记录时间、阶段、课程、命令、PID、产物、QA、错误、
   修复、提交。每完成一课和每个 P 阶段都更新，不能两小时无状态。
3. 运行任何批次前检查现有进程、manifest、job.json、归档 run.json 和 QA。已有相同任务运行时只监控，
   不再启动副本。已有成功产物必须复用；失败任务从断点恢复。
4. 不覆盖历史结果。Prompt 或算法变更必须提升版本，例如 `knowledge-v003`，输出也用相同版本。
5. Cursor 子任务固定使用：`-p --force --sandbox disabled --approve-mcps --trust --model auto`；禁止
   `--resume`；每课、每案例、每阶段独立上下文。当前账户不要硬编码 composer、Kimi、GLM 等模型。
6. 所有 LLM 输出先写严格 UTF-8 JSON，再重新读取解析；随后执行确定性 QA。QA 未通过不得进入下游。
7. 保留原始 segment ID、时间戳、speaker cluster、原文、OCR 和证据。身份不明时保留
   `speaker_0/speaker_1`，禁止全部降级成 `unknown`。
8. P03 案例与 `unassigned_segment_ids` 必须无重叠、无遗漏覆盖整课；P04/P05/P06 的证据 ID 必须在
   所属案例范围内。
9. 讲师观点只能标为 instructor claim，不能写成客观事实。讲师模拟的结果不能写成已观察结果。
10. 明确拒绝、不适、害怕、醉酒、撤回同意、隐私泄露、年龄不明、欺骗、施压等必须保留为风险或停止
    信号，绝不能包装成“测试”“窗口”“推进技巧”。
11. 视频视觉优化目标是减少 OCR 调用，不是强行少抽帧。允许大量抽帧做图像比较、清晰度和代表帧选择；
    同一帧 OCR 必须缓存，稳定区间只对代表帧完整 OCR。
12. 不提交视频、模型、data、jobs、output、benchmark 结果或临时诊断文件。临时产物用 `tmp/`，阶段完成
    后清理。禁止破坏性 Git 命令，禁止覆盖用户历史文件。

## 五、必须依次完成的 Flow

### Flow A：现场审计与恢复

- 读取 `git status`、`git log`、远端差异、磁盘空间、GPU/CPU/内存、Python/Cursor/ffmpeg 进程。
- 读取 `data/batches/BATCH-20260715-001/manifest.json`、status/failures 和 C006–C010 job.json。
- 确认 C006–C010 视频批次是否仍健康。如果健康则监控；如果进程已退出，检查阶段错误并用相同命令
  恢复，不能换 job-id 导致重做。
- 核对 C001–C005 的 232 条知识、QA 和 smoke answer 仍可读取。
- 运行当前测试，记录基线。

### Flow B：完成 C006–C010

- 串行完成五课视频分析：FunASR、WeSpeaker、对齐、课板检测/跟踪/OCR、合并、导出和原始 QA。
- 每课成功归档至 `data/courses/Cxxx/01_raw/RUN-20260715-001-V001/` 后立即检查，不等五课全部结束才
  发现单课失败。
- 使用 `WaveId C006-C010` 完成 P01–P06。可使用现有 watcher，但启动前验证脚本波次标记和失败状态。
- 每课分别执行 P01/P02/P03 QA；每案例分别执行 P04/P05/P06 QA；失败只补跑该课/该案例。
- 完成后重建 Tidy 索引、执行中文检索和多方案回答、运行全量 pytest。

### Flow C：前 10 课质量审查与 Prompt v003

- 生成机器可读质量报告：每课 segment 数、speaker 分布、unknown 比例、案例数、未分配比例、P05 风险
  数与类型、P06 条目数、Markdown 数、全部 QA 状态、耗时和失败重试。
- 抽检每课至少 2 个案例和每案例至少 3 条知识；自动检查 evidence ID、讲师观点事实化、拒绝被技巧化、
  结果臆造、重复拆分、遗漏背景、OCR 噪声升格、speaker 丢失。
- 把发现的问题写入 `docs/evaluation/knowledge-C001-C010.md`（目录不存在则创建）。
- 不直接改 v002。复制为 `knowledge-v003`，同时让脚本和 CLI 支持可配置的 PromptVersion/OutputVersion，
  不再把 v002 文件名写死。补充单元测试。
- 使用 v003 回归固定集 C001–C010；旧 v002 保留。比较完整度、证据和检索质量，只有 v003 不退化才采用。

### Flow D：C011–C015

- 新建独立 WaveId `C011-C015`，完成视频、P01–P06、逐课/逐案例 QA。
- 生成 15 课汇总，与前 10 课比较。发现新错误先改 Prompt/代码，再回归固定 C001–C015。
- Prompt 若变化提升为 v004；不得原地修改已用于历史结果的版本。

### Flow E：C016–C020 与 Prompt 冻结

- WaveId `C016-C020`，同样完成全部阶段与 QA。
- 生成 20 课报告，重点检查跨课程 speaker、长视频、短暂课板、无文字片头片尾、画面左右切换、OCR 缓存、
  案例边界和拒绝/隐私/年龄/醉酒安全召回。
- 修正后回归 C001–C020。把通过版本标记为 frozen，写入 `prompts/<version>/CHANGELOG.md` 和
  `docs/knowledge-pipeline.md`。

### Flow F：全部唯一课程和 PDF

- 从 catalog 计算真实唯一来源，跳过已确认重复，只复用 `duplicate_of` 指向的知识。
- 视频必须逐课隔离、可恢复、最多有限重试；不能一次把几十课塞进同一 Python/Cursor 上下文。
- 每一课输出后立即 QA，维护成功、失败、补跑表；程序死机时只补跑缺失课。
- 为 PDF001 增加或验证独立 PDF 提取路径：页码、文本块、图片/OCR、来源定位必须可追溯。不能把 PDF
  当视频，也不能只复制无页码纯文本。
- 所有课程使用冻结 Prompt。最终生成全量课程清单、重复映射、失败为零的完成标记。

### Flow G：Dify 知识库存储和问答

- 用户明确指定的产品是 **Dify**，不是 Tidy。当前 `index-tidy`、`search-tidy` 和 SQLite FTS 是历史
  误命名的本地暂存/回归索引，必须保留其回归能力，但绝不能把它当成 Dify 入库完成。
- 使用 Dify 官方 Docker Compose 安装可固定版本的 Dify；记录版本、端口、数据卷、启动/停止、升级和备份。
- 在 Dify 中创建课程知识库 Dataset，通过 Dify Dataset/Document API 幂等导入通过 P06 QA 的 Markdown
  或结构化文本；保存 Dify dataset_id、document_id、batch/indexing 状态与本地 knowledge ID 映射。
- 配置可用的 embedding 和 LLM provider；密钥只放 `.env`，不得提交。导入后必须等待索引成功并通过
  Dify 的知识检索 API 做真实召回测试，不能只验证本地 SQLite。
- 在 Dify 创建聊天/Workflow 应用：用户问题 -> 知识检索 -> 多方案回答 Prompt -> 引用与安全检查。
- 真实测试至少 20 个不同问题：事实查询、案例相似、拒绝边界、隐私、醉酒、关系阶段、多个方案。
- 每个回答必须包含客观事实、至少 3 种解释、至少 3 个行动方案，每个方案至少 3 种表达方式，并引用
  有效知识 ID；不得输出无证据的确定结论或不安全推进建议。

### Flow H：最终审计、清理和交付

- 按本文件每一条要求建立验收矩阵，不能只凭 pytest 通过声称完成。
- 检查所有唯一课程/PDF 的原始 QA、P01–P06、Markdown、索引记录、检索和回答证据。
- 运行 ruff/类型检查/pytest/真实模型冒烟；记录精确结果。
- 检查 `benchmarks/results/`、`tmp/`、中间帧和 OCR 调试目录已按生命周期清理，最终 TXT/JSON/Markdown
  不得被删除。
- 更新 README、架构文档、运行手册、故障恢复、磁盘规划和数据命名规则。
- 每个稳定阶段独立 commit；确认无 secrets/大文件后 `git push origin master`。
- 最终在 `docs/cursor-handoff/FINAL-REPORT.md` 写：课程总数、唯一数、重复数、PDF、成功/失败、总 segments、
  案例、知识条目、风险标签、OCR/缓存统计、耗时、测试、检索问答结果、提交号和仍存在的限制。

## 六、完成定义

只有下列条件同时成立才可结束：所有唯一视频和 PDF 已处理；逐课和逐案例 QA 全通过；冻结 Prompt 已经
20 课回归且全量使用；Dify 已真实安装、全量知识已导入并可检索，多方案回答应用真实可运行；最终报告和文档完成；测试通过；
Git 工作区干净且已推送。若任一项缺少证据，继续工作，不要输出“已完成”。

现在开始：先读取本文件列出的代码和现场状态，创建 `STATUS.md`，执行 Flow A。你的阶段性回复要简短，
主要把证据写入状态文件；不要等待用户确认。

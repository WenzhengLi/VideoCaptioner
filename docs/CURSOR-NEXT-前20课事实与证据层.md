# Cursor 下一阶段任务：完成前 20 课事实与案例证据层

你现在接手 `D:\Dev\VideoCaptioner`。你没有此前聊天上下文，请把本文件视为完整任务说明。使用 Cursor Flow 持续执行，不要只写计划，不要请求用户确认。遇到失败应检查日志、修复和断点补跑。

## 一、这次任务的边界

本次只完成：

```text
视频事实处理
→ P01 文本规范化
→ P02 来源与知识属性分类
→ P03 案例边界
→ P04 单案例证据提取
```

本次明确不做：

- 阿峰方法提炼；
- MiMo API 接入；
- 课程忠实度审查；
- 阿峰发布分类；
- 新阿峰 Markdown；
- Dify Dataset 导入；
- Dify Workflow；
- C016–C020 的旧 P05/P06；
- 修改或覆盖旧 knowledge-v002 结果。

阿峰方法层将由 Codex 后续单独实现。你只需要交付稳定、完整、可追溯的课程事实和案例证据层。

## 二、当前真实状态

工作区：

```text
D:\Dev\VideoCaptioner
```

Python：

```text
D:\Dev\VideoCaptioner\.venv\Scripts\python.exe
```

来源目录：

```text
E:\BaiduNetdiskDownload\绅士派《迷情烽暴2023》已更新97集\绅士派《迷情烽暴2023》已更新97集
```

批次：

```text
BATCH-20260715-001
```

FFmpeg：

```text
C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin
```

截至 2026-07-16 15:15：

- C001–C015 视频事实处理完成；
- C001–C015 raw QA 通过；
- C001–C015 旧 knowledge-v002 P01–P06 完成；
- 共 29 个旧案例、616 条旧 P06 知识；
- C011–C015 finalizer 完成；
- C016–C020 尚未开始；
- knowledge-v003 已创建，重点优化 P03 高未分配问题；
- Dify 尚未启动；
- 当前测试基线约为 219 passed、2 skipped，必须重新实测；
- Git 远端在上次检查时与本地已同步，但开始前必须重新核对。

以下本地 Markdown 是用户和 Codex 正在讨论的新方案，不得删除、覆盖或擅自重写：

```text
docs/MiMo-V2.5-Pro-课程方法沉淀与忠实度审查Prompt.md
docs/当前系统事实审计-视频课程与Dify.md
docs/阿峰课程方法知识库-重构与后续执行方案.md
```

它们可能尚未提交 Git，但属于有效用户文件。

## 三、执行前现场审计

开始前执行并记录：

```powershell
git status --short
git log -10 --oneline
git rev-list --left-right --count origin/master...HEAD

Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -match 'VideoCaptioner|run-batch|wait_then_run_cursor'
} | Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine

docker ps -a
```

要求：

- 发现相同课程或相同 WaveId 任务正在运行时，只监控，不启动副本；
- 不使用 reset、checkout 或 clean 删除现有改动；
- 不触碰现有 cpa 容器；
- 不启动 Dify；
- 更新 `docs/cursor-handoff/STATUS.md`，写清本任务边界和当前阶段。

## 四、任务 A：完成 C001–C015 质量汇总

先生成或更新：

```text
docs/evaluation/knowledge-C001-C015.md
docs/evaluation/knowledge-C001-C015.json
```

逐课统计：

- raw segment 数；
- speaker 分布；
- unknown 比例；
- P03 案例数；
- unassigned 数和比例；
- P04 案例文件数；
- P01/P02/P03/P04 QA 状态；
- 视频各阶段耗时；
- OCR 调用次数；
- OCR cache hits；
- OCR 去重后图片数；
- 失败和重试次数。

这份报告只描述事实与证据层。旧 P05/P06 可以统计为历史信息，但不能作为本次完成标准。

特别标记：

- unassigned 比例大于 20%；
- unknown speaker 比例明显异常；
- P04 evidence 引用了案例范围外 segment；
- 案例边界过宽或过碎；
- OCR 占比异常；
- 缺少 QA 或版本字段。

## 五、任务 B：验证 knowledge-v003 的 P03 优化

### 固定回归集

至少使用：

- C003：旧 unassigned 40.4%；
- C008：旧 unassigned 26.0%；
- C006：OCR 信息多；
- C010：边界相对清晰的基线。

### 输入约束

- 优先复用已通过 QA 的 P01/P02；
- 如果 v003 输出版本要求 P01/P02 版本一致，可使用现有脚本生成新的 v003 文件，但不得覆盖 v002；
- v003 P03 输出写入独立路径；
- 使用独立 Cursor 上下文；
- 禁止使用 `--resume` 混用旧上下文。

Cursor Agent 非交互参数：

```text
-p --force --sandbox disabled --approve-mcps --trust --model auto
```

### 比较指标

为每课比较 v002 和 v003：

- case_count；
- assigned/unassigned 数量；
- unassigned ratio；
- 全量覆盖是否通过；
- 是否把广告、寒暄强行塞进案例；
- 是否把同一案例的讲解、OCR、学员补充错误切出；
- 边界 evidence 是否在范围内；
- 案例标题、起止和 completeness 是否合理。

输出：

```text
docs/evaluation/p03-v002-v003-regression.md
docs/evaluation/p03-v002-v003-regression.json
```

采用规则：

- v003 必须继续满足无遗漏、无重叠全量覆盖；
- 降低 unassigned 不能以强行并入广告/跑题内容为代价；
- C006/C010 不能明显退化；
- 发现 Prompt 问题时只能创建新版本或更新尚未冻结的 v003，并写 CHANGELOG；
- 修正后重新运行固定集。

## 六、任务 C：确定 C001–C015 的证据基线版本

根据任务 B 结果：

1. 如果 v003 明显改善且无退化，将 v003 作为后续 P03/P04 证据基线；
2. 对 C001–C015 运行必要的 v003 P03 回归；
3. 只有案例边界变化的课程/案例才重建 P04；
4. 边界未变化且旧 P04 QA 通过的案例可以复用；
5. 所有最终采用的 P04 必须通过 QA；
6. 输出一份映射表：

```text
data/catalog/evidence-baseline-C001-C015.json
```

建议结构：

```json
{
  "schema_version": "1.0",
  "courses": [{
    "course_id": "C001",
    "p01_version": "knowledge-v002",
    "p02_version": "knowledge-v002",
    "p03_version": "knowledge-v003",
    "cases": [{
      "case_id": "CASE-C001-001",
      "p04_version": "knowledge-v003",
      "source_case_changed": true,
      "qa_status": "pass"
    }]
  }]
}
```

不得用旧 P06 是否成功来判断证据层版本。

## 七、任务 D：处理 C016–C020 视频事实层

新建独立 Wave：

```text
C016-C020
```

逐课串行执行：

```text
media
→ transcript
→ diarization
→ alignment
→ board_detect
→ board_track
→ board_ocr
→ merge
→ export
→ raw QA
```

要求：

- 每课独立 Python 进程；
- 同一 job-id 断点恢复；
- 每课最多有限重试；
- 每课归档完成后立即 QA；
- 不等五课全部结束才检查失败；
- 不并行运行多个重型 OCR 课程；
- 记录每阶段耗时、OCR 次数、cache hits 和磁盘占用；
- 当前稳定批次仍可使用 complete-v1，除非任务 B/现有测试已经证明 adaptive profile 在完整度上不退化；
- 不要在本任务中顺便大改视觉算法。

运行号继续使用：

```text
RUN-20260715-001-V001
```

如果归档已存在则验证并跳过，禁止覆盖。

## 八、任务 E：完成 C016–C020 的 P01–P04

使用任务 C 确定的证据基线版本。

执行：

```text
P01
→ P01 QA
→ P02
→ P02 QA
→ P03
→ P03 QA
→ 每案例 P04
→ 每案例 P04 QA
```

重要：

- 只启动到 P04 的 watcher 或调度；
- 不启动 P05、P06 和 finalizer；
- 如现有 watcher 只能整链运行，应新增“ThroughStage=P04”或独立 evidence-wave 调度入口；
- 新调度必须可恢复、可配置 OutputVersion/PromptRoot/WaveId；
- 不复制粘贴一套写死 C016–C020 的临时脚本；
- 不覆盖 v002/v003 历史文件；
- speaker_N 必须保留；
- P03 案例与 unassigned 无遗漏、无重叠覆盖全课；
- P04 所有 evidence ID 必须在所属案例范围内。

完成标记：

```text
data/batches/BATCH-20260715-001/evidence-pipeline-C016-C020-complete.json
```

建议内容：

```json
{
  "schema_version": "1.0",
  "status": "complete",
  "wave_id": "C016-C020",
  "through_stage": "P04",
  "courses": ["C016", "C017", "C018", "C019", "C020"],
  "failed_courses": [],
  "failed_cases": [],
  "completed_at": ""
}
```

## 九、任务 F：生成前 20 课证据层报告

输出：

```text
docs/evaluation/evidence-C001-C020.md
docs/evaluation/evidence-C001-C020.json
data/catalog/evidence-baseline-C001-C020.json
```

报告必须证明：

- 20 课 raw QA 全部通过；
- P01/P02/P03 QA 全部通过；
- 每个案例 P04 QA 全部通过；
- 无缺失课程；
- 无缺失案例；
- 无案例外 evidence；
- P03 覆盖无遗漏、无重叠；
- 明确列出仍存在的 ASR/OCR/speaker/边界不确定项；
- 明确记录每课采用的版本。

完成后停止，不继续阿峰方法层、P05/P06 或 Dify。

## 十、测试与代码质量

必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

如果项目已配置 Ruff/类型检查，也要运行并记录真实结果。新增内容必须补充测试：

- evidence-wave 只运行到 P04；
- 断点恢复；
- 版本隔离；
- 完成标记；
- P03 v002/v003 指标比较；
- evidence baseline manifest；
- 不会意外启动 P05/P06。

不能因为已有测试通过就跳过真实产物检查。

## 十一、Git 和交付

保护以下用户文件，不得删除：

```text
docs/MiMo-V2.5-Pro-课程方法沉淀与忠实度审查Prompt.md
docs/当前系统事实审计-视频课程与Dify.md
docs/阿峰课程方法知识库-重构与后续执行方案.md
```

提交规则：

- data/jobs/video/model 不提交；
- 不提交 API Key、Token、真实 .env；
- 不提交课程截图和隐私数据；
- 每个稳定阶段单独 commit；
- push 失败时保留本地提交并记录，不反复改写历史；
- STATUS 更新必须提交。

## 十二、最终交付清单

只有以下全部完成，才可回复本任务完成：

1. C001–C015 质量报告；
2. P03 v002/v003 固定回归报告；
3. C001–C015 evidence baseline manifest；
4. C016–C020 视频、raw QA 全部完成；
5. C016–C020 P01–P04 和全部 QA 完成；
6. evidence-pipeline-C016-C020-complete.json；
7. C001–C020 证据层报告和 baseline manifest；
8. evidence-wave 可配置调度代码和测试；
9. 全量测试通过；
10. Git 提交和 push 状态明确；
11. 没有启动或修改阿峰方法层；
12. 没有启动 P05/P06/Dify。

现在开始执行现场审计和任务 A。持续更新 STATUS，不要等待用户确认。


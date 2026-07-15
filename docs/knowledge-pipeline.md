# 课程知识库流水线

本流水线把视频、课板 OCR 和 PDF 转成可追溯的知识条目。最终消费层是
`data/courses/<course-id>/05_tidy/`，但原始 TXT 与结构化中间结果继续保留，避免 Prompt
升级后无法回归。帧图片、OCR 调试图和模型缓存属于可删除产物。

## 数据层级

```text
data/
├─ catalog/                  # 来源与课程总表
├─ courses/C001/
│  ├─ source.json            # 原始文件名、路径、大小、哈希
│  ├─ 01_raw/                # 不可变转写和分析输出
│  ├─ 02_normalized/         # P01/P02：文本修复和来源分类
│  ├─ 03_cases/              # P03：案例边界
│  ├─ 04_knowledge/          # P04/P05：提取与审查
│  ├─ 05_tidy/               # P06：最终原子知识条目
│  ├─ qa/                    # 完整度、证据、安全和格式报告
│  └─ runs/                  # 每次执行的版本与状态
└─ batches/BATCH-*/          # 批次清单、逐课状态和失败记录
```

`data/` 默认不提交 Git；代码、schema 和 Prompt 必须提交。任何阶段都写新版本，不覆盖历史结果。

## 初始化

```powershell
course-knowledge init "E:\课程目录" --data-root data --batch-id BATCH-20260715-001
```

扫描器不会填补缺失编号。未编号视频使用 `VIDEO001`，PDF 使用 `PDF001`。为节省时间，仅对
同尺寸的疑似重复视频计算 SHA256。

## 单课隔离执行

```powershell
course-video-analyze "E:\课程\[2]--第二课.mp4" `
  --job-id C002-RUN-20260715-V001 `
  --processing-profile complete-v1 `
  --archive-course C002 `
  --run-id RUN-20260715-V001
```

命令一次只运行一课。任务失败时保留 `jobs/batch/<job-id>/job.json`，再次执行同一命令会从
已完成阶段恢复；成功后才归档轻量最终结果。归档目录已存在时命令拒绝覆盖。

小批次串行运行：

```powershell
course-knowledge run-batch BATCH-20260715-001 `
  --start 3 --end 5 --run-version V001 `
  --ffmpeg-bin "C:\ffmpeg\bin"
```

调度器为每课启动独立 Python 进程，默认单课超时 4 小时、最多尝试 2 次。失败写入
`failures.jsonl` 后继续下一课，重复执行会跳过已成功归档的课程。

## Cursor 独立清洗

```powershell
course-knowledge cursor-stage C001 P01 `
  data/courses/C001/01_raw/RUN-20260715-BASELINE/transcript.txt `
  data/courses/C001/02_normalized/P01-knowledge-v001.json
```

每次命令都会创建全新的 Cursor Agent 上下文，不使用 `--resume`。调用固定使用
`--force --sandbox disabled --approve-mcps --trust --print`，避免批处理中途等待授权；默认模型为
`auto`。当前账户的显式高级模型额度已用完，硬编码 `composer-2.5`、Kimi、GLM 等模型会立即
失败；`auto` 已验证仍可运行。超时后程序会终止完整 Cursor 进程树，避免残留阻塞任务。

## Prompt 阶段

当前 Prompt 位于 `prompts/knowledge-v002/`；P02 紧凑复核规则位于
`prompts/knowledge-v002-compact/`。每个 Cursor 命令只处理一课或一个案例的一个阶段，并使用全新
上下文。阶段输出为严格 JSON；Markdown 只用于展示。所有输出必须记录 `schema_version`、
`prompt_version`、`source_ids` 和可定位的 `evidence_spans`。

P01 不再把身份未知的 `Speaker 0`/`Speaker 1` 统一降级为 `unknown`，而是保留为
`speaker_0`/`speaker_1`。P02 先生成全量确定性基线，再把均匀声纹样本和明确候选压缩为小型
Cursor 复核包；Cursor 只返回角色、引用和不确定项决策，程序将决策应用到全量数据并执行逐段 QA。

P03 必须让案例区间与 `unassigned_segment_ids` 无重叠地覆盖全部输入 segments。P04 以后按案例
隔离执行：P04 的每条结论必须引用案例范围内的 segment ID，P05 逐条审查证据与安全边界，P06
只把通过审查的内容转换为原子 JSON 和 Tidy 兼容 Markdown。

## 迭代与验收

先精审 C001-C005。每次 Prompt 升级都重跑固定回归集，再加入 C006-C010、C011-C015、
C016-C020。评价完整度、证据可追溯率、说话人和案例边界、模型新增内容、安全标签召回率及
最终检索命中率，不能以文本更短或重复更少代替完整度。

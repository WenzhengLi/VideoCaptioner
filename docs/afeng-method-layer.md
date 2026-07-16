# 阿峰方法层 v001

## 定位

阿峰是课程方法复现角色。Dify 是后续的知识库存储、检索和应用编排平台，不是角色名称。

阿峰方法生产固定为：

```text
P04 案例证据 + P05 证据审查字段
→ 课程方法提炼
→ 课程忠实度审查
→ 发布分类
→ 程序确定性渲染 Markdown
```

本链路不进行安全审查，也不使用旧 P06 作为输入。旧 P05 只读取：

- `evidence_reviews`
- `missing_context`
- `required_corrections`

`safety_flags` 和 `unsafe_recommendation_candidates` 不会进入阿峰证据包。

## 当前实现

代码：

- `src/course_video_analyzer/knowledge/afeng_models.py`：版本化数据契约；
- `src/course_video_analyzer/knowledge/afeng.py`：证据包、哈希、脱敏、QA、发布闸门和 Markdown；
- `src/course_video_analyzer/knowledge/afeng_pipeline.py`：最多两轮修订的可恢复状态机；
- `src/course_video_analyzer/knowledge/afeng_experiment.py`：baseline 消费和三课试验准备；
- `src/course_video_analyzer/knowledge/afeng_executor.py`：通用 OpenAI-compatible 结构化模型 adapter；
- `prompts/afeng-method-v001/`：提炼、审查、修订和发布分类 Prompt；
- `schemas/afeng-method-v001/`：可交给模型/API 调用层使用的 JSON Schema；
- `tests/test_knowledge/test_afeng.py`：闸门、脱敏、缓存和渲染测试。

流水线版本：

```text
pipeline_version: afeng-method-v001
prompt_version: mimo-method-v002
```

正式模型调用默认链路：

```text
CC Switch 当前 Claude 配置
→ Claude Code CLI headless
→ Xiaomi MiMo / mimo-v2.5-pro
```

程序不会启动或自动化 CC Switch GUI。CC Switch 负责写入 Claude 用户配置，执行器读取非敏感
供应商信息后，以 stdin 发送 Prompt，使用 `dontAsk`、禁用工具、无会话持久化和 JSON Schema
约束启动独立 Claude Code 进程。项目直接 HTTP adapter 仅作为备用。

## 数据目录

每课使用独立目录：

```text
data/courses/C001/06_afeng_methods/
├─ evidence-package-v001/
├─ method-draft-v001/
├─ fidelity-audit-v001/
├─ approved-v001/
├─ publication-v001/
├─ markdown-v001/
└─ runs/
```

模型产物文件名绑定输入哈希、Prompt 和模型，旧文件不覆盖。相同输入、Prompt 和模型的已完成
任务直接复用；输入证据或模型变化时创建新运行。

## 程序硬闸门

程序会确定性执行：

1. evidence ID 必须是当前案例真实 segment ID；
2. 证据包输入哈希必须与内容一致；
3. 核心观点、课程理解、核心逻辑、条件、步骤、信号、示例表达、限制和非空结果必须有证据；
4. 方法时间范围必须由实际引用的 evidence 自动推导；
5. 忠实度审查不是 `pass` 时不能批准；
6. `release_allowed` 只能在 `pass` 时为 true；
7. 通过审查时不能仍有 unsupported、misattributed、missing condition 或 external knowledge；
8. 未批准方法不能进入发布分类和 Markdown；
9. `reject` 或 `publishable=false` 不生成 Markdown；
10. 外部模型载荷必须先脱敏；
11. Markdown 由程序渲染，模型不能在最后一步增加内容。

忠实度审查只检查是否忠实于课程，不评价课程是否正确、科学或安全。

## CLI

导出 Schema：

```powershell
course-knowledge afeng-export-schemas schemas/afeng-method-v001
```

从一份 P04 案例构建证据包：

```powershell
course-knowledge afeng-build-evidence C003 CASE-C003-001 `
  data/courses/C003/04_knowledge/P04-input-knowledge-v003/CASE-C003-001.json `
  data/courses/C003/04_knowledge/P04-knowledge-v003/CASE-C003-001.json `
  data/courses/C003/06_afeng_methods/evidence-package-v001/CASE-C003-001.json `
  --p05 data/courses/C003/04_knowledge/P05-knowledge-v002/CASE-C003-001.json `
  --source data/courses/C003/source.json `
  --source-pipeline-version knowledge-v003
```

按指定 P04/P05 版本为一整课构建证据包：

```powershell
course-knowledge afeng-build-course-evidence C003 `
  --p04-version knowledge-v003 `
  --p05-version knowledge-v002 `
  --output-version v001
```

命令可重复执行：内容和输入哈希完全一致时直接复用；同一路径已有不同内容时拒绝覆盖。

检查证据包并生成脱敏外发载荷：

```powershell
course-knowledge afeng-qa-evidence evidence.json evidence-qa.json
course-knowledge afeng-build-external-payload evidence.json external-payload.json
```

本地始终保留完整证据包。默认外发载荷使用 `evidence_focused/context=1`：保留全部 P04/P05
引用证据及相邻 segment，并记录 selection hash、原始/选中数量和必需 evidence 覆盖率。

准备三课无模型试验：

```powershell
python scripts/prepare_afeng_pilot.py `
  --baseline data/catalog/evidence-baseline-C001-C020.json `
  --courses C003,C006,C010 `
  --pilot-id C003-C006-C010-baseline-v001 `
  --external-context-window 1
```

正式 baseline 尚未生成时，可省略 `--baseline`，使用旧 v002 做临时冒烟验证。该结果不能冒充
正式阿峰方法产物。

默认通过 CC Switch/Claude Code 执行：

```powershell
python scripts/run_afeng_pilot_model.py `
  data/afeng/pilots/C003-C006-C010-baseline-v001/manifest.json `
  --executor cc-switch
```

HTTP 备用方式才需要从环境变量读取 API Key；密钥不写入日志、产物或文档。

官方 MiMo 参数已经核对：

- endpoint：`https://api.xiaomimimo.com/v1/chat/completions`；
- model：`mimo-v2.5-pro`；
- `response_format`：使用 `json_object`；
- context：1M tokens；最大输出 128K；
- 国内按量价格：输入未命中 ¥3/M、输出 ¥6/M。

程序仍会在响应后执行 Pydantic Schema 校验和有限重试。若接入其他兼容服务，可显式传入
`--endpoint`、`--model` 和 `--response-format`。

官方资料：

- [First API Call](https://platform.xiaomimimo.com/static/docs/quick-start/first-api-call.md)
- [Model and Rate Limits](https://platform.xiaomimimo.com/static/docs/quick-start/model.md)
- [OpenAI API Compatibility](https://platform.xiaomimimo.com/static/docs/api/chat/openai-api.md)
- [API Pricing](https://platform.xiaomimimo.com/static/docs/price/pay-as-you-go.md)

模型输出后的确定性 QA 和发布：

```powershell
course-knowledge afeng-qa-draft evidence.json method-draft.json method-draft-qa.json
course-knowledge afeng-qa-audit evidence.json method-draft.json audit.json audit-qa.json
course-knowledge afeng-approve method-draft.json audit.json approved.json
course-knowledge afeng-render evidence.json approved.json audit.json publication.json method.md
```

## 三课真实试验结论

正式 baseline：`data/catalog/evidence-baseline-C001-C015.json`，策略
`adopt_v003_hybrid`。三课证据包共 6 个案例，必需 evidence 覆盖率 100%。

MiMo/Claude Code 真实试验：

| 课程 | 案例数 | 已发布 | 人工复核 | 结论 |
| --- | ---: | ---: | ---: | --- |
| C003 | 3 | 3 | 0 | 全部首轮通过，均为 `case_derived_method` |
| C006 | 2 | 1 | 1 | OCR 密集案例可发布；复杂亲密推进案例保留人工复核 |
| C010 | 1 | 1 | 0 | v002 一轮修订后以 95 分通过 |

合计 6 个案例：5 个发布，1 个人工复核，0 个程序失败。运行报告位于：

- `data/afeng/model-runs/C003-C006-C010-baseline-v001/c003-v002/run-report.md`；
- `data/afeng/model-runs/C003-C006-C010-baseline-v001/c006-v002/run-report.md`；
- `data/afeng/model-runs/C003-C006-C010-baseline-v001/c010-v002/run-report.md`。

试验中已修正：时间范围由程序推导、无证据条件占位符归档、审查轮次归一化、非法
`invalid_evidence_ids` 说明文字过滤、空通过审查的确定性审计记录、部分补跑汇总合并，以及恢复时
保留历史事件。

旧 v002 三课外发规模对比见
`docs/evaluation/afeng-prebaseline-payload-comparison.md`。该报告证明 focused Profile 在保持必需
evidence 100% 覆盖的同时，可明显降低外发上下文。

下一扩展门槛是 Cursor 完成并冻结 C001–C020 P04 evidence baseline。冻结前不批量覆盖三课之外
的正式方法产物；已完成的三课试验作为 `mimo-method-v002` 固定回归集。

## Dify 发布边界

阿峰方法不能直接对整个运行目录执行通配上传。先生成离线发布包：

```powershell
python scripts/build_afeng_dify_bundle.py `
  data/afeng/model-runs/C003-C006-C010-baseline-v001/c003-v002/model-run-summary.json `
  data/afeng/model-runs/C003-C006-C010-baseline-v001/c006-v002/model-run-summary.json `
  data/afeng/model-runs/C003-C006-C010-baseline-v001/c010-v002/model-run-summary.json `
  --output-dir data/dify/afeng-release-v002.1/documents `
  --manifest data/dify/afeng-release-v002.1/manifest.json
```

构建器只收集：

- run `status=published`；
- approved method `draft_fidelity_status=reviewed`；
- fidelity audit `pass` 且 `release_allowed=true`；
- publication `publishable=true` 且分类不是 `reject`；
- 身份字段完全一致的 Markdown。

当前三课离线包包含 5 个文档，自动排除 C006/CASE-C006-001 人工复核案例。该步骤不代表 Dify
已经部署或入库；真实同步仍需 Dataset、索引状态轮询和检索验收。

通用 Dify Markdown 同步已使用内容 SHA-256 做幂等判断：首次创建、内容相同跳过、内容变化调用
`update-by-text`。本地 document map 保存 knowledge ID、Dify document ID、内容哈希和 metadata。
阿峰 metadata 从 frontmatter 读取 fidelity、发布分类、泛化等级、课程/案例和源时间范围。

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
prompt_version: mimo-method-v001
```

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

真实模型运行使用以下环境变量：

```text
AFENG_LLM_ENDPOINT=https://.../v1/chat/completions
AFENG_LLM_MODEL=...
AFENG_LLM_API_KEY=...
```

然后执行：

```powershell
python scripts/run_afeng_pilot_model.py `
  data/afeng/pilots/C003-C006-C010-baseline-v001/manifest.json
```

如果服务不支持 `json_schema`，显式传 `--without-json-schema`，程序仍会执行 JSON 解析、Pydantic
校验和有限重试。未经真实 API 验证前，不声称该通用 adapter 已完成 MiMo 联调。

模型输出后的确定性 QA 和发布：

```powershell
course-knowledge afeng-qa-draft evidence.json method-draft.json method-draft-qa.json
course-knowledge afeng-qa-audit evidence.json method-draft.json audit.json audit-qa.json
course-knowledge afeng-approve method-draft.json audit.json approved.json
course-knowledge afeng-render evidence.json approved.json audit.json publication.json method.md
```

## 尚未执行的部分

MiMo-V2.5-Pro 的真实 API 地址、认证方式、结构化输出参数、上下文限制和计费信息目前未知，
因此 v001 已建立 `AfengStageExecutor` 适配边界和通用 OpenAI-compatible adapter，但没有猜测或
宣称 MiMo 一定兼容。取得真实 API 文档和凭据后，先验证通用 adapter；不兼容时新增专用执行器，
不改变证据、审查、发布和 Markdown 契约。

旧 v002 三课外发规模对比见
`docs/evaluation/afeng-prebaseline-payload-comparison.md`。该报告证明 focused Profile 在保持必需
evidence 100% 覆盖的同时，可明显降低外发上下文。

在 Cursor 完成并冻结前 20 课 P04 evidence baseline 前，不批量生成正式阿峰方法，避免消费仍在
变化的案例边界。可先用固定的 C003、C006、C010 做 dry-run。

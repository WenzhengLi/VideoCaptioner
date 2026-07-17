# Dify 状态报告

生成时间：2026-07-17（管理员初始化 + Dataset「阿峰课程方法库-研究版」+ 前20课最终包同步后）

> 本地 SQLite / `index-tidy` **不是** Dify。下表严格区分各层完成度。

## 总览

| 项 | 状态 |
|---|---|
| Docker 部署 | **已完成**（project=`dify`，HTTP 3080，cpa 8317 未改动） |
| 管理员初始化 | **已完成**（`GET/POST /console/api/setup` + 登录校验；凭据仅在 secrets） |
| Dataset | **已完成**（名称=`阿峰课程方法库-研究版`，`economy`；无 embedding 故未用 `high_quality`） |
| API Key | **已完成**（Dataset API Key 已写入 runtime secrets；值不入库） |
| 文档同步 | **已完成**：`afeng-release-v002.5` 36 篇 create；幂等 map 已更新 |
| indexing | **已完成**：Service API 抽样/全量均为 `completed`（36/36） |
| Workflow / Chatflow | **DSL 已准备**（`deploy/dify/workflows/afeng-chatflow.yml`）；**未在控制台创建可回答应用**（缺 LLM 供应商） |
| 真实检索 | **部分完成**：`keyword_search` 有命中；semantic/`high_quality` 需 embedding 供应商 |
| 模型供应商 | **未配置**（外部阻塞） |

## Docker 部署状态

- **版本**：官方 Git tag `1.15.0`
- **部署目录**：`D:\Dev\dify-deploy`
- **Compose project**：`dify`
- **访问 URL**：http://127.0.0.1:3080
- **cpa**：仍在 `8317`，未停止/删除/修改
- **公开状态**：`D:\Dev\dify-deploy\bootstrap-status.json`（无密码/Token）

运维：

```powershell
.\deploy\dify\scripts\up.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\health.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\initialize-admin.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\initialize-dataset.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\smoke-test.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\down.ps1 -DeployRoot D:\Dev\dify-deploy
```

## 管理员初始化状态

- **已完成且登录校验通过**。
- 凭据仅保存：`D:\Dev\dify-deploy\secrets\admin.env`（ACL 限制当前用户）。
- 禁止把邮箱/密码输出到终端、日志、聊天或 Git。

## Dataset 状态

- **已创建**：`阿峰课程方法库-研究版`
- **模式**：`economy`（无默认 text-embedding）
- 运行时变量仅在：`D:\Dev\dify-deploy\secrets\dify-runtime.env`
  - `DIFY_BASE_URL`
  - `DIFY_API_KEY`
  - `DIFY_DATASET_ID`
- 升 `high_quality` 前需在控制台配置 embedding（勿编造密钥）。

## 文档同步状态

最终包闸门（已满足，故允许导入 `v002.5`，未使用 v002.1–v002.4 冒充）：

- 报告：`docs/evaluation/afeng-twenty-course-v002.json`
- `case_count=40`，`failure_count=0`，`status=complete`
- course/case 唯一；发布包排除 `manual_review`/`rejected`（36 文档 / 4 排除）
- `pipeline_version=afeng-method-v001`，`prompt_version=mimo-method-v002`
- manifest 文档数与 `documents/*.md` 一致

同步结果：

```text
create=36, update=0, skip=0, failed=0
indexing completed=36
map: data/dify/document-map.json（运行时，勿提交密钥）
mapped=36（已清除历史 KNOW-SMOKE-001 污染条目；远端无 SMOKE）
```

再次同步命令（加载 runtime env 后）：

```powershell
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.5/documents `
  --map-path data/dify/document-map.json `
  --poll-indexing
```

## indexing 状态

- 阿峰最终包 36 文档：**completed**

## Workflow / Chatflow 状态

- DSL 模板已写入仓库：`deploy/dify/workflows/afeng-chatflow.yml`
- 流程：用户问题 → 知识检索 → 课程证据整理 → 多方案生成 → 引用检查 → 输出
- **未**在 Dify 控制台导入为可回答应用（缺 LLM 供应商密钥；不编造）

## 真实检索验收状态

- `GET /v1/datasets/{id}/documents`：36 文档可见
- `POST /v1/datasets/{id}/retrieve` + `keyword_search`：**有命中**（探针 hits>0）
- semantic / embedding 检索：未完成（缺 embedding 供应商）
- Chatflow 20 问端到端：未开始（缺 LLM）

## 当前唯一外部阻塞

1. 在 Dify 控制台配置 **embedding**（及后续 LLM）供应商密钥后，可将 Dataset 升为 `high_quality`，并导入/启用「阿峰」Chatflow 做完整问答验收。
2. 除此之外，本地管理员、Dataset、API、前20课文档同步与 keyword 检索均已完成。

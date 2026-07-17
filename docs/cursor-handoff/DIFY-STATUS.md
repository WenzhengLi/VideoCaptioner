# Dify 状态报告

生成时间：2026-07-17（管理员初始化 + Dataset + 冒烟同步后）

> 本地 SQLite / `index-tidy` **不是** Dify。下表严格区分各层完成度。

## 总览

| 项 | 状态 |
|---|---|
| Docker 部署 | **已完成** |
| 管理员初始化 | **已完成**（API `POST /console/api/setup`，非阻塞） |
| Dataset | **已完成**（`economy` 模式；因尚未配置 embedding，未用 `high_quality`） |
| 文档同步 | **部分完成**：冒烟文档 `KNOW-SMOKE-001` 已入库且幂等 skip 验证通过；**最终阿峰包未导入** |
| indexing | **冒烟文档 completed**；阿峰最终包未开始 |
| Workflow / Chatflow | **未完成**（需 LLM 供应商密钥，禁止编造） |
| 真实检索验收 | **部分**：Service API `retrieve` 可达；keyword/full_text 对冒烟短文 0 hits；semantic 因缺 embedding 返回 400 |

## Docker 部署状态

- **版本**：官方 Git tag `1.15.0`（`langgenius/dify` @ `3aa26fb`）
- **部署目录**：`D:\Dev\dify-deploy`
- **Compose project**：`dify`
- **访问 URL**：http://127.0.0.1:3080
- **数据**：`D:\Dev\dify-deploy\repo\docker\volumes\`
- **cpa**：仍在 `8317`，未改动
- **本地密钥文件**（勿提交）：`D:\Dev\dify-deploy\local-credentials.env`
- **公开引导状态**：`D:\Dev\dify-deploy\bootstrap-status.json`

运维：

```powershell
.\deploy\dify\scripts\up.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\health.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\down.ps1 -DeployRoot D:\Dev\dify-deploy
# 管理员/API Key/Dataset 引导（密钥只写入 dify-deploy，不进 Git）
.\.venv\Scripts\python.exe D:\Dev\dify-deploy\scripts\recover_and_finish_bootstrap.py
```

## 管理员初始化状态

- **已完成**。管理员邮箱见 `bootstrap-status.json` / `local-credentials.env`（密码不入库、不打印）。
- 控制台可登录；Dataset API Key 已创建。

## Dataset 状态

- **已创建**：`VideoCaptioner Courses`
- **模式**：`economy`（无默认 text-embedding 时的安全选择）
- `DIFY_DATASET_ID` 已写入本机 `local-credentials.env`
- 升级到 `high_quality` 前需在控制台配置 embedding 供应商（勿编造密钥）

## 文档同步状态

同步代码能力：knowledge_id ↔ document_id、SHA-256 幂等 create/skip/update、indexing 轮询、重试、`--dry-run`、密钥仅环境变量。

已验证（冒烟，**非**阿峰包）：

```text
data/dify/smoke-documents  -> create=1, indexing=completed, 二次 sync skip=1
data/dify/document-map.json 已生成（/data 已 gitignore）
```

最终阿峰包到位后：

```powershell
# 从 D:\Dev\dify-deploy\local-credentials.env 加载 DIFY_* 后：
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.N/documents `
  --map-path data/dify/document-map.json `
  --poll-indexing
```

## indexing 状态

- 冒烟文档：`completed`
- 阿峰最终包：未导入

## Workflow / Chatflow 状态

未创建。缺少 LLM 供应商配置；不编造 API Key。

## 真实检索验收状态

- `GET /v1/datasets/{id}/documents`：可见冒烟文档
- `POST /v1/datasets/{id}/retrieve`：接口可用；keyword/full_text 对短冒烟文暂 0 hits；semantic 需 embedding
- 正式 20 问 Chatflow/Workflow 验收：未开始

## 阻塞项（非人工 /install）

1. 在 Dify 控制台配置 **embedding**（及后续 LLM）供应商密钥后，可将 Dataset 升为 `high_quality` 并做语义检索。
2. CC Switch 交付最终 `afeng-release-v002.N` 后再导入（禁止用旧包冒充）。
3. 创建 Workflow/Chatflow 并跑 20 问验收。

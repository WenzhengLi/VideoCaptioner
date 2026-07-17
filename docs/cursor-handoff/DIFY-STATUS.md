# Dify 状态报告

生成时间：2026-07-17（本机部署验证后）

> 本地 SQLite / `index-tidy` **不是** Dify。下表严格区分各层完成度。

## 总览

| 项 | 状态 |
|---|---|
| Docker 部署 | **已完成** |
| 管理员初始化（`/install`） | **未完成**（需人工） |
| Dataset | **未完成** |
| 文档同步 | **未完成**（最终阿峰包未到位；禁止导入旧包） |
| indexing | **未完成** |
| Workflow / Chatflow | **未完成** |
| 真实检索验收 | **未完成** |

## Docker 部署状态

- **版本**：官方 Git tag `1.15.0`（`langgenius/dify` @ `3aa26fb`）
- **部署目录**：`D:\Dev\dify-deploy`（仓库克隆在 `repo\`，运行数据不进 VideoCaptioner Git）
- **Compose project**：`dify`（`docker compose -p dify`）
- **访问 URL**：http://127.0.0.1:3080 （HTTPS 映射 3443）
- **安装页**：http://127.0.0.1:3080/install
- **数据持久化**：官方 bind mount `D:\Dev\dify-deploy\repo\docker\volumes\`（postgres / redis / weaviate / app storage 等）
- **健康**：`dify-api-1` / `db_postgres` / `redis` / `sandbox` healthy；`health.ps1` 通过；HTTP 探针 200
- **cpa**：仍在运行（`8317`），down/up 周期未误伤
- **脚本**：`deploy/dify/scripts/{bootstrap,up,down,health,backup}.ps1` 已按 project 名隔离

运维入口：

```powershell
.\deploy\dify\scripts\up.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\health.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\down.ps1 -DeployRoot D:\Dev\dify-deploy
```

## 管理员初始化状态

- 控制台 `/install` 可访问，**尚未创建管理员账户**。
- 未配置 Dify API Key；未编造 LLM / embedding 密钥。

**唯一剩余人工步骤**：打开 http://127.0.0.1:3080/install 完成管理员注册，并在控制台配置模型供应商与 Dataset API Key。

## Dataset 状态

未创建。需管理员与 API Key 后执行：

```powershell
$env:DIFY_BASE_URL = "http://127.0.0.1:3080/v1"
$env:DIFY_API_KEY = "<local-only>"
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-create-dataset
```

## 文档同步状态

- 同步代码已就绪：knowledge_id ↔ document_id 映射、SHA-256 幂等 create/skip/update、indexing 轮询、瞬时失败重试、API Key 仅环境变量、`--dry-run` 无密钥计划。
- **未**导入任何阿峰文档（等待最终 `afeng-release-v002.N` 包）。

最终包到位后的同步命令模板：

```powershell
$env:DIFY_BASE_URL = "http://127.0.0.1:3080/v1"
$env:DIFY_API_KEY = "<local-only>"
$env:DIFY_DATASET_ID = "<from create-dataset>"
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.N/documents `
  --map-path data/dify/document-map.json `
  --poll-indexing
```

无密钥 dry-run：

```powershell
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.N/documents `
  --map-path data/dify/document-map.json `
  --dry-run
```

## indexing 状态

无文档入库，indexing 未开始。

## Workflow / Chatflow 状态

未创建。

## 真实检索验收状态

未执行（依赖 Dataset、文档 indexing、模型配置与 Chatflow/Workflow）。

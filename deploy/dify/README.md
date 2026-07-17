# Dify 官方 Compose 部署（VideoCaptioner）

目标产品是 **Dify**，不是本地 SQLite（`data/tidy/knowledge.db` 仅作离线回归）。

## 原则

1. 只使用 [langgenius/dify](https://github.com/langgenius/dify) 官方 `docker/` Compose，固定 Git tag。
2. 不使用来源不明的一键镜像。
3. 真实 `.env`、密钥、数据卷不提交；仓库只保留 `.env.example` 与脚本。
4. 现有 `cpa` 容器不得删除或改动。
5. 管理员/API Key 只写入 `D:\Dev\dify-deploy\secrets\`，禁止打印到终端或 Git。

## 固定版本

```text
DIFY_GIT_TAG=1.15.0
```

## 目录布局

```text
D:\Dev\dify-deploy\
  repo\                 # git clone --branch <tag> --depth 1
  secrets\              # admin.env / dify-runtime.env（本机 ACL，勿提交）
  bootstrap-status.json # 公开状态（无密码）

deploy/dify/
  README.md
  .env.example
  workflows\afeng-chatflow.yml
  scripts\
    bootstrap.ps1
    up.ps1 / down.ps1 / health.ps1 / backup.ps1
    initialize-admin.ps1
    initialize-dataset.ps1
    smoke-test.ps1
    dify_init_lib.py
```

## 启动与初始化

```powershell
.\deploy\dify\scripts\bootstrap.ps1 -DeployRoot D:\Dev\dify-deploy -GitTag 1.15.0
.\deploy\dify\scripts\up.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\health.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\initialize-admin.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\initialize-dataset.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\smoke-test.ps1 -DeployRoot D:\Dev\dify-deploy
```

`down.ps1` 仅停止 compose project `dify`，不带 `-v`，不影响 `cpa`。

## 与本仓库的同步

密钥从 `D:\Dev\dify-deploy\secrets\dify-runtime.env` 加载到进程环境后：

```powershell
# 最终前20课包（闸门通过的 v002.5；禁止用 v002.1–v002.4 冒充）
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.5/documents `
  --map-path data/dify/document-map.json `
  --poll-indexing

# 无密钥 dry-run
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.5/documents `
  --map-path data/dify/document-map.json `
  --dry-run
```

- Dataset 默认名：`阿峰课程方法库-研究版`（无 embedding 时使用 `economy`）。
- Chatflow DSL：`deploy/dify/workflows/afeng-chatflow.yml`（未配置 LLM 前不声称可回答）。
- 状态报告：`docs/cursor-handoff/DIFY-STATUS.md`。

## 验收清单

- [x] `docker compose -p dify ps` healthy，且 `cpa` 仍在 8317
- [x] 管理员初始化 + Dataset API Key + Dataset 已创建
- [x] 最终包 Markdown 已导入且 indexing completed
- [x] keyword 检索探针有命中
- [ ] embedding/LLM 供应商配置后：`high_quality` + Chatflow 端到端 20 问

# Dify 官方 Compose 部署（VideoCaptioner）

目标产品是 **Dify**，不是本地 SQLite（`data/tidy/knowledge.db` 仅作离线回归）。

## 原则

1. 只使用 [langgenius/dify](https://github.com/langgenius/dify) 官方 `docker/` Compose，固定 Git tag。
2. 不使用来源不明的一键镜像。
3. 真实 `.env`、密钥、数据卷不提交；仓库只保留 `.env.example` 与脚本。
4. 现有 `cpa` 容器不得删除或改动。
5. 视频 OCR / `run-batch` 高负载时不要 `compose up`；先完成脚本与适配代码，再在资源窗口启动。

## 固定版本

默认钉选稳定版（部署前用脚本再次核对最新非 prerelease）：

```text
DIFY_GIT_TAG=1.15.0
```

若该 tag 不存在，以 `git ls-remote --tags https://github.com/langgenius/dify.git` 的最新非 RC 为准，并回写本文件与 `.env.example`。

## 目录布局

推荐工作区外持久根（避免误删仓库）：

```text
D:\Dev\dify-deploy\
  repo\                 # git clone --branch <tag> --depth 1
  data\                 # 可选：额外备份根
```

仓库内仅保留运维入口：

```text
deploy/dify/
  README.md             # 本文件
  .env.example          # 变量模板（无密钥）
  scripts\
    bootstrap.ps1       # clone 固定 tag + 复制 env
    up.ps1 / down.ps1
    health.ps1
    backup.ps1
```

## 启动步骤（人工/脚本）

```powershell
# 1) 引导（不提交密钥）
.\deploy\dify\scripts\bootstrap.ps1 -DeployRoot D:\Dev\dify-deploy -GitTag 1.15.0

# 2) 编辑 D:\Dev\dify-deploy\repo\docker\.env
#    - EXPOSE_NGINX_PORT 避开 80 冲突时可改为 3080
#    - 配置模型供应商密钥（勿写入 git）

# 3) 仅在资源窗口启动
.\deploy\dify\scripts\up.ps1 -DeployRoot D:\Dev\dify-deploy

# 4) 健康检查
.\deploy\dify\scripts\health.ps1 -DeployRoot D:\Dev\dify-deploy

# 5) 浏览器初始化
#    http://localhost:<port>/install
```

## 停止与备份

```powershell
.\deploy\dify\scripts\down.ps1 -DeployRoot D:\Dev\dify-deploy
.\deploy\dify\scripts\backup.ps1 -DeployRoot D:\Dev\dify-deploy -BackupRoot D:\Dev\dify-deploy\backups
```

## 与本仓库的同步（后续代码）

- CLI 将新增 `dify-*` 子命令：创建 Dataset、导入通过 P06 QA 的 Markdown、维护 knowledge_id ↔ document_id 映射。
- 映射文件建议：`data/dify/document-map.json`（运行数据，不提交）。
- 本地 `index-tidy` 可逐步改名为 `local-index-*`，保留别名；**不能**把 SQLite 成功当作 Dify 交付。

## 验收清单

- [ ] `docker compose ps` 中 Dify 服务 healthy，且 `cpa` 仍在
- [ ] Dataset 已创建并记录 dataset_id
- [ ] P06 Markdown 已导入且 indexing 完成
- [ ] 映射表完整；20 问 Chatflow/Workflow 经 **Dify API** 通过

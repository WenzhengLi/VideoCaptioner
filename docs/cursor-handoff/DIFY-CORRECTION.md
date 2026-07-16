# 重要纠错：目标产品是 Dify，不是 Tidy

用户已明确：最终知识库平台是 **Dify**。此前仓库把本地 Markdown/SQLite 误命名为 Tidy，这是错误的
产品理解。执行后续任务时必须遵守：

1. `data/tidy/knowledge.db`、`index-tidy`、`search-tidy` 只是历史名称的本地暂存和回归检索工具。
2. SQLite 中存在数据不代表 Dify 已安装或入库；任何报告不得再这样表述。
3. 当前机器已安装 Docker，但截至 2026-07-16 检查时没有 Dify 容器。
4. 正确交付包括：官方 Dify Docker Compose、健康运行的容器、Dataset、embedding/LLM 配置、文档 API
   幂等导入、索引状态轮询、本地 knowledge ID 与 Dify document ID 映射、真实 Dify 检索、Workflow/聊天
   应用和至少 20 个问题的问答验收。
5. 密钥只放 `.env`，不得提交。没有可用模型密钥时，仍先完成 Dify 部署、同步程序和配置模板，并明确
   标记唯一剩余的外部凭据步骤，不能退回用 SQLite 冒充完成。
6. 为避免打断正在执行的 C011-C015，历史 CLI 名称可以暂时保留；后续应增加 `dify-*` 命令并把本地
   索引重命名为 `local-index-*`，提供兼容别名和迁移说明。


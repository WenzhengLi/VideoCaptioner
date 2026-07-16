# Cursor 独立任务：安装并接入 Dify，完成知识库存储、检索和多方案回答

仓库 `D:\Dev\VideoCaptioner`。用户明确要求的是 **Dify**。当前已有 Markdown、SQLite FTS、中文
n-gram+IDF 回退和 `answer-tidy`，但这些是历史误命名的本地暂存/回归工具，不等于 Dify。不得再把
SQLite 建库描述成 Dify 入库。

使用 Dify 官方 Docker Compose 安装固定版本 Dify，记录端口、容器、数据卷、健康检查、备份和升级。
创建课程 Dataset，通过官方 Dataset/Document API 幂等导入 P06 Markdown；建立本地 knowledge ID 到
Dify dataset/document ID 的映射，支持新增、更新、删除和失败重试。配置 embedding/LLM provider，密钥
只进入未提交的 `.env`。等待每个文档 indexing 完成，失败文档必须补跑。

在 Dify 中索引全量 P06，验证课程、案例、speaker、时间/页码、evidence、安全标签和 Prompt 版本可查询。构建不少于
20 个真实问题的测试集，覆盖事实、相似案例、多个解释、拒绝边界、隐私、醉酒、年龄、不同关系阶段。
每个回答必须包含客观事实、至少 3 种解释、至少 3 个行动方案，每方案至少 3 种说法，引用有效知识 ID，
并明确不确定性和安全停止条件。禁止把讲师观点当事实或输出施压/欺骗推进建议。

在 Dify 中创建聊天或 Workflow 应用，把知识检索节点接到多方案回答 Prompt，并保留引用与安全停止条件。
交付：Dify Docker 部署、Dataset、导入映射、幂等同步程序、Workflow/应用配置、20 问结果与 QA、性能和
命中率报告、README、测试、commit 和 push。本地 SQLite 只作为离线回归，不是最终交付。

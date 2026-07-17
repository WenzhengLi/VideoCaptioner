# TASK-015：Dify 正式 Dataset 与索引能力就绪

## 状态

代码完成（embedding Provider 需 Web UI 配置）；依赖 TASK-014。

## 目标

解决当前 Dataset 为 `economy`、同步代码硬编码 `high_quality`、缺少 embedding 导致语义检索不可用的
不一致，在不编造密钥的前提下准备正式知识库。

## 当前事实

- Dify 1.15.0 已运行于 `http://127.0.0.1:3080`；
- 管理员和工作 Dataset `阿峰课程方法库-研究版` 已创建；
- 当前工作 Dataset 为 `economy`，其中已经导入 v002.5 的 36 篇文档，indexing 36/36 completed，
  keyword retrieval 有真实命中；该 Dataset 保留为历史/工作库，不冒充最终语义库；
- semantic retrieve 因缺 embedding 返回 400；
- v002.5 已导入工作库；v002.6 尚未生成，也尚未导入任何正式库；
- `create_document_by_text` 当前硬编码 `high_quality`。

## 必须完成

1. 让 Dataset 创建和文档同步显式支持 `economy` / `high_quality`，禁止隐藏硬编码；
2. CLI 增加明确参数和环境配置，并校验 Dataset 模式与文档模式一致；
3. 为无 embedding 的失败路径增加可读错误，不泄露密钥；
4. 以 Dify 1.15.0 的真实插件/Provider 能力为准，核对 Ollama、Xinference、OpenAI-compatible
   embedding 等本地接入方式，并把核对证据写入报告；不得凭印象选型；
5. 优先采用本地 embedding，用磁盘和本机计算换取后续批量入库成本。候选模型优先评估
   `BAAI/bge-m3`，但只有在 Dify 1.15.0 实际兼容、健康检查和小样本向量调用均通过时才能落地；
6. 本地 embedding 可行时，创建正式 Dataset：`阿峰课程方法库-研究版-v1`，使用
   `high_quality`，并记录 Provider 类型、模型名、维度和健康状态，但不得记录密钥；
7. 本地方案不可行且本机没有合法外部 embedding 配置时，仍须完成代码、测试、Provider
   可用性探测、部署模板、dry-run 和故障说明，再标记 `external_blocked`；不得停在调研或计划；
8. 工作 Dataset 与正式 Dataset 必须使用不同名称和独立 document map，禁止复用旧 map 导致
   跨 Dataset 错绑远端 document ID；
9. 不删除、不清空、不重建已有工作 Dataset；
10. 保持 `cpa` 容器和端口 8317 不变。

## 允许修改

- `src/course_video_analyzer/knowledge/dify_sync.py`
- `src/course_video_analyzer/knowledge/cli.py`
- `tests/test_knowledge/test_dify_sync.py`
- `deploy/dify/`
- `docs/cursor-handoff/DIFY-STATUS.md`
- Dify 部署根的非仓库本地脚本和状态文件

## 禁止事项

- 不提交真实密钥；
- 不输出 Token、密码或 API Key；
- 不删除 volume；
- 不停止或修改 `cpa`；
- 不复制 CC Switch/Cursor/Claude Code 的 Token 到 Dify；
- 不修改已有 economy 工作 Dataset 中的 36 篇 v002.5 文档；
- 未配置 embedding 时不得声称语义检索可用。

## 验收标准

- indexing technique 可配置且有测试；
- 模式不匹配能在同步前失败；
- Dify 容器健康；
- 正式 Dataset 与已有 economy 工作 Dataset 明确区分，map 也相互隔离；
- 有 embedding 时 high_quality Dataset 创建成功；无 embedding 时阻塞说明准确；
- 若落地本地 embedding，至少完成一次真实 embedding 调用和一个小样本 Dataset 的语义检索；
- 全量测试通过。

## 完成说明（代码部分）

已完成：
- `sync_markdown_dir` 新增 `indexing_technique` 显式参数，移除 `DIFY_DATASET_INDEXING` 环境变量硬编码；
  优先级：CLI 参数 > 环境变量 > Dataset 模式 > 默认 economy。
- `high_quality` 模式同步前校验 Dataset 已配置 embedding，否则抛出可读错误。
- `dify-sync-markdown` CLI 新增 `--indexing-technique` 参数。
- 本地 embedding 已验证可用：Ollama v0.32.1 + bge-m3 (1024 维, GGUF F16, RTX 4080)。
- 探测脚本 `scripts/probe_local_embedding.py` 和正式 Dataset 创建脚本 `scripts/create_formal_dataset.py`。
- 3 个新增测试覆盖显式参数传递、模式校验和回退逻辑。
- `pytest -q` 266 passed、1 skipped；`ruff` 通过；`pyright` 0 errors。

待完成（需人工 Web UI 操作）：
- 在 Dify Web UI 安装 Ollama 插件并配置 embedding provider。
- 创建正式 Dataset `阿峰课程方法库-研究版-v1`（high_quality + bge-m3）。
- 详见 `docs/evaluation/afeng-embedding-investigation.md`。

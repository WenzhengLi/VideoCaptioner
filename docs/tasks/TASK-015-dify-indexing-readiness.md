# TASK-015：Dify 正式 Dataset 与索引能力就绪

## 状态

待执行；依赖 TASK-014。

## 目标

解决当前 Dataset 为 `economy`、同步代码硬编码 `high_quality`、缺少 embedding 导致语义检索不可用的
不一致，在不编造密钥的前提下准备正式知识库。

## 当前事实

- Dify 1.15.0 已运行于 `http://127.0.0.1:3080`；
- 管理员和冒烟 Dataset 已创建；
- 当前 Dataset 为 `economy`；
- semantic retrieve 因缺 embedding 返回 400；
- 正式 v002.5/v002.6 尚未导入；
- `create_document_by_text` 当前硬编码 `high_quality`。

## 必须完成

1. 让 Dataset 创建和文档同步显式支持 `economy` / `high_quality`，禁止隐藏硬编码；
2. CLI 增加明确参数和环境配置，并校验 Dataset 模式与文档模式一致；
3. 为无 embedding 的失败路径增加可读错误，不泄露密钥；
4. 核对 Dify 当前可用 embedding 供应商，但不得编造 API Key；
5. 若本机已有合法 embedding 配置，创建正式 Dataset：`阿峰课程方法库-研究版-v1`，使用
   `high_quality`；
6. 若缺少 embedding 密钥，完成所有代码、测试、文档和 dry-run，并把唯一人工阻塞写清楚；
7. 不使用冒烟 Dataset 冒充正式 Dataset；
8. 保持 `cpa` 容器和端口 8317 不变。

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
- 未配置 embedding 时不得声称语义检索可用。

## 验收标准

- indexing technique 可配置且有测试；
- 模式不匹配能在同步前失败；
- Dify 容器健康；
- 正式 Dataset 与冒烟 Dataset 明确区分；
- 有 embedding 时 high_quality Dataset 创建成功；无 embedding 时阻塞说明准确；
- 全量测试通过。

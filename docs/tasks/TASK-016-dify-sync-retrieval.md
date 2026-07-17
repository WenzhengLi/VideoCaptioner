# TASK-016：阿峰 v002.6 正式同步、索引与检索验收

## 状态

待执行；依赖 TASK-014、TASK-015，且正式 high_quality Dataset 已可用。

## 目标

将 v002.6 的 36 个发布文档真实导入 Dify，完成索引和可重复检索验收。

## 必须完成

1. 真实同步 `data/dify/afeng-release-v002.6/documents`；
2. 首次同步预期 create=36、failed=0；
3. 轮询全部 indexing 到 completed；
4. 二次同步预期 skip=36；
5. 修改一份测试副本验证 update-by-text，不改正式 v002.6；
6. document map 覆盖 36 个 canonical ID，远端 document ID 唯一；
7. 设计不少于 20 个检索问题，覆盖课程、案例、方法、条件、限制、话术、时间戳和证据；
8. 记录 top-k、召回文档、相关性、来源课程、时间范围和错误召回；
9. 检查 `partial_method` 能被识别，manual_review/rejected 不得出现在 Dataset；
10. 生成机器可读 JSON 和 Markdown 验收报告。

## 允许修改

- Dify 同步与检索验收脚本
- `tests/test_knowledge/test_dify_sync.py`
- `docs/evaluation/dify-*`
- `docs/cursor-handoff/DIFY-STATUS.md`
- `data/dify/document-map.json` 等 gitignored 运行数据

## 禁止事项

- 不导入 v002.5 或更早包冒充最终包；
- 不上传 4 个排除案例；
- 不修改 v002.6；
- 不把接口可达当成检索通过。

## 验收标准

- create=36、failed=0、indexing completed=36；
- 二次同步 skip=36；
- Dataset 中无 manual_review/rejected；
- 20 问检索报告完整；
- 时间戳和来源 metadata 可返回；
- 检索失败有明确原因分类。

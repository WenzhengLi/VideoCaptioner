# TASK-013：阿峰稳定知识标识与模型血缘

## 状态

待执行。

## 目标

让阿峰知识文档拥有由程序控制、跨模型和跨重跑稳定的标识，并为每份发布文档保存可追溯的模型、
运行和输入血缘。解决当前模型自由生成 `knowledge_id` 导致 Dify 重复创建文档的问题。

## 当前事实

- v002.5 有 36 个发布文档，但 0 个使用统一的系统标识格式；
- 当前存在中文、英文、哈希等多种 knowledge ID；
- C001–C015 使用 MiMo，C016–C020 使用 `glm-5-2-260617[1M]`；
- v002.5 manifest 没有逐文档 model/run metadata；
- v002.5 **已正式导入** Dify（economy Dataset，36 文档 indexing completed）；
- 因此本任务必须产出可对远端做 **update/skip（按 canonical ID）** 的迁移路径，并在 v002.6 包中完成身份归一；不得假设“尚未入库”。

## 必须完成

1. 冻结 canonical knowledge ID：`AFENG-{course_id}-{case_id}`，例如
   `AFENG-C007-CASE-C007-001`；
2. canonical ID 必须由程序生成，模型输出不得改变；
3. 方法草稿、审查、发布分类、Markdown、run manifest 和 Dify bundle 的身份必须一致；
4. 对未来新运行直接使用 canonical ID；
5. 对现有 40 案例提供确定性迁移/重建路径，不修改或覆盖历史模型原始产物；
6. Dify bundle 每份文档增加：
   - `model`；
   - `run_token` 或等价稳定运行标识；
   - `input_hash`；
   - `source_summary`；
   - canonical `knowledge_id`；
7. Dify metadata 解析和 document map 使用 canonical ID 作为幂等键；
8. 重跑同一案例时，内容相同必须 skip，内容变化必须 update，不能 create duplicate；
9. 增加正常、模型乱写 ID、历史迁移、重复 ID 和内容更新测试。

## 允许修改

- `src/course_video_analyzer/knowledge/afeng*.py`
- `src/course_video_analyzer/knowledge/dify_sync.py`
- `scripts/build_afeng_dify_bundle.py`
- 新增必要的确定性迁移/重建脚本
- `tests/test_knowledge/test_afeng.py`
- `tests/test_knowledge/test_dify_sync.py`
- 新增相关测试
- 阿峰与 Dify 文档

## 禁止事项

- 不重新调用模型生成 C001–C020 方法；
- 不覆盖 v002.1–v002.5；
- 不修改事实层 P01–P04；
- 不把模型生成的任意 knowledge ID 继续作为远端幂等主键；
- 不导入 Dify。

## 交付内容

- 稳定 ID 实现；
- 模型血缘字段；
- 历史产物确定性迁移/重建工具；
- 单元测试；
- 设计与迁移说明。

## 验收标准

- 40 个案例均能映射到唯一 canonical ID；
- 同案例跨模型/跨运行 ID 不变；
- bundle 中 model metadata 覆盖率 100%；
- 同 ID 同内容为 skip，不同内容为 update；
- 全量 pytest、Ruff、Pyright 通过。

# TASK-014：重建阿峰 v002.6 与重点案例忠实度审查

## 状态

待执行；依赖 TASK-013。

## 目标

不重新调用模型，使用现有 40 案例终态和新的稳定 ID/血缘逻辑，生成不可变的 v002.6 离线发布包，
并完成重点案例的证据级审查材料。

## 输入

- `docs/evaluation/afeng-twenty-course-v002.json`
- C001–C015 既有 run summaries；
- C016–C020 GLM run summary；
- `data/dify/afeng-release-v002.5/` 仅作为历史对照。

## 必须完成

1. 重新聚合 40 案例，保持已有终态：36 published、2 manual_review、2 rejected；
2. 生成新目录 `data/dify/afeng-release-v002.6/`，禁止覆盖旧包；
3. 只纳入 36 个通过发布闸门的文档；
4. 逐文档验证 canonical ID、model、run、input hash、内容 hash、时间范围和来源 summary；
5. 运行无密钥 Dify dry-run，预期 36 个唯一 create、0 duplicate；
6. 对以下案例生成证据审查包：
   - C018-002：经历一轮修订；
   - C018-003、C019-001：`verified_method`；
   - C020-002、C020-003：`partial_method`；
   - C006-001、C008-002：manual_review；
   - C014-001、C015-001：rejected；
7. 审查课程归属表达、无证据扩写、条件/限制遗漏、evidence ID 支持关系和时间范围；
8. 机器/Agent 审查不得冒充真人审查，报告必须保留 `human_confirmation_required` 字段。

## 允许修改

- `scripts/` 中阿峰 bundle/审查工具
- `docs/evaluation/afeng-*v0026*`
- `docs/evaluation/afeng-human-review-*`
- 对应测试

## 禁止事项

- 不调用模型重写已完成课程；
- 不把 manual_review/rejected 改成 published；
- 不覆盖 v002.5；
- 不导入 Dify。

## 交付内容

- v002.6 bundle 和 manifest；
- 40 案例最终汇总；
- 9 个重点案例的审查报告与人工确认清单；
- dry-run 报告；
- bundle 完整性验证报告。

## 验收标准

- 40 案例、0 unresolved failure；
- 36 文档、4 排除；
- canonical ID 唯一率 100%；
- model/run/input hash 元数据覆盖率 100%；
- 文本哈希校验 100%；
- dry-run 无重复知识 ID；
- 全量测试通过。

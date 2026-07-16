# 阿峰方法层：下一阶段执行总计划

> 更新：2026-07-16
> 当前版本：`afeng-method-v001` / `mimo-method-v002`
> 三课状态：6 案例中 5 个发布、1 个人工复核、0 程序失败

## 一、目标

将已经落地的阿峰方法层程序骨架推进到可真实批量生产：

```text
前20课 evidence baseline
→ C003/C006/C010 固定试验（已完成）
→ Prompt v002 与忠实度抽检（已完成第一轮）
→ 5课 / 15课 / 20课扩展
→ 冻结 afeng-method-v001
→ Dify 阿峰课程方法库
```

本阶段不改变视频 ASR、OCR 和 P01–P04 的事实层算法。

## 二、并行边界

### Cursor 负责事实与证据层

1. 完成 C001–C015 质量报告；
2. 完成 C003/C008/C006/C010 的 P03 v002/v003 回归；
3. 确定 `evidence-baseline-C001-C015.json`；
4. 完成 C016–C020 的 P01–P04 和全部 QA；
5. 生成 `evidence-baseline-C001-C020.json`；
6. 完成后停止，不进入 P05/P06、阿峰方法层或 Dify。

### Codex 负责阿峰方法层

1. 消费 Cursor 生成的 evidence baseline manifest；
2. 生成 AfengEvidencePackage 和脱敏外发载荷；
3. 接入结构化模型执行器；
4. 执行方法提炼、忠实度审查、最多两次修订和发布分类；
5. 程序渲染 Markdown；
6. 生成 A/B、质量、成本和人工复核报告；
7. 稳定后同步 Dify。

## 三、执行阶段

### A01：baseline 消费器

输入：

- `data/catalog/evidence-baseline-C001-C015.json` 或 C001–C020；
- manifest 中每课 P01/P02/P03 版本和每案例 P04 版本；
- 可选历史 P05 evidence fields。

交付：

- manifest schema/完整性检查；
- 案例文件解析和 QA pass 强制检查；
- 按 manifest 精确选择 P04，不依赖“latest”；
- C003/C006/C010 pilot manifest；
- evidence package、外发脱敏和输入哈希报告。

### A02：模型执行器

交付：

- 可配置 API endpoint、model、timeout 和 retries；
- API Key 只从环境变量读取；
- 每阶段绑定对应 Prompt 和 JSON Schema；
- Markdown 代码围栏清理、JSON 解析、Schema 校验和有限重试；
- 请求耗时、token usage、request ID 和失败原因记录；
- 相同输入哈希、Prompt、模型和阶段不重复调用。

默认执行器已经改为 CC Switch 当前配置驱动的 Claude Code CLI headless；直接 HTTP adapter
保留备用。响应后继续执行本地 Schema 强校验、确定性 QA、缓存和断点恢复。

### A03：三课固定试验（已完成）

固定课程：

| 课程 | 用途 |
| --- | --- |
| C003 | 案例边界复杂、P03 未分配较高 |
| C006 | OCR 信息量大，检查语音与课板融合 |
| C010 | 边界相对清晰，作为基准 |

每个案例执行：

```text
evidence package QA
→ external payload QA
→ extract_method
→ audit_fidelity
→ revise（最多2次）
→ classify_publication
→ deterministic Markdown
```

### A04：人工审查与 Prompt 迭代

逐案例记录：

- 方法是否提完整；
- 是否新增课程外概念；
- 讲师观点是否保持来源归属；
- 声称结果是否被升级成事实；
- 单案例是否被扩大成普遍规律；
- 条件、限制、失败和例外是否遗漏；
- evidence ID 是否真实支持字段；
- direct adaptation / combination 是否改变原意。

输出：

- `docs/evaluation/afeng-pilot-v001.md/.json`；
- 人工审查模板；
- `mimo-method-v002` 固定回归与继续扩展决策记录。

### A05：扩展与冻结

扩展门槛：

- JSON 解析成功率 100%；
- evidence ID 合法率 100%；
- 通过审查的方法核心字段 evidence 覆盖率 100%；
- 未脱敏 PII 外发 0；
- 无证据扩写率达到人工验收目标；
- 单案例失败可恢复且不影响其他案例。

扩展顺序：

```text
3课 → 5课 → 15课 → 20课
```

前20课通过后冻结 `afeng-method-v001`，后续改动使用新版本，不覆盖历史。

### A06：Dify

仅导入：

- 忠实度 `pass`；
- `release_allowed=true`；
- 发布分类不是 `reject`；
- `publishable=true`；
- 已通过程序 QA 的 Markdown。

Dataset：`阿峰课程方法库-研究版`

应用：`阿峰`

## 四、当前阻塞条件

真实模型链路和三课试验已经完成。当前唯一批量扩展阻塞项是 Cursor 尚未冻结
`evidence-baseline-C001-C020.json`。C006/CASE-C006-001 保留人工复核，不阻塞其他案例。

## 五、当前立即动作

1. 监控 Cursor 完成 C016–C020 事实层、P01–P04 和全量 QA；
2. 冻结 `evidence-baseline-C001-C020.json`；
3. 对发生 source case 变化的三课案例重建 evidence package 并定点回归；
4. 对 C006/CASE-C006-001 做人工忠实度复核，不强行发布；
5. 选择 5 课扩展集，运行 v002 并统计发布率、人工复核率、耗时和成本；
6. 5 课通过后再扩展到 15 课和 20 课；
7. 稳定后设计 Dify 导入清单和检索元数据，不让 Dify 承担方法提炼。

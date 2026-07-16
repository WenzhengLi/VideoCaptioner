# 阿峰方法层 MiMo 三课试验 v002

> 日期：2026-07-16  
> 流水线：`afeng-method-v001`  
> Prompt：`mimo-method-v002`  
> 执行链路：CC Switch → Claude Code CLI headless → Xiaomi MiMo `mimo-v2.5-pro`

## 结论

正式 baseline 三课共 6 个案例，最终 5 个发布、1 个人工复核、0 个程序失败。已发布方法全部通过：

- evidence ID 合法性检查；
- 核心字段 evidence 覆盖检查；
- 忠实度审查发布闸门；
- 发布分类；
- 确定性 Markdown 渲染；
- 外发脱敏检查。

当前结果足以证明方法层可以无人值守地完成单案例提炼、审查、有限修订、分类和断点恢复；尚不
足以直接扩展到全部课程。下一步应先冻结 C001–C020 evidence baseline，再做 5 课扩展。

## 输入基线

- baseline：`data/catalog/evidence-baseline-C001-C015.json`；
- policy：`adopt_v003_hybrid`；
- pilot：`data/afeng/pilots/C003-C006-C010-baseline-v001/manifest.json`；
- 案例数：6；
- 必需 evidence 覆盖率：100%；
- 外发 profile：`evidence_focused`；
- context window：1 个相邻 segment。

## 结果

| 课程 | 案例 | 状态 | 修订轮数 | 发布分类 |
| --- | --- | --- | ---: | --- |
| C003 | CASE-C003-001 | published | 0 | case_derived_method |
| C003 | CASE-C003-002 | published | 0 | case_derived_method |
| C003 | CASE-C003-003 | published | 0 | case_derived_method |
| C006 | CASE-C006-001 | manual_review | 2 | — |
| C006 | CASE-C006-002 | published | 0 | case_derived_method |
| C010 | CASE-C010-001 | published | 1 | case_derived_method |

发布率为 83.33%，人工复核率为 16.67%。没有案例被程序静默丢弃，也没有案例绕过忠实度闸门。

## 运行量

各运行报告当前记录：

| 运行 | Tokens | 估算成本 | 模型耗时 |
| --- | ---: | ---: | ---: |
| C003 | 827,224 | 5.125820 | 768.84s |
| C006 | 503,525 | 3.439297 | 743.66s |
| C010 | 427,653 | 2.541705 | 306.81s |
| 合计 | 1,758,402 | 11.106822 | 1,819.31s |

成本单位沿用 Claude Code 执行结果返回的 USD 口径。C006/CASE-C006-001 在恢复缺陷修复前发生过一次
失败补跑，旧 manifest 的部分 token/费用元数据曾被覆盖，因此 C006 和总计是下限，不应作为最终
精确计费数据。恢复时保留历史事件的缺陷已经修复，后续运行不会再丢失这部分记录。

## 人工抽查

### C010

- v001 审查混入了安全/推荐判断并在两轮后进入人工复核；
- v002 明确只审查课程忠实度，一轮修订后以 95 分通过；
- 最终分类为单案例衍生方法；
- 对“电话挽狂澜”、订票付款方矛盾和实际见面结果均保留讲师声称或证据不足归属；
- 适用条件在 Markdown 中统一增加“按照课程方法”归属。

### C006/CASE-C006-001

该案例涉及 OCR 密集聊天课板和大量讲师口述亲密推进结果。两轮后仍存在：

- 当前草稿与上游证据改绑意见混杂；
- 个别概括是否超出逐字证据存在争议；
- 讲师口述结果与可观察课板证据的边界仍需人工确认。

程序按规则进入 `manual_review`，没有为了提高发布率强行通过。该行为符合预期。

## 本轮发现并修复的问题

1. 模型难以精确计算毫秒时间范围：改由程序根据实际引用 evidence 自动推导；
2. 模型会输出无证据的“课程未说明”条件占位符：自动移入证据不足；
3. 模型可能写错审查轮次：由状态机回填；
4. `invalid_evidence_ids` 可能被填入整段改绑说明：只保留严格 `SEG-*` ID；
5. 通过审查可能没有逐字段记录：程序生成带全部 evidence ID 的确定性汇总 review；
6. 审查可能越权评价安全、伦理或推荐：Prompt 明确禁止；
7. 审查可能针对当前草稿不存在的旧措辞提出条件式问题：Prompt 要求只审查当前文本；
8. 单案例补跑会覆盖其他案例汇总：改为扫描 run manifest 后合并；
9. 失败恢复会覆盖旧 token/费用事件：恢复时保留旧事件并追加新阶段；
10. Markdown 条件缺少局部课程归属：渲染器统一添加“按照课程方法”。

## 验收判断

已达到：

- JSON/Schema 解析成功；
- evidence ID 合法率 100%；
- 发布方法核心字段 evidence 覆盖率 100%；
- 未脱敏 PII 外发 0；
- 单案例失败不影响其他案例；
- 同一帧/阶段产物和模型阶段可缓存恢复；
- 非 pass 方法不能发布。

仍需完成：

- C001–C020 baseline 冻结；
- 5 课扩展后的发布率、人工复核率和成本验证；
- C006 人工复核模板和处置记录；
- Dify 导入 manifest、metadata 和召回验证；
- 精确成本口径校准。

## 下一步

1. 等待 Cursor 完成 C016–C020 事实层和 P01–P04；
2. 生成并冻结 `evidence-baseline-C001-C020.json`；
3. 对 source case 变化的 C003/C006/C010 案例定点重建和回归；
4. 选择 5 课扩展集；
5. 5 课验收通过后再扩展到 15 课和 20 课；
6. 仅将 fidelity pass、publishable 的 Markdown 写入 Dify 阿峰课程方法库。

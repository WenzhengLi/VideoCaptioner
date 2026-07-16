# MiMo-V2.5-Pro 课程方法沉淀与忠实度审查 Prompt

## 1. 目标

使用外部 API 模型 MiMo-V2.5-Pro，将已经完成基础清洗、案例切分和证据提取的课程内容，沉淀为可供 Dify 检索和回答使用的 Markdown 方法文档。

产品定位不是通用情感顾问，也不是独立判断课程观点是否正确，而是：

> 忠实理解课程，提炼课程提供的方法，并在用户提问时按照课程方法提供可执行思路。

硬性发布规则：

> 任何方法文档必须通过课程忠实度审查，未通过审查的内容不得写入正式 Dify Dataset。

## 2. 当前事实与第一版假设

- 视频、ASR、说话人、OCR 和时间线处理在 Dify 外完成。
- 当前 P01–P06 由 Cursor Agent `--model auto` 执行。
- MiMo-V2.5-Pro 通过外部 API 使用，目前尚未接入。
- MiMo 第一版不替换 ASR、OCR、P01–P03。
- MiMo 第一版只消费由 P04 和 P05 证据字段构建的“案例证据包”，负责方法提炼、忠实度审查和发布分类。
- 旧 P06 不作为 MiMo 输入，只保留为 Cursor Auto 历史 A/B 基线。
- Markdown 由程序确定性渲染，模型不得在最后一步增加、删除或纠正课程内容。
- 由于当前课程授权与个人信息授权尚未建立，发送外部 API 前必须先进行脱敏；未授权内容只能标记为 `research_only`。
- 忠实度审查只审查“是否忠实于课程”，不判断课程观点是否科学、正确或符合其他理论。

## 3. 禁止事项

MiMo 不得：

1. 使用外部心理学、社会学、两性理论或个人经验纠正课程。
2. 把课程没有讲过的技巧补充进方法文档。
3. 把讲师推测、案例复盘或声称结果写成客观事实。
4. 为了让方法显得完整而补写不存在的前提、步骤、结果或话术。
5. 将单个案例自动升级为适用于所有人的普遍规律。
6. 将 OCR 画面文字错误地当成讲师口述。
7. 删除课程明确提出的适用条件、例外、限制和失败情况。
8. 输出未脱敏的姓名、头像信息、微信号、手机号、地址或其他可识别信息。
9. 在忠实度审查未通过时生成可发布 Markdown。

当课程证据不足时，必须返回“课程证据不足”，不得自由发挥。

## 4. 推荐处理流程

```text
P04 + P05 evidence fields
        ↓
AfengEvidencePackage
        ↓
Prompt A：课程方法提炼
        ↓
方法草稿 JSON
        ↓
Prompt B：课程忠实度审查（强制闸门）
        ↓
pass / revise / reject
        ↓
Prompt C：按审查意见修订
        ↓
再次执行 Prompt B
        ↓
仅 pass 结果进入 Prompt D
        ↓
Prompt D：发布分类
        ↓
程序确定性渲染 Markdown
        ↓
Dify 阿峰测试 Dataset
```

最大修订次数建议为 2 次。两次后仍未通过，进入人工复核，不允许继续自动重写。

## 5. 输入数据契约

推荐向 MiMo 提交以下 JSON。不存在的字段使用空数组或 `null`，禁止伪造。

```json
{
  "course_id": "C006",
  "course_title": "",
  "case_id": "CASE-C006-003",
  "case_title": "",
  "rights_status": "research_only",
  "course_context": "",
  "segments": [
    {
      "segment_id": "SEG-C006-000123",
      "start_ms": 191061,
      "end_ms": 200368,
      "source_type": "speech|ocr|chat|board",
      "speaker_role": "instructor|student|chat_left|chat_right|unknown",
      "raw_text": "",
      "normalized_text": ""
    }
  ],
  "observations": [],
  "instructor_claims": [],
  "claimed_outcomes": [],
  "quoted_expressions": [],
  "existing_principles": [],
  "evidence_reviews": [],
  "source_warnings": [],
  "pipeline_version": "knowledge-v003",
  "prompt_version": "mimo-method-v001"
}
```

## 6. Prompt A：课程方法提炼

### System Prompt

```text
你是“课程方法提炼器”。

你的唯一知识来源是用户提供的课程案例证据包。你的任务不是评价课程是否正确，也不是提供你自己的建议，而是忠实提炼课程实际讲授的方法。

你必须区分：
1. 可观察事实：聊天原文、行为、时间和明确发生的事件。
2. 讲师观点：讲师对事实的解释、判断和总结。
3. 声称结果：由讲师或课程口述的结果，但缺少独立验证。
4. 课程方法：课程明确提出，或能够由多条课程证据直接归纳出的操作方法。
5. 模型推断：证据没有明确支持、只能由模型猜测的内容。

课程方法可以被提炼和重新组织，但不得被纠正、反驳或替换。模型推断不得进入正式方法。

每一个核心判断、适用条件、执行步骤和示例表达都必须引用 evidence segment_id。没有证据时必须留空或标记为课程证据不足。

只输出合法 JSON，不要输出 Markdown，不要解释你的工作过程。
```

### User Prompt

```text
请从以下课程案例证据包中提炼课程提供的方法。

提炼目标：
- 让学习者知道这个方法解决什么问题。
- 让学习者知道课程如何理解该情境。
- 让学习者知道什么情况下使用。
- 让学习者知道课程建议按什么顺序行动。
- 保留课程中的示例话术，但不得自行创作课程没有提供的方法。
- 保留课程明确提到的限制、失败情况和停止条件。

课程案例证据包：
{{evidence_package_json}}

严格输出以下 JSON：
{
  "knowledge_id": "",
  "course_id": "",
  "case_id": "",
  "method_name": "",
  "problem_addressed": "",
  "course_perspective": "",
  "applicable_conditions": [
    {
      "condition": "",
      "evidence_ids": []
    }
  ],
  "not_applicable_conditions": [
    {
      "condition": "",
      "evidence_ids": []
    }
  ],
  "core_logic": {
    "content": "",
    "evidence_ids": [],
    "evidence_level": "explicit|direct_summary|insufficient"
  },
  "steps": [
    {
      "order": 1,
      "action": "",
      "purpose_according_to_course": "",
      "evidence_ids": []
    }
  ],
  "signals_used_by_course": [
    {
      "signal": "",
      "course_interpretation": "",
      "evidence_ids": []
    }
  ],
  "example_expressions": [
    {
      "text": "",
      "source": "course_quote|direct_adaptation",
      "evidence_ids": []
    }
  ],
  "course_reported_outcome": {
    "content": "",
    "evidence_ids": [],
    "evidence_level": "observed|instructor_claimed|unknown"
  },
  "course_stated_limits": [
    {
      "content": "",
      "evidence_ids": []
    }
  ],
  "insufficient_course_evidence": [],
  "source_time_range": {
    "start_ms": 0,
    "end_ms": 0
  },
  "draft_fidelity_status": "pending_review"
}

额外约束：
1. `course_perspective` 必须使用“课程将其理解为”“按照课程方法”等来源归属表达。
2. `direct_adaptation` 只能对课程已有表达做贴近原意的口语化改写。
3. 课程没有明确提出不适用条件时，保持空数组，不得补充常识。
4. 不能确认实际结果时，`evidence_level` 必须是 `instructor_claimed` 或 `unknown`。
```

## 7. Prompt B：课程忠实度审查（硬性闸门）

### System Prompt

```text
你是“课程忠实度审查员”。

这是发布前不可绕过的强制审查。你只判断方法草稿是否忠实于输入课程证据，不判断课程观点是否正确、科学或符合其他理论。

审查原则：
1. 没有课程证据支持的内容不得通过。
2. evidence_id 必须真实存在于证据包中，并支持对应字段。
3. 讲师观点不得伪装成可观察事实。
4. 声称结果不得伪装成独立验证结果。
5. 单个案例不得被无依据地扩大为普遍规律。
6. 课程中的条件、限制、失败和例外不得被遗漏。
7. 不得出现外部理论、模型自创术语或模型独立建议。
8. 审查不得通过“纠正课程”来解决问题，只能要求删除、降级、重新归属或补充课程证据。

只输出合法 JSON，不要输出 Markdown。
```

### User Prompt

```text
请对方法草稿执行课程忠实度审查。

原始课程证据包：
{{evidence_package_json}}

待审方法草稿：
{{method_draft_json}}

逐字段检查：
- 核心观点是否忠实于课程。
- 方法步骤是否全部有证据。
- 适用条件是否由课程提出。
- 示例表达是否来自课程或属于直接改写。
- 是否混淆事实、讲师观点和声称结果。
- 是否遗漏会改变方法含义的条件。
- 是否出现课程外新增概念。
- evidence_id 是否存在并真正支持对应内容。

输出：
{
  "audit_result": "pass|revise|reject",
  "fidelity_score": 0,
  "field_reviews": [
    {
      "field": "",
      "status": "supported|partially_supported|unsupported|misattributed|missing_condition",
      "issue": "",
      "evidence_ids": [],
      "required_action": "keep|delete|downgrade|reattribute|rewrite_from_evidence"
    }
  ],
  "unsupported_additions": [],
  "misattributed_claims": [],
  "missing_course_conditions": [],
  "invalid_evidence_ids": [],
  "external_knowledge_detected": [],
  "revision_instructions": [],
  "release_allowed": false
}

判定规则：
- 只有 `audit_result=pass` 时，`release_allowed` 才能为 true。
- 任何核心逻辑或核心步骤无证据支持时，不得 pass。
- 只存在不影响含义的文字问题时可以 revise。
- 证据包无法支持方法成立时必须 reject。
```

## 8. Prompt C：忠实度修订

### System Prompt

```text
你是“课程方法忠实度修订器”。

你只能按照忠实度审查报告修订方法草稿。不得增加审查报告没有要求的新内容，不得使用外部知识，也不得改变课程立场。

修订动作只允许：
- 删除无证据内容。
- 将客观陈述改为“课程观点”或“讲师声称”。
- 降低证据等级。
- 补回课程证据中已经存在但草稿遗漏的条件。
- 使用课程证据重新表述。

只输出完整、合法的修订版 JSON。
```

### User Prompt

```text
原始课程证据包：
{{evidence_package_json}}

原方法草稿：
{{method_draft_json}}

忠实度审查报告：
{{fidelity_audit_json}}

请严格按照 `revision_instructions` 输出完整修订版。

修订后：
- 所有核心字段必须有有效 evidence_ids。
- 不得保留 unsupported 内容。
- 不得引入新方法、新理论或新案例。
- `draft_fidelity_status` 保持 `pending_review`，必须重新进入忠实度审查。
```

## 9. Prompt D：发布分类

### System Prompt

```text
你是“课程方法发布分类器”。

你只能对已经通过课程忠实度审查的方法进行内容类型和证据成熟度分类。分类不是安全审查，也不评价课程是否正确、科学或值得采用。

如果 `audit_result` 不是 `pass`，或 `release_allowed` 不是 true，必须停止并输出：
NOT_RELEASED: fidelity audit not passed
```

### User Prompt

```text
通过审查的方法：
{{approved_method_json}}

忠实度审查结果：
{{fidelity_audit_json}}

请严格输出：

{
  "schema_version": "1.0",
  "pipeline_version": "afeng-method-v001",
  "prompt_version": "mimo-method-v001",
  "knowledge_id": "",
  "course_id": "",
  "case_id": "",
  "publication_class": "verified_method|case_derived_method|course_claim|reported_outcome|partial_method|insufficient_evidence|reject",
  "generalization_level": "course_explicit|single_case|partial|none",
  "classification_rationale": "",
  "evidence_ids": [],
  "publishable": true
}

分类只表达课程内容类型和证据成熟度。不得因为课程方法存在争议而使用 `reject`。
```

分类通过程序校验后，由程序按照固定章节确定性渲染 Markdown。渲染器只读取已批准方法 JSON、
忠实度审查结果和发布分类，不调用模型。

## 10. 发布程序硬规则

程序层必须执行以下规则，不能只依赖 Prompt：

```text
if rights_status not in [research_only, authorized]:
    reject

if fidelity_audit.audit_result != "pass":
    reject

if fidelity_audit.release_allowed != true:
    reject

if approved_method.draft_fidelity_status is not reviewed:
    reject

if any core field has no valid evidence_id:
    reject

if personally_identifiable_information_detected:
    reject_or_manual_review

if publication_record.publication_class == "reject":
    do_not_render_markdown

if publication_record.publishable != true:
    do_not_render_markdown
```

正式用户 Dataset 还需要额外要求：

```text
rights_status == authorized
```

`research_only` 只能进入隔离的测试 Dataset。

## 11. 验收标准

1. 每个正式方法文档均存在独立忠实度审查结果。
2. 忠实度未通过的内容无法进入发布分类和 Markdown 渲染步骤。
3. 所有核心观点、步骤和示例表达都有有效 evidence_id。
4. 讲师观点、可观察事实和声称结果被明确区分。
5. 模型没有引入课程外理论、术语和独立建议。
6. 课程没有覆盖的内容明确标记为“课程未明确说明”。
7. 每篇 Markdown 由程序确定性渲染，并能追溯到课程、案例、时间范围和 Prompt 版本。
8. 外部 API 输入不包含未脱敏的个人识别信息。
9. `research_only` 内容不会进入正式用户 Dataset。
10. 同一固定测试集能够比较 Cursor Auto 与 MiMo-V2.5-Pro 的忠实度、完整性、耗时和成本。

## 12. 第一轮 A/B 测试建议

第一轮只测试三类课程：

- C003：P03 未分配比例高，用于检验输入案例完整性对方法沉淀的影响。
- C006：OCR 信息多，用于检验语音与课板证据融合。
- 一门边界清晰的正常课程，作为基线。

Cursor Auto 与 MiMo 使用完全相同的证据包和输出契约，比较：

- 忠实度审查通过率；
- 核心字段证据覆盖率；
- 课程外新增概念数量；
- 错误归属数量；
- JSON 解析成功率；
- 人工抽检一致率；
- 单案例耗时和 API 成本。

不要以语言是否更华丽作为主要评价标准。

## 13. 二轮确认项

- MiMo-V2.5-Pro 的 API 上下文限制、结构化输出能力和计费方式。
- 现有 P04 和 P05 evidence fields 已映射到 AfengEvidencePackage；P06 明确排除。
- 方法文档是“一案例一篇”还是“一种方法合并多个案例一篇”。第一版建议一案例一篇，稳定后再做跨案例归并。
- Dify 最终实时回答使用 MiMo、其他 API 模型还是独立本地模型。

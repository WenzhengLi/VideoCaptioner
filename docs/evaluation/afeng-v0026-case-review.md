# 阿峰 v002.6 重点案例审查报告

生成时间：2026-07-17
分支：`cursor/afeng-canonical-id-dify-bundle`
基于：commit 2b2cf70 + 9ecefa9 收尾

## 一、Bundle 概况

| 项 | 值 |
|---|---|
| Bundle 目录 | `data/dify/afeng-release-v002.6/` |
| 文档数 | 36 |
| 排除数 | 4 |
| Canonical ID 唯一率 | 36/36 (100%) |
| Lineage 覆盖率 | 36/36 (100%) |
| 内容 SHA-256 匹配率 | 36/36 (100%) |
| Frontmatter 一致率 | 36/36 (100%) |
| Dry-run 预期 | create=36, update=0, skip=0, duplicate=0 |

## 二、9 个重点案例审查

### 已发布案例（Bundle 内）

| 案例 | Canonical ID | 审查原因 | 状态 | 发布分类 | 修订轮次 | Hash 匹配 | Evidence IDs | Frontmatter |
|---|---|---|---|---|---|---|---|---|
| C018-002 | AFENG-C018-CASE-C018-002 | 经历一轮修订 | published | case_derived_method | 1 | OK | OK | OK |
| C018-003 | AFENG-C018-CASE-C018-003 | verified_method | published | verified_method | 0 | OK | OK | OK |
| C019-001 | AFENG-C019-CASE-C019-001 | verified_method | published | verified_method | 0 | OK | OK | OK |
| C020-002 | AFENG-C020-CASE-C020-002 | partial_method | published | partial_method | 0 | OK | OK | OK |
| C020-003 | AFENG-C020-CASE-C020-003 | partial_method | published | partial_method | 0 | OK | OK | OK |

### 排除案例（Bundle 外）

| 案例 | Canonical ID | 审查原因 | 状态 | 发布分类 | 修订轮次 | 排除原因 | human_confirmation_required |
|---|---|---|---|---|---|---|---|
| C006-001 | AFENG-C006-CASE-C006-001 | manual_review | manual_review | - | 2 | manual_review | True |
| C008-002 | AFENG-C008-CASE-C008-002 | manual_review | manual_review | - | 2 | manual_review | True |
| C014-001 | AFENG-C014-CASE-C014-001 | rejected | rejected | insufficient_evidence | 2 | rejected | True |
| C015-001 | AFENG-C015-CASE-C015-001 | rejected | rejected | case_derived_method | 0 | rejected | True |

## 三、元数据完整性

| 字段 | 覆盖率 | 说明 |
|---|---|---|
| `knowledge_id` (canonical) | 36/36 | AFENG-{course_id}-{case_id} 格式 |
| `model` | 36/36 | mimo-v2.5-pro 或 glm-5-2-260617[1M] |
| `run_token` | 36/36 | 12-hex 从 artifact 文件名恢复 |
| `input_hash` | 36/36 | 证据包输入哈希 |
| `source_summary` | 36/36 | 模型运行汇总文件路径 |
| `content_sha256` | 36/36 | Markdown 内容哈希 |
| `prompt_version` | 36/36 | mimo-method-v002 |
| `pipeline_version` | 36/36 | afeng-method-v001 |

## 四、内容抽查

### C018-002（一轮修订案例）

- Frontmatter: knowledge_id 正确为 canonical 格式
- Evidence IDs: 15 个 SEG- 格式引用
- 时间范围: 968520–1314000 ms
- 发布分类: case_derived_method
- 课程归属表达: 按照课程方法...

### C018-003（verified_method）

- Frontmatter: knowledge_id 正确
- Evidence IDs: 15 个 SEG- 格式引用
- 时间范围: 1454260–2704400 ms
- 泛化等级: course_explicit（课程明确验证的方法）

### C020-002（partial_method）

- Frontmatter: knowledge_id 正确
- Evidence IDs: 15 个 SEG- 格式引用
- 时间范围: 1579750–2857175 ms
- 发布分类: partial_method（课程覆盖不完整）

## 五、审查结论

| 维度 | 结果 |
|---|---|
| 40 案例终态 | 36 published + 2 manual_review + 2 rejected = 40 |
| Bundle 文档 | 36 篇，与 published 数量一致 |
| Bundle 排除 | 4 篇（2 manual_review + 2 rejected） |
| Canonical ID 唯一 | 100% |
| Lineage 元数据 | 100% |
| 内容哈希一致 | 100% |
| Frontmatter 一致 | 100% |
| Dry-run 无重复 | 0 duplicate |
| human_confirmation_required | 仅用于排除案例，未冒充真人确认 |

**机器审查保留 `human_confirmation_required` 字段**：manual_review 和 rejected 案例的审查标记为
需要人工确认，机器审查未冒充真人确认。

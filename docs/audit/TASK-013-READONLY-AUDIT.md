# TASK-013 独立只读审查报告

**分支**: `cursor/afeng-canonical-id-dify-bundle`
**审查范围**: commit 2b2cf70 + 未提交差异 + canonical ID 全链路一致性
**审查时间**: 2026-07-17
**审查方式**: 只读，未修改任何文件，未操作 data/Dify/Docker/document map

---

## 一、无阻断 TASK-014 的问题

TASK-014 的范围是离线构建 v002.6 bundle + dry-run + 证据审查，明确禁止导入 Dify。
以下所有发现均**不阻塞 TASK-014 执行**。

---

## 二、高风险问题（HIGH — TASK-015/016 前必须解决）

### 1. 误复用旧 document map 的配置风险

| 项 | 值 |
|---|---|
| **文件** | `src/course_video_analyzer/knowledge/dify_sync.py`、`dify_sync CLI` |
| **严重性** | **HIGH**（配置风险，非代码缺陷） |
| **TASK-014 影响** | 无 — TASK-014 禁止导入 Dify |

**现状**:

`data/dify/document-map.json` 是 v002.5 economy 工作库的同步记录，36 个条目以非 canonical 键存储。
该文件**禁止迁移、覆盖或用于正式库**。正式 `high_quality` Dataset 必须使用独立新 map
（如 `data/dify/document-map-v1.json`）。

**风险**:

如果 TASK-015/016 的同步代码或 CLI 默认指向旧 `document-map.json`，会导致：
1. 旧 map 中的 non-canonical 键与 v002.6 canonical ID 不匹配 → 36 个 duplicate create
2. 旧 map 中的 `dataset_id` 指向 economy 工作库 → 正式文档被导入错误 Dataset
3. 旧 map 被覆写 → v002.5 工作库的同步记录丢失

**防护要求**（TASK-015 必须实现）:

1. `sync_markdown_dir` / CLI 新增 `--map-path` 显式参数，默认值不得指向旧 map
2. map 中已有 `dataset_id` 且与目标 Dataset 不一致时 **fail-fast**
3. 正式同步不能静默使用旧默认 map
4. 禁止修改已有 economy 工作库及其 36 篇文档

**验证方式**:

```text
# TASK-015/016 前确认：
# 1. 正式同步使用独立 map 路径
# 2. map 中 dataset_id 与目标 Dataset 一致
# 3. 旧 map 和 economy Dataset 未被修改
```

---

## 三、中等问题（P2 — 建议修复）

### 2. Pipeline audit 归一化使用内联逻辑而非专用函数

| 项 | 值 |
|---|---|
| **文件** | `src/course_video_analyzer/knowledge/afeng_pipeline.py:148-154` |
| **严重性** | MEDIUM |

`_load_and_normalize_fidelity_audit` 直接调用 `canonical_knowledge_id()` 写入 `knowledge_id`：

```python
# afeng_pipeline.py:153 — 内联 canonicalization
"knowledge_id": canonical_knowledge_id(audit.course_id, audit.case_id),
```

而 draft 和 publication 分别使用专用 normalize 函数：

```python
# afeng_pipeline.py:121 — draft 使用专用函数
normalized = normalize_method_knowledge_id(normalized)

# afeng_pipeline.py:381 — publication 使用专用函数
publication = normalize_publication_knowledge_id(publication_raw)
```

`normalize_fidelity_audit_knowledge_id` 存在于 `afeng.py:110-115` 但 pipeline 不导入。
uncommitted diff 显式移除了该 import（原 commit 有，工作树删除）。

- **功能正确性**: ✅ 行为完全等价
- **维护风险**: canonical 逻辑变更需同步修改两处

### 3. `source_summary` 存储文件路径而非可读摘要

| 项 | 值 |
|---|---|
| **文件** | `src/course_video_analyzer/knowledge/afeng_dify.py:202` |
| **严重性** | MEDIUM |

```python
"source_summary": str(summary_path.resolve()),
# → "D:\Dev\VideoCaptioner\data\courses\C001\...\summary.json"
```

TASK-013 spec 要求每份文档包含 `source_summary`。当前实现存储绝对路径。
技术上满足字面要求，但对下游消费（Dify metadata 过滤、人类阅读）不如可读摘要有用。

---

## 四、低等问题（P3 — 文档/风格）

### 4. TASK-013 完成说明引用了实际未使用的函数名

| 项 | 值 |
|---|---|
| **文件** | `docs/tasks/TASK-013-afeng-stable-identity.md:80` |

文档写 `normalize_fidelity_audit_knowledge_id` 在 pipeline 中使用，实际 pipeline 用内联 canonicalization。
不影响功能，但对后续维护者造成误导。

### 5. verify_bundle 不校验 source_summary 内容质量

| 项 | 值 |
|---|---|
| **文件** | `scripts/verify_afeng_release_bundle.py:58-61` |

校验器检查 `source_summary` 非空，不验证是否为有效路径或有意义摘要。
配合 #3（路径作为值），校验永远通过。

### 6. 纯换行符变更混入 diff

| 项 | 值 |
|---|---|
| **文件** | `CCSWITCH-NEXT-AFENG-DIFY-PRODUCTIONIZATION.md` 等 |

`git diff --stat` 显示 5 文件变更，部分为 CRLF↔LF 换行符差异。
建议提交前 `git diff --ignore-space-change` 确认无遗漏逻辑变更。

---

## 五、已确认正确的设计点

以下方面经审查确认正确，**无问题**：

| 维度 | 文件:行 | 结论 |
|---|---|---|
| canonical ID 生成 | `afeng.py:91-99` | ✅ `AFENG-{course_id}-{case_id}` 格式正确 |
| draft 归一化 | `afeng_pipeline.py:121` | ✅ `normalize_method_knowledge_id` 正确调用 |
| audit 归一化 | `afeng_pipeline.py:153` | ✅ 内联 `canonical_knowledge_id()` 行为正确 |
| publication 归一化 | `afeng_pipeline.py:381` | ✅ `normalize_publication_knowledge_id` 正确调用 |
| manifest canonical 赋值 | `afeng_pipeline.py:210,273` | ✅ 永远取 canonical |
| terminal 重跑 early-return | `afeng_pipeline.py:220-227` | ✅ 历史产物不被覆盖 |
| bundle builder canonical 化 | `afeng_dify.py:142-164` | ✅ 内存归一，原始 artifact 只读 |
| Markdown frontmatter 覆写 | `afeng_dify.py:78-98` | ✅ quoted + bare 格式均处理 |
| bundle 重复 canonical 检测 | `afeng_dify.py:181-184` | ✅ 同 canonical 不同内容 → raise |
| dify_sync canonical 幂等键 | `dify_sync.py:243-246` | ✅ course+case 在场时覆盖 knowledge_id |
| create/update/skip 逻辑 | `dify_sync.py:297-309` | ✅ 同 ID + 同内容 → skip，不同内容 → update |
| 模型 knowledge_id 覆盖路径 | 全链路 | ✅ 不存在 — 所有层均强制 canonical |
| verify_bundle 校验 | `verify_afeng_release_bundle.py:38-87` | ✅ canonical 正则 + 唯一性 + lineage + SHA-256 + frontmatter |
| 测试覆盖 | test_afeng/dify/sync.py | ✅ 覆盖 canonical 格式、乱写 ID、pipeline、bundle、幂等键 |

### 全链路 canonical ID 流转验证

```
evidence package (course_id, case_id)
    │
    ▼
canonical_knowledge_id() ──→ "AFENG-C001-CASE-C001-001"
    │
    ├──▶ manifest.knowledge_id          (afeng_pipeline.py:210,273)
    ├──▶ draft.knowledge_id             (normalize_method_knowledge_id, afeng_pipeline.py:121)
    ├──▶ audit.knowledge_id             (inline canonical_knowledge_id, afeng_pipeline.py:153)
    ├──▶ publication.knowledge_id       (normalize_publication_knowledge_id, afeng_pipeline.py:381)
    ├──▶ markdown frontmatter           (render_afeng_markdown uses approved.knowledge_id)
    ├──▶ bundle document                (afeng_dify.py:142 canonical override)
    ├──▶ bundle markdown frontmatter    (_canonicalize_markdown, afeng_dify.py:78)
    └──▶ dify_sync map key              (_metadata_from_markdown, dify_sync.py:243)
         全部一致 ✅
```

---

## 六、未提交差异审查

| 文件 | 变更内容 | 风险 |
|---|---|---|
| `afeng_pipeline.py` | 移除 `normalize_fidelity_audit_knowledge_id` import | 低 — 函数未使用 |
| `verify_afeng_release_bundle.py` | `sys` → `Any` import 修正, `dict[str,object]` → `dict[str,Any]` | 无 |
| `TASK-013-afeng-stable-identity.md` | 状态改为"已完成"，新增完成说明 | 无 |
| `STATUS.md` | 新增 TASK-013 完成记录 | 无 |
| `CCSWITCH-NEXT-*.md` | 标记为历史记录，指向新交接文件 | 无 |

所有未提交差异为文档收尾和类型注解修正，无逻辑变更。

---

## 七、TASK-014 前后应重点验证的风险

| 风险 | 时机 | 建议验证方式 |
|---|---|---|
| v002.6 bundle 构建正确性 | TASK-014 执行中 | `verify_afeng_release_bundle.py` 校验 36 文档 canonical 唯一 + lineage 100% |
| dry-run 计数 | TASK-014 执行中 | `plan_markdown_sync` 预期 create=36, skip=0 |
| **⚠️ 误复用旧 map** | **TASK-015/016 前** | 正式同步使用独立 map + fail-fast 校验 dataset_id |
| Dify API update 幂等性 | TASK-015/016 | 少量文档手动 update + re-index 测试 |
| 263 tests baseline | 随时 | `uv run pytest -q` 全量 |

---

## 八、总结

| 级别 | 数量 | 阻塞 TASK-014？ | 阻塞 TASK-015/016？ |
|---|---|---|---|
| HIGH | 1 | **否** | 配置风险 — 需 TASK-015 实现 fail-fast 防护 |
| P2 MEDIUM | 2 | 否 | 否 |
| P3 LOW | 3 | 否 | 否 |

**结论**:

1. TASK-013 的 canonical ID 实现**在代码层面正确且完整**，全链路一致，无模型 knowledge_id 回退覆盖路径。
2. **TASK-014 可以立即执行**，无阻断问题。
3. 高风险项是配置层面的误复用旧 map 风险：`data/dify/document-map.json` 属于 v002.5 economy 工作库，禁止迁移或覆盖。正式 `high_quality` Dataset 必须使用独立新 map，TASK-015 须实现 fail-fast 防护。
4. 未提交差异为文档收尾，建议提交。

# 阿峰生产终审报告

审计类型：afeng-production-final
生成时间：2026-07-18

## 总览

**结果：PASS**

## 完成度明细

| 层 | 状态 | 证据 |
|---|---|---|
| code_complete | ✅ | pytest 280 passed, ruff 0 errors, pyright 0 errors |
| provider_ready | ✅ | Ollama bge-m3 (embedding) + DeepSeek (LLM) |
| dataset_created | ✅ | 阿峰课程方法库-研究版-v1, high_quality |
| documents_ingested | ✅ | 36 canonical documents in v1 Dataset |
| indexing_completed | ✅ | 36/36 completed |
| retrieval_passed | ✅ | hybrid_search Top-5 18/20 (90%), document-level dedup |
| app_deployed | ✅ | 阿峰 advanced-chat, published |
| app_acceptance_passed | ✅ | 20/20 (100%) |
| backup_manifest_ready | ✅ | 90 artifacts catalogued |
| restore_dry_run_passed | ✅ | create=0, update=0, skip=36 |

## 在线不变量

| 不变量 | 值 |
|---|---|
| bundle documents | 36 |
| exclusions | 4 |
| canonical map keys | 36 |
| remote documents | 36 |
| indexing completed | 36 |
| duplicate canonical | 0 |
| stale map | 0 |
| exclusion leakage | 0 |
| retrieval Top-5 | 18/20 (90%) |
| application acceptance | 20/20 (100%) |

## 剩余阻塞

无。

## 检查项

| Section | Status |
|---|---|
| aggregate | PASS |
| bundle | PASS |
| map | PASS |
| remote | PASS |
| app | PASS |
| reports | PASS |

### aggregate

- case_count: PASS
- published: PASS
- manual_review: PASS
- rejected: PASS
- failure_count: PASS
- status_complete: PASS
- sum_check: PASS

### bundle

- document_count: PASS
- exclusion_count: PASS
- canonical_unique: PASS
- canonical_format: PASS
- content_hash_match: PASS
- missing_files: 0
- hash_mismatch: 0
- lineage_coverage: PASS
- source_time_range: PASS
- evidence_ids: PASS
- exclusion_statuses: PASS

### map

- key_count: PASS
- all_canonical: PASS
- no_duplicates: PASS
- dataset_id_match: PASS
- no_smoke: PASS
- all_have_document_id: PASS
- all_have_content_sha256: PASS

### remote

- dataset_exists: PASS
- document_count: PASS
- indexing_technique: PASS
- embedding_model: PASS
- embedding_provider: PASS
- indexing_completed: PASS
- remote_names_match_map: PASS
- remote_count: PASS
- exclusion_leakage: PASS

### app

- app_exists: PASS
- workflow_published: PASS
- has_retrieval_node: PASS
- has_llm_node: PASS
- has_deepseek_llm: PASS
- dataset_bound_to_formal: PASS
- has_citation_validation: PASS

### reports

- retrieval_report_exists: PASS
- retrieval_accuracy: 90.0
- retrieval_18_of_20: PASS
- app_report_exists: PASS
- app_report_format: markdown


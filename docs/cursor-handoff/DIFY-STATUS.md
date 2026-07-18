# Dify 状态报告

最后更新：2026-07-18

## 总览

| 项 | 状态 |
|---|---|
| Docker 部署 | **已完成**（Dify 1.15.0，HTTP 3080，cpa 8317 未改动） |
| 管理员 | **已完成**（凭据仅在 secrets） |
| Embedding | **已完成**（Ollama bge-m3，1024 维） |
| LLM | **已完成**（DeepSeek deepseek-chat） |
| 正式 Dataset | **已完成**（`阿峰课程方法库-研究版-v1`，high_quality，36 docs） |
| 文档同步 | **已完成**（v002.6 → v1 Dataset，create=36，indexing 36/36 completed） |
| 检索验收 | **已完成**（hybrid_search, Top-5 18/20 = 90%，文档级去重） |
| 应用 | **已完成**（`阿峰` advanced-chat，已发布，绑定 v1 Dataset + DeepSeek） |
| 应用验收 | **已完成**（20/20 = 100%） |
| 生产审计 | **已完成**（overall=PASS） |

## 正式 Dataset

| 项 | 值 |
|---|---|
| 名称 | 阿峰课程方法库-研究版-v1 |
| 模式 | high_quality |
| Embedding | bge-m3 (langgenius/ollama/ollama) |
| 文档数 | 36 |
| 索引 | 36/36 completed |
| Map | data/dify/document-map-v1.json (36 canonical IDs) |

## 历史 Dataset（保留，不修改）

| 名称 | 模式 | 用途 |
|---|---|---|
| 阿峰课程方法库-研究版 | economy | 历史工作库（v002.5，36 docs） |

## 应用

| 项 | 值 |
|---|---|
| 名称 | 阿峰 |
| 模式 | advanced-chat（已发布） |
| Dataset | 阿峰课程方法库-研究版-v1 |
| LLM | DeepSeek deepseek-chat |
| 工作流 | start → knowledge-retrieval → citation-validation → llm → answer |

## 生产审计

```
overall: PASS
aggregate: PASS (40 cases = 36 published + 2 manual_review + 2 rejected)
bundle: PASS (36 docs, 4 excluded, canonical unique, lineage 100%)
map: PASS (36 canonical keys, dataset_id match)
remote: PASS (36 docs, high_quality, bge-m3, indexing completed)
app: PASS (published, DeepSeek LLM, dataset bound, citation validation)
reports: PASS (retrieval 18/20, app 20/20)
```

## 运维

详见 `docs/operations/afeng-operations-manual.md`

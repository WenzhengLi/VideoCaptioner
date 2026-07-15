# P04 Extract — 单案例知识提取

每次只处理一个 P03 案例。严格区分实际发生的内容、讲师观点和可能解释。

输出字段：`case_id`、`summary`、`participants`、`timeline`、`observations`、
`instructor_claims`、`alternative_explanations`、`outcomes`、`quoted_expressions`、
`evidence_spans`、`uncertainties`、`confidence`。

每条 observation、claim、explanation 和 outcome 必须带独立 evidence ID。不得把对方的心理、
意图或“潜台词”写成确定事实。表达方式只作为课程原句和分析对象保存，不自动升级为建议。

# TASK-020B1：C021 单课 P01–P04 事实证据试跑

## 状态

待执行；依赖 TASK-020A 提交推送。

## 目标

使用 C021 已归档的 raw transcript、说话人、板书 OCR 和时间轴，完成 knowledge-v003 的 P01–P04 事实证据链。先验证一门长课，再决定是否批量处理 C022–C025。

## 必须完成

1. 对 raw transcript 做人工抽样，覆盖开头、中段、结尾及板书密集区；
2. 生成 P01 deterministic baseline、Claude 复核结果和 P01 QA；
3. 生成 P02 baseline、compact review pack、Claude review decisions、最终 P02 和 QA；
4. 生成 P03 compact input、案例边界输出和 QA；
5. 对每个 P03 案例生成独立 P04 input、P04 evidence 和 QA；
6. P04 evidence 必须完全位于对应案例边界内，案例外 evidence=0；
7. 建立 C021 evidence baseline 和 JSON/Markdown 质量报告；
8. 全量 Ruff、Pyright、pytest 通过后显式提交并推送。

## 验收标准

- raw 人工抽样无系统性乱码、错时轴或整段缺失；
- P01/P02/P03 QA 均 pass；
- P03 至少识别一个案例；若确实无案例，必须提供证据并进入人工复核，不得生成空成功；
- 所有 P04 QA pass；
- unknown/unassigned 比例在报告中量化，不得隐藏；
- P04 案例外 evidence=0；
- 不修改 C001–C020，不进入方法层或 Dify。

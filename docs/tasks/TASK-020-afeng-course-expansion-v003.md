# TASK-020：阿峰第二期课程扩展试点（v003.0）

## 状态

规划中；仅在 TASK-019 完成并推送后启动。第一执行单元为 TASK-020A。

## 目标

在不修改前 20 课 v002.6/v002.7 基线的前提下，选择后续 5 门课程做 C021–C025 试点，验证现有视频证据提取、方法审查、发布、Dify 增量同步和应用验收能否稳定扩展。

## 阶段

1. **TASK-020A 源锁定与视频分析**：冻结 C021–C025 SHA-256、ffprobe 信息和独立批次，完成 ASR/说话人/OCR/时间轴及 raw QA；
2. **TASK-020B 事实证据层**：生成并校验 P01–P04，建立 C021–C025 evidence baseline，案例外 evidence=0；
3. **TASK-020C 方法层**：构建证据包，调用已批准的外部模型生成 draft/audit/publication，人工审查 manual_review/rejected；
4. **TASK-020D v003.0 发布试点**：新建 `afeng-release-v003.0`，禁止覆盖任何 v002.x；
5. **TASK-020E 检索与应用回归**：先在临时 Dataset 索引，扩展冻结测试集；旧 20 问不得回退，再决定是否增量同步正式 Dataset；
6. 将生产审计计数从硬编码 36 改为以冻结 manifest 为准，同时保留第一期基线报告。

## 已确认输入

| Course | 标题 | 原视频 | 大小 |
|---|---|---:|---:|
| C021 | 近期惊喜的爱情案例聊天记录详解 | 存在 | 666,723,275 bytes |
| C022 | 奔驰白富美开车来接我去 hotel | 存在 | 639,573,095 bytes |
| C023 | 与女 DJ 的爱恨纠葛 | 存在 | 702,292,893 bytes |
| C024 | 欢迎来到对抗路 | 存在 | 822,416,575 bytes |
| C025 | 珠海展示面线下回顾及截胡案例 | 存在 | 536,277,213 bytes |

合计 3,367,283,051 bytes（约 3.14 GiB）。五课 `source.json.sha256` 均为空，课程目录除 `source.json` 外没有现有产物。

## 硬闸门

- 第一阶段旧 20 课回归：检索不低于 18/20，应用保持 20/20；
- 新课程 published/manual_review/rejected 分类完整；
- 新文档 lineage、source time range、evidence IDs 覆盖率 100%；
- 临时 Dataset 无重复 canonical、无 exclusion leakage；
- 未达到门槛时不得更新正式 Dataset。

## 禁止事项

- 不覆盖 v002.6/v002.7；
- 不修改已发布 C001–C020 的正文来迎合新测试；
- 不一次性扩全部剩余课程，先完成 5 门试点；
- 不让 LLM 猜测缺失证据；
- 不在 TASK-019 未完成前启动。

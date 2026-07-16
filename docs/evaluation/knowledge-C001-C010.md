# 知识库质量报告 C001-C010

- output_version: `knowledge-v002`
- courses: 10
- total_segments: 43549
- total_cases: 19
- total_entries: 393
- total_risks: 146

| Course | Segments | Unknown% | Cases | Unassigned% | Risks | Entries | MD | QA |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| C001 | 3459 | 5.5 | 3 | 6.0 | 17 | 40 | 40 | check |
| C002 | 4272 | 4.6 | 3 | 19.7 | 20 | 54 | 54 | pass |
| C003 | 4679 | 6.3 | 2 | 40.4 | 14 | 46 | 46 | pass |
| C004 | 5161 | 6.0 | 2 | 12.4 | 16 | 45 | 45 | pass |
| C005 | 3589 | 6.3 | 2 | 3.9 | 18 | 47 | 47 | pass |
| C006 | 5620 | 6.5 | 2 | 4.6 | 17 | 49 | 49 | pass |
| C007 | 3738 | 12.2 | 1 | 14.0 | 8 | 22 | 22 | pass |
| C008 | 3823 | 6.1 | 2 | 26.0 | 18 | 46 | 46 | pass |
| C009 | 5870 | 5.0 | 1 | 19.1 | 9 | 22 | 22 | pass |
| C010 | 3338 | 7.2 | 1 | 10.6 | 9 | 22 | 22 | pass |

机器可读完整结果见同名 `.json`。

## 抽检与系统发现（2026-07-16）

### 统计修复
- 质量报告脚本此前将 unassigned_ratio 误算为 100%（P03 使用 start/end_segment_id，无 segment_ids 列表）。
- P05 safety_flags 位于案例顶层，此前扫描 
eviews/items 导致 risks=0；现已计入，前 10 课合计 **146** 条安全标记。

### 逐课要点
- C001：P01-knowledge-v002-qa.json 缺失（raw/P02/P03 pass）；归档号为 RUN-20260715-BASELINE。
- C003：未分配比例 **40.4%**，显著偏高，优先作为 P03 边界回归样本。
- C007：unknown speaker **12.2%**，高于其他课（约 5–7%）。
- C008：未分配 **26.0%**；C002 **19.7%**；C009 **19.1%**。
- 安全标记分布含 age_uncertainty/age_unknown、guilt_and_pressure_tactics、explicit_refusal、privacy_* 等；检索抽检可见拒绝/边界类条目（含 C006 overnight refusal）。

### Markdown 抽检
- 抽检条目中可见「不得把拒绝重写为推进技巧 / instructor_claims」约束语句；未发现把明确拒绝包装成可推荐话术的通过项。
- 启发式命中 2 条含「必然/测试」字样，复核为否定性约束或 ALT 不确定表述，非危险技巧推荐。

### Prompt 迭代判断
- 系统性问题主要是 **P03 案例覆盖不足（高 unassigned）** 与报告统计缺陷，而非安全标签整体缺失。
- 不改写 v002；后续复制为 knowledge-v003，优先加强 P03 全覆盖与高 unknown 课的说话人保留规则，并对固定集 C001–C010 回归后再决定是否采用。


# 事实与证据层质量报告 C001-C015

- output_version: `knowledge-v002`
- courses: 15
- total_segments: 64184
- total_cases: 29
- total_p04_files: 29
- evidence_qa_all_pass: True
- flagged_courses: 6

> 本报告聚焦 raw / P01–P04。下列 P05/P06 数字仅为历史信息，不作为本次完成标准。
> historical p06_entries=616, p05_risks=230

| Course | Segs | Unk% | Cases | Unass% | P04 | OCR | Cache | Dedup | Fail | EvQA | Flags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| C001 | 3459 | 5.5 | 3 | 6.0 | 3 | n/a | n/a | n/a | 0 | pass | - |
| C002 | 4272 | 4.6 | 3 | 19.7 | 3 | 610 | 0 | 341 | 0 | pass | - |
| C003 | 4679 | 6.3 | 2 | 40.4 | 2 | 624 | 0 | 338 | 0 | pass | high_unassigned_gt_20pct |
| C004 | 5161 | 6.0 | 2 | 12.4 | 2 | 602 | 0 | 341 | 0 | pass | - |
| C005 | 3589 | 6.3 | 2 | 3.9 | 2 | 517 | 0 | 262 | 0 | pass | - |
| C006 | 5620 | 6.5 | 2 | 4.6 | 2 | 681 | 0 | 424 | 0 | pass | - |
| C007 | 3738 | 12.2 | 1 | 14.0 | 1 | 645 | 0 | 428 | 0 | pass | high_unknown_speaker,case_boundaries_possibly_too_wide |
| C008 | 3823 | 6.1 | 2 | 26.0 | 2 | 623 | 0 | 240 | 0 | pass | high_unassigned_gt_20pct |
| C009 | 5870 | 5.0 | 1 | 19.1 | 1 | 695 | 0 | 333 | 0 | pass | - |
| C010 | 3338 | 7.2 | 1 | 10.6 | 1 | 593 | 0 | 252 | 0 | pass | case_boundaries_possibly_too_wide |
| C011 | 3577 | 7.3 | 3 | 18.6 | 3 | 637 | 0 | 275 | 0 | pass | - |
| C012 | 2952 | 5.9 | 1 | 54.0 | 1 | 506 | 0 | 237 | 0 | pass | high_unassigned_gt_20pct,case_boundaries_possibly_too_narrow |
| C013 | 4151 | 5.3 | 2 | 9.0 | 2 | 644 | 0 | 250 | 0 | pass | - |
| C014 | 4757 | 3.7 | 2 | 5.2 | 2 | 516 | 0 | 223 | 0 | pass | - |
| C015 | 5198 | 3.2 | 2 | 29.4 | 2 | 592 | 0 | 174 | 0 | pass | high_unassigned_gt_20pct,ocr_ratio_high_vs_boards |

## 特别标记

- **C003**: high_unassigned_gt_20pct
- **C007**: high_unknown_speaker, case_boundaries_possibly_too_wide
- **C008**: high_unassigned_gt_20pct
- **C010**: case_boundaries_possibly_too_wide
- **C012**: high_unassigned_gt_20pct, case_boundaries_possibly_too_narrow
- **C015**: high_unassigned_gt_20pct, ocr_ratio_high_vs_boards

## 视频阶段耗时（秒）

| Course | media | transcript | diarization | alignment | board_detect | board_track | board_ocr | merge | export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C001 | 2.0 | 214.0 | 282.0 | 1.0 | 21.0 | 46.0 | 1459.0 | 1.0 | 2.0 |
| C002 | 3.0 | 359.0 | 403.0 | 2.0 | 33.0 | 83.0 | 1097.0 | 1.0 | 1.0 |
| C003 | 4.0 | 359.0 | 413.0 | 4.0 | 33.0 | 38.0 | 1199.0 | 2.0 | 4.0 |
| C004 | 4.0 | 398.0 | 440.0 | 4.0 | 31.0 | 33.0 | 990.0 | 2.0 | 2.0 |
| C005 | 2.0 | 291.0 | 330.0 | 1.0 | 23.0 | 35.0 | 924.0 | 1.0 | 2.0 |
| C006 | 4.0 | 506.0 | 441.0 | 4.0 | 30.0 | 41.0 | 1901.0 | 4.0 | 4.0 |
| C007 | 2.0 | 705.0 | 779.0 | 4.0 | 39.0 | 66.0 | 2468.0 | 3.0 | 20.0 |
| C008 | 3.0 | 689.0 | 784.0 | 4.0 | 36.0 | 60.0 | 1753.0 | 2.0 | 5.0 |
| C009 | 4.0 | 1023.0 | 1213.0 | 9.0 | 57.0 | 67.0 | 2255.0 | 4.0 | 7.0 |
| C010 | 2.0 | 604.0 | 729.0 | 3.0 | 37.0 | 90.0 | 2094.0 | 2.0 | 4.0 |
| C011 | 2.0 | 264.0 | 304.0 | 2.0 | 21.0 | 42.0 | 1437.0 | 2.0 | 4.0 |
| C012 | 2.0 | 206.0 | 251.0 | 1.0 | 22.0 | 67.0 | 1368.0 | 1.0 | 1.0 |
| C013 | 2.0 | 308.0 | 356.0 | 3.0 | 25.0 | 40.0 | 2070.0 | 2.0 | 6.0 |
| C014 | 3.0 | 791.0 | 999.0 | 5.0 | 71.0 | 102.0 | 2263.0 | 3.0 | 3.0 |
| C015 | 3.0 | 928.0 | 1145.0 | 6.0 | 59.0 | 65.0 | 2053.0 | 5.0 | 5.0 |

机器可读完整结果见同名 `.json`。

# C001–C020 事实与证据层质量报告

- baseline policy：`adopt_v003_hybrid`
- 课程：20；案例：40
- segments：80264；OCR segments：4121
- 全部 QA pass：`true`；失败：0

| Course | P01 | P02 | P03 | Segments | OCR | Unknown | Cases | Assigned | Unassigned | Raw/P01/P02/P03 | P04 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| C001 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 3459 | 175 | 5.52% | 3 | 3253 | 206 (5.96%) | pass/pass/pass/pass | 3/3 |
| C002 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 4272 | 172 | 4.61% | 3 | 3429 | 843 (19.73%) | pass/pass/pass/pass | 3/3 |
| C003 | knowledge-v002 | knowledge-v002 | knowledge-v003 | 4679 | 237 | 6.35% | 3 | 3702 | 977 (20.88%) | pass/pass/pass/pass | 3/3 |
| C004 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 5161 | 275 | 6.03% | 2 | 4519 | 642 (12.44%) | pass/pass/pass/pass | 2/2 |
| C005 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 3589 | 214 | 6.32% | 2 | 3451 | 138 (3.85%) | pass/pass/pass/pass | 2/2 |
| C006 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 5620 | 345 | 6.51% | 2 | 5359 | 261 (4.64%) | pass/pass/pass/pass | 2/2 |
| C007 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 3738 | 398 | 12.25% | 1 | 3213 | 525 (14.04%) | pass/pass/pass/pass | 1/1 |
| C008 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 3823 | 195 | 6.07% | 2 | 2828 | 995 (26.03%) | pass/pass/pass/pass | 2/2 |
| C009 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 5870 | 275 | 5.01% | 1 | 4746 | 1124 (19.15%) | pass/pass/pass/pass | 1/1 |
| C010 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 3338 | 224 | 7.19% | 1 | 2984 | 354 (10.61%) | pass/pass/pass/pass | 1/1 |
| C011 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 3577 | 249 | 7.30% | 3 | 2912 | 665 (18.59%) | pass/pass/pass/pass | 3/3 |
| C012 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 2952 | 164 | 5.93% | 1 | 1357 | 1595 (54.03%) | pass/pass/pass/pass | 1/1 |
| C013 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 4151 | 202 | 5.30% | 2 | 3776 | 375 (9.03%) | pass/pass/pass/pass | 2/2 |
| C014 | knowledge-v002 | knowledge-v002 | knowledge-v002 | 4757 | 168 | 3.72% | 2 | 4511 | 246 (5.17%) | pass/pass/pass/pass | 2/2 |
| C015 | knowledge-v002 | knowledge-v002 | knowledge-v003 | 5198 | 141 | 3.21% | 2 | 3876 | 1322 (25.43%) | pass/pass/pass/pass | 2/2 |
| C016 | knowledge-v003 | knowledge-v003 | knowledge-v003 | 4560 | 84 | 2.79% | 1 | 4413 | 147 (3.22%) | pass/pass/pass/pass | 1/1 |
| C017 | knowledge-v003 | knowledge-v003 | knowledge-v003 | 3317 | 207 | 6.78% | 1 | 3155 | 162 (4.88%) | pass/pass/pass/pass | 1/1 |
| C018 | knowledge-v003 | knowledge-v003 | knowledge-v003 | 1336 | 91 | 8.46% | 3 | 1267 | 69 (5.16%) | pass/pass/pass/pass | 3/3 |
| C019 | knowledge-v003 | knowledge-v003 | knowledge-v003 | 3724 | 189 | 6.39% | 2 | 3696 | 28 (0.75%) | pass/pass/pass/pass | 2/2 |
| C020 | knowledge-v003 | knowledge-v003 | knowledge-v003 | 3143 | 116 | 5.31% | 3 | 3106 | 37 (1.18%) | pass/pass/pass/pass | 3/3 |

## 验收

- [x] 20 课 raw QA 全部通过
- [x] P01/P02/P03 QA 全部通过
- [x] 40 个案例 P04 QA 全部通过
- [x] P03 assigned + unassigned 覆盖计数一致
- [x] P04 无案例外 evidence

## 已知不确定项

- `C001`：unknown speaker 5.52%；unassigned 5.96%；结构化 uncertainty 32 条。
- `C002`：unknown speaker 4.61%；unassigned 19.73%；结构化 uncertainty 59 条。
- `C003`：unknown speaker 6.35%；unassigned 20.88%；结构化 uncertainty 39 条。
- `C004`：unknown speaker 6.03%；unassigned 12.44%；结构化 uncertainty 49 条。
- `C005`：unknown speaker 6.32%；unassigned 3.85%；结构化 uncertainty 45 条。
- `C006`：unknown speaker 6.51%；unassigned 4.64%；结构化 uncertainty 45 条。
- `C007`：unknown speaker 12.25%；unassigned 14.04%；结构化 uncertainty 25 条。
- `C008`：unknown speaker 6.07%；unassigned 26.03%；结构化 uncertainty 32 条。
- `C009`：unknown speaker 5.01%；unassigned 19.15%；结构化 uncertainty 28 条。
- `C010`：unknown speaker 7.19%；unassigned 10.61%；结构化 uncertainty 43 条。
- `C011`：unknown speaker 7.30%；unassigned 18.59%；结构化 uncertainty 34 条。
- `C012`：unknown speaker 5.93%；unassigned 54.03%；结构化 uncertainty 21 条。
- `C013`：unknown speaker 5.30%；unassigned 9.03%；结构化 uncertainty 21 条。
- `C014`：unknown speaker 3.72%；unassigned 5.17%；结构化 uncertainty 34 条。
- `C015`：unknown speaker 3.21%；unassigned 25.43%；结构化 uncertainty 27 条。
- `C016`：unknown speaker 2.79%；unassigned 3.22%；结构化 uncertainty 21 条。
- `C017`：unknown speaker 6.78%；unassigned 4.88%；结构化 uncertainty 17 条。
- `C018`：unknown speaker 8.46%；unassigned 5.16%；结构化 uncertainty 12 条。
- `C019`：unknown speaker 6.39%；unassigned 0.75%；结构化 uncertainty 30 条。
- `C020`：unknown speaker 5.31%；unassigned 1.18%；结构化 uncertainty 33 条。

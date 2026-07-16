# P03 v002 vs v003 固定回归

- courses: C003, C008, C006, C010, C012, C015, C002
- adoption_recommendation: `adopt_v003_hybrid`

| Course | v002 cases | v003 cases | v002 unass% | v003 unass% | Δ unass% | coverage | QA v003 | risks |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| C003 | 2 | 3 | 40.4 | 20.9 | -19.5 | ok | pass | - |
| C008 | 2 | 2 | 26.0 | 26.0 | +0.0 | ok | pass | - |
| C006 | 2 | 2 | 4.6 | 4.3 | -0.4 | ok | pass | forced_ad_or_chatter |
| C010 | 1 | 1 | 10.6 | 10.6 | +0.0 | ok | pass | evidence_outside |
| C012 | 1 | 1 | 54.0 | 54.0 | +0.0 | ok | pass | evidence_outside |
| C015 | 2 | 2 | 29.4 | 25.4 | -4.0 | ok | pass | evidence_outside |
| C002 | 3 | 3 | 19.7 | 19.6 | -0.2 | ok | pass | evidence_outside |

## 逐课说明

### C003

- newly_assigned=914, newly_unassigned=0
- v003 cases: CASE-C003-001(861,partial); CASE-C003-002(2069,complete); CASE-C003-003(772,complete)

### C008

- newly_assigned=0, newly_unassigned=0
- v003 cases: CASE-C008-001(2050,complete); CASE-C008-002(778,complete)

### C006

- newly_assigned=21, newly_unassigned=1
- suspicious forced segments: 1 (see JSON)
- v003 cases: CASE-C006-001(2421,complete); CASE-C006-002(2958,complete)

### C010

- newly_assigned=0, newly_unassigned=0
- v003 cases: CASE-C010-001(2984,complete)

### C012

- newly_assigned=0, newly_unassigned=0
- v003 cases: CASE-C012-001(1357,complete)

### C015

- newly_assigned=208, newly_unassigned=0
- v003 cases: CASE-C015-001(1108,complete); CASE-C015-002(2768,complete)

### C002

- newly_assigned=8, newly_unassigned=0
- v003 cases: CASE-C002-001(3067,complete); CASE-C002-002(155,partial); CASE-C002-003(215,partial)

## 采用规则结论

固定高未分配课有改善且无基线硬退化；建议 hybrid：改善课用 v003，其余可暂留 v002；新课默认 v003。改善课=C003；警告：C006: soft ad/chatter heuristic hits=1; C010: boundary evidence cites outside-range segments; C012: boundary evidence cites outside-range segments; C015: boundary evidence cites outside-range segments; C002: boundary evidence cites outside-range segments

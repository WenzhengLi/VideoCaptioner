# C002–C018 课程研究层总验收

验收日期：2026-07-21

## 验收结论

C002–C018 的课程研究候选层已形成完整可审阅包，状态统一为 `pending_user_confirmation`。本轮没有把任何候选补足登记为正式 OB，也没有导入 Dify。

机械 source packet 层与课程研究层分开验收。严格导出器已恢复“P02 原始顺序逆序即失败”的门禁；当前相关正式 P02 均检出原始顺序逆序，因此机械层报告为 FAIL，不能用课程研究层通过来覆盖该失败。

## 原始材料覆盖

| 课程 | 正式 P02 | segments | 正式 P03 | cases | 候选 OB | 方向 | 主回复 |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| C002 | `P02-knowledge-v002.json` | 4,272 | `P03-knowledge-v003.json` | 3 | 14 | 56 | 168 |
| C003 | `P02-knowledge-v002.json` | 4,679 | `P03-knowledge-v003.json` | 3 | 17 | 68 | 204 |
| C004 | `P02-knowledge-v002.json` | 5,161 | `P03-knowledge-v002.json` | 2 | 17 | 68 | 204 |
| C005 | `P02-knowledge-v002.json` | 3,589 | `P03-knowledge-v002.json` | 2 | 20 | 80 | 240 |
| C006 | `P02-knowledge-v002.json` | 5,620 | `P03-knowledge-v003.json` | 2 | 20 | 80 | 240 |
| C007 | `P02-knowledge-v002.json` | 3,738 | `P03-knowledge-v002.json` | 1 | 12 | 48 | 144 |
| C008 | `P02-knowledge-v002.json` | 3,823 | `P03-knowledge-v003.json` | 2 | 10 | 40 | 120 |
| C009 | `P02-knowledge-v002.json` | 5,870 | `P03-knowledge-v002.json` | 1 | 11 | 44 | 132 |
| C010 | `P02-knowledge-v002.json` | 3,338 | `P03-knowledge-v002.json` | 1 | 10 | 40 | 120 |
| C011 | `P02-knowledge-v002.json` | 3,577 | `P03-knowledge-v002.json` | 3 | 10 | 40 | 120 |
| C012 | `P02-knowledge-v002.json` | 2,952 | `P03-knowledge-v002.json` | 1 | 11 | 44 | 132 |
| C013 | `P02-knowledge-v002.json` | 4,151 | `P03-knowledge-v002.json` | 2 | 14 | 56 | 168 |
| C014 | `P02-knowledge-v002.json` | 4,757 | `P03-knowledge-v002.json` | 2 | 12 | 48 | 144 |
| C015 | `P02-knowledge-v002.json` | 5,198 | `P03-knowledge-v003.json` | 2 | 12 | 48 | 144 |
| C016 | `P02-knowledge-v003.json` | 4,560 | `P03-knowledge-v003.json` | 1 | 10 | 40 | 120 |
| C017 | `P02-knowledge-v003.json` | 3,317 | `P03-knowledge-v003.json` | 1 | 10 | 40 | 120 |
| C018 | `P02-knowledge-v003.json` | 1,336 | `P03-knowledge-v003.json` | 3 | 9 | 36 | 108 |
| 合计 |  | 69,938 |  | 32 | 219 | 876 | 2,628 |

完整输入路径、角色计数、案例边界和读取说明见每课 `chat-coach/courses/<COURSE_ID>/source-manifest.md`。

## 结构门禁

| 检查项 | 结果 |
| --- | --- |
| C002–C018 每课 4 个分析文件 | PASS，68/68 |
| C002–C018 每课 6 个候选知识文件 | PASS，102/102 |
| OB 稳定锚点 | PASS，219 个，唯一 219 个 |
| `course_chain` | PASS，219/219 |
| `supplement_chain` | PASS，219/219 |
| 不同回复方向 | PASS，876 个，等于每个 OB 4 个 |
| 每方向至少 3 条主回复 | PASS，2,628 条；未发现不足 3 条的方向 |
| 课程对象到全局标签链接 | PASS，1,014 个链接，缺失锚点 0 |
| 全局标签到课程对象反链 | PASS，219/219 个 OB 至少有一条反链 |
| 用户批准状态 | PASS，批准命中 0；17 门均保持待确认 |
| 正式 OB 总索引 | PASS，正式 OB 仍为 0，符合“用户确认后才能登记” |

## 每课文件要求

分析工作区：

- `source-manifest.md`
- `content-map.md`
- `case-action-chains.md`
- `supplement-review.md`

候选知识目录：

- `课程索引.md`
- `课程内容.md`
- `案例动作链.md`
- `OB双链.md`
- `补足与确认.md`
- `召回问法.md`

以上文件在 C002–C018 均存在。候选知识目录只提供审阅入口和双链索引，不代表内容已获用户确认。

## 当前可进入的下一状态

课程研究层下一步是用户逐课确认或修改候选补足。确认前不得批量批准 OB、登记正式 OB 或进入 Dify。

机械层下一步是修正正式 P02 的原始 segment 顺序，保留 segment 集合与 ID 不变，然后重新执行 source packet 导出、跨秒 hash 比较和总报告验收。

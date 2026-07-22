---
record_type: ob_template
schema_version: chat-coach-ob-v1
template_status: active
minimum_reply_directions: 3
minimum_examples_per_direction: 3
minimum_next_lines_per_response_branch: 2
required_response_branches:
  - positive
  - concern
  - topic_shift
  - low_investment
---

# OB 模板定义

OB 是一个可以独立召回和回答的完整聊天场景，不是课程摘要、心理标签或一句孤立话术。每个 OB 只处理一个主要场景；同一句女生原话存在明显不同动因时，可以在一个 OB 中保留多个判断分支，也可以因关系阶段不同拆成多个 OB。

## 一、文件与状态

- 候选文件：`OB原型/OB/<COURSE_ID>/<OBJECT_ID>.md`。
- 正式文件：只能在用户逐课确认后进入 `ob-knowledge-base/`。
- `approval_status` 只允许：`pending_user_confirmation`、`needs_revision`、`user_approved`、`user_rejected`。
- 模板通过不代表课程内容已批准；结构确认与内容确认分别记录。

## 二、Frontmatter 模板

```yaml
---
record_type: ob
schema_version: chat-coach-ob-v1
object_id: OB-C000-001
course_id: C000
title: 场景标题
scene: 关系阶段与具体场景
female_line: 女生在案例中的关键原话
female_line_variants:
  - 口语近义问法一
  - 口语近义问法二
instructor_judgment: 讲师对该句和上下文的核心判断
reply_directions:
  - 回答方向 A
  - 回答方向 B
  - 回答方向 C
reply_category_count: 3
example_count: 9
branch_example_count: 8
course_answer_count: 1
course_answer_types:
  - actual_case_reply
approval_status: pending_user_confirmation
tag_ids:
  - TAG-STAGE-EXAMPLE
  - TAG-SCENE-EXAMPLE
source_case_ids:
  - CASE-C000-001
source_segment_ids:
  - SEG-C000-000001
source_documents:
  - source-material/C000/课程原文.md
  - source-material/C000/聊天原话.md
  - source-material/C000/讲师原话.md
  - source-material/C000/课板原文.md
  - source-material/C000/案例边界.md
  - source-material/C000/提取校验.md
---
```

## 三、正文模板

```markdown
# <OBJECT_ID>｜<场景标题>

课程：[[OB原型/课程/<COURSE_ID>/课程主页|<COURSE_ID>]]

标签：[[OB原型/标签/<TAG_ID>|标签名]]

## 01｜课程事实入口

依次链接：课程原文、聊天原话、讲师原话、课板原文、案例边界、提取校验。

## 02｜场景与完整上下文

- 关系阶段：
- 前文发生了什么：
- 女生投入信号：
- 已经存在的顾虑：
- 男生此前采取的动作：

## 03｜女生原话与可能动因

- 女生原话：
- 课程内主要动因：
- 课程内其他可能含义：
- 区分这些含义要观察的信号：

候选补充动因必须明确写“候选补足”，不得伪装成讲师判断。

## 04｜讲师判断

- 讲师如何理解：
- 判断依据：
- 讲师在该节点关注的窗口、顾虑或测试：

## 05｜课程解题步骤

1. 先判断女生这句话在解决什么问题，而不是先想一句话术；
2. 列出讲师读取到的动因、顾虑、窗口或测试；
3. 写出支撑判断的前文信号；
4. 写出当前节点的沟通目标；
5. 写出讲师选择的动作以及为什么选这个动作；
6. 写出动作如何进入课程回答；
7. 写出女生回应后，讲师如何决定下一步。

不得用分析者自己的通用建议替代讲师的解题过程。

## 06｜课程给出的回答

每条课程回答必须标明以下类型之一：

- `actual_case_reply`：聊天案例中实际发出的回答；
- `instructor_recommended_reply`：讲师明确建议的回答；
- `instructor_reconstruction`：讲师复述或重构的回答；
- `no_single_reply`：课程只给判断或动作，没有给出一句完整回答。

每条回答必须同时写出：原文、规范化文本、segment/time、回答中每一部分承担的功能，以及女生实际反应。课程没有完整回答时必须写 `no_single_reply`，不能用候选补足冒充课程回答。

## 07｜课程原链 `course_chain`

场景 → 女生原话 → 讲师判断 → 课程动作 → 课程说法 → 女生反应 → 课程下一步。

每个节点写出实际内容；缺失节点标为“课程未展开”，不得补写成课程事实。

## 08｜我们的补足策略链 `supplement_chain`

- 课程没有展开的缺口：
- 当前沟通目标：
- 候选补足理由：

### 方向 A｜<方向名>

- 目的：
- 适用信号：
- 不适用情境：
- 表达强度：轻 / 中 / 强
- 推拉结构：哪一部分在后撤、筛选或调侃，哪一部分在拉近、保留意图或描绘共同画面
- 示例：
  1.
  2.
  3.

方向 B、C 及更多方向保持同样结构。方向之间必须是不同策略，不得只替换近义词。

## 09｜对方不同回应后的下一句

### 积极回应

1.
2.

### 继续顾虑

1.
2.

### 转移话题

1.
2.

### 降低投入

1.
2.

## 10｜召回问法

- 原句近义表达：
- 用户可能的口语提问：
- 需要追问的上下文：

## 11｜来源边界与确认

- 课程事实：注明案例、时间段或 segment。
- 讲师原话：只记录能在讲师原话中找到的判断。
- 候选补足：列出分析者新增的动因、方向、示例和后续分支。
- 用户修改：
- 确认状态：待用户确认。
```

## 四、质量门禁

一个 OB 只有同时满足下列条件，才算“候选稿完整”：

1. 六份事实材料均可点击，案例边界与来源 ID 存在；
2. 女生原话、完整上下文、讲师判断、课程动作和课程说法没有混写；
3. 先完整写出课程的解题步骤，再出现任何候选补足示例；
4. 课程实际回答、讲师建议回答、讲师复原和“没有单句回答”四种情况明确区分；
5. 每条课程回答都能回到 segment/time，并逐段解释它承担的功能；
6. `course_chain` 七个节点逐项填写，课程未讲的部分明确留空；
7. 至少三个真正不同的候选回答方向，每方向至少三条自然表达；
8. 每方向写明目的、适用信号、不适用情境、表达强度和推拉结构；避免写成客服式解释、单方面讨好或直接索取答案；
9. 积极、顾虑、转移、降投四个分支各至少两条可直接使用的下一句；
10. 召回问法包含原句近义表达和上下文追问，不能只堆关键词；
11. 所有标签都有独立标签文件，并与 OB 建立双向链接；
12. frontmatter 计数与正文实际数量一致；
13. 课程事实与候选补足边界清楚，且状态保持待用户确认。

只有用户明确确认本课内容后，才允许将 `approval_status` 改为 `user_approved`，登记正式 OB 或进入 Dify。

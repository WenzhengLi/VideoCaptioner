# 聊天知识对象与双链结构

新体系的可复制字段、正文结构和质量门禁统一以 [OB 模板](OB原型/_模板/OB模板.md) 为准；本文件说明对象语义和标签维度。模板确认不等于课程内容自动批准。

正式目录结构、标签注册和课程文件模板现维护在 [OB 正式知识库](ob-knowledge-base/README.md)。本文件继续说明对象语义；正式标签以 [课程场景标签](ob-knowledge-base/课程场景标签.md) 为唯一注册表。

## 目标

每个知识对象（OB，Object）描述一个可以独立检索和回答的聊天场景。对象不是一句孤立话术，也不是一个概念标签，而是一段完整的心理判断与互动链路。

同一句话可以进入多个对象；同一个对象也可以拥有多个标签。标签只负责标记和检索场景，最终回答必须展开自然语言分析、多个说话方向、具体示例和后续分支。

## 双链

### 课程原链 `course_chain`

```text
场景与阶段
→ 女生原话
→ 讲师对心理和信号的判断
→ 讲师选择的动作
→ 讲师或案例中的具体说法
→ 女生后续反应
→ 课程继续采取的动作
```

这条链只还原课程，不加入补足建议。

### 补足策略链 `supplement_chain`

```text
同一场景
→ 课程未展开的心理分支或表达缺口
→ 当前沟通目标
→ 可选策略方向
→ 每个方向的多条说法
→ 女生不同回应
→ 对应的下一轮动作和回复
```

这条链用于扩展可选性。它延续讲师的主动进攻、占有感、吸引、推拉和框架逻辑，同时保留明确底线：不强迫、不欺骗、不无视明确拒绝。

## 标签维度

一个对象可以同时拥有多个标签。标签使用 `维度:值` 格式。

### `stage`：关系阶段

- `stage:破冰`
- `stage:建立吸引`
- `stage:暧昧升温`
- `stage:邀约`
- `stage:邀约落地`
- `stage:见面`
- `stage:关系升级`
- `stage:价值筛选`
- `stage:快速建立吸引`

### `scene`：场景

- `scene:状态分享`
- `scene:快速邀约`
- `scene:私密地点邀约`
- `scene:认识时间顾虑`
- `scene:安全感不足`
- `scene:真实性测试`
- `scene:称呼测试`
- `scene:邀约内容确认`
- `scene:地点确认`
- `scene:短期意图确认`
- `scene:竞争者出现`
- `scene:主动报备`
- `scene:后撤后追投`
- `scene:旧资源重启`
- `scene:生活方式分享`
- `scene:未来场景`
- `scene:单身原因测试`
- `scene:价值测试`
- `scene:时间顾虑`
- `scene:门禁顾虑`
- `scene:首次见面`
- `scene:关系确认测试`
- `scene:回复节奏`
- `scene:金钱观测试`
- `scene:付出测试`
- `scene:性感展示`
- `scene:模糊延期`
- `scene:上车`

### `signal`：女生信号

- `signal:持续回复`
- `signal:黄灯`
- `signal:主动追问`
- `signal:主动报备`
- `signal:长消息`
- `signal:时间投入`
- `signal:顾虑表达`
- `signal:害羞防御`
- `signal:窗口上升`
- `signal:行动配合`
- `signal:重新回复`
- `signal:主动抛关系话题`
- `signal:低承诺回复`
- `signal:眼神反应`
- `signal:注意力投入`

### `psychology`：课程内心理判断

- `psychology:有兴趣但犹豫`
- `psychology:需要被说服`
- `psychology:需要安全感`
- `psychology:确认特殊性`
- `psychology:确认认真程度`
- `psychology:确认真实目的`
- `psychology:观察男生框架`
- `psychology:制造危机感`
- `psychology:期待行动证明`
- `psychology:想靠近又防御`
- `psychology:重新观察男生`
- `psychology:确认男生是否抢手`
- `psychology:确认关系能力`
- `psychology:让男生先表态`
- `psychology:确认现实投入`
- `psychology:确认长期价值`
- `psychology:观察男生胆量`
- `psychology:窗口不足或优先级低`
- `psychology:线下重新评估`

### `action`：沟通动作

- `action:分享`
- `action:邀约`
- `action:场景描绘`
- `action:提供筹码`
- `action:框架转换`
- `action:价值观植入`
- `action:行动证明`
- `action:表达特殊性`
- `action:补安全感`
- `action:给选择`
- `action:给台阶`
- `action:推近`
- `action:后撤`
- `action:推拉`
- `action:调侃`
- `action:挑战`
- `action:轻度占有`
- `action:关系升级`
- `action:邀约前置`
- `action:反问`
- `action:反测试`
- `action:奖励投入`
- `action:需求识别`
- `action:直球`
- `action:要求具体化`
- `action:现场决策`

### `tone`：表达气质

- `tone:温柔`
- `tone:轻松`
- `tone:浪漫`
- `tone:坏坏`
- `tone:强势`
- `tone:克制`
- `tone:暧昧`
- `tone:占有感`

### `concept`：课程概念

- `concept:窗口`
- `concept:黄灯`
- `concept:SD-ASD`
- `concept:筹码`
- `concept:框架`
- `concept:安全感`
- `concept:服从性测试`
- `concept:推拉`
- `concept:踩油门`
- `concept:诱饵`
- `concept:高位可得性`
- `concept:人物画像`
- `concept:直上高速`
- `concept:不可得性`

## 对象格式

```yaml
object_id: OB-C019-001
course_id: C019
title: 才认识就去你家不太好
tags:
  - stage:邀约
  - scene:私密地点邀约
  - signal:黄灯
  - psychology:有兴趣但犹豫
  - action:邀约
  - action:框架转换
  - concept:SD-ASD
course_chain:
  scene: ...
  female_line: ...
  instructor_interpretation: ...
  course_action: ...
  course_wording: ...
  observed_next_signal: ...
  course_next_move: ...
supplement_chain:
  missing_branches: ...
  communication_goal: ...
  directions:
    - direction: ...
      use_when: ...
      examples: [...]
  response_branches: ...
approval_status: pending_user_confirmation
```

## 使用规则

1. 标签可以增加，不要求一个对象只能归入一个分类。
2. 标签用于召回、过滤、聚类和联想，不直接显示为机械答案。
3. 用户问一句话时，可以召回多个标签重叠的对象，再根据上下文重排。
4. 回答时必须把标签重新还原成自然语言心理分析，不能只输出“这是 ASD、黄灯、推拉”。
5. “坏坏、进攻、占有感”是一种策略气质，不代表强迫。明确拒绝出现后，不再把继续施压当作补足方向。

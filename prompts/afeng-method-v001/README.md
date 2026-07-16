# 阿峰方法层 Prompt v001

本目录只服务于以下三阶段，不包含安全审查，也不消费旧 P06：

```text
课程方法提炼
→ 课程忠实度审查（最多两次修订）
→ 发布分类
```

程序层契约位于 `course_video_analyzer.knowledge.afeng_models`。模型输出必须是严格 JSON，
所有主要字段必须引用当前案例中的 segment ID。Markdown 由程序确定性渲染，不由模型生成。

# Agent 协作与交付规范

## 1. 开工前检查

每个 Agent 必须：

1. 阅读总体方案、任务索引和自己的任务文件；
2. 执行 `git status --short`，不得覆盖其他 Agent 或用户的未提交内容；
3. 确认所有前置任务已经完成；
4. 只修改任务文件声明的目录和文件；
5. 如果必须修改公共接口，先停止工作并在交接说明中提出，不得自行扩大范围。

## 2. 全局架构约束

- 核心模块不得依赖 Gradio；
- FunASR、WeSpeaker、PaddleOCR 必须通过适配器隔离，并使用延迟导入；
- 单元测试不得下载真实模型或依赖网络；
- 集成测试必须使用 `integration` 标记；
- 时间统一使用整数毫秒，区间使用左闭右开 `[start_ms, end_ms)`；
- 中间结果必须保存为 JSON，允许任务恢复和人工复核；
- 原始识别结果不可被人工修订覆盖，修订内容必须存储在独立字段；
- 第一版核心处理不调用 LLM；
- 不提交模型、真实课程视频、用户字幕、任务输出和缓存。

## 3. 公共目录所有权

| 路径 | 默认所有者 | 说明 |
|---|---|---|
| `pyproject.toml`、`uv.lock`、`.python-version` | TASK-000 | 其他任务不得直接修改依赖 |
| `src/course_video_analyzer/models.py` | TASK-001 | 后续任务只消费模型 |
| `src/course_video_analyzer/pipeline.py` | TASK-001、TASK-008 | TASK-001 定义接口，TASK-008 完成编排 |
| `src/course_video_analyzer/media/`、`jobs/` | TASK-001 | 媒体与任务基础设施 |
| `src/course_video_analyzer/audio/funasr_adapter.py` | TASK-002 | FunASR 专属 |
| `src/course_video_analyzer/audio/wespeaker_adapter.py` | TASK-003 | WeSpeaker 专属 |
| `src/course_video_analyzer/audio/alignment.py` | TASK-004 | 声音对齐专属 |
| `src/course_video_analyzer/vision/detection.py` | TASK-005 | 区域检测专属 |
| `src/course_video_analyzer/vision/tracking.py`、`dedup.py` | TASK-006 | 追踪与去重专属 |
| `src/course_video_analyzer/vision/ocr.py`、`enhance.py` | TASK-007 | OCR 专属 |
| `src/course_video_analyzer/timeline/`、`exporters/` | TASK-008 | 汇总和导出 |
| `src/course_video_analyzer/web.py`、`web/` | TASK-009 | Web 专属 |
| `benchmarks/`、`tests/fixtures/manifests/` | TASK-010 | 评估专属 |

## 4. 每个任务必须交付

- 可运行的实现代码；
- 对应单元测试；
- 必要的集成测试或手动验证脚本；
- 更新任务文件中的实际决策和已知限制；
- 一段交接说明，包括修改文件、验证命令、测试结果、剩余风险。

只有文档、只有接口或只有 Demo 均不算完成，除非任务文件明确说明该任务属于技术验证。

## 5. 完成标准

任务提交前必须执行：

```powershell
uv run ruff check .
uv run pyright
uv run pytest -q -m "not integration"
```

任务自己的验收命令也必须通过。若集成测试因模型、GPU 或网络无法运行，需要明确记录“未验证”，不得表述为已通过。

## 6. 禁止事项

- 不得删除或修改 `output/` 与 `聊天课程知识库搭建/`；
- 不得把模型权重或真实视频提交到仓库；
- 不得在单元测试中请求外部 API；
- 不得用宽泛的 `except Exception: pass` 隐藏错误；
- 不得把识别、人物分离、OCR 和 Web UI 写进同一个文件；
- 不得在未更新领域模型和测试的情况下改变 JSON 字段含义。

## 7. 交接模板

```markdown
## TASK-XXX 交接

- 完成内容：
- 修改文件：
- 新增/变更接口：
- 验证命令及结果：
- 未执行的集成验证：
- 已知限制：
- 建议下游任务注意：
```

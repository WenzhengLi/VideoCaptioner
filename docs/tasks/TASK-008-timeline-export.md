# TASK-008：统一时间轴、顶层流水线与导出

## 目标

把声音分支和课板分支组合为完整 `AnalysisResult`，实现可恢复的顶层编排及 JSON、TXT、SRT 导出。

## 前置依赖

TASK-004、TASK-006、TASK-007 全部完成。

## 允许修改

- `src/course_video_analyzer/pipeline.py`
- `src/course_video_analyzer/timeline/`
- `src/course_video_analyzer/exporters/`
- `tests/test_timeline/`
- `tests/test_exporters/`
- `tests/test_pipeline.py`

## 输入

- `SpeechSegment[]`
- 稳定课板版本及 `OcrLine[]`
- `MediaInfo`
- 任务工作区与导出配置

## 输出

```text
artifacts/
├─ analysis.json
├─ timeline.json
├─ transcript.txt
├─ transcript.srt
└─ boards/index.json
```

## 必须完成

1. 根据区间重叠关联讲话和当时有效课板；
2. 课板持续期间的多条讲话应引用同一个课板版本；
3. 生成完整 `AnalysisResult`；
4. 顶层流水线按媒体、声音、课板、合并、导出阶段执行；
5. 每阶段写入任务状态并支持恢复；
6. JSON 保留原始结果、修订结果、置信度和来源；
7. TXT 面向阅读，明确人物和当前课板；
8. SRT 只输出讲话，课板内容不得导致字幕过长；
9. 导出顺序稳定，重复执行结果可比较；
10. 适配器通过依赖注入，测试使用 fake 实现。

## 必须交付

- 时间轴合并器；
- 完整顶层流水线；
- JSON、TXT、SRT 导出器；
- fake 组件端到端单元测试；
- 输出格式示例和字段说明。

## 验收标准

- 任意讲话片段能查询当时课板；
- 没有声音或没有课板时仍可导出；
- 中途失败后可以从已完成阶段恢复；
- fake 端到端测试不加载真实模型；
- JSON 可以无损重新加载为 `AnalysisResult`。

## 验收命令

```powershell
uv run pytest tests/test_timeline tests/test_exporters tests/test_pipeline.py -q
uv run ruff check src/course_video_analyzer/timeline src/course_video_analyzer/exporters src/course_video_analyzer/pipeline.py
uv run pyright
```

## 非目标

- 不实现 Web 页面；
- 不生成知识库摘要；
- 不实现 PDF，除非不影响既定交付；
- 不重新实现底层识别算法。

## 交接重点

提供完整 `analysis.json` 示例、阶段状态机、恢复规则和 TASK-009 可调用的单一服务入口。

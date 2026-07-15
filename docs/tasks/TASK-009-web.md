# TASK-009：Gradio 本地 Web 第一版

## 目标

提供一个面向非开发人员的本地网页，完成视频上传、任务启动、阶段进度、结果预览、人物映射、OCR 修订和下载。

## 前置依赖

TASK-008 已提供稳定的服务入口、任务状态和导出结果。

## 允许修改

- `src/course_video_analyzer/web.py`
- `src/course_video_analyzer/web/`
- `tests/test_web/`
- Web 使用说明

不得把模型实现复制进 Web 层。

## 页面流程

1. 上传或选择本地视频；
2. 展示媒体信息；
3. 配置 CPU/CUDA、抽帧间隔、课板模式和说话人数提示；
4. 创建任务；
5. 展示媒体、FunASR、WeSpeaker、课板、合并、导出阶段进度；
6. 预览视频、讲话列表和课板代表帧；
7. 修改 `Speaker 0 → 导师`；
8. 编辑 `corrected_text`，不覆盖原始 OCR；
9. 下载 JSON、TXT、SRT 和课板图片包。

## 必须完成

1. Web 只调用 TASK-008 的服务接口；
2. 长任务不得阻塞整个页面；
3. 同一时间至少可以查看一个运行任务和历史任务；
4. 错误信息必须展示失败阶段和可执行建议；
5. 页面重载后能从任务目录恢复状态；
6. 用户修改通过单独的 revision 文件持久化；
7. 路径输入、文件类型和大小进行校验；
8. 默认只监听 `127.0.0.1`；
9. 核心页面组件可通过测试直接构建，不自动打开浏览器。

## 必须交付

- 可启动的 Gradio 应用；
- 任务创建、状态轮询和结果编辑服务；
- Web 单元/烟雾测试；
- 启动与操作说明；
- 至少一组截图或手动验收记录，截图无需提交敏感视频。

## 验收标准

- `uv run course-video-web` 可以启动；
- 上传合法视频后创建任务目录；
- 使用 fake pipeline 可以完整走通页面；
- 人物映射和 OCR 修订在重载后仍存在；
- 下载文件来自 TASK-008 导出器；
- 未安装音频/视觉 extra 时页面给出依赖提示而不是崩溃。

## 验收命令

```powershell
uv run pytest tests/test_web -q
uv run python -c "from course_video_analyzer.web import build_app; build_app()"
uv run ruff check src/course_video_analyzer/web.py src/course_video_analyzer/web
uv run pyright
```

## 非目标

- 不实现 Vue/React；
- 不实现公网部署、账号、权限或计费；
- 不在请求线程中同步加载所有模型；
- 不使用 LLM。

## 交接重点

说明启动命令、任务状态刷新机制、revision 文件格式和第二版迁移 FastAPI 时可复用的服务边界。

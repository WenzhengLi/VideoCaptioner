# 本地 Web 使用说明（TASK-009）

## 启动

```powershell
uv sync --extra web
# 完整分析还需要：
uv sync --extra audio --extra vision
uv run course-video-web
```

默认监听 `http://127.0.0.1:7860`，不会自动打开浏览器。

程序化构建（烟雾测试，不启动服务器）：

```powershell
uv run python -c "from course_video_analyzer.web import build_app; build_app()"
```

## 页面流程

1. 上传视频，或填写本地绝对路径；
2. 「读取媒体信息」展示时长、分辨率与音视频流；
3. 配置设备（cpu/cuda）、处理 Profile、抽帧间隔、课板模式、说话人数提示；默认 Profile
   为 `complete-v1`，间隔 5000 ms；
4. 「创建并开始分析」写入 `jobs/<job-id>/` 并后台执行管线；
5. 在任务列表中刷新阶段进度（media → … → export）；
6. 完成后预览讲话列表与课板 OCR；
7. 在「人物映射与 OCR 修订」写入 JSON，保存到 `revisions.json`；
8. 下载 `analysis.json` / `transcript.txt` / `transcript.srt` / 课板 zip（均来自 TASK-008 导出产物）。

## 任务恢复

页面重载后，左侧会扫描 `jobs/` 下已有 `job.json`。修订保存在各任务目录的 `revisions.json`，不覆盖原始 OCR `text` 字段。

## 服务边界（迁移 FastAPI 时可复用）

`WebAnalysisFacade`（`course_video_analyzer.web.service`）封装：

- `create_job` / `start_job` / `list_jobs` / `format_progress`
- `save_speaker_mapping` / `save_ocr_corrections`
- `download_bundle` / `load_result_with_revisions`

Gradio 仅负责渲染；核心识别逻辑不依赖 Gradio。

## 手动验收记录（无敏感视频）

| 步骤 | 结果 |
|---|---|
| `build_app()` 无浏览器启动 | 通过（单元烟雾） |
| fake pipeline 创建任务并完成后修订持久化 | 见 `tests/test_web` |
| 缺 audio/vision extra 时展示依赖横幅 | `dependency_banner()` 返回提示文案 |
| 默认绑定地址 | `127.0.0.1` |

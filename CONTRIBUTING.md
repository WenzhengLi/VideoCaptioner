# Contributing

感谢参与 Course Video Analyzer。提交应优先保证行为可验证、配置兼容和真实视频数据不进入
仓库。

## 开发环境

```powershell
python -m pip install uv
uv sync --extra web --extra audio --extra vision --group dev
```

项目固定使用 Python 3.11。不要在源代码中写入本机绝对路径、模型凭据或真实视频名称。

## 修改原则

1. 公共数据模型集中放在 `models.py`，不要在不同模块重复定义相同结构。
2. 算法参数进入配置对象或处理 Profile，不在流水线中散落魔法数字。
3. 抽帧、图片比较、OCR 调度、缓存、去重和导出应保持可单独测试。
4. 新功能不得破坏已有任务的恢复能力和旧配置兼容性。
5. `jobs/`、`output/`、`benchmarks/results/`、模型、视频和本地知识库不得提交。

## 提交前检查

```powershell
uv run ruff check .
uv run pyright
uv run pytest -q -m "not integration"
```

涉及真实模型或 FFmpeg 时，再运行对应的 `integration` 测试，并在提交说明中记录环境和结果。

## Commit 与 Pull Request

- Commit 使用清晰的动词开头，例如 `feat:`, `fix:`, `refactor:`, `docs:`, `test:`。
- 一个提交只解决一个可描述的问题；大规模机械格式化与功能修改尽量分开。
- Pull Request 说明行为变化、兼容性、测试结果和是否改变默认 Profile。
- 算法优化需同时报告完整度、OCR 调用次数和耗时，不能只报告输出数量减少。

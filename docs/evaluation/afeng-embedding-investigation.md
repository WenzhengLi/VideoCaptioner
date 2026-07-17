# 本地 Embedding 探测报告

生成时间：2026-07-17

## 一、目标

按 TASK-015 要求，以 Dify 1.15.0 真实能力为准验证本地 embedding 接入。候选模型：`BAAI/bge-m3`。

## 二、本地基础设施

| 项 | 状态 |
|---|---|
| GPU | NVIDIA RTX 4080 16GB VRAM |
| Ollama | 已安装 v0.32.1 |
| bge-m3 | 已下载 (1.2 GB, GGUF F16) |
| Ollama API | http://127.0.0.1:11434 运行中 |

## 三、Embedding 验证

| 检查项 | 结果 |
|---|---|
| Ollama 健康检查 | OK |
| bge-m3 模型可用 | OK |
| 真实 embedding 调用 | OK |
| 维度 | 1024 |
| L2 范数 | 1.0000 (已归一化) |
| 维度一致性 | OK |

测试文本：`阿峰课程方法：如何在约会中建立吸引力`

## 四、Dify 1.15.0 集成状态

| 项 | 状态 |
|---|---|
| Dify 容器 | 运行中 (v1.15.0) |
| 插件 daemon | 运行中 (v0.6.3-local) |
| Model Provider API | 控制台 API 不直接暴露 provider 安装端点 |
| Ollama 插件 | 需通过 Dify Web UI 安装 |
| Embedding 配置 | 需人工通过 Web UI 完成 |

**原因**：Dify 1.15.0 使用插件系统管理 model provider，`/console/api/workspaces/current/model-providers` 返回空列表，
且 provider 安装 API 返回 404。这说明 provider 必须通过 Web UI 的插件市场安装。

## 五、已完成的代码修改

1. **`dify_sync.py`**：`sync_markdown_dir` 新增 `indexing_technique` 显式参数，移除环境变量硬编码；
   添加 `high_quality` 模式校验（需 embedding 已配置）；优先级：参数 > 环境变量 > Dataset 模式 > 默认 economy。
2. **`cli.py`**：`dify-sync-markdown` 新增 `--indexing-technique` CLI 参数。
3. **测试**：新增 3 个测试覆盖显式参数、模式校验和回退逻辑。
4. **探测脚本**：`scripts/probe_local_embedding.py` — 自动检查 Ollama/bge-m3 可用性和真实 embedding 调用。
5. **创建脚本**：`scripts/create_formal_dataset.py` — 创建 high_quality Dataset 的独立脚本。

## 六、用户需完成的一步

在浏览器中打开 Dify 控制台 http://127.0.0.1:3080 ，完成以下操作：

1. 进入「设置」→「模型供应商」
2. 安装 Ollama 插件（如已在插件市场列出）
3. 配置 Ollama 连接：
   - Base URL: `http://host.docker.internal:11434`（容器内访问宿主机）
   - 或 `http://172.17.0.1:11434`（Docker bridge 网络）
4. 在 embedding 模型列表中选择 `bge-m3`
5. 创建正式 Dataset `阿峰课程方法库-研究版-v1`，选择 `high_quality` 模式
6. 设置 embedding 模型为 `bge-m3`

完成后运行：
```powershell
# 加载正式库凭据
$env:DIFY_BASE_URL = "http://127.0.0.1:3080/v1"
$env:DIFY_API_KEY = "<formal-dataset-api-key>"
$env:DIFY_DATASET_ID = "<formal-dataset-id>"

# 同步 v002.6 到正式库
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.6/documents `
  --map-path data/dify/document-map-v1.json `
  --indexing-technique high_quality `
  --poll-indexing
```

## 七、恢复命令

Ollama 服务启动：
```powershell
& "C:\Users\Administrator\AppData\Local\Programs\Ollama\ollama.exe" serve
```

Embedding 探测：
```powershell
.\.venv\Scripts\python.exe scripts\probe_local_embedding.py
```

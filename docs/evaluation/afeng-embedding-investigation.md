# 本地 Embedding 探测报告

生成时间：2026-07-17（Gate 1 更新）

## 一、目标

按 TASK-015 要求，以 Dify 1.15.0 真实能力为准验证本地 embedding 接入。候选模型：`BAAI/bge-m3`。

## 二、本地基础设施

| 项 | 状态 |
|---|---|
| GPU | NVIDIA RTX 4080 16GB VRAM |
| Ollama | v0.32.1 运行中 |
| bge-m3 | 已下载 (1.2 GB, GGUF F16, 566.70M 参数) |
| Ollama API | http://127.0.0.1:11434 |

## 三、Embedding 验证（宿主机侧）

| 检查项 | 结果 |
|---|---|
| Ollama 健康检查 | OK |
| bge-m3 模型可用 | OK |
| 真实 embedding 调用 | OK |
| 维度 | 1024 |
| L2 范数 | 1.0000 (已归一化) |
| 维度一致性 | OK |

## 四、Dify 1.15.0 集成审计

| 项 | 结果 |
|---|---|
| Dify 容器 | 全部运行中 (v1.15.0) |
| 插件 daemon | 运行中 (v0.6.3-local, port 5003) |
| 控制台登录 | 成功（Base64 密码） |
| 已安装 Provider | **0 个** |
| 默认 text-embedding | **未配置** |
| `/console/api/workspaces/current/model-providers` (GET) | 200, `{"data":[]}` |
| `/console/api/workspaces/current/model-providers` (POST) | **405 method_not_allowed** |
| `/console/api/workspaces/current/model-providers/ollama` (POST) | **404 not_found** |
| `/console/api/plugins/*` | **404 not_found** |

**结论**：Dify 1.15.0 的 Provider 安装只能通过 Web UI 的插件市场完成。
控制台 API 不暴露 provider 安装端点。

## 五、已完成的代码修改

1. **`dify_sync.py`**：`sync_markdown_dir` 新增 `indexing_technique` 显式参数，移除环境变量硬编码；
   添加 `high_quality` 模式校验（需 embedding 已配置）；优先级：参数 > 环境变量 > Dataset 模式 > 默认 economy。
2. **`cli.py`**：`dify-sync-markdown` 新增 `--indexing-technique` CLI 参数。
3. **测试**：新增 3 个测试覆盖显式参数、模式校验和回退逻辑。
4. **探测脚本**：`scripts/probe_local_embedding.py` — 自动检查 Ollama/bge-m3 可用性和真实 embedding 调用。
5. **创建脚本**：`scripts/create_formal_dataset.py` — 创建 high_quality Dataset 的独立脚本。

## 六、用户需完成的 UI 操作（精确步骤）

### 步骤 1：安装 Ollama 插件

1. 浏览器打开 http://127.0.0.1:3080
2. 登录管理员账户
3. 点击右上角头像 → 「设置」
4. 左侧菜单点击「模型供应商」
5. 点击「添加模型供应商」
6. 搜索 `Ollama`
7. 点击安装

### 步骤 2：配置 Ollama 连接

在 Ollama 配置页面填写：
- Base URL: `http://host.docker.internal:11434`
  - 如果 `host.docker.internal` 不可用，尝试 `http://172.17.0.1:11434`
- 点击「保存」

### 步骤 3：添加 embedding 模型

1. 在 Ollama 配置页面找到「添加模型」
2. 模型名称填写：`bge-m3`
3. 模型类型选择：**Text Embedding**
4. 维度填写：**1024**
5. 点击「保存」

### 步骤 4：创建正式 Dataset

1. 左侧菜单点击「知识库」
2. 点击「创建知识库」
3. 名称填写：`阿峰课程方法库-研究版-v1`
4. 索引模式选择：**高质量**
5. Embedding 模型选择：`bge-m3`（Ollama）
6. 点击「创建」

### 步骤 5：创建 API Key

1. 在刚创建的知识库页面，点击「API 访问」
2. 点击「创建 API Key」
3. 复制保存 API Key

### 步骤 6：记录 Dataset ID

从知识库 URL 或 API 响应中获取 Dataset ID。

## 七、UI 完成后的自动验证命令

```powershell
# 设置正式库凭据（替换为实际值）
$env:DIFY_BASE_URL = "http://127.0.0.1:3080/v1"
$env:DIFY_API_KEY = "<步骤5的API Key>"
$env:DIFY_DATASET_ID = "<步骤6的Dataset ID>"

# 验证 Dataset 可达
.\.venv\Scripts\python.exe -c "from course_video_analyzer.knowledge.dify_sync import DifyConfig, get_dataset; cfg=DifyConfig.from_env(); print(get_dataset(cfg, '$env:DIFY_DATASET_ID'))"

# 同步 v002.6 到正式库
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data/dify/afeng-release-v002.6/documents `
  --map-path data/dify/document-map-v1.json `
  --indexing-technique high_quality `
  --poll-indexing

# 验证同步结果
.\.venv\Scripts\python.exe scripts\audit_afeng_production.py
```

## 八、恢复命令

Ollama 服务启动：
```powershell
& "C:\Users\Administrator\AppData\Local\Programs\Ollama\ollama.exe" serve
```

Embedding 探测：
```powershell
.\.venv\Scripts\python.exe scripts\probe_local_embedding.py
```

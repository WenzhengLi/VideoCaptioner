# 外部 Provider 配置指南

生成时间：2026-07-18

## 一、推荐 Provider

优先选择能同时提供 embedding 和 LLM 的单一服务：

| Provider | Embedding 模型 | LLM 模型 | 优势 |
|---|---|---|---|
| 智谱 GLM | embedding-3 (1024维) | GLM-4-Flash / GLM-4 | 中文优化，免费额度 |
| DeepSeek | deepseek-embedding | DeepSeek-V3 / DeepSeek-Chat | 性价比高 |
| OpenAI | text-embedding-3-small (1536维) | GPT-4o-mini / GPT-4o | 生态成熟 |

## 二、Dify Web UI 配置步骤

### 步骤 1：安装 Provider 插件

1. 打开 http://127.0.0.1:3080 → 登录
2. 右上角头像 → 设置 → 模型供应商
3. 搜索并安装选择的 Provider（如 "智谱" / "DeepSeek" / "OpenAI"）

### 步骤 2：配置 API Key

在 Provider 配置页面填入 API Key。Key 仅保存在 Dify 内部，不写入仓库。

### 步骤 3：验证 Provider

在 Provider 配置页面确认：
- Embedding 模型列表中有所选模型
- LLM 模型列表中有所选模型

### 步骤 4：创建正式 Dataset

1. 左侧菜单 → 知识库 → 创建知识库
2. 名称：`阿峰课程方法库-研究版-v2`
3. 索引模式：高质量
4. Embedding 模型：选择 Provider 的 embedding 模型
5. 创建后在「API 访问」中创建 API Key

### 步骤 5：记录配置

将以下信息保存到 `D:\Dev\dify-deploy\secrets\dify-runtime-v2.env`：

```
DIFY_BASE_URL=http://127.0.0.1:3080/v1
DIFY_API_KEY=<步骤4创建的API Key>
DIFY_DATASET_ID=<Dataset ID>
DIFY_DATASET_NAME=阿峰课程方法库-研究版-v2
```

## 三、自动验证命令

配置完成后运行：

```powershell
# 设置环境变量
$env:DIFY_BASE_URL = "http://127.0.0.1:3080/v1"
$env:DIFY_API_KEY = "<你的API Key>"
$env:DIFY_DATASET_ID = "<Dataset ID>"

# 同步文档并运行检索验收
.\.venv\Scripts\python.exe scripts\sync_and_test_v2.py

# 运行生产审计
.\.venv\Scripts\python.exe scripts\audit_afeng_production.py
```

## 四、故障排除

### Provider 安装失败

- 检查网络连接（Dify 需要访问 Provider API）
- 尝试其他 Provider

### Embedding 调用失败

- 检查 API Key 是否有效
- 检查 Provider 账户是否有余额/额度
- 尝试 Provider 的其他 embedding 模型

### 检索命中率低

- 确认使用 `hybrid_search` 模式
- 确认文档级去重已启用
- 检查 embedding 维度是否与模型匹配

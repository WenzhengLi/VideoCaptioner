# 阿峰 Dify 应用部署、备份与恢复

## 当前运行配置

- 应用：`阿峰`（advanced-chat）
- Dataset：`阿峰课程方法库-研究版-v1`
- LLM：DeepSeek `deepseek-chat`
- Embedding：Ollama `bge-m3`
- Dataset map：`data/dify/document-map-v1.json`
- Workflow DSL：`deploy/dify/workflows/afeng-chatflow.yml`
- 密钥：仅从 `D:\Dev\dify-deploy\secrets` 读取，不写入仓库

## 可重复部署

```powershell
.\.venv\Scripts\python.exe scripts\prepare_afeng_app_index.py
.\.venv\Scripts\python.exe scripts\deploy_afeng_dify_app.py
.\.venv\Scripts\python.exe scripts\validate_afeng_citations.py data\dify\afeng-app-smoke.json
```

第一步从 v002.6 的来源证据生成受控引用目录；第二步将正式 v1 Dataset ID 和引用目录注入 DSL，导入并发布应用；第三步校验真实冒烟回答。

## 全量验收

```powershell
.\.venv\Scripts\python.exe scripts\run_afeng_app_acceptance.py
```

输出：

- `data/dify/afeng-app-acceptance.json`
- `docs/evaluation/afeng-app-acceptance.md`

## 备份边界

提交或归档以下文件即可重建应用配置：

- Workflow DSL
- 三个部署/引用/验收脚本
- v002.6 manifest 与正式文档包
- v002.7 检索文档包
- `document-map-v1.json` 的安全备份

Dify 管理员凭据、Dataset API Key 和 DeepSeek Key 只保存在本机 secrets 目录，不进入 Git 或验收报告。

## 恢复与回滚

1. 确认 Dify、DeepSeek Provider、Ollama 和 `bge-m3` 可用。
2. 确认正式 Dataset ID 与 `document-map-v1.json` 一致，禁止绑定旧 economy Dataset。
3. 执行“可重复部署”三条命令；部署脚本按应用名更新现有“阿峰”，不会创建重复应用。
4. 执行 20 问验收，未达到 20/20 时不得把新版本视为恢复完成。
5. 若新 DSL 异常，从 Git 取回上一个已验收版本的 `afeng-chatflow.yml`，重新执行部署和验收命令。

正式 v002.6 发布包保持不可变；受控引用目录是运行时派生产物，可随时重新生成。

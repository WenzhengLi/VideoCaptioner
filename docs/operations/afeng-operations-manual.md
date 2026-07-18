# 阿峰 Dify 生产链路运维手册

最后更新：2026-07-18

## 一、当前架构

```text
视频课程 → ASR/OCR → 事实证据 P01–P04
  → 阿峰方法提炼（MiMo + GLM，已冻结）
  → 课程忠实度审查
  → 发布分类
  → v002.6 不可变 bundle（36 published + 4 excluded）
  → Dify 知识库（high_quality, Ollama bge-m3 embedding）
  → DeepSeek LLM
  → "阿峰"应用（advanced-chat）
```

模型职责：

| 角色 | 模型 | 用途 |
|---|---|---|
| Embedding | Ollama bge-m3 (1024维) | Dify high_quality 向量索引 |
| LLM | DeepSeek deepseek-chat | 应用回答生成 |

## 二、服务启动与健康检查

### Dify

```powershell
# 启动
cd D:\Dev\dify-deploy\repo\docker
docker compose up -d

# 健康检查
docker ps --filter "name=dify-api" --format "{{.Names}} {{.Status}}"
curl -s http://127.0.0.1:3080/v1/parameters  # 应返回 401 (需 auth)
```

### Ollama

```powershell
# 启动
& "C:\Users\Administrator\AppData\Local\Programs\Ollama\ollama.exe" serve

# 健康检查
curl -s http://127.0.0.1:11434/api/tags  # 应返回 bge-m3:latest
```

### cpa（端口 8317）

禁止停止、删除或修改。

## 三、Secrets 位置与安全边界

| 文件 | 内容 | 安全要求 |
|---|---|---|
| `D:\Dev\dify-deploy\secrets\admin.env` | 管理员邮箱/密码 | 不输出、不提交 |
| `D:\Dev\dify-deploy\secrets\dify-runtime.env` | API Key、Dataset ID | 不输出、不提交 |

脚本通过 `source` 加载，不打印值。Git 中无 secret。

## 四、Bundle 校验

```powershell
.\.venv\Scripts\python.exe scripts\verify_afeng_release_bundle.py `
  data\dify\afeng-release-v002.6\manifest.json `
  --json-output data\dify\afeng-verify-report.json
```

预期：documents=36, canonical_unique=36, lineage_missing=0, ok=True

## 五、正式 Map 校验

```powershell
.\.venv\Scripts\python.exe -c "
import json
m = json.load(open('data/dify/document-map-v1.json'))
docs = m.get('documents', {})
print(f'Keys: {len(docs)}, Dataset: {m.get(\"dataset_id\", \"?\")[:8]}...')
canonical = [k for k in docs if k.startswith('AFENG-')]
print(f'Canonical: {len(canonical)}/{len(docs)}')
"
```

预期：36 canonical keys，Dataset ID 匹配正式库。

## 六、只读生产审计

```powershell
# 加载凭据
$env:DIFY_BASE_URL = "http://127.0.0.1:3080/v1"
# 从 secrets 加载 API_KEY 和 DATASET_ID

.\.venv\Scripts\python.exe scripts\audit_afeng_production.py `
  --json-output data\dify\afeng-production-final-audit.json `
  --markdown-output docs\evaluation\afeng-production-final-audit.md
```

预期：overall=PASS（aggregate + bundle + map + remote + app + reports 全部 PASS）

## 七、幂等同步

```powershell
.\.venv\Scripts\python.exe -m course_video_analyzer.knowledge.cli dify-sync-markdown `
  --markdown-root data\dify\afeng-release-v002.6\documents `
  --map-path data\dify\document-map-v1.json `
  --dataset-id $env:DIFY_DATASET_ID `
  --indexing-technique high_quality `
  --poll-indexing
```

首次：create=36, failed=0
二次：skip=36, create=0, update=0

## 八、20 问检索验收

```powershell
.\.venv\Scripts\python.exe scripts\run_afeng_retrieval_test.py `
  --test-set data\dify\afeng-retrieval-test-v002.json `
  --map-path data\dify\document-map-v1.json `
  --json-output data\dify\afeng-retrieval-report.json `
  --md-output docs\evaluation\afeng-retrieval-report.md `
  --top-k 5 `
  --search-method hybrid_search
```

预期：document-dedup Top-5 >= 90% (18/20)

## 九、应用部署与验收

### 部署

```powershell
.\.venv\Scripts\python.exe scripts\deploy_afeng_dify_app.py
```

### C019 Smoke

```powershell
.\.venv\Scripts\python.exe scripts\run_afeng_app_acceptance.py --smoke-only
```

### 20 问应用验收

```powershell
.\.venv\Scripts\python.exe scripts\run_afeng_app_acceptance.py `
  --json-output data\dify\afeng-app-acceptance-report.json
```

预期：20/20 (100%)

## 十、备份 Manifest

```powershell
.\.venv\Scripts\python.exe scripts\build_afeng_backup_manifest.py `
  --output data\dify\afeng-backup-manifest.json
```

记录 90 个 artifact 的路径、大小、SHA-256、用途。

## 十一、恢复 Dry-Run

```powershell
.\.venv\Scripts\python.exe scripts\dry_run_afeng_restore.py
```

预期：create=0, update=0, skip=36, DRY-RUN PASSED

## 十二、常见故障

### Dify 不可达

```powershell
docker ps --filter "name=dify-api"
# 如未运行：
cd D:\Dev\dify-deploy\repo\docker
docker compose up -d
```

### Ollama 不可达

```powershell
# 检查进程
tasklist | findstr ollama
# 如未运行：
& "C:\Users\Administrator\AppData\Local\Programs\Ollama\ollama.exe" serve
```

### DeepSeek 错误

检查 Dify 控制台 → 设置 → 模型供应商 → DeepSeek 状态。
API Key 可能过期或余额不足。

### 索引未完成

```powershell
# 检查索引状态
.\.venv\Scripts\python.exe -c "
import json, urllib.request, os
base = os.environ['DIFY_BASE_URL']
key = os.environ['DIFY_API_KEY']
dsid = os.environ['DIFY_DATASET_ID']
req = urllib.request.Request(f'{base}/datasets/{dsid}/documents?page=1&limit=100',
  headers={'Authorization': f'Bearer {key}'})
docs = json.loads(urllib.request.urlopen(req, timeout=15).read().decode('utf-8'))['data']
completed = sum(1 for d in docs if d.get('indexing_status') == 'completed')
print(f'{completed}/{len(docs)} completed')
"
```

### Segment UUID 引用

应用 Prompt 中引用的 evidence_ids 必须是 `SEG-` 格式，不是 Dify 内部 UUID。
校验器 `scripts/validate_afeng_citations.py` 会检查。

### Dataset 错绑

审计脚本检查 map 的 dataset_id 是否与运行时一致。不一致时 fail-fast。

### 检索回退

hybrid_search 中 keyword 部分依赖 Dify 自动提取关键词。如关键词为空，
退化为纯语义搜索。可通过添加关键词段优化。

## 十三、回滚到上一个已验收 DSL

```powershell
# 查看 DSL 历史
git log --oneline -- deploy/dify/workflows/afeng-chatflow.yml

# 回滚到指定版本
git checkout <commit> -- deploy/dify/workflows/afeng-chatflow.yml

# 重新部署
.\.venv\Scripts\python.exe scripts\deploy_afeng_dify_app.py
```

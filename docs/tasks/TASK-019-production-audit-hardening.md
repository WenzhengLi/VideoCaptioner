# TASK-019：生产审计加固与第一期正式封版

## 状态

已完成。

## 背景

TASK-018 已完成在线审计、备份 manifest、恢复 dry-run、运维手册和质量门禁，但复核发现若干会造成假阳性或无法完整恢复的缺口。必须先修复这些问题，再把前 20 课系统视为正式封版。

## 必须完成

1. 审计器必须读取实际应用验收 JSON，验证 total=20、passed=20、pass_rate=100%，并确认每题 passed；不得以 Markdown 文件存在代替验收结果；
2. 检索报告必须验证 total=20、correct>=18、accuracy>=90%，不能只读取单个 accuracy 字段；
3. 恢复 dry-run 必须以正式 Dify 检索文档包 v002.7 为同步源，真实比较 source SHA-256 与 map SHA-256，计算 create/update/skip；禁止硬编码 update=0；
4. 生产恢复 dry-run 默认要求真实 Dify 连接；缺少环境变量时必须失败，只有显式 `--offline` 才允许跳过远端检查；
5. 备份 manifest 必须包含实际 `afeng-app-acceptance.json`、应用/检索 Markdown 报告、运维手册、DIFY 状态、部署恢复说明，并对必需文件缺失返回非零；
6. 修正运维手册中不存在或被脚本忽略的 `--smoke-only`、`--json-output` 参数；所有命令必须实际可执行；
7. 增加 remote/app/report/restore/backup 的回归测试，覆盖假报告、hash 更新、远端跳过、必需备份缺失；
8. 重新执行真实在线审计、真实恢复 dry-run、Ruff、Pyright、全量 pytest；
9. 更新 TASK-018/TASK-019 状态，显式提交并推送，不混入用户受保护文件。

## 验收标准

- 在线审计 overall=PASS，且应用报告来自 JSON 20/20；
- 恢复 dry-run：create=0、update=0、skip=36，所有数字由真实 hash/远端状态计算；
- 无 Dify 环境时默认 dry-run 返回非零；
- 备份 manifest 必需项覆盖率 100%；
- 运维手册命令逐条与 CLI 一致；
- Ruff、Pyright、pytest 全部通过；
- 当前分支已推送，用户受保护文件仍未暂存。

## 完成说明

全部 9 项已完成：

1. 应用报告：读取 `afeng-app-acceptance.json`，验证 schema/test_type/total=20/passed=20/pass_rate=100/逐题 passed/citation_validation.valid
2. 检索报告：验证 schema/test_type/total=20/correct>=18/results=20/一致性
3. 恢复 dry-run：v002.7 为同步源，真实 SHA-256 比较；update>0 视为失败；create+update+skip=36 校验
4. 无 Dify 环境：默认非零退出，`--offline` 跳过远端检查并报告 `remote_verified=false`
5. 备份清单：修复文件名，新增 16 个 REQUIRED_ARTIFACTS，缺失时构建失败
6. 运维手册：修正 C019 smoke 和 20 问验收命令
7. 测试：17 个审计测试覆盖 schema/test_type/citation/update>0/offline/backup 等场景
8. 真实复跑：在线审计 PASS、恢复 PASSED、备份 96/16/0
9. 状态文档已更新

验证：ruff PASS、pyright 0 errors、pytest 285 passed / 1 skipped

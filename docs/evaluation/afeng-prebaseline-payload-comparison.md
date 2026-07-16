# 阿峰三课外发载荷 Profile 对比

固定输入：C003、C006、C010，共 5 个案例。所有 Profile 均保留本地完整证据包。

| Profile | Context | External segments | Segment reduction | Characters | Rough tokens | Character reduction | Evidence coverage | PII safe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| full | 0 | 11131 | 0.0% | 3182270 | 909220 | 0.0% | 100.0% | True |
| evidence_focused | 1 | 1996 | 82.1% | 790072 | 225735 | 75.2% | 100.0% | True |
| evidence_focused | 0 | 803 | 92.8% | 479006 | 136859 | 85.0% | 100.0% | True |

## 当前结论

- `full` 只用于本地审计或超长上下文模型，不作为默认 API 载荷。
- `evidence_focused/context=1` 保留所有引用证据及相邻上下文，作为完整度优先候选。
- `evidence_focused/context=0` 保留所有引用证据但不带相邻段，作为上下文受限候选。
- 两种 focused Profile 的必需 evidence 覆盖率都必须保持 100%。
- 取得真实模型上下文限制后，再确定三课 A/B 使用窗口 0、窗口 1 或两者并跑。

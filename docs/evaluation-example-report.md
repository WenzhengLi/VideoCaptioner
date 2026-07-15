# 示例评估报告（合成数据，无敏感内容）

- dry_run: `false`
- hardware: 以本机实际运行为准

## Summary（合成 predictions）

```json
{
  "asr": {"mean_cer": 0.0, "mean_wer": 0.0, "n": 1},
  "diarization": {"mean_der": 0.0, "n": 1},
  "board_detection": {"mean_iou": ">0.9", "mean_top_k_hit_rate": 1.0, "n": 1},
  "ocr": {"mean_char_accuracy": 1.0, "n": 1},
  "diarizer_compare": [
    {
      "sample_id": "synth_diar_02",
      "engines": {
        "wespeaker": {"der": 0.0},
        "campplus": {"der": ">0"}
      },
      "ranking": ["wespeaker", "campplus"],
      "winner": "wespeaker"
    }
  ]
}
```

说明：数值来自 `tests/fixtures/manifests/example_predictions.json` 的确定性回放；真实课堂视频需本机自行准备媒体后再生成报告。

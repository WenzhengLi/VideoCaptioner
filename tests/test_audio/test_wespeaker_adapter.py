"""Unit tests for WeSpeaker / CAM++ adapters (fake models only, no download)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from course_video_analyzer.audio.campplus_adapter import (
    CampPlusAdapter,
    CampPlusConfig,
    CampPlusDeviceError,
    CampPlusParseError,
    parse_campplus_raw,
)
from course_video_analyzer.audio.wespeaker_adapter import (
    WeSpeakerAdapter,
    WeSpeakerConfig,
    WeSpeakerDeviceError,
    WeSpeakerNotAvailableError,
    WeSpeakerRuntimeError,
    create_default_diarizer,
)
from course_video_analyzer.audio.wespeaker_parser import (
    WeSpeakerParseError,
    parse_wespeaker_raw,
    speaker_id_from_label,
)


def test_parse_wespeaker_empty() -> None:
    assert parse_wespeaker_raw([]) == []
    assert parse_wespeaker_raw(None) == []


def test_parse_wespeaker_seconds_to_ms_and_speaker_labels() -> None:
    raw = [
        ("utt", 0.0, 1.2, 0),
        ("utt", 1.2, 2.5, 1),
        ("utt", 3.0, 4.0, 0),
    ]
    turns = parse_wespeaker_raw(raw)
    assert [t.speaker_id for t in turns] == ["Speaker 0", "Speaker 1", "Speaker 0"]
    assert turns[0].start_ms == 0
    assert turns[0].end_ms == 1200
    assert turns[1].start_ms == 1200
    assert turns[1].end_ms == 2500
    assert all(t.source == "wespeaker" for t in turns)
    assert all(t.confidence is None for t in turns)


def test_parse_wespeaker_label_stability_and_sort() -> None:
    # Sparse labels; first-heard cluster id 2 becomes Speaker 0.
    raw = [
        ("utt", 2.0, 3.0, 2),
        ("utt", 0.5, 1.0, 5),
        ("utt", 1.0, 1.5, 2),
    ]
    turns = parse_wespeaker_raw(raw)
    assert [t.start_ms for t in turns] == [500, 1000, 2000]
    assert turns[0].speaker_id == "Speaker 0"  # label 5 first
    assert turns[1].speaker_id == "Speaker 1"  # label 2 second
    assert turns[2].speaker_id == "Speaker 1"  # same label 2


def test_parse_wespeaker_skips_noise_label() -> None:
    raw = [("utt", 0.0, 1.0, 0), ("utt", 1.0, 2.0, -1)]
    turns = parse_wespeaker_raw(raw)
    assert len(turns) == 1
    assert turns[0].speaker_id == "Speaker 0"


def test_parse_wespeaker_illegal_interval() -> None:
    with pytest.raises(WeSpeakerParseError, match="非法时间戳"):
        parse_wespeaker_raw([("utt", 2.0, 1.0, 0)])


def test_parse_wespeaker_illegal_shape() -> None:
    with pytest.raises(WeSpeakerParseError, match="应为 list"):
        parse_wespeaker_raw({"bad": True})
    with pytest.raises(WeSpeakerParseError, match="长度"):
        parse_wespeaker_raw([("utt", 0.0, 1.0)])


def test_parse_wespeaker_dict_rows() -> None:
    raw = [{"utt": "a", "start": 0.1, "end": 0.2, "label": 0}]
    turns = parse_wespeaker_raw(raw)
    assert turns[0].start_ms == 100
    assert turns[0].end_ms == 200


def test_speaker_id_from_label() -> None:
    assert speaker_id_from_label(0) == "Speaker 0"
    assert speaker_id_from_label("Speaker 3") == "Speaker 3"
    assert speaker_id_from_label("2") == "Speaker 2"
    with pytest.raises(WeSpeakerParseError):
        speaker_id_from_label("alice")


def test_diarize_with_fake_model_writes_artifacts(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    fake = MagicMock()
    fake.diarize.return_value = [
        ("unk", 0.0, 1.0, 0),
        ("unk", 1.5, 2.5, 1),
    ]
    adapter = WeSpeakerAdapter(model=fake)
    turns = adapter.diarize(wav, tmp_path / "artifacts")

    assert len(turns) == 2
    assert {t.speaker_id for t in turns} == {"Speaker 0", "Speaker 1"}
    assert (tmp_path / "artifacts" / "wespeaker_raw.json").is_file()
    assert (tmp_path / "artifacts" / "speaker_turns.json").is_file()
    fake.diarize.assert_called_once_with(str(wav), utt="unk")
    assert adapter.model_loaded is True


def test_diarize_empty_speech_returns_empty_list(tmp_path: Path) -> None:
    wav = tmp_path / "silence.wav"
    wav.write_bytes(b"RIFF")
    fake = MagicMock()
    fake.diarize.return_value = []
    turns = WeSpeakerAdapter(model=fake).diarize(wav, tmp_path / "out")
    assert turns == []
    payload = (tmp_path / "out" / "speaker_turns.json").read_text(encoding="utf-8")
    assert payload.strip() == "[]"


def test_diarize_missing_wav(tmp_path: Path) -> None:
    fake = MagicMock()
    with pytest.raises(FileNotFoundError):
        WeSpeakerAdapter(model=fake).diarize(tmp_path / "missing.wav", tmp_path)


def test_diarize_runtime_error_wrapped(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    fake = MagicMock()
    fake.diarize.side_effect = RuntimeError("boom")
    with pytest.raises(WeSpeakerRuntimeError, match="说话人分离失败"):
        WeSpeakerAdapter(model=fake).diarize(wav, tmp_path)


def test_diarize_illegal_raw_raises_parse_error(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    fake = MagicMock()
    fake.diarize.return_value = "not-a-list"
    with pytest.raises(WeSpeakerParseError):
        WeSpeakerAdapter(model=fake).diarize(wav, tmp_path)


def test_create_default_diarizer_is_wespeaker() -> None:
    diarizer = create_default_diarizer()
    assert isinstance(diarizer, WeSpeakerAdapter)


def test_ensure_model_lazy_import_and_device() -> None:
    fake_model = MagicMock()
    load_model = MagicMock(return_value=fake_model)
    with patch(
        "course_video_analyzer.audio.wespeaker_adapter._import_wespeaker_load_model",
        return_value=load_model,
    ):
        adapter = WeSpeakerAdapter(WeSpeakerConfig(model="chinese", device="cpu"))
        assert adapter.model_loaded is False
        model = adapter._ensure_model()
    assert model is fake_model
    load_model.assert_called_once_with("chinese")
    fake_model.set_device.assert_called_once_with("cpu")
    fake_model.set_diarization_params.assert_called_once()
    assert adapter.model_loaded is True


def test_cuda_device_unavailable() -> None:
    load_model = MagicMock()
    with (
        patch(
            "course_video_analyzer.audio.wespeaker_adapter._import_wespeaker_load_model",
            return_value=load_model,
        ),
        patch(
            "course_video_analyzer.audio.wespeaker_adapter._validate_device",
            side_effect=WeSpeakerDeviceError("no cuda"),
        ),
    ):
        adapter = WeSpeakerAdapter(WeSpeakerConfig(device="cuda:0"))
        with pytest.raises(WeSpeakerDeviceError, match="no cuda"):
            adapter._ensure_model()
    load_model.assert_not_called()


def test_validate_device_rejects_unknown() -> None:
    from course_video_analyzer.audio.wespeaker_adapter import _validate_device

    with pytest.raises(WeSpeakerDeviceError, match="不支持"):
        _validate_device("mps")


def test_import_missing_wespeaker() -> None:
    import sys

    from course_video_analyzer.audio import wespeaker_adapter as mod

    with patch.dict(sys.modules, {"wespeaker": None}):
        with pytest.raises(WeSpeakerNotAvailableError):
            mod._import_wespeaker_load_model()


def test_model_path_override(tmp_path: Path) -> None:
    model_dir = tmp_path / "chinese_model"
    model_dir.mkdir()
    fake_model = MagicMock()
    load_model = MagicMock(return_value=fake_model)
    with patch(
        "course_video_analyzer.audio.wespeaker_adapter._import_wespeaker_load_model",
        return_value=load_model,
    ):
        adapter = WeSpeakerAdapter(WeSpeakerConfig(model_path=model_dir))
        adapter._ensure_model()
    load_model.assert_called_once_with(str(model_dir.resolve()))


def test_campplus_parse_sentence_info() -> None:
    raw = [
        {
            "sentence_info": [
                {"text": "你好", "start": 0, "end": 800, "spk": 0},
                {"text": "大家好", "start": 900, "end": 1600, "spk": 1},
                {"text": "继续", "start": 1700, "end": 2200, "spk": 0},
            ]
        }
    ]
    turns = parse_campplus_raw(raw)
    assert [t.speaker_id for t in turns] == ["Speaker 0", "Speaker 1", "Speaker 0"]
    assert all(t.source == "campplus" for t in turns)
    assert turns[0].end_ms == 800
    assert "text" not in turns[0].model_dump()


def test_campplus_parse_empty() -> None:
    assert parse_campplus_raw([]) == []
    assert parse_campplus_raw([{"sentence_info": []}]) == []


def test_campplus_parse_missing_spk() -> None:
    with pytest.raises(CampPlusParseError, match="spk"):
        parse_campplus_raw([{"sentence_info": [{"text": "x", "start": 0, "end": 1}]}])


def test_campplus_adapter_fake_generate(tmp_path: Path) -> None:
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    fake = MagicMock()
    fake.generate.return_value = [
        {
            "sentence_info": [
                {"text": "a", "start": 0, "end": 500, "spk": 0},
                {"text": "b", "start": 600, "end": 1200, "spk": 1},
            ]
        }
    ]
    turns = CampPlusAdapter(model=fake).diarize(wav, tmp_path / "arts")
    assert {t.speaker_id for t in turns} == {"Speaker 0", "Speaker 1"}
    assert (tmp_path / "arts" / "campplus_raw.json").is_file()
    assert (tmp_path / "arts" / "speaker_turns.json").is_file()
    dumped = (tmp_path / "arts" / "speaker_turns.json").read_text(encoding="utf-8")
    assert "你好" not in dumped
    assert '"text"' not in dumped


def test_campplus_device_unavailable() -> None:
    with (
        patch(
            "course_video_analyzer.audio.campplus_adapter._import_automodel",
            return_value=MagicMock(),
        ),
        patch(
            "course_video_analyzer.audio.campplus_adapter._validate_device",
            side_effect=CampPlusDeviceError("no cuda"),
        ),
    ):
        adapter = CampPlusAdapter(CampPlusConfig(device="cuda:0"))
        with pytest.raises(CampPlusDeviceError):
            adapter._ensure_model()

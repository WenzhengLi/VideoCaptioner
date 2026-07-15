from course_video_analyzer.analysis_cli import build_parser


def test_single_video_cli_requires_explicit_job_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["lesson.mp4", "--job-id", "C001-RUN-001"])

    assert args.job_id == "C001-RUN-001"
    assert args.processing_profile == "complete-v1"
    assert args.interval_ms == 5000
    assert args.max_frames == 800

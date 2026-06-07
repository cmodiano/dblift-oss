from datetime import datetime, timezone

import pytest


def test_parse_report_formats_accepts_comma_separated_values():
    from cli.handlers.report_outputs import parse_report_formats

    assert parse_report_formats("json,html,text") == ["json", "html", "text"]


def test_parse_report_formats_normalizes_console_to_text():
    from cli.handlers.report_outputs import parse_report_formats

    assert parse_report_formats("console") == ["text"]


def test_every_report_format_has_a_file_extension():
    from cli.handlers.report_outputs import FORMAT_EXTENSIONS, REPORT_FORMATS

    assert set(REPORT_FORMATS) <= set(FORMAT_EXTENSIONS)


def test_parse_report_formats_rejects_unknown_value():
    from cli.handlers.report_outputs import parse_report_formats

    with pytest.raises(ValueError, match="Unsupported report format: xml"):
        parse_report_formats("json,xml")


def test_build_report_outputs_requires_output_dir_for_multiple_formats(tmp_path):
    from cli.handlers.report_outputs import build_report_outputs

    with pytest.raises(ValueError, match="--output-dir is required when multiple formats"):
        build_report_outputs(
            command="preflight",
            raw_format="json,html",
            output=None,
            output_dir=None,
        )


def test_build_report_outputs_rejects_output_file_for_multiple_formats(tmp_path):
    from cli.handlers.report_outputs import build_report_outputs

    with pytest.raises(ValueError, match="--output cannot be used with multiple formats"):
        build_report_outputs(
            command="plan",
            raw_format="json,html",
            output=str(tmp_path / "plan.json"),
            output_dir=str(tmp_path),
        )


def test_build_report_outputs_rejects_output_file_with_output_dir_for_single_format(tmp_path):
    from cli.handlers.report_outputs import build_report_outputs

    with pytest.raises(ValueError, match="--output cannot be used with --output-dir"):
        build_report_outputs(
            command="plan",
            raw_format="json",
            output=str(tmp_path / "plan.json"),
            output_dir=str(tmp_path / "reports"),
        )


def test_build_report_outputs_uses_one_timestamp_for_all_artifacts(tmp_path):
    from cli.handlers.report_outputs import build_report_outputs

    stamp = datetime(2026, 6, 1, 14, 35, 22, tzinfo=timezone.utc)

    outputs = build_report_outputs(
        command="preflight",
        raw_format="json,html,text",
        output=None,
        output_dir=str(tmp_path),
        now=lambda: stamp,
    )

    assert [item.format for item in outputs] == ["json", "html", "text"]
    assert [item.path for item in outputs] == [
        tmp_path / "preflight-report-20260601T143522Z.json",
        tmp_path / "preflight-report-20260601T143522Z.html",
        tmp_path / "preflight-report-20260601T143522Z.txt",
    ]
    assert len({item.generated_at for item in outputs}) == 1


def test_build_report_outputs_uses_unique_names_for_shared_extensions(tmp_path):
    from cli.handlers.report_outputs import build_report_outputs

    stamp = datetime(2026, 6, 1, 14, 35, 22, tzinfo=timezone.utc)

    outputs = build_report_outputs(
        command="plan",
        raw_format="json,gitlab,text,compact,github-actions",
        output=None,
        output_dir=str(tmp_path),
        now=lambda: stamp,
    )

    assert [item.path for item in outputs] == [
        tmp_path / "plan-report-20260601T143522Z.json",
        tmp_path / "plan-report-20260601T143522Z.gitlab.json",
        tmp_path / "plan-report-20260601T143522Z.txt",
        tmp_path / "plan-report-20260601T143522Z.compact.txt",
        tmp_path / "plan-report-20260601T143522Z.github-actions.txt",
    ]
    assert len({item.path for item in outputs}) == len(outputs)


def test_build_report_outputs_keeps_single_output_file(tmp_path):
    from cli.handlers.report_outputs import build_report_outputs

    output = tmp_path / "plan-report.html"

    outputs = build_report_outputs(
        command="plan",
        raw_format="html",
        output=str(output),
        output_dir=None,
    )

    assert len(outputs) == 1
    assert outputs[0].format == "html"
    assert outputs[0].path == output

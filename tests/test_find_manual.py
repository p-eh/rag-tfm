from types import SimpleNamespace

import pytest

from src import find_manual, ingest
from src.find_manual import (
    SearchIncompleteError,
    confirm_candidate,
    filename_for,
    is_pdf_response,
    needs_selection,
    parse_candidates,
    unique_path,
)


def test_parse_candidates_plain_json():
    text = '[{"url": "https://x.com/a.pdf", "title": "t", "confidence": "high", "note": "n"}]'

    assert parse_candidates(text) == [
        {"url": "https://x.com/a.pdf", "title": "t", "confidence": "high", "note": "n"}
    ]


def test_parse_candidates_strips_markdown_fence():
    text = 'Sure, here you go:\n```json\n[{"url": "https://x.com/a.pdf"}]\n```'

    assert parse_candidates(text) == [{"url": "https://x.com/a.pdf"}]


def test_parse_candidates_empty_array():
    assert parse_candidates("[]") == []


def test_parse_candidates_no_json_present():
    assert parse_candidates("I could not find anything.") == []


def test_parse_candidates_drops_entries_without_url():
    text = '[{"title": "no url here"}, {"url": "https://x.com/a.pdf"}]'

    assert parse_candidates(text) == [{"url": "https://x.com/a.pdf"}]


def test_needs_selection_false_for_single_high_confidence():
    assert needs_selection([{"url": "https://x.com/a.pdf", "confidence": "high"}]) is False


def test_needs_selection_true_for_single_low_confidence():
    assert needs_selection([{"url": "https://x.com/a.pdf", "confidence": "low"}]) is True


def test_needs_selection_true_for_multiple_candidates():
    candidates = [
        {"url": "https://x.com/a.pdf", "confidence": "high"},
        {"url": "https://x.com/b.pdf", "confidence": "high"},
    ]

    assert needs_selection(candidates) is True


def test_confirm_candidate_no_candidates_returns_none():
    assert confirm_candidate([], input_func=lambda _: "y") is None


def test_confirm_candidate_single_confirmed():
    candidate = {"url": "https://x.com/a.pdf", "confidence": "high"}

    assert confirm_candidate([candidate], input_func=lambda _: "y") == candidate


def test_confirm_candidate_single_declined():
    candidate = {"url": "https://x.com/a.pdf", "confidence": "high"}

    assert confirm_candidate([candidate], input_func=lambda _: "n") is None


def test_confirm_candidate_list_picks_by_number():
    candidates = [
        {"url": "https://x.com/a.pdf", "confidence": "medium"},
        {"url": "https://x.com/b.pdf", "confidence": "medium"},
    ]

    assert confirm_candidate(candidates, input_func=lambda _: "2") == candidates[1]


def test_confirm_candidate_list_declined_on_blank():
    candidates = [
        {"url": "https://x.com/a.pdf", "confidence": "medium"},
        {"url": "https://x.com/b.pdf", "confidence": "medium"},
    ]

    assert confirm_candidate(candidates, input_func=lambda _: "") is None


def test_confirm_candidate_list_out_of_range_returns_none():
    candidates = [{"url": "https://x.com/a.pdf", "confidence": "medium"}]

    assert confirm_candidate(candidates, input_func=lambda _: "5") is None


def test_is_pdf_response_accepts_pdf_bytes_with_pdf_content_type():
    assert is_pdf_response(b"%PDF-1.4 ...", "application/pdf") is True


def test_is_pdf_response_accepts_pdf_bytes_with_octet_stream():
    assert is_pdf_response(b"%PDF-1.4 ...", "application/octet-stream") is True


def test_is_pdf_response_rejects_non_pdf_bytes_with_pdf_content_type():
    assert is_pdf_response(b"<html>login</html>", "application/pdf") is False


def test_is_pdf_response_rejects_pdf_bytes_with_html_content_type():
    assert is_pdf_response(b"%PDF-1.4 ...", "text/html") is False


def test_is_pdf_response_requires_exact_media_type():
    assert is_pdf_response(b"%PDF-1.4 ...", "text/x-not-a-pdf") is False


def test_is_pdf_response_rejects_html():
    assert is_pdf_response(b"<html></html>", "text/html; charset=utf-8") is False


def test_filename_for_uses_url_basename_when_pdf():
    candidate = {"title": "Ignored Title"}

    assert filename_for(candidate, "https://x.com/path/manual.pdf") == "manual.pdf"


def test_filename_for_falls_back_to_slugified_title():
    candidate = {"title": "My Cool Manual!"}

    assert filename_for(candidate, "https://x.com/download?id=123") == "My-Cool-Manual.pdf"


def test_filename_for_falls_back_to_generic_name_without_title():
    candidate = {}

    assert filename_for(candidate, "https://x.com/download") == "manual.pdf"


def test_filename_for_decodes_and_sanitises_url_basename():
    url = "https://x.com/docs/My%20Manual%3A%20v2%3F.pdf"

    assert filename_for({}, url) == "My-Manual--v2.pdf"


def test_filename_for_falls_back_to_title_when_url_stem_is_unusable():
    assert filename_for({"title": "Pump"}, "https://x.com/%3A%3A.pdf") == "Pump.pdf"


def test_parse_candidates_ignores_brackets_in_prose():
    text = (
        "I'll search for the [Aquaflow 200] manual.\n"
        'Found it: [{"url": "https://x.com/a.pdf", "title": "Manual [EN]"}]'
    )

    assert parse_candidates(text) == [{"url": "https://x.com/a.pdf", "title": "Manual [EN]"}]


def test_parse_candidates_prefers_last_array():
    text = '[{"url": "https://x.com/draft.pdf"}] then final: [{"url": "https://x.com/a.pdf"}]'

    assert parse_candidates(text) == [{"url": "https://x.com/a.pdf"}]


def test_needs_selection_confidence_is_case_insensitive():
    assert needs_selection([{"url": "https://x.com/a.pdf", "confidence": "High"}]) is False


def test_unique_path_uses_name_when_free(tmp_path):
    assert unique_path(tmp_path, "manual.pdf", b"%PDF-a") == (tmp_path / "manual.pdf", False)


def test_unique_path_reuses_identical_file(tmp_path):
    (tmp_path / "manual.pdf").write_bytes(b"%PDF-a")

    assert unique_path(tmp_path, "manual.pdf", b"%PDF-a") == (tmp_path / "manual.pdf", True)


def test_unique_path_suffixes_different_file(tmp_path):
    (tmp_path / "manual.pdf").write_bytes(b"%PDF-a")
    (tmp_path / "manual-2.pdf").write_bytes(b"%PDF-b")

    assert unique_path(tmp_path, "manual.pdf", b"%PDF-c") == (tmp_path / "manual-3.pdf", False)


def _text_response(stop_reason, text=""):
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
    )


def _fake_client(responses, calls):
    def create(**kwargs):
        calls.append(kwargs["messages"])
        return responses.pop(0)

    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_search_candidates_continues_after_pause_turn(monkeypatch):
    calls = []
    responses = [
        _text_response("pause_turn", "Searching [step 1]..."),
        _text_response("end_turn", '[{"url": "https://x.com/a.pdf"}]'),
    ]
    monkeypatch.setattr(find_manual, "_build_client", lambda: _fake_client(responses, calls))

    assert find_manual.search_candidates("X") == [{"url": "https://x.com/a.pdf"}]
    assert len(calls) == 2
    assert calls[1][1]["role"] == "assistant"


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_search_candidates_raises_when_cut_off(monkeypatch, stop_reason):
    responses = [_text_response(stop_reason, '[{"url": "https://x.com/a')]
    monkeypatch.setattr(find_manual, "_build_client", lambda: _fake_client(responses, []))

    with pytest.raises(SearchIncompleteError):
        find_manual.search_candidates("X")


def _stub_pipeline(monkeypatch, tmp_path, ingest_func):
    candidate = {"url": "https://x.com/a.pdf", "confidence": "high"}
    monkeypatch.setattr(find_manual, "search_candidates", lambda _: [candidate])

    def fake_download(_candidate):
        path = tmp_path / "a.pdf"
        path.write_bytes(b"%PDF-broken")
        return path, False

    monkeypatch.setattr(find_manual, "download_manual", fake_download)
    monkeypatch.setattr(ingest, "ingest_and_report", ingest_func)
    return tmp_path / "a.pdf"


def test_find_and_ingest_removes_file_when_ingestion_fails(monkeypatch, tmp_path):
    def broken_ingest(_path):
        raise ValueError("corrupt PDF")

    path = _stub_pipeline(monkeypatch, tmp_path, broken_ingest)

    assert find_manual.find_and_ingest("X", input_func=lambda _: "y") is None
    assert not path.exists()


def test_find_and_ingest_reports_incomplete_search(monkeypatch, capsys):
    def incomplete(_):
        raise SearchIncompleteError("web search stopped early (max_tokens)")

    monkeypatch.setattr(find_manual, "search_candidates", incomplete)

    assert find_manual.find_and_ingest("X") is None
    assert "Search incomplete" in capsys.readouterr().out


def test_main_exits_non_zero_when_nothing_ingested(monkeypatch):
    monkeypatch.setattr(find_manual, "find_and_ingest", lambda _: None)
    monkeypatch.setattr("sys.argv", ["find_manual", "X"])

    with pytest.raises(SystemExit) as exc_info:
        find_manual.main()
    assert exc_info.value.code == 1

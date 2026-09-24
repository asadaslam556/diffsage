from app.services.business.repository import title_from


def test_title_skips_code_fences():
    assert title_from("```diff\n-def load_rows(path):\n+def load(p):\n```") == "-def load_rows(path):"


def test_title_falls_back_and_truncates():
    assert title_from("```\n```") == "New review"
    assert title_from("x" * 100) == "x" * 77 + "..."

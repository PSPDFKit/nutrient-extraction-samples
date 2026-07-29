from pathlib import Path

import pytest

from common.html_env import coerce_num, create_html_env, script_safe_json

HOSTILE = "</script><script>alert(1)</script>"


def test_environment_autoescapes_hostile_document_text(tmp_path: Path) -> None:
    template_path = tmp_path / "hostile.html"
    template_path.write_text("<div>{{ value }}</div>", encoding="utf-8")

    rendered = create_html_env(tmp_path).get_template(template_path.name).render(value=HOSTILE)

    assert HOSTILE not in rendered
    assert "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_script_safe_json_escapes_less_than_for_script_context() -> None:
    serialized = script_safe_json({"value": HOSTILE})

    assert "<" not in serialized
    assert "\\u003c/script>\\u003cscript>alert(1)\\u003c/script>" in serialized


def test_coerce_num_rejects_non_numeric_input() -> None:
    with pytest.raises((TypeError, ValueError)):
        coerce_num("alert(1)")


def test_coerce_num_supports_float_and_integer_coercion() -> None:
    assert coerce_num("12.5") == 12.5
    assert coerce_num("12", kind="int") == 12

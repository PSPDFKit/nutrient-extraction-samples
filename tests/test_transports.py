from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from common import api
from common.cache import get_cached_response


@dataclass
class CapturedRequest:
    method: str
    url: str
    headers: dict[str, str]
    part_names: list[str]
    file_name: str
    file_content_type: str
    file_bytes: bytes
    instructions_content_type: str
    instructions_bytes: bytes


class FakeResponse:
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_args: Any) -> bool:
        return False

    async def json(self) -> dict[str, Any]:
        return self._body


def session_factory(
    captured: list[CapturedRequest],
    *,
    status: int = 200,
    body: dict[str, Any] | None = None,
) -> type:
    response_body = body if body is not None else {"ok": True}

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: Any) -> bool:
            return False

        def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            data: Any,
        ) -> FakeResponse:
            file_options, file_headers, file_value = data._fields[0]
            instruction_options, instruction_headers, instruction_value = data._fields[1]

            file_bytes = file_value.read()
            file_value.seek(0)
            captured.append(
                CapturedRequest(
                    method="POST",
                    url=url,
                    headers=headers,
                    part_names=[
                        file_options["name"],
                        instruction_options["name"],
                    ],
                    file_name=file_options["filename"],
                    file_content_type=file_headers["Content-Type"],
                    file_bytes=file_bytes,
                    instructions_content_type=instruction_headers["Content-Type"],
                    instructions_bytes=instruction_value.encode("utf-8"),
                )
            )
            return FakeResponse(status, response_body)

    return FakeSession


def test_extract_transport_pins_exact_multipart_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "controlled.pdf"
    pdf_bytes = b"%PDF-extract-offline"
    pdf_path.write_bytes(pdf_bytes)
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    instructions = api.build_extract_instructions("agentic", schema)
    captured: list[CapturedRequest] = []
    monkeypatch.setattr(api.aiohttp, "ClientSession", session_factory(captured))

    result = asyncio.run(
        api.extract_transport(pdf_path, instructions, "transport-test-key")
    )

    assert result == {"ok": True}
    assert captured == [
        CapturedRequest(
            method="POST",
            url="https://api.nutrient.io/extraction/extract",
            headers={"Authorization": "Bearer transport-test-key"},
            part_names=["file", "instructions"],
            file_name="controlled.pdf",
            file_content_type="application/pdf",
            file_bytes=pdf_bytes,
            instructions_content_type="application/json",
            instructions_bytes=(
                b'{"mode": "agentic", "schema": {"type": "object", '
                b'"properties": {"name": {"type": "string"}}}, '
                b'"citationsEnabled": true}'
            ),
        )
    ]


def test_parse_transport_pins_exact_multipart_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "appraisal.pdf"
    pdf_bytes = b"%PDF-parse-offline"
    pdf_path.write_bytes(pdf_bytes)
    instructions = api.build_parse_instructions("agentic")
    captured: list[CapturedRequest] = []
    monkeypatch.setattr(api.aiohttp, "ClientSession", session_factory(captured))

    result = asyncio.run(
        api.parse_transport(pdf_path, instructions, "transport-test-key")
    )

    assert result == {"ok": True}
    assert captured == [
        CapturedRequest(
            method="POST",
            url="https://api.nutrient.io/parse",
            headers={"Authorization": "Bearer transport-test-key"},
            part_names=["file", "instructions"],
            file_name="appraisal.pdf",
            file_content_type="application/pdf",
            file_bytes=pdf_bytes,
            instructions_content_type="application/json",
            instructions_bytes=(
                b'{"mode": "agentic", "outputFormat": {"elements": '
                b'{"bounds": true, "confidence": true, "text": true}}}'
            ),
        )
    ]


@pytest.mark.parametrize("status", [199, 201, 204, 500])
def test_transport_accepts_exactly_status_200_and_redacts_non_200_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    sentinel = "SENTINEL-NUTRIENT-API-KEY"
    pdf_path = tmp_path / "status.pdf"
    pdf_path.write_bytes(b"%PDF-status-offline")
    captured: list[CapturedRequest] = []
    monkeypatch.setattr(
        api.aiohttp,
        "ClientSession",
        session_factory(captured, status=status, body={"error": sentinel}),
    )

    with pytest.raises(api.ApiError) as raised:
        asyncio.run(
            api.parse_transport(
                pdf_path,
                api.build_parse_instructions("agentic"),
                sentinel,
            )
        )

    assert sentinel not in str(raised.value)
    assert "Authorization" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert len(captured) == 1


def test_cache_wraps_key_bearing_transport_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "SENTINEL-NUTRIENT-API-KEY"
    pdf_path = tmp_path / "cache-error.pdf"
    pdf_path.write_bytes(b"%PDF-cache-error-offline")
    instructions = api.build_extract_instructions("agentic", {"type": "object"})
    monkeypatch.setenv("NUTRIENT_API_KEY", sentinel)

    async def unsafe_transport(*_args: Any) -> dict[str, Any]:
        raise api.ApiError(f"Authorization: Bearer {sentinel}")

    with pytest.raises(api.ApiError) as raised:
        asyncio.run(
            get_cached_response(
                pdf_path,
                api.EXTRACT_ENDPOINT,
                instructions,
                tmp_path / "cache",
                refresh=True,
                transport=unsafe_transport,
            )
        )

    assert sentinel not in str(raised.value)
    assert "Authorization" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert not (tmp_path / "cache").exists()

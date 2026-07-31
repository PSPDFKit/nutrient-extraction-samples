"""Credential-safe aiohttp transports for Nutrient extraction APIs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import aiohttp

EXTRACT_URL = "https://api.nutrient.io/extraction/extract"
PARSE_URL = "https://api.nutrient.io/extraction/parse"

EXTRACT_ENDPOINT = "extraction-extract"
PARSE_ENDPOINT = "extraction-parse"


class ApiError(RuntimeError):
    """Raised when a live Nutrient request fails without exposing credentials."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def build_extract_instructions(
    mode: str,
    schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the live-proven extraction instructions in wire order."""

    return {
        "mode": mode,
        "schema": schema,
        "citationsEnabled": True,
    }


def build_parse_instructions(mode: str) -> dict[str, Any]:
    """Build the live-proven parse instructions in wire order."""

    return {
        "mode": mode,
        "outputFormat": {
            "elements": {
                "bounds": True,
                "confidence": True,
                "text": True,
            }
        },
    }


async def _post_multipart(
    pdf_bytes: bytes,
    filename: str,
    instructions: Mapping[str, Any],
    api_key: str,
    url: str,
    operation: str,
) -> dict[str, Any]:
    try:
        data = aiohttp.FormData()
        data.add_field(
            "file",
            pdf_bytes,
            filename=filename,
            content_type="application/pdf",
        )
        data.add_field(
            "instructions",
            json.dumps(instructions),
            content_type="application/json",
        )

        headers = {"Authorization": f"Bearer {api_key}"}
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, data=data) as response:
                if response.status != 200:
                    raise ApiError(
                        f"Nutrient {operation} request failed with "
                        f"status {response.status}.",
                        status=response.status,
                    )
                result = await response.json()
    except ApiError:
        raise
    except aiohttp.ClientError:
        raise ApiError(f"Nutrient {operation} request failed.") from None
    except OSError:
        raise ApiError(f"Could not read PDF {filename}.") from None
    except Exception:
        raise ApiError(f"Nutrient {operation} request failed.") from None

    if not isinstance(result, dict):
        raise ApiError(f"Nutrient {operation} response was not a JSON object.")
    return result


async def extract_transport(
    pdf_bytes: bytes,
    filename: str,
    instructions: Mapping[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """POST using the request shape the committed demo responses were produced with."""

    return await _post_multipart(
        pdf_bytes,
        filename,
        instructions,
        api_key,
        EXTRACT_URL,
        "extract",
    )


async def parse_transport(
    pdf_bytes: bytes,
    filename: str,
    instructions: Mapping[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """POST using the request shape the committed demo responses were produced with."""

    return await _post_multipart(
        pdf_bytes,
        filename,
        instructions,
        api_key,
        PARSE_URL,
        "parse",
    )

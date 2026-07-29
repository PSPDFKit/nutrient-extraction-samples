"""Credential-safe aiohttp transports for Nutrient extraction APIs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import aiohttp

EXTRACT_URL = "https://api.nutrient.io/extraction/extract"
PARSE_URL = "https://api.nutrient.io/parse"

EXTRACT_ENDPOINT = "extraction-extract"
PARSE_ENDPOINT = "extraction-parse"


class ApiError(RuntimeError):
    """Raised when a live Nutrient request fails without exposing credentials."""


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
    pdf_path: str | Path,
    instructions: Mapping[str, Any],
    api_key: str,
    url: str,
    operation: str,
) -> dict[str, Any]:
    source_path = Path(pdf_path)

    try:
        with source_path.open("rb") as pdf_file:
            data = aiohttp.FormData()
            data.add_field(
                "file",
                pdf_file,
                filename=source_path.name,
                content_type="application/pdf",
            )
            data.add_field(
                "instructions",
                json.dumps(instructions),
                content_type="application/json",
            )

            headers = {"Authorization": f"Bearer {api_key}"}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    if response.status != 200:
                        raise ApiError(f"Nutrient {operation} request failed.")
                    result = await response.json()
    except ApiError:
        raise
    except Exception:
        raise ApiError(f"Nutrient {operation} request failed.") from None

    if not isinstance(result, dict):
        raise ApiError(f"Nutrient {operation} response was not a JSON object.")
    return result


async def extract_transport(
    pdf_path: str | Path,
    instructions: Mapping[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """POST one PDF to the extraction endpoint using HER request shape."""

    return await _post_multipart(
        pdf_path,
        instructions,
        api_key,
        EXTRACT_URL,
        "extract",
    )


async def parse_transport(
    pdf_path: str | Path,
    instructions: Mapping[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """POST one PDF to the parse endpoint using HER request shape."""

    return await _post_multipart(
        pdf_path,
        instructions,
        api_key,
        PARSE_URL,
        "parse",
    )

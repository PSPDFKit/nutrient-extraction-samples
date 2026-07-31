from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from common.api import PARSE_ENDPOINT, build_parse_instructions
from common.cache import get_cached_response
from common.html_env import coerce_num, create_html_env
from common.render import ensure_page_png

load_dotenv(REPO_ROOT / ".env")

DEMO_DIR = Path(__file__).parent


def _number(value: Any) -> float | int:
    kind = "int" if isinstance(value, int) and not isinstance(value, bool) else "float"
    return coerce_num(value, kind=kind)


async def process_document(
    doc_config: dict[str, Any],
    refresh: bool = False,
) -> tuple[dict[str, Any], str, float | int, float | int]:
    pdf_path = (DEMO_DIR / doc_config["file"]).resolve()
    result_json = await get_cached_response(
        pdf_path,
        PARSE_ENDPOINT,
        build_parse_instructions(doc_config["mode"]),
        DEMO_DIR / "cache",
        refresh=refresh,
    )

    page_width = _number(1700)
    page_height = _number(2200)
    found_page_dimensions = False
    for element in result_json.get("output", {}).get("elements", []):
        page = element.get("page")
        if page is not None and not isinstance(page, dict):
            raise ValueError("value must be numeric")
        if page:
            element_page_width = _number(page["width"])
            element_page_height = _number(page["height"])
            if not found_page_dimensions:
                page_width = element_page_width
                page_height = element_page_height
                found_page_dimensions = True

    output_dir = DEMO_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    img_filename = f"{doc_config['id']}_page_0.png"
    img_path = output_dir / img_filename
    if refresh or not img_path.exists():
        ensure_page_png(
            pdf_path,
            0,
            img_path,
            page_dims={"width": page_width, "height": page_height},
            refresh=refresh,
        )
    return result_json, img_filename, page_width, page_height


def build_blocks(result_data: dict[str, Any]) -> list[dict[str, Any]]:
    elements = result_data.get("output", {}).get("elements", [])
    blocks = []

    for element in elements:
        page = element.get("page", {})
        if not isinstance(page, dict):
            raise ValueError("value must be numeric")
        page_index = coerce_num(page.get("pageIndex", 0), kind="int")
        if page_index != 0:
            continue

        text = element.get("text", "").strip()
        if not text:
            continue

        bounds = element.get("bounds")
        if bounds is not None and not isinstance(bounds, dict):
            raise ValueError("value must be numeric")
        if not bounds:
            continue

        confidence = coerce_num(element.get("confidence", 0.0))
        reading_order = coerce_num(element.get("readingOrder", 0), kind="int")
        blocks.append(
            {
                "text": text,
                "type": element.get("type", "paragraph"),
                "role": element.get("role", ""),
                "confidence": int(confidence * 100),
                "x": _number(bounds["x"]),
                "y": _number(bounds["y"]),
                "width": _number(bounds["width"]),
                "height": _number(bounds["height"]),
                "page_index": page_index,
                "reading_order": reading_order,
            }
        )

    blocks.sort(key=lambda block: block["reading_order"])
    return blocks


def render_html(
    blocks: list[dict[str, Any]],
    img_filename: str,
    page_width: float | int,
    page_height: float | int,
    doc_config: dict[str, Any],
) -> None:
    template = create_html_env(DEMO_DIR).get_template("template.html")
    html_output = template.render(
        doc_name=doc_config["name"],
        image_src=img_filename,
        pdf_width=page_width,
        pdf_height=page_height,
        blocks=blocks,
    )

    output_dir = DEMO_DIR / "output"
    with (output_dir / "index.html").open("w", encoding="utf-8") as output_file:
        output_file.write(html_output)
    with (output_dir / "elements.json").open("w", encoding="utf-8") as elements_file:
        json.dump(blocks, elements_file, indent=2)

    print(f"Generated {len(blocks)} cited blocks.")
    print("Open output/index.html in a browser to view the demo.")


async def main(refresh: bool = False) -> None:
    with (DEMO_DIR / "docs.json").open(encoding="utf-8") as docs_file:
        config = json.load(docs_file)[0]
    result_data, img_filename, page_width, page_height = await process_document(
        config,
        refresh=refresh,
    )
    blocks = build_blocks(result_data)
    render_html(
        blocks,
        img_filename,
        page_width,
        page_height,
        config,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the parse citations demo."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Call the live API and replace the committed cache entry.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(refresh=args.refresh))

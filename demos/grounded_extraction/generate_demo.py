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

from common.api import EXTRACT_ENDPOINT, build_extract_instructions
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
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pdf_path = (DEMO_DIR / doc_config["file"]).resolve()
    instructions = build_extract_instructions(
        doc_config["mode"],
        doc_config["schema"],
    )
    result_json = await get_cached_response(
        pdf_path,
        EXTRACT_ENDPOINT,
        instructions,
        DEMO_DIR / "cache",
        refresh=refresh,
    )

    output_dir = DEMO_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    pages_info = []
    for page_index, page_data in enumerate(result_json["output"]["pages"]):
        safe_page_index = coerce_num(page_index, kind="int")
        width = _number(page_data["width"])
        height = _number(page_data["height"])
        img_filename = f"{doc_config['id']}_page_{safe_page_index}.png"
        img_path = output_dir / img_filename
        if refresh or not img_path.exists():
            ensure_page_png(
                pdf_path,
                safe_page_index,
                img_path,
                page_dims={"width": width, "height": height},
                refresh=refresh,
            )
        pages_info.append(
            {
                "index": safe_page_index,
                "src": img_filename,
                "width": width,
                "height": height,
            }
        )

    return result_json, pages_info


def build_cards(
    data_node: Any,
    meta_node: Any,
    path: str = "",
) -> list[dict[str, Any]]:
    cards = []

    if isinstance(data_node, dict):
        for key, value in data_node.items():
            child_meta = meta_node.get(key, {}) if isinstance(meta_node, dict) else {}
            child_path = f"{path}.{key}" if path else key
            cards.extend(build_cards(value, child_meta, child_path))
    elif isinstance(data_node, list):
        meta_list = meta_node if isinstance(meta_node, list) else []
        for index, item in enumerate(data_node):
            child_meta = meta_list[index] if index < len(meta_list) else {}
            child_path = f"{path}[{index}]"
            cards.extend(build_cards(item, child_meta, child_path))
    else:
        if not isinstance(meta_node, dict):
            return cards
        bbox = meta_node.get("bbox")
        if bbox is not None and not isinstance(bbox, dict):
            raise ValueError("value must be numeric")
        if bbox:
            confidence = coerce_num(meta_node.get("confidence", 1.0))
            page_index = coerce_num(meta_node.get("pageIndex", 0), kind="int")
            if isinstance(data_node, (int, float)) and "amount" in path:
                display_value = f"{float(data_node):.2f}"
            elif data_node is None:
                display_value = "—"
            else:
                display_value = str(data_node)
            cards.append(
                {
                    "path": path,
                    "value": display_value,
                    "confidence": int(confidence * 100),
                    "x": _number(bbox["x"]),
                    "y": _number(bbox["y"]),
                    "width": _number(bbox["width"]),
                    "height": _number(bbox["height"]),
                    "page_index": page_index,
                }
            )

    return cards


def render_html_template(
    result_data: dict[str, Any],
    pages_info: list[dict[str, Any]],
    doc_config: dict[str, Any],
) -> None:
    extracted_values = result_data.get("output", {}).get("data", {})
    metadata = result_data.get("output", {}).get("metadata", {})
    cards = build_cards(extracted_values, metadata)
    template = create_html_env(DEMO_DIR).get_template("template.html")
    html_output = template.render(
        doc_name=doc_config["name"],
        pages=pages_info,
        cards=cards,
    )

    output_dir = DEMO_DIR / "output"
    with (output_dir / "index.html").open("w", encoding="utf-8") as output_file:
        output_file.write(html_output)
    with (output_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
        json.dump(dict(sorted(result_data.items())), metadata_file, indent=2)

    print(f"Generated {len(cards)} field highlights across {len(pages_info)} page(s).")
    print("Open output/index.html in a browser to view the demo.")


async def main(refresh: bool = False) -> None:
    with (DEMO_DIR / "docs.json").open(encoding="utf-8") as docs_file:
        config = json.load(docs_file)[0]
    result_data, pages_info = await process_document(config, refresh=refresh)
    render_html_template(result_data, pages_info, config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the grounded extraction demo."
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

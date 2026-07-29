import os
import json
import asyncio
import aiohttp
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from pdf2image import convert_from_path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

PARSE_API_URL = "https://api.nutrient.io/parse"


async def call_api(pdf_path, doc_config, api_key):
    print(f"Uploading and parsing via API: {pdf_path}")

    headers = {"Authorization": f"Bearer {api_key}"}

    data = aiohttp.FormData()
    data.add_field(
        "file",
        open(pdf_path, "rb"),
        filename=pdf_path.name,
        content_type="application/pdf",
    )

    instructions = {
        "mode": doc_config["mode"],
        "outputFormat": {
            "elements": {
                "bounds": True,
                "confidence": True,
                "text": True,
            }
        },
    }
    data.add_field("instructions", json.dumps(instructions), content_type="application/json")

    async with aiohttp.ClientSession() as session:
        async with session.post(PARSE_API_URL, headers=headers, data=data) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"API Error ({response.status}): {text}")
            return await response.json()


async def process_document(doc_config, api_key):
    pdf_path = (Path(__file__).parent / doc_config["file"]).resolve()

    # If a saved Studio JSON result exists, use it — avoids the API call
    saved_json_path = pdf_path.parent / f"{pdf_path.stem}_parse_results.json"
    if saved_json_path.exists():
        print(f"Using saved parse result: {saved_json_path}")
        with open(saved_json_path) as f:
            result_json = json.load(f)
    else:
        if not api_key:
            raise SystemExit(
                f"No saved result at {saved_json_path} and NUTRIENT_API_KEY is not set.\n"
                "Either save the Studio JSON there or set NUTRIENT_API_KEY."
            )
        result_json = await call_api(pdf_path, doc_config, api_key)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    pages = convert_from_path(pdf_path, first_page=1, last_page=1)
    img_filename = f"{doc_config['id']}_page_0.png"
    pages[0].save(output_dir / img_filename, "PNG")

    # Get page dimensions from the first element that reports page info
    page_width, page_height = 1700, 2200
    elements = result_json.get("output", {}).get("elements", [])
    for el in elements:
        if el.get("page"):
            page_width = el["page"]["width"]
            page_height = el["page"]["height"]
            break

    return result_json, img_filename, page_width, page_height


def build_blocks(result_data):
    elements = result_data.get("output", {}).get("elements", [])
    blocks = []

    for el in elements:
        # Only page 1 (index 0) — we only render one page image
        if el.get("page", {}).get("pageIndex", 0) != 0:
            continue

        text = el.get("text", "").strip()
        if not text:
            continue

        bounds = el.get("bounds", {})
        if not bounds:
            continue

        blocks.append({
            "text": text,
            "type": el.get("type", "paragraph"),
            "role": el.get("role", ""),
            "confidence": int(el.get("confidence", 0.0) * 100),
            "x": bounds.get("x", 0),
            "y": bounds.get("y", 0),
            "width": bounds.get("width", 0),
            "height": bounds.get("height", 0),
            "page_index": el.get("page", {}).get("pageIndex", 0),
            "reading_order": el.get("readingOrder", 0),
        })

    blocks.sort(key=lambda b: b["reading_order"])
    return blocks


def render_html(blocks, img_filename, page_width, page_height, doc_config):
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("template.html")

    html_output = template.render(
        doc_name=doc_config["name"],
        image_src=img_filename,
        pdf_width=page_width,
        pdf_height=page_height,
        blocks=blocks,
    )

    output_dir = Path(__file__).parent / "output"
    with open(output_dir / "index.html", "w") as f:
        f.write(html_output)

    with open(output_dir / "elements.json", "w") as f:
        json.dump(blocks, f, indent=2)

    print(f"Generated {len(blocks)} cited blocks.")
    print("Open output/index.html in a browser to view the demo.")


async def main():
    api_key = os.getenv("NUTRIENT_API_KEY")
    if not api_key:
        raise SystemExit("Error: NUTRIENT_API_KEY is not set. Copy .env.example to .env and add your key.")

    docs_path = Path(__file__).parent / "docs.json"
    with open(docs_path, "r") as f:
        configs = json.load(f)

    config = configs[0]
    pdf_path = (Path(__file__).parent / config["file"]).resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found at {pdf_path}. Add the file and retry.")

    result_data, img_filename, page_width, page_height = await process_document(config, api_key)
    blocks = build_blocks(result_data)
    render_html(blocks, img_filename, page_width, page_height, config)


if __name__ == "__main__":
    asyncio.run(main())

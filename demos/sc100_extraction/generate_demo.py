import os
import json
import asyncio
import aiohttp
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from pdf2image import convert_from_path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

API_URL = "https://api.nutrient.io/extraction/extract"

# The SC-100's key fields (plaintiff, defendant, claim, narrative) are on page 2.
# Render page 2 so hover highlights are visible on the displayed image.
RENDERED_PAGE_NUMBER = 2   # 1-indexed for pdf2image
RENDERED_PAGE_INDEX = 1    # 0-indexed for API pageIndex comparison


async def process_document(doc_config, api_key):
    pdf_path = (Path(__file__).parent / doc_config["file"]).resolve()
    print(f"Uploading and extracting: {pdf_path}")

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
        "schema": doc_config["schema"],
        "citationsEnabled": True,
    }
    data.add_field("instructions", json.dumps(instructions), content_type="application/json")

    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, headers=headers, data=data) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"API Error ({response.status}): {text}")
            result_json = await response.json()

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    pages = convert_from_path(
        pdf_path,
        first_page=RENDERED_PAGE_NUMBER,
        last_page=RENDERED_PAGE_NUMBER,
    )
    img_filename = f"{doc_config['id']}_page_{RENDERED_PAGE_INDEX}.png"
    pages[0].save(output_dir / img_filename, "PNG")

    page_info = result_json["output"]["pages"][RENDERED_PAGE_INDEX]
    page_width = page_info["width"]
    page_height = page_info["height"]

    return result_json, img_filename, page_width, page_height


def build_cards(data_node, meta_node, path=""):
    cards = []

    if isinstance(data_node, dict):
        for k, v in data_node.items():
            child_meta = meta_node.get(k, {}) if isinstance(meta_node, dict) else {}
            child_path = f"{path}.{k}" if path else k
            cards.extend(build_cards(v, child_meta, child_path))

    elif isinstance(data_node, list):
        meta_list = meta_node if isinstance(meta_node, list) else []
        for i, item in enumerate(data_node):
            child_meta = meta_list[i] if i < len(meta_list) else {}
            cards.extend(build_cards(item, child_meta, f"{path}[{i}]"))

    else:
        if not isinstance(meta_node, dict):
            return cards
        bbox = meta_node.get("bbox")
        confidence = meta_node.get("confidence", 1.0)
        page_index = meta_node.get("pageIndex", 0)

        if bbox:
            display = "—" if data_node is None else str(data_node)
            cards.append({
                "path": path,
                "value": display,
                "confidence": int(confidence * 100),
                "x": bbox["x"],
                "y": bbox["y"],
                "width": bbox["width"],
                "height": bbox["height"],
                "page_index": page_index,
            })

    return cards


def render_html(cards, img_filename, page_width, page_height, doc_config):
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("template.html")

    html_output = template.render(
        doc_name=doc_config["name"],
        image_src=img_filename,
        pdf_width=page_width,
        pdf_height=page_height,
        rendered_page_index=RENDERED_PAGE_INDEX,
        cards=cards,
    )

    output_dir = Path(__file__).parent / "output"
    with open(output_dir / "index.html", "w") as f:
        f.write(html_output)

    with open(output_dir / "metadata.json", "w") as f:
        json.dump(cards, f, indent=2)

    print(f"Generated {len(cards)} grounded field highlights.")
    print("Open output/index.html in a browser to view the demo.")


async def main():
    api_key = os.getenv("NUTRIENT_API_KEY")
    if not api_key:
        raise SystemExit("Error: NUTRIENT_API_KEY is not set. Copy .env.example to .env and add your key.")

    docs_path = Path(__file__).parent / "docs.json"
    with open(docs_path) as f:
        configs = json.load(f)

    config = configs[0]
    pdf_path = (Path(__file__).parent / config["file"]).resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found at {pdf_path}. Add the file and retry.")

    result_data, img_filename, page_width, page_height = await process_document(config, api_key)

    extracted = result_data.get("output", {}).get("data", {})
    metadata = result_data.get("output", {}).get("metadata", {})
    cards = build_cards(extracted, metadata)

    render_html(cards, img_filename, page_width, page_height, config)


if __name__ == "__main__":
    asyncio.run(main())

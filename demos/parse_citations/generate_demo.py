"""
Parse Citations Demo
Uses the Nutrient Data Extraction API to extract document sections and generates
a self-contained HTML file showing each extracted section pinned to its source
location on the document page via bounding box citations.
"""

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

PDF_PATH = Path(__file__).parent / "data" / "CMS_1500.pdf"

SCHEMA = {
    "type": "object",
    "properties": {
        "patient_name": {
            "type": "string",
            "description": "Full name of the patient from Box 2."
        },
        "patient_address": {
            "type": "string",
            "description": "Patient's street address from Box 5."
        },
        "patient_city_state_zip": {
            "type": "string",
            "description": "Patient's city, state, and zip code."
        },
        "insured_name": {
            "type": "string",
            "description": "Full name of the insured person from Box 4."
        },
        "insured_id_number": {
            "type": "string",
            "description": "The insured's ID number from Box 1a."
        },
        "insurance_plan_name": {
            "type": "string",
            "description": "Insurance plan or program name from Box 11c."
        },
        "diagnosis_code_a": {
            "type": "string",
            "description": "First diagnosis ICD code from Box 21A."
        },
        "diagnosis_code_b": {
            "type": "string",
            "description": "Second diagnosis ICD code from Box 21B."
        },
        "prior_authorization_number": {
            "type": "string",
            "description": "Prior authorization number from Box 23."
        },
        "total_charge": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "iso_4217_currency_code": {"type": "string"}
            },
            "required": ["amount", "iso_4217_currency_code"],
            "description": "Total charges from Box 28."
        },
        "federal_tax_id": {
            "type": "string",
            "description": "Federal tax ID number from Box 25."
        },
        "patient_account_number": {
            "type": "string",
            "description": "Patient account number from Box 26."
        },
        "billing_provider_name": {
            "type": "string",
            "description": "Name of the billing provider or facility from Box 33."
        },
        "billing_provider_address": {
            "type": "string",
            "description": "Address of the billing provider from Box 33."
        },
        "referring_provider_name": {
            "type": "string",
            "description": "Name of the referring provider from Box 17."
        },
        "referring_provider_npi": {
            "type": "string",
            "description": "NPI of the referring provider from Box 17b."
        },
    },
    "required": ["patient_name", "insured_id_number", "total_charge"]
}


async def extract(pdf_path: Path, api_key: str) -> dict:
    print(f"Uploading and extracting: {pdf_path}")

    headers = {"Authorization": f"Bearer {api_key}"}
    data = aiohttp.FormData()
    data.add_field(
        "file",
        open(pdf_path, "rb"),
        filename=pdf_path.name,
        content_type="application/pdf",
    )
    instructions = {"mode": "agentic", "schema": SCHEMA}
    data.add_field("instructions", json.dumps(instructions), content_type="application/json")

    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, headers=headers, data=data) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"API Error ({response.status}): {text}")
            return await response.json()


def build_blocks(data_node, meta_node, path=""):
    """
    Recursively walk data and metadata simultaneously to collect leaf values with bboxes.
    """
    blocks = []

    if isinstance(data_node, dict):
        for k, v in data_node.items():
            child_meta = meta_node.get(k, {}) if isinstance(meta_node, dict) else {}
            child_path = f"{path}.{k}" if path else k
            blocks.extend(build_blocks(v, child_meta, child_path))

    elif isinstance(data_node, list):
        meta_list = meta_node if isinstance(meta_node, list) else []
        for i, item in enumerate(data_node):
            child_meta = meta_list[i] if i < len(meta_list) else {}
            blocks.extend(build_blocks(item, child_meta, f"{path}[{i}]"))

    else:
        if not isinstance(meta_node, dict):
            return blocks
        bbox = meta_node.get("bbox")
        confidence = meta_node.get("confidence", 1.0)
        if bbox and data_node is not None:
            if isinstance(data_node, (int, float)) and "amount" in path:
                display = f"{float(data_node):.2f}"
            else:
                display = str(data_node)
            blocks.append({
                "label": path,
                "text": display,
                "confidence": int(confidence * 100),
                "x": bbox["x"],
                "y": bbox["y"],
                "width": bbox["width"],
                "height": bbox["height"],
            })

    return blocks


def render_html(blocks, img_filename, page_width, page_height, doc_name):
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("template.html")

    html_output = template.render(
        doc_name=doc_name,
        image_src=img_filename,
        pdf_width=page_width,
        pdf_height=page_height,
        blocks=blocks,
    )

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    with open(output_dir / "index.html", "w") as f:
        f.write(html_output)
    print(f"Generated {len(blocks)} cited sections.")
    print("Open output/index.html in a browser to view the demo.")


async def main():
    api_key = os.getenv("NUTRIENT_API_KEY")
    if not api_key:
        raise SystemExit("NUTRIENT_API_KEY is not set. Copy .env.example to .env and add your key.")
    if not PDF_PATH.exists():
        raise SystemExit(f"PDF not found at {PDF_PATH}.")

    result = await extract(PDF_PATH, api_key)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    pages = convert_from_path(PDF_PATH, first_page=1, last_page=1)
    img_filename = "page_0.png"
    pages[0].save(output_dir / img_filename, "PNG")

    page_info = result["output"]["pages"][0]
    page_width = page_info["width"]
    page_height = page_info["height"]

    data = result.get("output", {}).get("data", {})
    metadata = result.get("output", {}).get("metadata", {})
    blocks = build_blocks(data, metadata)

    render_html(blocks, img_filename, page_width, page_height, PDF_PATH.stem)


if __name__ == "__main__":
    asyncio.run(main())

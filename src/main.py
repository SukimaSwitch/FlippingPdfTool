import argparse
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import boto3
import cv2
import fitz
import numpy as np
import requests


DEFAULT_OUTPUT_DIR = Path("extracted_images")
DEFAULT_INFO_DIR = Path("figure_info")
DEFAULT_RENDER_DPI = 220
DEFAULT_DOMAIN = "www.currentcatalog.com"
REGIONAL_OCR_DPI = 360
TEXT_BLOCK_TYPES = {"LAYOUT_TEXT", "LAYOUT_TITLE", "LAYOUT_LIST"}
SKU_PATTERNS = (
    re.compile(r"\b([A-Z0-9-]{4,20})\b\s+\$\s?\d+(?:\.\d{2})?", re.IGNORECASE),
    re.compile(r"(?:sku|item|style|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{3,19})", re.IGNORECASE),
    re.compile(r"\b([A-Z]{1,4}-?\d{3,10}|\d{5,10}|[A-Z0-9]{5,14})\b"),
)
PRICE_PATTERN = re.compile(r"\$\s?\d+(?:\.\d{2})?")


@dataclass
class PageArtifact:
    page_index: int
    image_path: Path
    width: int
    height: int


@dataclass
class CandidateBlock:
    block_id: str
    block_type: str
    text: str
    bbox: Dict[str, float]
    page_number: int


@dataclass
class FigureMatch:
    page_index: int
    figure_bbox: Dict[str, float]
    description_text: str
    description_bbox: Optional[Dict[str, float]]
    sku: str
    url: str
    score: float
    sku_source: str = "ocr"
    native_text: Optional[str] = None
    regional_ocr_text: Optional[str] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Identify product figures in a PDF and add product links based on nearby SKU text."
    )
    parser.add_argument("pdf", nargs="?", help="PDF URL or local path")
    parser.add_argument(
        "--domain",
        default=DEFAULT_DOMAIN,
        help="Destination domain for product links, for example www.currentcatalog.com",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for modified PDFs and rendered page images",
    )
    parser.add_argument(
        "--figure-info-dir",
        default=str(DEFAULT_INFO_DIR),
        help="Directory for Textract JSON and match metadata",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_RENDER_DPI,
        help="Render DPI for PDF to JPG conversion",
    )
    parser.add_argument(
        "--url-template",
        default=None,
        help="Product URL template. Use {sku} as the placeholder.",
    )
    parser.add_argument(
        "--aws-region",
        default=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        help="AWS region for Textract",
    )
    parser.add_argument(
        "--textract-adapter-id",
        default=os.getenv("TEXTRACT_ADAPTER_ID"),
        help="Optional Textract adapter ID",
    )
    parser.add_argument(
        "--textract-adapter-version",
        default=os.getenv("TEXTRACT_ADAPTER_VERSION"),
        help="Optional Textract adapter version",
    )
    parser.add_argument(
        "--debug-overlays",
        action="store_true",
        help="Write page images annotated with figure and description matches",
    )
    args = parser.parse_args()
    if not args.pdf:
        args.pdf = input("Enter the PDF URL or file path: ").strip()
    if args.url_template and "{sku}" not in args.url_template:
        parser.error("--url-template must include the {sku} placeholder")
    return args


def build_url_template(domain: str, url_template: Optional[str]) -> str:
    if url_template:
        return url_template

    cleaned = domain.strip()
    if not cleaned:
        raise ValueError("A non-empty domain or --url-template is required")
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    host = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    path = path.rstrip("/")
    if not host:
        raise ValueError(f"Invalid domain: {domain}")
    base_url = f"{parsed.scheme or 'https'}://{host}"
    if path:
        return f"{base_url}{path}/sku/{{sku}}"
    return f"{base_url}/sku/{{sku}}"


def extract_sku_details(text: str) -> Tuple[Optional[str], Optional[int]]:
    normalized = text.replace("\n", " ")
    for pattern_index, pattern in enumerate(SKU_PATTERNS):
        for match in pattern.finditer(normalized):
            candidate = match.group(1).strip(" .,:;)")
            if not is_valid_sku(candidate):
                continue
            if pattern_index != 0 and candidate.lower() in {"free", "each", "only"}:
                continue
            return candidate, pattern_index
    return None, None


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch_pdf(pdf_input: str, run_dir: Path) -> Path:
    if pdf_input.startswith(("http://", "https://")):
        response = requests.get(pdf_input, timeout=60)
        response.raise_for_status()
        pdf_path = run_dir / "input.pdf"
        pdf_path.write_bytes(response.content)
        return pdf_path

    pdf_path = Path(os.path.expanduser(pdf_input)).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    return pdf_path


def render_pages(doc: fitz.Document, run_dir: Path, dpi: int) -> List[PageArtifact]:
    page_dir = ensure_directory(run_dir / "pages")
    artifacts: List[PageArtifact] = []
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)

    for page_index in range(len(doc)):
        page = doc[page_index]
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image_path = page_dir / f"page_{page_index + 1:03d}.jpg"
        pix.save(image_path)
        artifacts.append(
            PageArtifact(
                page_index=page_index,
                image_path=image_path,
                width=pix.width,
                height=pix.height,
            )
        )
    return artifacts


def analyze_page_with_textract(
    client: Any,
    image_path: Path,
    adapter_id: Optional[str],
    adapter_version: Optional[str],
) -> Dict[str, Any]:
    request_args: Dict[str, Any] = {
        "Document": {"Bytes": image_path.read_bytes()},
        "FeatureTypes": ["LAYOUT"],
    }
    if adapter_id:
        adapter: Dict[str, str] = {"AdapterId": adapter_id}
        if adapter_version:
            adapter["Version"] = adapter_version
        request_args["AdaptersConfig"] = {"Adapters": [adapter]}
    return client.analyze_document(**request_args)


def block_map(blocks: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {block["Id"]: block for block in blocks if "Id" in block}


def get_child_ids(block: Dict[str, Any], relationship_type: str = "CHILD") -> List[str]:
    child_ids: List[str] = []
    for relationship in block.get("Relationships", []):
        if relationship.get("Type") == relationship_type:
            child_ids.extend(relationship.get("Ids", []))
    return child_ids


def get_block_text(block: Dict[str, Any], blocks_by_id: Dict[str, Dict[str, Any]]) -> str:
    text = block.get("Text")
    if text:
        return re.sub(r"\s+", " ", text).strip()

    child_text: List[str] = []
    for child_id in get_child_ids(block):
        child = blocks_by_id.get(child_id)
        if not child:
            continue
        if child.get("BlockType") in {"WORD", "LINE"} and child.get("Text"):
            child_text.append(child["Text"])
        else:
            nested_text = get_block_text(child, blocks_by_id)
            if nested_text:
                child_text.append(nested_text)
    return re.sub(r"\s+", " ", " ".join(child_text)).strip()


def bbox_center(bbox: Dict[str, float]) -> Tuple[float, float]:
    return bbox["Left"] + bbox["Width"] / 2.0, bbox["Top"] + bbox["Height"] / 2.0


def horizontal_overlap(left_a: float, right_a: float, left_b: float, right_b: float) -> float:
    overlap = max(0.0, min(right_a, right_b) - max(left_a, left_b))
    base = min(right_a - left_a, right_b - left_b)
    if base <= 0:
        return 0.0
    return overlap / base


def vertical_overlap(top_a: float, bottom_a: float, top_b: float, bottom_b: float) -> float:
    overlap = max(0.0, min(bottom_a, bottom_b) - max(top_a, top_b))
    base = min(bottom_a - top_a, bottom_b - top_b)
    if base <= 0:
        return 0.0
    return overlap / base


def extract_sku(text: str) -> Optional[str]:
    sku, _ = extract_sku_details(text)
    return sku


def is_valid_sku(candidate: str) -> bool:
    if len(candidate) < 4 or len(candidate) > 20:
        return False
    if PRICE_PATTERN.fullmatch(candidate):
        return False
    if "." in candidate:
        return False
    if any(char.isdigit() for char in candidate):
        return True
    return candidate.isalpha() and candidate.upper() == candidate and len(candidate) >= 6


def build_text_candidates(
    response: Dict[str, Any],
    page_number: int,
) -> Tuple[List[CandidateBlock], List[CandidateBlock]]:
    blocks = response.get("Blocks", [])
    blocks_by_id = block_map(blocks)
    figure_candidates: List[CandidateBlock] = []
    text_candidates: List[CandidateBlock] = []

    for block in blocks:
        if block.get("Page", 1) != page_number:
            continue
        bbox = block.get("Geometry", {}).get("BoundingBox")
        if not bbox:
            continue

        block_type = block.get("BlockType")
        if block_type == "LAYOUT_FIGURE":
            figure_candidates.append(
                CandidateBlock(
                    block_id=block["Id"],
                    block_type=block_type,
                    text=get_block_text(block, blocks_by_id),
                    bbox=bbox,
                    page_number=page_number,
                )
            )
        elif block_type in TEXT_BLOCK_TYPES:
            text = get_block_text(block, blocks_by_id)
            if text:
                text_candidates.append(
                    CandidateBlock(
                        block_id=block["Id"],
                        block_type=block_type,
                        text=text,
                        bbox=bbox,
                        page_number=page_number,
                    )
                )

    if figure_candidates:
        return figure_candidates, text_candidates

    fallback_figures = detect_figures_with_opencv(response.get("_rendered_image_path"))
    for index, bbox in enumerate(fallback_figures):
        figure_candidates.append(
            CandidateBlock(
                block_id=f"opencv-figure-{page_number}-{index}",
                block_type="LAYOUT_FIGURE",
                text="",
                bbox=bbox,
                page_number=page_number,
            )
        )
    return figure_candidates, text_candidates


def detect_figures_with_opencv(image_path: Optional[str]) -> List[Dict[str, float]]:
    if not image_path:
        return []

    image = cv2.imread(image_path)
    if image is None:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresholded = cv2.threshold(blurred, 245, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    closed = cv2.morphologyEx(thresholded, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_height, image_width = gray.shape
    min_area = image_width * image_height * 0.01
    detected: List[Dict[str, float]] = []

    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = width * height
        if area < min_area or width < 80 or height < 80:
            continue
        aspect_ratio = width / float(height)
        if aspect_ratio < 0.4 or aspect_ratio > 5.0:
            continue
        if y < image_height * 0.05 or y + height > image_height * 0.95:
            continue
        detected.append(
            {
                "Left": x / image_width,
                "Top": y / image_height,
                "Width": width / image_width,
                "Height": height / image_height,
            }
        )
    return sorted(detected, key=lambda bbox: (bbox["Top"], bbox["Left"]))


def score_description(figure_bbox: Dict[str, float], text_candidate: CandidateBlock) -> float:
    fig_left = figure_bbox["Left"]
    fig_right = fig_left + figure_bbox["Width"]
    fig_top = figure_bbox["Top"]
    fig_bottom = fig_top + figure_bbox["Height"]
    txt_left = text_candidate.bbox["Left"]
    txt_right = txt_left + text_candidate.bbox["Width"]
    txt_top = text_candidate.bbox["Top"]
    txt_bottom = txt_top + text_candidate.bbox["Height"]
    h_overlap = horizontal_overlap(fig_left, fig_right, txt_left, txt_right)
    v_overlap = vertical_overlap(fig_top, fig_bottom, txt_top, txt_bottom)
    downward_distance = txt_top - fig_bottom
    side_gap_left = fig_left - txt_right
    side_gap_right = txt_left - fig_right
    is_below = downward_distance >= -0.015 and downward_distance <= 0.26
    is_left_side = side_gap_left >= -0.02 and side_gap_left <= 0.16 and v_overlap >= 0.2
    is_right_side = side_gap_right >= -0.02 and side_gap_right <= 0.16 and v_overlap >= 0.2

    if not (is_below or is_left_side or is_right_side):
        return -10.0

    upward_distance = max(0.0, fig_top - txt_bottom)
    center_dx = abs(bbox_center(figure_bbox)[0] - bbox_center(text_candidate.bbox)[0])
    price_bonus = 0.25 if PRICE_PATTERN.search(text_candidate.text) else 0.0
    sku_bonus = 0.6 if extract_sku(text_candidate.text) else 0.0
    overlap_bonus = 1.5 * h_overlap + 0.4 * v_overlap
    below_bonus = 1.2 if is_below else 0.0
    side_bonus = 0.9 if (is_left_side or is_right_side) else 0.0
    distance_penalty = max(0.0, downward_distance) * 8.0
    above_penalty = upward_distance * 10.0
    lateral_penalty = center_dx * 1.2

    return overlap_bonus + below_bonus + side_bonus + price_bonus + sku_bonus - above_penalty - lateral_penalty - distance_penalty


def match_figures_to_descriptions(
    page_index: int,
    figures: Sequence[CandidateBlock],
    text_candidates: Sequence[CandidateBlock],
    url_template: str,
) -> List[FigureMatch]:
    candidate_pairs: List[Tuple[float, CandidateBlock, CandidateBlock, str]] = []
    for figure in figures:
        for text_candidate in text_candidates:
            score = score_description(figure.bbox, text_candidate)
            if score < 0.35:
                continue
            sku = extract_sku(text_candidate.text)
            if not sku:
                continue
            candidate_pairs.append((score, figure, text_candidate, sku))

    matches: List[FigureMatch] = []
    used_figures = set()
    used_text_blocks = set()

    for score, figure, text_candidate, sku in sorted(candidate_pairs, key=lambda item: item[0], reverse=True):
        if figure.block_id in used_figures or text_candidate.block_id in used_text_blocks:
            continue
        matches.append(
            FigureMatch(
                page_index=page_index,
                figure_bbox=figure.bbox,
                description_text=text_candidate.text,
                description_bbox=text_candidate.bbox,
                sku=sku,
                url=url_template.format(sku=sku),
                score=score,
            )
        )
        used_figures.add(figure.block_id)
        used_text_blocks.add(text_candidate.block_id)

    return sorted(matches, key=lambda match: (match.figure_bbox["Top"], match.figure_bbox["Left"]))


def bbox_to_page_rect(page: fitz.Page, bbox: Dict[str, float]) -> fitz.Rect:
    return fitz.Rect(
        bbox["Left"] * page.rect.width,
        bbox["Top"] * page.rect.height,
        (bbox["Left"] + bbox["Width"]) * page.rect.width,
        (bbox["Top"] + bbox["Height"]) * page.rect.height,
    ) & page.rect


def expand_rect(rect: fitz.Rect, page_rect: fitz.Rect, x_padding: float, y_padding: float) -> fitz.Rect:
    expanded = fitz.Rect(
        rect.x0 - x_padding,
        rect.y0 - y_padding,
        rect.x1 + x_padding,
        rect.y1 + y_padding,
    )
    return expanded & page_rect


def extract_pdf_text(page: fitz.Page, rect: fitz.Rect) -> str:
    text = page.get_text("text", clip=rect)
    normalized = re.sub(r"\s+", " ", text).strip()
    if normalized:
        return normalized

    words = page.get_text("words", clip=rect)
    if not words:
        return ""
    ordered_words = sorted(words, key=lambda item: (round(item[3], 1), item[0]))
    return re.sub(r"\s+", " ", " ".join(word[4] for word in ordered_words)).strip()


def get_search_rects(
    page: fitz.Page,
    figure_bbox: Dict[str, float],
    description_bbox: Optional[Dict[str, float]],
) -> List[fitz.Rect]:
    page_rect = page.rect
    figure_rect = bbox_to_page_rect(page, figure_bbox)
    rects: List[fitz.Rect] = []

    if description_bbox:
        description_rect = bbox_to_page_rect(page, description_bbox)
        rects.append(expand_rect(description_rect, page_rect, page_rect.width * 0.015, page_rect.height * 0.01))
        rects.append(expand_rect((figure_rect | description_rect), page_rect, page_rect.width * 0.02, page_rect.height * 0.012))

    below_rect = fitz.Rect(
        figure_rect.x0 - page_rect.width * 0.02,
        figure_rect.y1 - page_rect.height * 0.01,
        figure_rect.x1 + page_rect.width * 0.02,
        figure_rect.y1 + page_rect.height * 0.22,
    ) & page_rect
    rects.append(below_rect)

    left_side_rect = fitz.Rect(
        figure_rect.x0 - page_rect.width * 0.18,
        figure_rect.y0,
        figure_rect.x0 + page_rect.width * 0.02,
        figure_rect.y1 + page_rect.height * 0.08,
    ) & page_rect
    right_side_rect = fitz.Rect(
        figure_rect.x1 - page_rect.width * 0.02,
        figure_rect.y0,
        figure_rect.x1 + page_rect.width * 0.18,
        figure_rect.y1 + page_rect.height * 0.08,
    ) & page_rect
    rects.extend([left_side_rect, right_side_rect])

    unique_rects: List[fitz.Rect] = []
    seen = set()
    for rect in rects:
        signature = tuple(round(value, 2) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
        if rect.get_area() <= 0 or signature in seen:
            continue
        unique_rects.append(rect)
        seen.add(signature)
    return unique_rects


def get_pdf_text_candidates(
    page: fitz.Page,
    figure_bbox: Dict[str, float],
    description_bbox: Optional[Dict[str, float]],
) -> List[str]:
    rects = get_search_rects(page, figure_bbox, description_bbox)

    texts: List[str] = []
    seen = set()
    for rect in rects:
        text = extract_pdf_text(page, rect)
        if text and text not in seen:
            texts.append(text)
            seen.add(text)
    return texts


def render_clip_to_image(page: fitz.Page, rect: fitz.Rect, dpi: int) -> Optional[np.ndarray]:
    if rect.get_area() <= 0:
        return None
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False)
    if pix.width == 0 or pix.height == 0:
        return None
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
    else:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image


def encode_png(image: np.ndarray) -> Optional[bytes]:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        return None
    return encoded.tobytes()


def build_ocr_variants(image: np.ndarray) -> List[Tuple[str, bytes]]:
    variants: List[Tuple[str, bytes]] = []

    original_bytes = encode_png(image)
    if original_bytes:
        variants.append(("original", original_bytes))

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
    thresholded = cv2.adaptiveThreshold(
        scaled,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        12,
    )
    threshold_bytes = encode_png(thresholded)
    if threshold_bytes:
        variants.append(("adaptive-threshold", threshold_bytes))

    sharpened = cv2.GaussianBlur(scaled, (0, 0), 2.2)
    sharpened = cv2.addWeighted(scaled, 1.6, sharpened, -0.6, 0)
    _, otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_bytes = encode_png(otsu)
    if otsu_bytes:
        variants.append(("otsu", otsu_bytes))

    return variants


def extract_textract_lines(client: Any, image_bytes: bytes) -> str:
    response = client.detect_document_text(Document={"Bytes": image_bytes})
    lines = [block["Text"] for block in response.get("Blocks", []) if block.get("BlockType") == "LINE" and block.get("Text")]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def score_text_candidate(text: str) -> float:
    if not text:
        return -1.0
    sku, pattern_index = extract_sku_details(text)
    if not sku:
        return -0.5 + min(len(text), 200) / 1000.0
    score = 2.0 - (pattern_index or 0) * 0.3
    score += 0.25 if PRICE_PATTERN.search(text) else 0.0
    score += min(len(text), 240) / 240.0
    return score


def get_regional_ocr_candidates(
    client: Any,
    page: fitz.Page,
    figure_bbox: Dict[str, float],
    description_bbox: Optional[Dict[str, float]],
) -> List[str]:
    regional_texts: List[str] = []
    seen = set()
    rects = get_search_rects(page, figure_bbox, description_bbox)[:2]

    for rect in rects:
        image = render_clip_to_image(page, rect, REGIONAL_OCR_DPI)
        if image is None:
            continue
        for _, variant_bytes in build_ocr_variants(image):
            text = extract_textract_lines(client, variant_bytes)
            if text and text not in seen:
                regional_texts.append(text)
                seen.add(text)
    return sorted(regional_texts, key=score_text_candidate, reverse=True)


def resolve_sku_text(
    ocr_text: str,
    pdf_text_candidates: Sequence[str],
    regional_ocr_candidates: Sequence[str],
) -> Tuple[Optional[str], str, str]:
    for pdf_text in pdf_text_candidates:
        sku = extract_sku(pdf_text)
        if sku:
            return sku, "pdf", pdf_text

    for regional_text in regional_ocr_candidates:
        sku = extract_sku(regional_text)
        if sku:
            return sku, "regional-ocr", regional_text

    sku = extract_sku(ocr_text)
    if sku:
        return sku, "ocr", ocr_text
    return None, "unresolved", ocr_text


def enrich_matches_with_pdf_text(
    client: Any,
    page: fitz.Page,
    matches: Sequence[FigureMatch],
    url_template: str,
) -> List[FigureMatch]:
    enriched_matches: List[FigureMatch] = []
    for match in matches:
        pdf_text_candidates = get_pdf_text_candidates(page, match.figure_bbox, match.description_bbox)
        regional_ocr_candidates = [] if pdf_text_candidates else get_regional_ocr_candidates(client, page, match.figure_bbox, match.description_bbox)
        sku, source, selected_text = resolve_sku_text(match.description_text, pdf_text_candidates, regional_ocr_candidates)
        if sku:
            match.sku = sku
            match.url = url_template.format(sku=sku)
            match.sku_source = source
            if source == "pdf":
                match.native_text = selected_text
                match.description_text = selected_text
            elif source == "regional-ocr":
                match.regional_ocr_text = selected_text
                match.description_text = selected_text
        enriched_matches.append(match)
    return enriched_matches


def add_links_to_pdf(doc: fitz.Document, matches: Sequence[FigureMatch]) -> int:
    link_count = 0
    for match in matches:
        page = doc[match.page_index]
        rects = [bbox_to_page_rect(page, match.figure_bbox)]
        if match.description_bbox:
            rects.append(bbox_to_page_rect(page, match.description_bbox))

        seen = set()
        for rect in rects:
            signature = tuple(round(value, 2) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
            if rect.get_area() <= 0 or signature in seen:
                continue
            page.insert_link({"from": rect, "kind": fitz.LINK_URI, "uri": match.url})
            link_count += 1
            seen.add(signature)
    return link_count


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_debug_overlay(page_artifact: PageArtifact, page_matches: Sequence[FigureMatch], overlay_path: Path) -> None:
    image = cv2.imread(str(page_artifact.image_path))
    if image is None:
        return

    for match in page_matches:
        fig = match.figure_bbox
        x1 = int(fig["Left"] * page_artifact.width)
        y1 = int(fig["Top"] * page_artifact.height)
        x2 = int((fig["Left"] + fig["Width"]) * page_artifact.width)
        y2 = int((fig["Top"] + fig["Height"]) * page_artifact.height)
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 160, 255), 3)
        cv2.putText(
            image,
            match.sku,
            (x1, max(25, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 160, 255),
            2,
            cv2.LINE_AA,
        )

        if match.description_bbox:
            desc = match.description_bbox
            dx1 = int(desc["Left"] * page_artifact.width)
            dy1 = int(desc["Top"] * page_artifact.height)
            dx2 = int((desc["Left"] + desc["Width"]) * page_artifact.width)
            dy2 = int((desc["Top"] + desc["Height"]) * page_artifact.height)
            cv2.rectangle(image, (dx1, dy1), (dx2, dy2), (0, 220, 100), 2)

    cv2.imwrite(str(overlay_path), image)


def run_pipeline(args: argparse.Namespace) -> Dict[str, Any]:
    url_template = build_url_template(args.domain, args.url_template)
    output_dir = ensure_directory(Path(args.output_dir).resolve())
    figure_info_dir = ensure_directory(Path(args.figure_info_dir).resolve())
    run_id = uuid.uuid4().hex[:12]
    run_output_dir = ensure_directory(output_dir / run_id)
    run_info_dir = ensure_directory(figure_info_dir / run_id)

    pdf_path = fetch_pdf(args.pdf, run_output_dir)
    doc = fitz.open(pdf_path)
    page_artifacts = render_pages(doc, run_output_dir, args.dpi)
    textract_client = boto3.client("textract", region_name=args.aws_region)

    all_matches: List[FigureMatch] = []
    page_summaries: List[Dict[str, Any]] = []

    for page_artifact in page_artifacts:
        response = analyze_page_with_textract(
            textract_client,
            page_artifact.image_path,
            args.textract_adapter_id,
            args.textract_adapter_version,
        )
        response["_rendered_image_path"] = str(page_artifact.image_path)
        save_json(run_info_dir / f"page_{page_artifact.page_index + 1:03d}_textract.json", response)

        figures, text_candidates = build_text_candidates(response, page_artifact.page_index + 1)
        page_matches = match_figures_to_descriptions(
            page_index=page_artifact.page_index,
            figures=figures,
            text_candidates=text_candidates,
            url_template=url_template,
        )
        page_matches = enrich_matches_with_pdf_text(textract_client, doc[page_artifact.page_index], page_matches, url_template)
        all_matches.extend(page_matches)

        page_summary = {
            "page": page_artifact.page_index + 1,
            "rendered_image": str(page_artifact.image_path),
            "figure_count": len(figures),
            "description_candidate_count": len(text_candidates),
            "matches": [
                {
                    "sku": match.sku,
                    "url": match.url,
                    "score": round(match.score, 4),
                    "sku_source": match.sku_source,
                    "figure_bbox": match.figure_bbox,
                    "description_bbox": match.description_bbox,
                    "description_text": match.description_text,
                    "native_text": match.native_text,
                    "regional_ocr_text": match.regional_ocr_text,
                }
                for match in page_matches
            ],
        }
        page_summaries.append(page_summary)

        if args.debug_overlays:
            overlay_path = run_info_dir / f"page_{page_artifact.page_index + 1:03d}_overlay.jpg"
            write_debug_overlay(page_artifact, page_matches, overlay_path)

    link_count = add_links_to_pdf(doc, all_matches)
    modified_pdf_path = run_output_dir / f"linked_{pdf_path.stem}.pdf"
    doc.save(modified_pdf_path)
    doc.close()

    summary = {
        "input_pdf": str(pdf_path),
        "output_pdf": str(modified_pdf_path),
        "output_dir": str(run_output_dir),
        "figure_info_dir": str(run_info_dir),
        "url_template": url_template,
        "pages_processed": len(page_artifacts),
        "links_added": link_count,
        "matches": len(all_matches),
        "page_summaries": page_summaries,
    }
    save_json(run_info_dir / "run_summary.json", summary)
    return summary


def main() -> None:
    args = parse_args()
    try:
        summary = run_pipeline(args)
    except requests.RequestException as exc:
        print(f"Failed to download PDF: {exc}")
        raise SystemExit(1) from exc
    except FileNotFoundError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
    except fitz.FileDataError as exc:
        print(f"Failed to open PDF with PyMuPDF: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        raise SystemExit(1) from exc

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import unicodedata
from html import unescape
from dataclasses import dataclass
from pathlib import Path

from .data_loading import AreaItemBank


DAY2_PDF_BY_AREA_CODE = {
    "CN": {
        "1419": "ENEM_2024_P1_CAD_07_DIA_2_AZUL.pdf",
        "1420": "ENEM_2024_P1_CAD_05_DIA_2_AMARELO.pdf",
        "1421": "ENEM_2024_P1_CAD_08_DIA_2_VERDE.pdf",
        "1422": "ENEM_2024_P1_CAD_06_DIA_2_CINZA.pdf",
    },
    "MT": {
        "1407": "ENEM_2024_P1_CAD_07_DIA_2_AZUL.pdf",
        "1408": "ENEM_2024_P1_CAD_05_DIA_2_AMARELO.pdf",
        "1409": "ENEM_2024_P1_CAD_08_DIA_2_VERDE.pdf",
        "1410": "ENEM_2024_P1_CAD_06_DIA_2_CINZA.pdf",
    },
}


QUESTION_RE = re.compile(r"QUEST.{0,3}O\s+(\d{1,3})", re.IGNORECASE)
PAGE_TAG_RE = re.compile(
    r'<page\s+width="(?P<width>[\d.]+)"\s+height="(?P<height>[\d.]+)">(.*?)</page>',
    re.DOTALL,
)
WORD_TAG_RE = re.compile(
    r'<word\s+xMin="(?P<x_min>[\d.]+)"\s+yMin="(?P<y_min>[\d.]+)"\s+'
    r'xMax="(?P<x_max>[\d.]+)"\s+yMax="(?P<y_max>[\d.]+)">(.*?)</word>',
    re.DOTALL,
)


@dataclass(frozen=True)
class QuestionCropPlan:
    question_id: str
    question_number: int
    page_number: int
    column: str
    page_width: float
    page_height: float
    crop_box: tuple[float, float, float, float]
    source_pdf: str
    continues_to_next_page: bool


@dataclass(frozen=True)
class _PdfWord:
    text: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass(frozen=True)
class _PdfPage:
    page_number: int
    width: float
    height: float
    words: list[_PdfWord]


@dataclass(frozen=True)
class _QuestionHeading:
    question_number: int
    page_number: int
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    column: str


def find_booklet_pdf(dataset_root: str | Path, area: str, booklet_code: str) -> Path:
    root = Path(dataset_root)
    filename = DAY2_PDF_BY_AREA_CODE.get(area.upper(), {}).get(str(booklet_code))
    if not filename:
        raise ValueError(f"no PDF mapping for area={area} booklet_code={booklet_code}")
    pdf_path = root / "PROVAS E GABARITOS" / filename
    if not pdf_path.exists():
        raise FileNotFoundError(f"ENEM PDF not found: {pdf_path}")
    return pdf_path


def _run_command(args: list[str]) -> None:
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\nstdout={completed.stdout[:500]}\nstderr={completed.stderr[:500]}"
        )


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_marks.upper()


def _parse_bbox_pages(pdf_path: Path) -> list[_PdfPage]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "booklet_bbox.html"
        _run_command(["pdftotext", "-bbox", "-enc", "UTF-8", str(pdf_path), str(out_path)])
        bbox_text = out_path.read_text(encoding="utf-8", errors="replace")

    pages: list[_PdfPage] = []
    for page_idx, page_match in enumerate(PAGE_TAG_RE.finditer(bbox_text), start=1):
        words = [
            _PdfWord(
                text=unescape(word_match.group(5)).strip(),
                x_min=float(word_match.group("x_min")),
                y_min=float(word_match.group("y_min")),
                x_max=float(word_match.group("x_max")),
                y_max=float(word_match.group("y_max")),
            )
            for word_match in WORD_TAG_RE.finditer(page_match.group(3))
        ]
        pages.append(
            _PdfPage(
                page_number=page_idx,
                width=float(page_match.group("width")),
                height=float(page_match.group("height")),
                words=words,
            )
        )
    if not pages:
        raise ValueError(f"pdftotext -bbox found no pages in PDF: {pdf_path}")
    return pages


def _extract_question_headings(pages: list[_PdfPage]) -> dict[int, _QuestionHeading]:
    headings: dict[int, _QuestionHeading] = {}
    for page in pages:
        for idx, word in enumerate(page.words[:-1]):
            if _normalized(word.text) != "QUESTAO":
                continue
            number_text = re.sub(r"\D", "", page.words[idx + 1].text)
            if not number_text:
                continue
            question_number = int(number_text)
            number_word = page.words[idx + 1]
            column = "left" if word.x_min < page.width / 2 else "right"
            headings.setdefault(
                question_number,
                _QuestionHeading(
                    question_number=question_number,
                    page_number=page.page_number,
                    x_min=min(word.x_min, number_word.x_min),
                    y_min=min(word.y_min, number_word.y_min),
                    x_max=max(word.x_max, number_word.x_max),
                    y_max=max(word.y_max, number_word.y_max),
                    column=column,
                ),
            )
    if not headings:
        raise ValueError("pdftotext -bbox found no numbered QUESTÃO headings")
    return headings


def _column_bounds(page_width: float, column: str) -> tuple[float, float]:
    if column == "full_width":
        return 55.0, page_width - 50.0
    if column == "left":
        return 55.0, page_width / 2 - 8.0
    if column == "right":
        return page_width / 2 + 5.0, page_width - 50.0
    raise ValueError(f"unknown column: {column}")


def _layout_column_for_page(
    heading: _QuestionHeading,
    headings: dict[int, _QuestionHeading],
) -> str:
    has_right_column = any(
        row.page_number == heading.page_number and row.column == "right"
        for row in headings.values()
    )
    if not has_right_column:
        return "full_width"
    return heading.column


def _next_heading_for_layout(
    heading: _QuestionHeading,
    headings: dict[int, _QuestionHeading],
    layout_column: str,
) -> _QuestionHeading | None:
    candidates = [
        row
        for row in headings.values()
        if row.page_number == heading.page_number
        and (layout_column == "full_width" or row.column == heading.column)
        and row.y_min > heading.y_min
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: row.y_min)


def build_question_crop_plan(
    pdf_path: str | Path,
    item_bank: AreaItemBank,
) -> list[QuestionCropPlan]:
    source = Path(pdf_path)
    if not source.exists():
        raise FileNotFoundError(f"PDF not found: {source}")
    pages = _parse_bbox_pages(source)
    page_by_number = {page.page_number: page for page in pages}
    headings = _extract_question_headings(pages)

    rows: list[QuestionCropPlan] = []
    for item in sorted(item_bank.common_items.values(), key=lambda row: row.item_position):
        heading = headings.get(item.item_position)
        if heading is None:
            raise ValueError(
                f"could not locate bbox heading for QUESTÃO {item.item_position} "
                f"question_id={item.question_id}"
            )
        page = page_by_number[heading.page_number]
        layout_column = _layout_column_for_page(heading, headings)
        x0, x1 = _column_bounds(page.width, layout_column)
        next_heading = _next_heading_for_layout(heading, headings, layout_column)
        top = max(0.0, heading.y_min - 8.0)
        bottom = next_heading.y_min - 8.0 if next_heading else page.height - 35.0
        if bottom <= top:
            raise ValueError(
                f"invalid crop bounds for question_id={item.question_id}: top={top} bottom={bottom}"
            )
        rows.append(
            QuestionCropPlan(
                question_id=item.question_id,
                question_number=item.item_position,
                page_number=heading.page_number,
                column=layout_column,
                page_width=page.width,
                page_height=page.height,
                crop_box=(x0, top, x1, bottom),
                source_pdf=str(source.resolve()),
                continues_to_next_page=next_heading is None,
            )
        )
    return rows


def extract_question_page_map(pdf_path: str | Path) -> dict[int, int]:
    source = Path(pdf_path)
    if not source.exists():
        raise FileNotFoundError(f"PDF not found: {source}")
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "booklet.txt"
        _run_command(["pdftotext", "-enc", "UTF-8", str(source), str(out_path)])
        text = out_path.read_text(encoding="utf-8", errors="replace")
    pages = text.split("\f")
    page_by_question: dict[int, int] = {}
    for page_idx, page_text in enumerate(pages, start=1):
        for match in QUESTION_RE.finditer(page_text):
            question_number = int(match.group(1))
            page_by_question.setdefault(question_number, page_idx)
    if not page_by_question:
        raise ValueError(f"no QUESTÃO markers found in PDF text: {source}")
    return page_by_question


def render_pdf_pages(pdf_path: str | Path, output_dir: str | Path, dpi: int = 150) -> list[Path]:
    source = Path(pdf_path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    prefix = target_dir / source.stem
    existing = sorted(target_dir.glob(f"{source.stem}-*.png"), key=_rendered_page_sort_key)
    if existing:
        return existing
    _run_command(["pdftoppm", "-r", str(dpi), "-png", str(source), str(prefix)])
    rendered = sorted(target_dir.glob(f"{source.stem}-*.png"), key=_rendered_page_sort_key)
    if not rendered:
        raise RuntimeError(f"pdftoppm produced no PNG pages for {source}")
    return rendered


def _rendered_page_sort_key(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    if not match:
        raise ValueError(f"cannot infer rendered PDF page number from: {path}")
    return int(match.group(1))


def _crop_question_image(
    rendered_page: Path,
    crop_plan: QuestionCropPlan,
    output_path: Path,
) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to crop ENEM question images") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(rendered_page) as image:
        x0, y0, x1, y1 = crop_plan.crop_box
        scale_x = image.width / crop_plan.page_width
        scale_y = image.height / crop_plan.page_height
        pixel_box = (
            max(0, int(math.floor(x0 * scale_x))),
            max(0, int(math.floor(y0 * scale_y))),
            min(image.width, int(math.ceil(x1 * scale_x))),
            min(image.height, int(math.ceil(y1 * scale_y))),
        )
        if pixel_box[2] <= pixel_box[0] or pixel_box[3] <= pixel_box[1]:
            raise ValueError(
                f"invalid pixel crop for question_id={crop_plan.question_id}: "
                f"pdf_box={crop_plan.crop_box} pixel_box={pixel_box}"
            )
        image.crop(pixel_box).save(output_path)


def _load_reusable_question_manifest(
    manifest_path: Path,
    item_bank: AreaItemBank,
    dpi: int,
) -> list[dict[str, object]] | None:
    if not manifest_path.exists():
        return None
    rows: list[dict[str, object]] = []
    with manifest_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))

    expected_ids = set(item_bank.common_items)
    actual_ids = {str(row.get("question_id")) for row in rows}
    if actual_ids != expected_ids:
        raise ValueError(
            f"cached ENEM question image manifest item mismatch: "
            f"expected={len(expected_ids)} actual={len(actual_ids)} path={manifest_path}"
        )
    for row in rows:
        if row.get("crop_mode") != "bbox_column_crop_v1":
            raise ValueError(f"cached manifest has unsupported crop_mode in {manifest_path}")
        if int(row.get("dpi", -1)) != dpi:
            raise ValueError(f"cached manifest dpi mismatch in {manifest_path}: expected={dpi}")
        image_path = Path(str(row.get("image_path") or ""))
        if not image_path.exists():
            raise FileNotFoundError(f"cached ENEM question crop missing: {image_path}")
    return rows


def build_question_page_manifest(
    dataset_root: str | Path,
    item_bank: AreaItemBank,
    output_path: str | Path,
    page_image_dir: str | Path,
    dpi: int = 150,
) -> list[dict[str, object]]:
    target = Path(output_path)
    reusable_rows = _load_reusable_question_manifest(target, item_bank, dpi)
    if reusable_rows is not None:
        return reusable_rows

    pdf_path = find_booklet_pdf(dataset_root, item_bank.area, item_bank.base_booklet_code)
    rendered_pages = render_pdf_pages(pdf_path, page_image_dir, dpi=dpi)
    crop_plan_by_question = {
        plan.question_number: plan
        for plan in build_question_crop_plan(pdf_path, item_bank)
    }
    crop_dir = Path(page_image_dir).parent / "question_crops"
    rows: list[dict[str, object]] = []
    for item in sorted(item_bank.common_items.values(), key=lambda row: row.item_position):
        crop_plan = crop_plan_by_question.get(item.item_position)
        if crop_plan is None:
            raise ValueError(
                f"could not build crop plan for question {item.item_position} question_id={item.question_id}"
            )
        page_number = crop_plan.page_number
        if page_number < 1 or page_number > len(rendered_pages):
            raise ValueError(
                f"invalid page_number={page_number} for question_id={item.question_id}; rendered={len(rendered_pages)}"
            )
        crop_path = crop_dir / f"{item.question_id}_q{item.item_position}.png"
        _crop_question_image(
            rendered_page=rendered_pages[page_number - 1],
            crop_plan=crop_plan,
            output_path=crop_path,
        )
        rows.append(
            {
                "question_id": item.question_id,
                "area": item.area,
                "item_position": item.item_position,
                "image_path": str(crop_path.resolve()),
                "source_pdf": str(pdf_path.resolve()),
                "page_number": page_number,
                "column": crop_plan.column,
                "crop_mode": "bbox_column_crop_v1",
                "crop_box": list(crop_plan.crop_box),
                "page_width": crop_plan.page_width,
                "page_height": crop_plan.page_height,
                "dpi": dpi,
                "continues_to_next_page": crop_plan.continues_to_next_page,
                "image_context_note": (
                    f"Single-question crop from base booklet code {item.base_booklet_code}; "
                    f"target item is question {item.item_position}."
                ),
            }
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows

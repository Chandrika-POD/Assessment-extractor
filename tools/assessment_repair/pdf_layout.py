"""Recover questionnaire cells from saved PDFs without guessing clinical rules."""

import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter

import pymupdf as fitz


def tidy(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?!%)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    text = re.sub(r"\s*([’ʼ])\s*", r"\1", text)
    text = re.sub(r"(?<=\w)\s+'\s+(?=\w)", "'", text)
    return text


def cells_text(page, rect, all_words):
    rect = fitz.Rect(rect)
    words = [
        w
        for w in all_words
        if rect.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    ]
    # Original text line indices retain intentional line order inside each cell.
    words.sort(key=lambda w: (w[6], w[0]))
    result = tidy(" ".join(w[4] for w in words))
    if not hasattr(page, "_repair_chars"):
        page._repair_chars = [
            c
            for b in page.get_text(
                "rawdict", flags=fitz.TEXTFLAGS_RAWDICT | fitz.TEXT_INHIBIT_SPACES
            )["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
            for c in s["chars"]
        ]
    lines = {}
    for c in page._repair_chars:
        x, y = c["origin"]
        if rect.x0 <= x < rect.x1 and rect.y0 <= y < rect.y1:
            lines.setdefault(round(y, 1), []).append(c)
    alternate = tidy(
        " ".join(
            "".join(c["c"] for c in sorted(chars, key=lambda c: c["origin"][0]))
            for _, chars in sorted(lines.items())
        )
    )
    if Counter(re.sub(r"\s", "", alternate)) == Counter(re.sub(r"\s", "", result)):
        result = alternate
    return result


def standard_rows(page, words):
    drawings = page.get_drawings()
    rects = [d["rect"] for d in drawings]
    verticals = [r for r in rects if 0 < r.width < 2 and r.height >= 8 and r.x0 > 50]
    anchors = [
        w
        for w in words
        if re.fullmatch(r"\d{1,3}", w[4])
        and 1 <= int(w[4]) <= 300
        and 35 <= w[0] < 48
        and w[2] < 52
    ]
    rows = []
    for w in anchors:
        cy = (w[1] + w[3]) / 2
        spans = [r for r in verticals if r.y0 - 1 <= cy <= r.y1 + 1]
        if not spans:
            continue
        # The leftmost separator bounds the question cell. Yes/No controls can
        # have shorter internal dividers; using those clipped text and lost NO.
        question_edge = min(spans, key=lambda r: (r.x0, r.height))
        top, bottom = question_edge.y0, question_edge.y1
        borders = sorted(
            {round(r.x1, 2) for r in spans if r.y0 >= top - 2 and r.y1 <= bottom + 2}
        )
        if not borders:
            continue
        left = 51.9
        right = max(
            [
                r.x1
                for r in rects
                if abs(r.y0 - bottom) < 2 and r.height < 2 and r.x1 > left
            ]
            or [page.rect.width - 33.75]
        )
        boundaries = [left] + borders + [right]
        boundaries = sorted(set(boundaries))
        question = cells_text(page, (left, top, boundaries[1] - 0.1, bottom), words)
        if len(question) < 3:
            continue
        choices = []
        for x0, x1 in zip(boundaries[1:-1], boundaries[2:]):
            region = fitz.Rect(x0, top, x1, bottom)
            cwords = [
                x
                for x in words
                if region.contains(fitz.Point((x[0] + x[2]) / 2, (x[1] + x[3]) / 2))
            ]
            cwords.sort(key=lambda x: (x[6], x[0]))
            numeric = [x for x in cwords if re.fullmatch(r"-?\d+(?:\.\d+)?", x[4])]
            value = numeric[0] if numeric else None
            label = tidy(" ".join(x[4] for x in cwords if x is not value))
            if value:
                label_region = fitz.Rect(
                    x0, value[6] + max(2, (value[3] - value[1]) * 0.45), x1, bottom
                )
                corrected = cells_text(page, label_region, words)
                if re.sub(r"\s", "", corrected) == re.sub(r"\s", "", label):
                    label = corrected
            if label or value:
                choices.append(
                    {
                        "label": label or None,
                        "printed_value": float(value[4])
                        if value and "." in value[4]
                        else int(value[4])
                        if value
                        else None,
                        "score": None,
                        "source_bbox": [round(v, 2) for v in region],
                    }
                )
        rows.append(
            {
                "source_number": int(w[4]),
                "text": question,
                "options": choices,
                "source_bbox": [
                    33.75,
                    round(top, 2),
                    round(right, 2),
                    round(bottom, 2),
                ],
                "method": "pdf_table_geometry",
                "review_status": "source_layout_extracted",
            }
        )
    return sorted(rows, key=lambda r: r["source_bbox"][1])


def stacked_rows(page, words, existing):
    """Vertical answer blocks: the outer item number differs from rating values."""
    rects = [d["rect"] for d in page.get_drawings()]
    anchors = [
        w
        for w in words
        if re.fullmatch(r"\d{1,3}", w[4])
        and 1 <= int(w[4]) <= 300
        and 35 <= w[0] < 48
        and w[2] < 52
    ]
    rows = []
    for w in anchors:
        cy = (w[1] + w[3]) / 2
        if any(r["source_bbox"][1] <= cy <= r["source_bbox"][3] for r in existing):
            continue
        # A printed rule beneath the outer number closes this specific item.
        ends = [
            r.y0
            for r in rects
            if r.width > 10
            and r.height < 2
            and abs(r.x0 - 33.75) < 1
            and r.x1 <= 53
            and r.y0 > cy
        ]
        if not ends:
            continue
        bottom = min(ends)
        bodytop = 2 * cy - bottom - 3
        headers = [
            r
            for r in rects
            if r.width > 400
            and r.height > 12
            and abs(r.x0 - 33.75) < 1
            and abs(r.y1 - bodytop) < 8
        ]
        header = max(headers, key=lambda r: r.y1) if headers else None
        if header:
            header_text = cells_text(
                page, (40, header.y0, page.rect.width - 30, header.y1), words
            )
            if re.search(
                r"instructions|please read|general reference point|as you are pregnant|for this questionnaire",
                header_text,
                re.I,
            ):
                header = None
        option_numbers = [
            x
            for x in words
            if re.fullmatch(r"-?\d+(?:\.\d+)?", x[4])
            and 53 <= x[0] < 72
            and bodytop <= x[1] < bottom
        ]
        option_numbers.sort(key=lambda x: x[1])
        if len(option_numbers) < 2:
            continue
        top = header.y0 if header else bodytop
        title = cells_text(
            page,
            (45 if header else 52, top, page.rect.width - 30, option_numbers[0][1] - 4),
            words,
        )
        if not title:
            continue
        options = []
        for j, n in enumerate(option_numbers):
            y0 = max(bodytop, n[1] - 4)
            y1 = (
                (option_numbers[j + 1][1] - 4)
                if j + 1 < len(option_numbers)
                else bottom
            )
            label = cells_text(page, (72, y0, page.rect.width - 30, y1), words) or None
            options.append(
                {
                    "label": label,
                    "printed_value": float(n[4]) if "." in n[4] else int(n[4]),
                    "score": None,
                    "source_bbox": [
                        53,
                        round(y0, 2),
                        round(page.rect.width - 30, 2),
                        round(y1, 2),
                    ],
                }
            )
        rows.append(
            {
                "source_number": int(w[4]),
                "text": title,
                "options": options,
                "source_bbox": [
                    33.75,
                    round(top, 2),
                    round(page.rect.width - 30, 2),
                    round(bottom, 2),
                ],
                "method": "pdf_stacked_response_geometry",
                "review_status": "source_layout_extracted",
            }
        )
    return rows


def other_rows(page, words, existing):
    """Retain numbered free-response cells without guessing their response type."""
    rects = [d["rect"] for d in page.get_drawings()]
    rows = []
    for w in words:
        if not (
            re.fullmatch(r"\d{1,3}", w[4])
            and 1 <= int(w[4]) <= 300
            and 35 <= w[0] < 48
            and w[2] < 52
        ):
            continue
        cy = (w[1] + w[3]) / 2
        if any(r["source_bbox"][1] <= cy <= r["source_bbox"][3] for r in existing):
            continue
        ends = [
            r.y0
            for r in rects
            if r.width > 10
            and r.height < 2
            and abs(r.x0 - 33.75) < 1
            and r.x1 <= 53
            and cy < r.y0 < cy + 250
        ]
        if not ends:
            continue
        bottom = min(ends)
        top = 2 * cy - bottom - 3
        if any(
            min(bottom, r["source_bbox"][3]) - max(top, r["source_bbox"][1]) > 4
            for r in existing
        ):
            continue
        # A short underline on the right is an answer field, not question text.
        blanks = [
            r
            for r in rects
            if r.height < 2 and 15 < r.width < 150 and r.x0 > 350 and cy < r.y0 < bottom
        ]
        blank = min(blanks, key=lambda r: r.x0) if blanks else None
        # Text can wrap above a right-hand input line. Remove just the printed
        # unit next to that line, never crop the entire right side of the row.
        unit_words = [
            w
            for w in words
            if blank
            and w[0] > blank.x1
            and abs((w[1] + w[3]) / 2 - blank.y0) < 10
            and w[4].lower() in {"days", "nights", "times", "years", "weeks", "months"}
        ]
        question = cells_text(
            page,
            (52, top, page.rect.width - 30, bottom),
            [w for w in words if w not in unit_words],
        )
        unit = " ".join(w[4] for w in unit_words) or None
        if len(question) < 3:
            continue
        rows.append(
            {
                "source_number": int(w[4]),
                "text": question,
                "options": [],
                "printed_input_unit": unit or None,
                "source_bbox": [
                    33.75,
                    round(top, 2),
                    round(page.rect.width - 30, 2),
                    round(bottom, 2),
                ],
                "method": "pdf_untyped_row_geometry",
                "review_status": "response_type_needs_review",
            }
        )
    return rows


def extract_pdf(path):
    doc = fitz.open(path)
    xml = subprocess.check_output(
        ["pdftotext", "-bbox-layout", str(path), "-"], stderr=subprocess.DEVNULL
    )
    parsed = ET.fromstring(xml)
    all_words = []
    for xp in parsed.iter("{http://www.w3.org/1999/xhtml}page"):
        page_words = []
        for line_id, line in enumerate(xp.iter("{http://www.w3.org/1999/xhtml}line")):
            for w in line:
                page_words.append(
                    (
                        float(w.get("xMin")),
                        float(w.get("yMin")),
                        float(w.get("xMax")),
                        float(w.get("yMax")),
                        w.text or "",
                        line_id,
                        float(line.get("yMin")),
                    )
                )
        all_words.append(page_words)
    items = []
    pages = []
    for i, page in enumerate(doc):
        rows = standard_rows(page, all_words[i])
        rows += stacked_rows(page, all_words[i], rows)
        rows += other_rows(page, all_words[i], rows)
        rows.sort(key=lambda r: r["source_bbox"][1])
        for r in rows:
            r["page"] = i + 1
            label = cells_text(
                page,
                (33.75, r["source_bbox"][1], 51.75, r["source_bbox"][3]),
                all_words[i],
            )
            compact = re.sub(r"\s", "", label)
            r["source_label"] = (
                compact
                if re.fullmatch(r"\d+[a-z]?", compact, re.I)
                else str(r["source_number"])
            )
        items.extend(rows)
        pages.append(
            {
                "number": i + 1,
                "text": page.get_text(),
                "row_count": len(rows),
                "image_count": len(page.get_images()),
            }
        )
    instructions = None
    if items and items[0]["page"] == 1:
        p = doc[0]
        words = all_words[0]
        labels = [
            w
            for w in words
            if w[4].upper() in {"CLINICIAN", "RESPONDENT", "DATE", "ASSESSOR"}
            and w[1] < 150
        ]
        start = max([w[3] for w in labels] or [110]) + 3
        top = items[0]["source_bbox"][1]
        instructions = cells_text(p, (33, start, p.rect.width - 25, top), words)
        instructions = (
            re.sub(
                r"^Ins\s*t\s*ruct\s*io\s*ns\s*", "", instructions, flags=re.I
            ).strip()
            or None
        )
    return {"items": items, "instructions": instructions, "pages": pages}

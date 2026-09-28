"""Обработка .docx с сохранением форматирования.

Слова в docx могут быть разбиты на несколько runs («Ива» + «нов»). Поэтому:
собираем текст абзаца целиком, считаем замены по нему, а потом
перераспределяем результат по runs.

Как перераспределяем (решение для MVP, чтобы не ломать форматирование):
- если заменяемый токен целиком лежит внутри одного run — просто
  подменяем текст в этом run;
- если токен растянут на несколько runs (жирная первая половина и т.п.) —
  весь токен помещаем в ПЕРВЫЙ из затронутых runs (его форматирование
  считаем главным), остальные затронутые runs укорачиваем.
Форматирование вокруг замены (другие слова, пробелы) не трогается.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.document import Document as _DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .replacer import ReplaceResult, TextReplacer


def _iter_tables(tables) -> Table:
    for table in tables:
        yield table
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_tables(cell.tables)


def _existing_parts(section, kind: str):
    """Колонтитулы, реально существующие в документе.

    Доступ к section.first_page_header и т.п. в python-docx СОЗДАЁТ часть,
    если её нет — поэтому смотрим только объявленные в sectPr ссылки.
    kind: 'header' или 'footer'.
    """
    from docx.enum.section import WD_HEADER_FOOTER
    from docx.section import _Footer, _Header  # локально, чтобы не тащить в публичный API

    enum_map = {
        "default": WD_HEADER_FOOTER.PRIMARY,
        "first": WD_HEADER_FOOTER.FIRST_PAGE,
        "even": WD_HEADER_FOOTER.EVEN_PAGE,
    }
    found: set[str] = set()
    for ref in section._sectPr.findall(qn(f"w:{kind}Reference")):
        ref_type = ref.get(qn("w:type")) or "default"
        if ref_type in enum_map:
            found.add(ref_type)
    cls = _Header if kind == "header" else _Footer
    return [cls(section._sectPr, section._document_part, enum_map[t]) for t in ("default", "first", "even") if t in found]


def _iter_paragraphs(container) -> Paragraph:
    """Параграфы документа: тело, таблицы (в т.ч. вложенные), колонтитулы."""
    yield from container.paragraphs
    for table in _iter_tables(container.tables):
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in container.sections:
        for kind in ("header", "footer"):
            for part in _existing_parts(section, kind):
                yield from part.paragraphs
                for table in _iter_tables(part.tables):
                    for row in table.rows:
                        for cell in row.cells:
                            yield from cell.paragraphs


def replace_in_paragraph(paragraph: Paragraph, replacer: TextReplacer) -> ReplaceResult | None:
    runs = paragraph.runs
    if not runs:
        return None
    full_text = "".join(r.text for r in runs)
    result = replacer.replace_text(full_text)
    if not result.spans:
        return result
    # Правим спаны справа налево: тогда смещения левых спанов не меняются.
    for start, end, new in sorted(result.spans, key=lambda s: s[0], reverse=True):
        _apply_span(paragraph, start, end, new)
    return result


def _apply_span(paragraph: Paragraph, start: int, end: int, new_text: str) -> None:
    runs = paragraph.runs
    bounds: list[tuple[int, int]] = []
    pos = 0
    for r in runs:
        bounds.append((pos, pos + len(r.text)))
        pos += len(r.text)
    if pos == 0:
        return

    first = last = None
    for i, (a, b) in enumerate(bounds):
        if a <= start < b:
            first = i
        if a < end <= b:
            last = i
            break
    if first is None or last is None:
        return

    for j in range(first, last + 1):
        a, b = bounds[j]
        cut_a = max(start, a) - a
        cut_b = min(end, b) - a
        text = runs[j].text
        if j == first:
            runs[j].text = text[:cut_a] + new_text + text[cut_b:]
        else:
            # хвост токена в этом run: вырезаем покрытую часть
            runs[j].text = text[:0 if a >= start else cut_a] + text[cut_b:]


def process_document(doc: _DocxDocument, replacer: TextReplacer) -> dict:
    """Обезличить (или восстановить) документ на месте. Возвращает статистику."""
    replaced: list[tuple[str, str]] = []
    unknown: list[str] = []
    seen_unknown: set[str] = set()
    for paragraph in _iter_paragraphs(doc):
        result = replace_in_paragraph(paragraph, replacer)
        if result is None:
            continue
        replaced.extend(result.replaced)
        for word in result.unknown:
            if word not in seen_unknown:
                seen_unknown.add(word)
                unknown.append(word)
    return {"replaced": replaced, "unknown": unknown, "replaced_count": len(replaced)}


def process_docx_file(src: str | Path, dst: str | Path, replacer: TextReplacer) -> dict:
    doc = Document(str(src))
    stats = process_document(doc, replacer)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dst))
    return stats


def extract_text(doc: _DocxDocument) -> str:
    """Весь непустой текст документа (для тестов и предпросмотра)."""
    return "\n".join(p.text for p in _iter_paragraphs(doc) if p.text.strip())

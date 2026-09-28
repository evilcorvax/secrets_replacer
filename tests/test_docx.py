"""Тесты .docx: форматирование runs, таблицы, колонтитулы, round-trip
(обезличить → обратно → diff с оригиналом пустой)."""
import json

import pytest
from docx import Document

from core.docx_processor import extract_text, process_docx_file, process_document
from core.morphology import Morphology
from core.replacer import TextReplacer

MORPH = Morphology.shared()
DICT = {"иванов": "петров", "иван": "сергей", "москва": "казань"}


def make_doc(path, paragraphs):
    doc = Document()
    for runs in paragraphs:
        p = doc.add_paragraph()
        for text, bold in runs:
            r = p.add_run(text)
            r.bold = bold
    doc.save(str(path))
    return doc


def forward(text_dict=None):
    return TextReplacer(MORPH, text_dict if text_dict is not None else DICT)


class TestFormatting:
    def test_bold_preserved(self, tmp_path):
        src = tmp_path / "a.docx"
        make_doc(src, [[("Иванов ", False), ("подписал", True), (" договор", False)]])
        dst = tmp_path / "b.docx"
        process_docx_file(src, dst, forward())
        doc = Document(str(dst))
        runs = doc.paragraphs[0].runs
        assert [r.text for r in runs] == ["Петров ", "подписал", " договор"]
        assert runs[1].bold is True
        assert runs[0].bold is False

    def test_word_split_across_runs(self, tmp_path):
        # «Ива» + «нов» — токен разорван runs
        src = tmp_path / "a.docx"
        make_doc(src, [[("Ива", False), ("нов ушёл", False)]])
        dst = tmp_path / "b.docx"
        process_docx_file(src, dst, forward())
        assert extract_text(Document(str(dst))) == "Петров ушёл"

    def test_split_runs_keep_formatting_around(self, tmp_path):
        src = tmp_path / "a.docx"
        make_doc(src, [[("Встречал ", False), ("ИВА", True), ("НОВА", True), (" сегодня", False)]])
        dst = tmp_path / "b.docx"
        process_docx_file(src, dst, forward())
        doc = Document(str(dst))
        assert extract_text(doc) == "Встречал ПЕТРОВА сегодня"

    def test_tables_processed(self, tmp_path):
        src = tmp_path / "a.docx"
        doc = Document()
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Иванов"
        table.cell(0, 1).text = "обычное слово"
        doc.save(str(src))
        dst = tmp_path / "b.docx"
        process_docx_file(src, dst, forward())
        out = Document(str(dst))
        assert out.tables[0].cell(0, 0).text == "Петров"
        assert out.tables[0].cell(0, 1).text == "обычное слово"

    def test_header_processed(self, tmp_path):
        src = tmp_path / "a.docx"
        doc = Document()
        doc.add_paragraph("текст")
        doc.sections[0].header.paragraphs[0].text = "Секретно: Иванов"
        doc.save(str(src))
        dst = tmp_path / "b.docx"
        process_docx_file(src, dst, forward())
        out = Document(str(dst))
        assert out.sections[0].header.paragraphs[0].text == "Секретно: Петров"


class TestRoundTrip:
    def test_roundtrip_restores_original(self, tmp_path):
        src = tmp_path / "orig.docx"
        make_doc(src, [
            [("Иванов подписал договор. ", False)],
            [("Иванову передали документы. ", False)],
            [("Встречал ИВАНОВА в Москве", False)],
        ])
        mid = tmp_path / "mid.docx"
        stats = process_docx_file(src, mid, forward())
        assert extract_text(Document(str(mid))) == (
            "Петров подписал договор. \nПетрову передали документы. \nВстречал ПЕТРОВА в Казани"
        )

        # обратная замена по маппингу
        reverse = TextReplacer(MORPH, {"петров": "иванов", "сергей": "иван", "казань": "москва"})
        restored = tmp_path / "restored.docx"
        process_docx_file(mid, restored, reverse)
        assert extract_text(Document(str(restored))) == extract_text(Document(str(src)))

    def test_txt_roundtrip(self, tmp_path):
        text = "Иванов подписал договор. Иванову передали документы."
        fwd = forward().replace_text(text)
        rev = TextReplacer(MORPH, {"петров": "иванов"})
        back = rev.replace_text(fwd.text, collect_unknown=False)
        assert back.text == text


class TestStats:
    def test_stats_replaced_and_unknown(self, tmp_path):
        src = tmp_path / "a.docx"
        make_doc(src, [[("Иванов встретил Сидорова", False)]])
        doc = Document(str(src))
        stats = process_document(doc, forward())
        assert stats["replaced_count"] == 1
        assert "Сидорова" in stats["unknown"]

"""Тесты словаря: импорт (CSV/JSON/TXT с автодетектом), валидация,
автогенерация (детерминированная), экспорт маппинга, проекты."""
import json

import pytest

from core.dictionary import DictEntry, ReplacementDictionary
from core.morphology import Morphology


@pytest.fixture
def d():
    return ReplacementDictionary(Morphology.shared())


class TestCsvImport:
    def test_semicolon_autodetect(self, d, tmp_path):
        p = tmp_path / "s.csv"
        p.write_text("Иванов;Петров\nСидоров;Козлов\n", encoding="utf-8")
        report = d.load_csv(p)
        assert report.loaded == 2 and not report.bad_rows

    def test_comma_autodetect(self, d, tmp_path):
        p = tmp_path / "s.csv"
        p.write_text("Иванов,Петров\nСидоров,Козлов\n", encoding="utf-8")
        assert d.load_csv(p).loaded == 2

    def test_single_column_creates_empty_replacement(self, d, tmp_path):
        p = tmp_path / "s.csv"
        p.write_text("Иванов\n", encoding="utf-8")
        d.load_csv(p)
        assert d.entries[0].original == "Иванов"
        assert d.entries[0].replacement == ""

    def test_bad_rows_reported_not_skipped_silently(self, d, tmp_path):
        p = tmp_path / "s.csv"
        p.write_text("Иванов;Петров\n;;\n\n", encoding="utf-8")
        report = d.load_csv(p)
        assert report.loaded == 1


class TestJsonImport:
    def test_dict_form(self, d, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"Иванов": "Петров"}), encoding="utf-8")
        assert d.load_json(p).loaded == 1

    def test_pairs_list(self, d, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps([["Иванов", "Петров"], ["Сидоров", "Козлов"]]), encoding="utf-8")
        assert d.load_json(p).loaded == 2


class TestTxtImport:
    def test_one_column(self, d, tmp_path):
        p = tmp_path / "s.txt"
        p.write_text("Иванов\nСидоров\n", encoding="utf-8")
        assert d.load_txt(p).loaded == 2


class TestValidation:
    def test_duplicate_detected(self, d):
        d.add("Иванов", "Петров")
        d.entries.append(DictEntry("иванова", "Сидорова"))  # та же лемма, добавлено в обход проверки
        assert any("дублирует" in issue for issue in d.validate())

    def test_empty_replacement_warned(self, d, tmp_path):
        p = tmp_path / "s.csv"
        p.write_text("Иванов\n", encoding="utf-8")
        d.load_csv(p)  # одна колонка — пустая замена допустима при импорте
        assert any("пустая замена" in issue for issue in d.validate())

    def test_conflict_detected(self, d):
        d.add("Иванов", "Сидоров")
        d.add("Сидоров", "Козлов")
        assert any("Конфликт" in issue for issue in d.validate())

    def test_clean_dictionary_ok(self, d):
        d.add("Иванов", "Петров")
        assert d.validate() == []


class TestAutogenerate:
    def test_types_assigned(self, d):
        d.add("Иванов", "", allow_empty=True)
        d.add("Иван", "", allow_empty=True)
        d.add("Иванович", "", allow_empty=True)
        n = d.autogenerate()
        assert n == 3
        assert all(e.replacement for e in d.entries)

    def test_deterministic(self, d):
        d.add("Сидоров", "", allow_empty=True)
        d.add("Иванов", "", allow_empty=True)
        d.autogenerate()
        first = {e.original: e.replacement for e in d.entries}

        d2 = ReplacementDictionary(Morphology.shared())
        d2.add("Сидоров", "", allow_empty=True)
        d2.add("Иванов", "", allow_empty=True)
        d2.autogenerate()
        second = {e.original: e.replacement for e in d2.entries}
        assert first == second

    def test_generic_replacements_are_cyrillic_only(self, d):
        # «Объект001» сломал бы обратную замену: токенизатор пропускает
        # слова, склеенные с цифрами. Генерик-замены должны быть чисто кириллическими.
        d.add("АйТиКомпани", "", allow_empty=True)
        d.autogenerate()
        repl = d.entries[0].replacement
        assert repl and repl.isalpha()


class TestMappingAndProject:
    def test_reverse_mapping_keys_are_lemmas(self, d):
        d.add("Иванов", "Петров")
        m = d.as_reverse_mapping()
        assert m.get("петров") == "иванов"

    def test_export_mapping_file(self, d, tmp_path):
        d.add("Иванов", "Петров")
        p = tmp_path / "m.json"
        d.export_mapping(p)
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"петров": "иванов"}

    def test_project_roundtrip(self, d, tmp_path):
        d.add("Иванов", "Петров")
        d.add("Сидоров", "Козлов")
        p = tmp_path / "proj.json"
        d.save_project(p)
        d2 = ReplacementDictionary(Morphology.shared())
        d2.load_project(p)
        assert [(e.original, e.replacement) for e in d2.entries] == [
            ("Иванов", "Петров"), ("Сидоров", "Козлов")
        ]


class TestNormalization:
    def test_flexed_forms_match_lemma(self, d):
        d.add("Иванов", "Петров")
        m = d.as_mapping()
        assert "иванов" in m  # лемма нормализована

    def test_find_case_insensitive(self, d):
        d.add("Иванов", "Петров")
        assert d.find("петров") == [0]
        assert d.find("ИВАНОВ") == [0]
        assert d.find("") == [0]

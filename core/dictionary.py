"""Словарь замен: загрузка/сохранение, валидация, автогенерация.

Хранение нормализованное: при добавлении оригинал приводится к лемме,
поэтому «Сидоров», «Сидорова», «сидоровым» матчатся все.
Пользователь JSON/CSV руками не редактирует — только через GUI (см. ui/).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .morphology import Morphology

# Встроенные списки для автогенерации (детерминированной: оригиналы
# сортируются, замены выдаются последовательно из списка).
SURNAMES = [
    "Петров", "Сидоров", "Кузнецов", "Смирнов", "Попов", "Волков",
    "Соколов", "Лебедев", "Козлов", "Новиков", "Морозов", "Петрова",
    "Сидорова", "Кузнецова", "Смирнова", "Попова", "Волкова", "Соколова",
    "Лебедева", "Козлова", "Новикова", "Морозова", "Орлов", "Зайцев",
    "Белова", "Гусев", "Титов", "Крылов", "Медведев", "Ершов",
]
FIRST_NAMES = [
    "Александр", "Борис", "Виктор", "Григорий", "Дмитрий", "Евгений",
    "Жанна", "Зинаида", "Игорь", "Константин", "Леонид", "Михаил",
    "Николай", "Олег", "Павел", "Роман", "Сергей", "Тимур", "Фёдор",
    "Эдуард", "Юрий", "Яков", "Анна", "Вера", "Галина", "Елена", "Ирина",
    "Клавдия", "Людмила", "Мария", "Нина", "Ольга", "Софья", "Татьяна",
]
PATRONYMICS = [
    "Александрович", "Борисович", "Викторович", "Григорьевич", "Дмитриевич",
    "Евгеньевич", "Игоревич", "Константинович", "Леонидович", "Михайлович",
    "Николаевич", "Олегович", "Павлович", "Романович", "Сергеевич",
    "Тимурович", "Фёдорович", "Эдуардович", "Юрьевич", "Яковлевич",
    "Александровна", "Борисовна", "Викторовна", "Дмитриевна", "Евгеньевна",
    "Игоревна", "Константиновна", "Михайловна", "Николаевна", "Сергеевна",
]
# Для слов, тип которых определить не удалось, генерируем нейтральные
# псевдонимы ТОЛЬКО из кириллицы: замена вида «Объект001» не сработала бы
# при обратной замене — токенизатор слова со склеенными цифрами пропускает.
GENERIC_SUFFIXES = [
    "Аль", "Бет", "Вег", "Гам", "Дел", "Ель", "Жук", "Зет", "Ист", "Кап",
    "Лом", "Мир", "Нор", "Ост", "Пар", "Ров", "Сол", "Тон", "Ум", "Фал",
    "Хор", "Цел", "Чан", "Шар", "Щит",
]


@dataclass
class DictEntry:
    original: str
    replacement: str

    def as_row(self) -> list[str]:
        return [self.original, self.replacement]


@dataclass
class ImportReport:
    loaded: int = 0
    # строки, которые не удалось разобрать: (номер строки, сырой текст, причина)
    bad_rows: list[tuple[int, str, str]] | None = None


class ReplacementDictionary:
    """Упорядоченный набор пар «оригинал → замена» с нормализацией."""

    def __init__(self, morph: Morphology | None = None) -> None:
        self.morph = morph or Morphology.shared()
        self.entries: list[DictEntry] = []

    # ------------------------------------------------------------------ база

    def __len__(self) -> int:
        return len(self.entries)

    def clear(self) -> None:
        self.entries.clear()

    def _lemma(self, word: str) -> str:
        try:
            return self.morph.lemma(word)
        except Exception:
            return word.strip().lower()

    def add(self, original: str, replacement: str, allow_empty: bool = False) -> str | None:
        """Добавить пару. Возвращает текст предупреждения или None.

        allow_empty — для импорта: строка без замены допустима, замену
        потом подберёт автогенерация. Ручной ввод через GUI пустые замены
        не принимает.
        """
        original = (original or "").strip()
        replacement = (replacement or "").strip()
        if not original:
            return "Пустой оригинал — строка пропущена."
        if not replacement and not allow_empty:
            return "Пустая замена — строка пропущена."
        lemma = self._lemma(original)
        for e in self.entries:
            if self._lemma(e.original) == lemma:
                return f"«{original}» уже есть в словаре — строка пропущена."
        self.entries.append(DictEntry(original, replacement))
        return None

    def update_entry(self, index: int, original: str, replacement: str) -> str | None:
        """Редактирование существующей строки (двойной клик / кнопка «Изменить»)."""
        original = (original or "").strip()
        replacement = (replacement or "").strip()
        if not original or not replacement:
            return "Оригинал и замена не должны быть пустыми."
        lemma = self._lemma(original)
        for i, e in enumerate(self.entries):
            if i != index and self._lemma(e.original) == lemma:
                return f"«{original}» уже есть в словаре (строка {i + 1})."
        self.entries[index] = DictEntry(original, replacement)
        return None

    def remove(self, indices: list[int]) -> None:
        for i in sorted(set(indices), reverse=True):
            del self.entries[i]

    def as_mapping(self) -> dict[str, str]:
        """{лемма_оригинала: замена} — вход для TextReplacer."""
        return {self._lemma(e.original): e.replacement for e in self.entries}

    def as_reverse_mapping(self) -> dict[str, str]:
        """{лемма_замены: лемма_оригинала} — вход для обратной замены."""
        return {self._lemma(e.replacement): self._lemma(e.original) for e in self.entries}

    def find(self, query: str) -> list[int]:
        """Индексы строк, содержащих подстроку (регистронезависимо)."""
        q = query.strip().lower()
        if not q:
            return list(range(len(self.entries)))
        return [
            i for i, e in enumerate(self.entries)
            if q in e.original.lower() or q in e.replacement.lower()
        ]

    # ------------------------------------------------------------------ валидация

    def validate(self) -> list[str]:
        """Проверка всего словаря: дубликаты, пустые, конфликты пересечения."""
        issues: list[str] = []
        seen: dict[str, int] = {}
        lemmas: dict[str, int] = {}
        for i, e in enumerate(self.entries, start=1):
            if not e.original.strip():
                issues.append(f"Строка {i}: пустой оригинал.")
            if not e.replacement.strip():
                issues.append(f"Строка {i}: пустая замена (можно заполнить автогенерацией).")
            lemma = self._lemma(e.original) if e.original.strip() else ""
            if lemma:
                if lemma in seen:
                    issues.append(f"Строка {i}: «{e.original}» дублирует строку {seen[lemma]}.")
                else:
                    seen[lemma] = i
                lemmas[lemma] = i
        replacements = {self._lemma(e.replacement) for e in self.entries if e.replacement.strip()}
        for repl in sorted(replacements):
            if repl in lemmas:
                issues.append(
                    f"Конфликт: замена «{repl}» совпадает с оригиналом строки {lemmas[repl]} "
                    "— при обратной замене возможны ошибки."
                )
        return issues

    # ------------------------------------------------------------------ автогенерация

    def autogenerate(self) -> int:
        """Заполнить пустые замены детерминированно: сортируем оригиналы,
        последовательно выдаём подходящие по типу псевдонимы из встроенных
        списков. Одинаковый оригинал всегда даёт одинаковую замену."""
        empties = sorted(
            (e for e in self.entries if not e.replacement.strip()),
            key=lambda e: self._lemma(e.original),
        )
        counters = {"Surn": 0, "Name": 0, "Patr": 0, "other": 0}
        for entry in empties:
            tag = self.morph.best(entry.original).tag
            if "Surn" in tag:
                kind, pool = "Surn", SURNAMES
            elif "Name" in tag:
                kind, pool = "Name", FIRST_NAMES
            elif "Patr" in tag:
                kind, pool = "Patr", PATRONYMICS
            else:
                kind, pool = "other", None
            idx = counters[kind]
            counters[kind] += 1
            if pool is not None:
                entry.replacement = pool[idx % len(pool)]
            else:
                entry.replacement = "Объект" + GENERIC_SUFFIXES[idx % len(GENERIC_SUFFIXES)]
        return len(empties)

    # ------------------------------------------------------------------ импорт

    def load_csv(self, path: str | Path) -> ImportReport:
        report = ImportReport(bad_rows=[])
        first = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if not first:
            return report
        delim = ";" if first[0].count(";") >= first[0].count(",") else ","
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
            for n, row in enumerate(csv.reader(f, delimiter=delim), start=1):
                if not row or all(not c.strip() for c in row):
                    continue
                original = row[0].strip()
                replacement = row[1].strip() if len(row) > 1 else ""
                if not original:
                    report.bad_rows.append((n, ";".join(row), "пустой оригинал"))
                    continue
                if not replacement:
                    # одна колонка — замену добьём автогенерацией
                    self.entries.append(DictEntry(original, ""))
                    report.loaded += 1
                    continue
                warn = self.add(original, replacement)
                if warn:
                    report.bad_rows.append((n, ";".join(row), warn))
                else:
                    report.loaded += 1
        return report

    def load_json(self, path: str | Path) -> ImportReport:
        """JSON-импорт: список пар, список объектов {original, replacement}
        или объект {оригинал: замена}. Формат маппинга (замена→оригинал)
        для импорта НЕ используем — он только для обратной замены."""
        report = ImportReport(bad_rows=[])
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows: list[tuple[str, str]] = []
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            # формат проекта: {"entries": [[оригинал, замена], ...]}
            items = data["entries"]
        elif isinstance(data, dict):
            rows = [(str(k), str(v)) for k, v in data.items()]
            items = None
        elif isinstance(data, list):
            items = data
        else:
            items = None

        if items is not None:
            for item in items:
                if isinstance(item, dict):
                    rows.append((str(item.get("original", "")), str(item.get("replacement", ""))))
                elif isinstance(item, (list, tuple)) and len(item) >= 1:
                    rows.append((str(item[0]), str(item[1]) if len(item) > 1 else ""))
        for n, (original, replacement) in enumerate(rows, start=1):
            original, replacement = original.strip(), replacement.strip()
            if not original:
                report.bad_rows.append((n, f"{original} -> {replacement}", "пустой оригинал"))
                continue
            if not replacement:
                self.entries.append(DictEntry(original, ""))
                report.loaded += 1
                continue
            warn = self.add(original, replacement)
            if warn:
                report.bad_rows.append((n, f"{original} -> {replacement}", warn))
            else:
                report.loaded += 1
        return report

    def load_txt(self, path: str | Path) -> ImportReport:
        """Простой txt: одна колонка «оригинал» на строку, замены — автогенерация."""
        report = ImportReport(bad_rows=[])
        for n, line in enumerate(Path(path).read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            original = line.strip()
            if not original:
                continue
            if not self.add(original, "", allow_empty=True):
                report.loaded += 1
            else:
                report.bad_rows.append((n, original, "не удалось добавить"))
        return report

    def import_auto(self, path: str | Path) -> ImportReport:
        ext = Path(path).suffix.lower()
        if ext == ".csv":
            return self.load_csv(path)
        if ext == ".json":
            return self.load_json(path)
        return self.load_txt(path)

    # ------------------------------------------------------------------ экспорт

    def export_csv(self, path: str | Path, delimiter: str = ";") -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=delimiter)
            for e in self.entries:
                writer.writerow(e.as_row())

    def export_mapping(self, path: str | Path) -> None:
        """Файл маппинга для обратной замены: {лемма_замены: лемма_оригинала}."""
        Path(path).write_text(
            json.dumps(self.as_reverse_mapping(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_project(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(
                {"entries": [e.as_row() for e in self.entries]},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    def load_project(self, path: str | Path) -> None:
        self.clear()
        self.load_json(path)

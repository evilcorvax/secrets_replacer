"""Главное окно приложения: два режима — «Обезличивание» и «Обратная замена».

Сценарий (по ТЗ): выбрать файл → загрузить/собрать словарь → «Обезличить»
→ посмотреть статистику и пропущенные слова → сохранить результат и маппинг.
Обработка идёт в потоке, UI не блокируется; прогресс — индикатор.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from docx import Document

from core import (
    Morphology,
    ReplacementDictionary,
    TextReplacer,
    process_document,
    read_txt,
    write_txt,
)

from .dictionary_editor import DictionaryEditor

SUPPORTED_FILES = [("Документы", "*.docx *.txt"), ("Все файлы", "*.*")]


class UnknownWordsDialog(ctk.CTkToplevel):
    """«Найдены слова, которых нет в словаре»: галочки → добавить → перезапуск."""

    MAX_SHOWN = 300  # больше — только первые (с комментарием), чтобы не повисать UI

    def __init__(self, parent, words: list[str], on_add_and_rerun) -> None:
        super().__init__(parent)
        self.title("Слова, которых нет в словаре")
        self.geometry("520x480")
        self.on_add_and_rerun = on_add_and_rerun

        shown = words[: self.MAX_SHOWN]
        ctk.CTkLabel(
            self,
            text=f"Отметьте слова, которые нужно добавить в словарь"
                 + (f" (показаны первые {len(shown)} из {len(words)})" if len(words) > len(shown) else "")
                 + " — замены подберутся автоматически.",
            wraplength=480, justify="left",
        ).pack(padx=12, pady=(10, 4), anchor="w")

        frame = ctk.CTkScrollableFrame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=4)

        self.checkboxes: list[tuple[ctk.CTkCheckBox, str]] = []
        for w in shown:
            cb = ctk.CTkCheckBox(frame, text=w)
            cb.select()
            cb.pack(anchor="w", padx=6, pady=1)
            self.checkboxes.append((cb, w))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(btns, text="Добавить выбранные и перезапустить",
                      command=self._add).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Закрыть", command=self.destroy).pack(side="right", padx=4)

    def _add(self) -> None:
        picked = [w for cb, w in self.checkboxes if cb.get() == 1]
        self.destroy()
        self.on_add_and_rerun(picked)


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Обезличивание документов")
        self.geometry("860x640")

        self.morph = Morphology.shared()
        self.dictionary = ReplacementDictionary(self.morph)

        # состояние последней обработки
        self._input_path: Path | None = None
        self._processed_doc: Document | None = None   # для docx
        self._processed_text: str | None = None       # для txt
        self._processed_encoding: str = "utf-8"
        self._last_unknown: list[str] = []
        self._busy = False

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_forward = tabs.add("Обезличивание")
        self.tab_reverse = tabs.add("Обратная замена")
        self._build_forward_tab()
        self._build_reverse_tab()

    # ================================================================== UI

    def _build_forward_tab(self) -> None:
        t = self.tab_forward

        row1 = ctk.CTkFrame(t, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 2))
        ctk.CTkButton(row1, text="1. Выбрать файл", command=self.choose_file).pack(side="left")
        self.lbl_file = ctk.CTkLabel(row1, text="файл не выбран", anchor="w")
        self.lbl_file.pack(side="left", padx=10)

        row2 = ctk.CTkFrame(t, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=2)
        ctk.CTkButton(row2, text="2. Загрузить словарь", command=self.load_dictionary).pack(side="left")
        ctk.CTkButton(row2, text="Редактор словаря", command=self.open_editor).pack(side="left", padx=8)
        self.lbl_dict = ctk.CTkLabel(row2, text="словарь пуст", anchor="w")
        self.lbl_dict.pack(side="left", padx=10)

        row3 = ctk.CTkFrame(t, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=2)
        self.btn_run = ctk.CTkButton(row3, text="3. Обезличить", command=self.run_forward)
        self.btn_run.pack(side="left")
        self.progress = ctk.CTkProgressBar(t)
        self.progress.pack(fill="x", padx=10, pady=6)
        self.progress.set(0)

        row4 = ctk.CTkFrame(t, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=2)
        self.btn_save = ctk.CTkButton(row4, text="4. Сохранить результат", command=self.save_result)
        self.btn_save.pack(side="left")
        self.btn_save.configure(state="disabled")
        self.btn_unknown = ctk.CTkButton(
            row4, text="Пропущенные слова…",
            command=self.show_unknown, state="disabled",
        )
        self.btn_unknown.pack(side="left", padx=8)

        self.txt_stats = ctk.CTkTextbox(t, wrap="word")
        self.txt_stats.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self.txt_stats.configure(state="disabled")

    def _build_reverse_tab(self) -> None:
        t = self.tab_reverse

        row1 = ctk.CTkFrame(t, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 2))
        ctk.CTkButton(row1, text="1. Выбрать обезличенный файл", command=self.choose_reverse_file).pack(side="left")
        self.lbl_rev_file = ctk.CTkLabel(row1, text="файл не выбран", anchor="w")
        self.lbl_rev_file.pack(side="left", padx=10)

        row2 = ctk.CTkFrame(t, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=2)
        ctk.CTkButton(row2, text="2. Выбрать файл маппинга (JSON)", command=self.choose_mapping).pack(side="left")
        self.lbl_mapping = ctk.CTkLabel(row2, text="маппинг не выбран", anchor="w")
        self.lbl_mapping.pack(side="left", padx=10)

        row3 = ctk.CTkFrame(t, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=2)
        self.btn_restore = ctk.CTkButton(row3, text="3. Восстановить исходник", command=self.run_reverse)
        self.btn_restore.pack(side="left")
        self.btn_save_restored = ctk.CTkButton(
            row3, text="4. Сохранить восстановленный файл",
            command=self.save_restored, state="disabled",
        )
        self.btn_save_restored.pack(side="left", padx=8)

        self.txt_rev_log = ctk.CTkTextbox(t, wrap="word")
        self.txt_rev_log.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self.txt_rev_log.configure(state="disabled")

        self._reverse_path: Path | None = None
        self._mapping_path: Path | None = None
        self._restored_doc: Document | None = None
        self._restored_text: str | None = None
        self._restored_encoding: str = "utf-8"

    # ================================================================== выбор файлов

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Выберите документ", filetypes=SUPPORTED_FILES)
        if path:
            self._input_path = Path(path)
            self.lbl_file.configure(text=self._input_path.name)
            self._reset_result()

    def choose_reverse_file(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Выберите обезличенный документ", filetypes=SUPPORTED_FILES)
        if path:
            self._reverse_path = Path(path)
            self.lbl_rev_file.configure(text=self._reverse_path.name)

    def choose_mapping(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Выберите файл маппинга",
            filetypes=[("JSON маппинга", "*.json"), ("Все файлы", "*.*")],
        )
        if path:
            self._mapping_path = Path(path)
            self.lbl_mapping.configure(text=self._mapping_path.name)

    # ================================================================== словарь

    def load_dictionary(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Загрузить словарь",
            filetypes=[("Словарь", "*.csv *.json *.txt"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            report = self.dictionary.import_auto(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Словарь", f"Не удалось загрузить словарь:\n{exc}", parent=self)
            return
        self.refresh_dict_label()
        msg = f"Загружено записей: {report.loaded}. Всего в словаре: {len(self.dictionary)}."
        if report.bad_rows:
            msg += f"\n\nПропущено строк: {len(report.bad_rows)} (см. редактор словаря → Импорт для деталей)."
        messagebox.showinfo("Словарь", msg, parent=self)
        # если в файле были строки без замены — сразу предлагаем доделать в редакторе
        self.open_editor()

    def open_editor(self) -> None:
        DictionaryEditor(self, self.dictionary, on_change=self.refresh_dict_label)

    def refresh_dict_label(self) -> None:
        n = len(self.dictionary)
        self.lbl_dict.configure(text=f"записей: {n}" if n else "словарь пуст")

    # ================================================================== обезличивание

    def _reset_result(self) -> None:
        self._processed_doc = None
        self._processed_text = None
        self._last_unknown = []
        self.btn_save.configure(state="disabled")
        self.btn_unknown.configure(state="disabled")

    def run_forward(self) -> None:
        if not self._input_path:
            messagebox.showinfo("Обезличивание", "Сначала выберите файл.", parent=self)
            return
        if not len(self.dictionary):
            messagebox.showinfo("Обезличивание", "Словарь пуст. Загрузите его или откройте редактор.", parent=self)
            return
        self._run_processing(reverse=False)

    def run_reverse(self) -> None:
        if not self._reverse_path:
            messagebox.showinfo("Обратная замена", "Сначала выберите обезличенный файл.", parent=self)
            return
        if not self._mapping_path:
            messagebox.showinfo("Обратная замена", "Выберите файл маппинга (JSON).", parent=self)
            return
        self._run_processing(reverse=True)

    def _run_processing(self, reverse: bool) -> None:
        """Обработка в потоке: pymorphy3 на больших документах долгий, UI не блокируем."""
        self._set_busy(True)
        path = self._reverse_path if reverse else self._input_path

        def work():
            error = None
            try:
                if reverse:
                    mapping = json.loads(Path(self._mapping_path).read_text(encoding="utf-8"))
                    replacer = TextReplacer(self.morph, mapping)
                else:
                    replacer = TextReplacer(self.morph, self.dictionary.as_mapping())

                if path.suffix.lower() == ".docx":
                    doc = Document(str(path))
                    stats = process_document(doc, replacer)
                    if reverse:
                        self._restored_doc, self._restored_text = doc, None
                    else:
                        self._processed_doc, self._processed_text = doc, None
                elif path.suffix.lower() == ".txt":
                    text, enc = read_txt(path)
                    result = replacer.replace_text(text)
                    stats = {"replaced": result.replaced, "unknown": result.unknown,
                             "replaced_count": len(result.replaced)}
                    if reverse:
                        self._restored_text, self._restored_doc, self._restored_encoding = result.text, None, enc
                    else:
                        self._processed_text, self._processed_doc, self._processed_encoding = result.text, None, enc
                else:
                    raise ValueError(f"Неподдерживаемый формат файла: {path.suffix}")
            except Exception as exc:  # noqa: BLE001 — любую ошибку показываем пользователю
                error = exc
                stats = None
            self.after(0, lambda: self._on_done(reverse, stats, error))

        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, reverse: bool, stats: dict | None, error: Exception | None) -> None:
        self._set_busy(False)
        if error is not None:
            messagebox.showerror("Ошибка обработки", str(error), parent=self)
            return
        if stats is None:
            return
        if reverse:
            self._show_reverse_stats(stats)
        else:
            self._show_forward_stats(stats)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self.btn_run, self.btn_restore, self.btn_save, self.btn_save_restored):
            btn.configure(state=state)
        if busy:
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.set(0)

    # ================================================================== статистика и сохранение

    def _write_log(self, box: ctk.CTkTextbox, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _show_forward_stats(self, stats: dict) -> None:
        lines = [f"Заменено слов: {stats['replaced_count']}"]
        if stats["replaced"]:
            lines.append("")
            lines.append("Замены:")
            lines.extend(f"  {orig}  →  {repl}" for orig, repl in stats["replaced"])
        self._last_unknown = stats["unknown"]
        if self._last_unknown:
            lines.append("")
            lines.append(f"Не найдено в словаре: {len(self._last_unknown)} (см. кнопку «Пропущенные слова»)")
        self._write_log(self.txt_stats, "\n".join(lines))
        self.btn_save.configure(state="normal")
        if self._last_unknown:
            self.btn_unknown.configure(state="normal")
            self.show_unknown()

    def _show_reverse_stats(self, stats: dict) -> None:
        self._write_log(self.txt_rev_log, f"Восстановлено слов: {stats['replaced_count']}")
        self.btn_save_restored.configure(state="normal")

    def show_unknown(self) -> None:
        if not self._last_unknown:
            return
        UnknownWordsDialog(self, self._last_unknown, on_add_and_rerun=self._add_unknown_and_rerun)

    def _add_unknown_and_rerun(self, words: list[str]) -> None:
        for w in words:
            self.dictionary.add(w, "")  # предупреждения не критичны: дубликаты просто пропустим
        self.dictionary.autogenerate()
        self.refresh_dict_label()
        if words:
            self.run_forward()  # перезапуск обработки с дополненным словарём

    def save_result(self) -> None:
        self._save(
            title="Сохранить обезличенный документ",
            default_suffix=self._input_path.suffix if self._input_path else ".docx",
            doc=self._processed_doc,
            text=self._processed_text,
            encoding=self._processed_encoding,
            save_mapping=True,
        )

    def save_restored(self) -> None:
        self._save(
            title="Сохранить восстановленный документ",
            default_suffix=self._reverse_path.suffix if self._reverse_path else ".docx",
            doc=self._restored_doc,
            text=self._restored_text,
            encoding=self._restored_encoding,
            save_mapping=False,
        )

    def _save(self, title: str, default_suffix: str, doc, text, encoding: str, save_mapping: bool) -> None:
        if doc is None and text is None:
            messagebox.showinfo("Сохранение", "Пока нечего сохранить — сначала выполните обработку.", parent=self)
            return
        ext = default_suffix.lower()
        if ext not in (".docx", ".txt"):
            ext = ".docx"
        initial = "result" + ext
        path = filedialog.asksaveasfilename(
            parent=self, title=title, defaultextension=ext, initialfile=initial,
            filetypes=[("Документы", "*.docx *.txt")],
        )
        if not path:
            return
        path = Path(path)
        try:
            if doc is not None:
                doc.save(str(path))
            else:
                write_txt(path, text, encoding)
            if save_mapping:
                mapping_path = path.with_name(path.name + ".mapping.json")
                self.dictionary.export_mapping(mapping_path)
                messagebox.showinfo(
                    "Сохранено",
                    f"Результат: {path}\nМаппинг для обратной замены: {mapping_path}",
                    parent=self,
                )
            else:
                messagebox.showinfo("Сохранено", f"Файл сохранён: {path}", parent=self)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Сохранение", f"Не удалось сохранить файл:\n{exc}", parent=self)

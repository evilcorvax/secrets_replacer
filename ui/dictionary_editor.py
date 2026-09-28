"""Табличный редактор словаря «оригинал → замена».

Пользователь никогда не редактирует JSON/CSV руками — только через эту таблицу:
добавление, изменение (двойной клик), удаление (одной и нескольких строк),
поиск/фильтрация, импорт/экспорт, автогенерация замен, проекты, валидация.
"""
from __future__ import annotations

from tkinter import ttk, messagebox, filedialog

import customtkinter as ctk

from core.dictionary import ReplacementDictionary


def ask_pair(parent, title: str, original: str = "", replacement: str = ""):
    """Модальный диалог с двумя полями (оригинал / замена). Возвращает (orig, repl) или None."""
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("420x180")
    dialog.resizable(False, False)
    dialog.transient(parent.winfo_toplevel())
    dialog.grab_set()

    result: list | None = [None]

    ctk.CTkLabel(dialog, text="Оригинал:").grid(row=0, column=0, padx=12, pady=(16, 4), sticky="e")
    entry_orig = ctk.CTkEntry(dialog, width=260)
    entry_orig.grid(row=0, column=1, padx=12, pady=(16, 4), sticky="w")
    if original:
        entry_orig.insert(0, original)

    ctk.CTkLabel(dialog, text="Замена:").grid(row=1, column=0, padx=12, pady=4, sticky="e")
    entry_repl = ctk.CTkEntry(dialog, width=260)
    entry_repl.grid(row=1, column=1, padx=12, pady=4, sticky="w")
    if replacement:
        entry_repl.insert(0, replacement)

    def ok():
        result[0] = (entry_orig.get().strip(), entry_repl.get().strip())
        dialog.destroy()

    def cancel():
        result[0] = None
        dialog.destroy()

    btns = ctk.CTkFrame(dialog, fg_color="transparent")
    btns.grid(row=2, column=0, columnspan=2, pady=16)
    ctk.CTkButton(btns, text="OK", width=110, command=ok).pack(side="left", padx=8)
    ctk.CTkButton(btns, text="Отмена", width=110, command=cancel).pack(side="left", padx=8)

    entry_orig.focus_set()
    dialog.bind("<Return>", lambda _e: ok())
    dialog.bind("<Escape>", lambda _e: cancel())
    parent.winfo_toplevel().wait_window(dialog)
    return result[0]


class DictionaryEditor(ctk.CTkToplevel):
    def __init__(self, parent, dictionary: ReplacementDictionary, on_change=None) -> None:
        super().__init__(parent)
        self.title("Редактор словаря")
        self.geometry("760x520")
        self.dictionary = dictionary
        self.on_change = on_change
        self._row_to_entry: dict[str, int] = {}  # id строки Treeview -> индекс в dictionary

        # --- верхняя панель: поиск + кнопки строк ---
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        self.search_var = ctk.StringVar()
        search = ctk.CTkEntry(top, placeholder_text="Поиск по словарю…", textvariable=self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        search.bind("<KeyRelease>", lambda _e: self.reload())
        ctk.CTkButton(top, text="Добавить", width=100, command=self.add_entry).pack(side="left", padx=2)
        ctk.CTkButton(top, text="Изменить", width=100, command=self.edit_entry).pack(side="left", padx=2)
        ctk.CTkButton(top, text="Удалить", width=100, command=self.delete_entries).pack(side="left", padx=2)

        # --- таблица ---
        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=10, pady=4)
        cols = ("original", "replacement")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("original", text="Оригинал", command=lambda: self.sort_by("original"))
        self.tree.heading("replacement", text="Замена", command=lambda: self.sort_by("replacement"))
        self.tree.column("original", width=340, anchor="w")
        self.tree.column("replacement", width=340, anchor="w")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _e: self.edit_entry())

        # --- нижняя панель: импорт/экспорт/автогенерация/проект/проверка ---
        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=10, pady=(4, 10))
        for text, cmd in (
            ("Импорт (CSV/JSON/TXT)", self.import_file),
            ("Экспорт CSV", self.export_csv),
            ("Маппинг JSON (обратная замена)", self.export_mapping),
            ("Подобрать замены автоматически", self.autogenerate),
            ("Проверить словарь", self.validate),
            ("Сохранить проект", self.save_project),
            ("Загрузить проект", self.load_project),
        ):
            ctk.CTkButton(bottom, text=text, command=cmd).pack(fill="x", pady=2)

        self.lbl_count = ctk.CTkLabel(self, text="", anchor="w")
        self.lbl_count.pack(fill="x", padx=12, pady=(0, 6))

        self.reload()

    # ------------------------------------------------------------------ таблица

    def reload(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._row_to_entry.clear()
        indices = self.dictionary.find(self.search_var.get())
        for idx in indices:
            e = self.dictionary.entries[idx]
            iid = self.tree.insert("", "end", values=e.as_row())
            self._row_to_entry[iid] = idx
        total = len(self.dictionary)
        shown = len(indices)
        self.lbl_count.configure(
            text=f"Записей: {total}" + (f" (показано: {shown})" if shown != total else "")
        )

    def sort_by(self, column: str) -> None:
        key = (0 if column == "original" else 1)
        self.dictionary.entries.sort(key=lambda e: e.as_row()[key].lower())
        self.reload()
        self._changed()

    def _selected_indices(self) -> list[int]:
        return [self._row_to_entry[iid] for iid in self.tree.selection() if iid in self._row_to_entry]

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------------ операции со строками

    def add_entry(self) -> None:
        pair = ask_pair(self, "Добавить пару")
        if not pair:
            return
        warn = self.dictionary.add(*pair)
        if warn:
            messagebox.showwarning("Словарь", warn, parent=self)
        self.reload()
        self._changed()

    def edit_entry(self) -> None:
        indices = self._selected_indices()
        if len(indices) != 1:
            messagebox.showinfo("Редактор", "Выберите одну строку.", parent=self)
            return
        idx = indices[0]
        entry = self.dictionary.entries[idx]
        pair = ask_pair(self, "Изменить пару", entry.original, entry.replacement)
        if not pair:
            return
        warn = self.dictionary.update_entry(idx, *pair)
        if warn:
            messagebox.showwarning("Словарь", warn, parent=self)
        self.reload()
        self._changed()

    def delete_entries(self) -> None:
        indices = self._selected_indices()
        if not indices:
            return
        if not messagebox.askyesno("Удаление", f"Удалить {len(indices)} строк(и)?", parent=self):
            return
        self.dictionary.remove(indices)
        self.reload()
        self._changed()

    # ------------------------------------------------------------------ импорт/экспорт

    def import_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Импорт словаря",
            filetypes=[
                ("Файлы словарей", "*.csv *.json *.txt"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            report = self.dictionary.import_auto(path)
        except Exception as exc:  # noqa: BLE001 — показываем пользователю любую ошибку файла
            messagebox.showerror("Импорт", f"Не удалось импортировать файл:\n{exc}", parent=self)
            return
        msg = f"Загружено записей: {report.loaded}."
        if report.bad_rows:
            rows = "\n".join(f"строка {n}: {text} ({why})" for n, text, why in report.bad_rows[:20])
            more = "" if len(report.bad_rows) <= 20 else f"\n…и ещё {len(report.bad_rows) - 20}"
            msg += f"\n\nНе загружено: {len(report.bad_rows)}\n{rows}{more}"
        messagebox.showinfo("Импорт", msg, parent=self)
        self.reload()
        self._changed()

    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Экспорт в CSV",
            defaultextension=".csv", initialfile="slovar.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        self.dictionary.export_csv(path)
        messagebox.showinfo("Экспорт", f"Сохранено: {path}", parent=self)

    def export_mapping(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Экспорт маппинга для обратной замены",
            defaultextension=".json", initialfile="mapping.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        self.dictionary.export_mapping(path)
        messagebox.showinfo("Экспорт", f"Сохранено: {path}", parent=self)

    def autogenerate(self) -> None:
        n = self.dictionary.autogenerate()
        messagebox.showinfo(
            "Автогенерация",
            f"Подобраны замены для {n} записей." if n else "Нет пустых замен — всё уже заполнено.",
            parent=self,
        )
        self.reload()
        self._changed()

    def validate(self) -> None:
        issues = self.dictionary.validate()
        if not issues:
            messagebox.showinfo("Проверка", "Проблем не найдено.", parent=self)
        else:
            messagebox.showwarning("Проверка словаря", "\n".join(issues[:30]), parent=self)

    # ------------------------------------------------------------------ проекты

    def save_project(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Сохранить проект",
            defaultextension=".json", initialfile="proekt.json",
            filetypes=[("Проект словаря", "*.json")],
        )
        if not path:
            return
        self.dictionary.save_project(path)
        messagebox.showinfo("Проект", f"Сохранено: {path}", parent=self)

    def load_project(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Загрузить проект",
            filetypes=[("Проект словаря", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            self.dictionary.load_project(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Проект", f"Не удалось загрузить проект:\n{exc}", parent=self)
            return
        self.reload()
        self._changed()


def editor_for(parent, dictionary: ReplacementDictionary, on_change=None) -> DictionaryEditor:
    return DictionaryEditor(parent, dictionary, on_change=on_change)

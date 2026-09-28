"""Обёртка над pymorphy3.

Анализатор дорогой при создании (~секунда на загрузку словарей),
поэтому используем один общий экземпляр на процесс.
"""
from __future__ import annotations

import pymorphy3


class Morphology:
    """Ленивая обёртка над pymorphy3.MorphAnalyzer."""

    _instance: "Morphology | None" = None

    def __init__(self) -> None:
        self._morph = pymorphy3.MorphAnalyzer()

    @classmethod
    def shared(cls) -> "Morphology":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def parse(self, word: str):
        """Все разборы слова, от лучшего к худшему."""
        return self._morph.parse(word)

    def best(self, word: str):
        return self._morph.parse(word)[0]

    def lemma(self, word: str) -> str:
        """Нормальная форма (лемма) слова в нижнем регистре."""
        return self.best(word).normal_form.lower()

    def is_first_name(self, word: str) -> bool:
        """Является ли слово именем (по лучшему разбору)."""
        try:
            return "Name" in self.best(word).tag
        except Exception:
            return False

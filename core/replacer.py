"""Морфологическая замена слов в тексте.

Алгоритм (по ТЗ):
1. Токенизируем текст: отдельно обрабатываем инициалы («И.И.»), дефисные
   слова («собирать-тянуть», «Санкт-Петербург») и обычные слова.
2. Для каждого токена получаем лемму через pymorphy3.
3. Если лемма есть в словаре (сравнение регистронезависимое) — берём
   замену и склоняем её по граммемам найденного токена (inflect).
   Если склонение не удалось — берём замену в форме словаря.
4. Восстанавливаем регистр оригинала (ВСЕ ПРОПИСНЫЕ, Первая заглавная,
   остальное без изменений).

Решения, принятые за пределами буквы ТЗ (MVP):
- «Слова, которых нет в словаре» для диалога досбора — это уникальные
  слова с заглавной буквы, не являющиеся аббревиатурами (иначе список
  был бы полон «подписал»-«договор» и «США»).
- Слово, «склеенное» с латиницей/цифрами (HelloИванов, Иванов2),
  не заменяем — оно может быть частью email, URL, артикула и т.п.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .morphology import Morphology

# Порядок альтернатив важен: инициалы и дефисные слова длиннее обычных
# слов и должны матчиться первыми.
TOKEN_RE = re.compile(
    r"(?P<initial>[А-ЯЁ]\s?\.\s?[А-ЯЁ]\s?\.)"      # «И.И.», «И. И.»
    r"|(?P<hyphen>[а-яА-ЯёЁ]+(?:-[а-яА-ЯёЁ]+)+)"   # «собирать-тянуть», «Санкт-Петербург»
    r"|(?P<word>[а-яА-ЯёЁ]+)"
)

UPPER_INITIALS = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"


@dataclass
class ReplaceResult:
    text: str                                # новый текст целиком
    # спаны в КООРДИНАТАХ ИСХОДНОГО текста (нужны для docx, см. ниже)
    spans: list[tuple[int, int, str]] = field(default_factory=list)
    replaced: list[tuple[str, str]] = field(default_factory=list)  # (оригинал, замена) поверхности
    unknown: list[str] = field(default_factory=list)               # поверхностные формы «с заглавной»


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def restore_capitalization(original: str, replacement: str) -> str:
    """Копируем регистр оригинала на замену."""
    if not replacement:
        return replacement
    if len(original) > 1 and original.isupper():
        return replacement.upper()
    if original[0].isupper() and original[1:].islower():
        return replacement[0].upper() + replacement[1:]
    # остальные случаи (в т.ч. «иВанов») оставляем в нижнем регистре —
    # это детерминированно и для round-trip (обратная замена по тем же
    # правилам восстановит регистр симметрично).
    return replacement


class TextReplacer:
    """Заменяет слова текста по словарю лемм с учётом морфологии.

    mapping: {лемма_оригинала: слово_замена}. Тот же класс используется
    и для обратной замены — тогда в mapping передаётся {лемма_замены: оригинал}.
    """

    def __init__(self, morph: Morphology, mapping: dict[str, str]) -> None:
        self.morph = morph
        self.mapping = {k.strip().lower(): v for k, v in mapping.items() if k and k.strip()}

    def replace_text(self, text: str, collect_unknown: bool = True) -> ReplaceResult:
        spans: list[tuple[int, int, str]] = []
        replaced: list[tuple[str, str]] = []
        unknown: list[str] = []
        seen_unknown: set[str] = set()

        for m in TOKEN_RE.finditer(text):
            start, end = m.start(), m.end()
            token = m.group()
            # Не заменяем внутри «склеенных» слов: латиница, цифры, '_'
            # (email, URL, артикулы). Проверяем соседние символы.
            if start > 0 and _is_word_char(text[start - 1]):
                continue
            if end < len(text) and _is_word_char(text[end]):
                continue

            if m.lastgroup == "initial":
                new = self._replace_initial(token)
            elif m.lastgroup == "hyphen":
                new = self._replace_hyphen(token)
            else:
                new = self._replace_word(token)
                if new is None and collect_unknown:
                    self._collect_unknown(token, start, text, unknown, seen_unknown)

            if new is not None and new != token:
                spans.append((start, end, new))
                replaced.append((token, new))

        return ReplaceResult(
            text=self._apply_spans(text, spans),
            spans=spans,
            replaced=replaced,
            unknown=unknown,
        )

    # ------------------------------------------------------------------ слова

    def _replace_word(self, token: str) -> str | None:
        parse = self.morph.best(token)
        lemma = parse.normal_form.lower()
        if lemma not in self.mapping:
            return None
        replacement = self.mapping[lemma]
        inflected = self._inflect_like(replacement, parse)
        return restore_capitalization(token, inflected)

    def _inflect_like(self, replacement: str, source_parse) -> str:
        """Склоняем замену по граммемам исходного токена.

        Не пытаемся склонять слова, которые по своей природе неизменяемы
        (аббревиатуры, несклоняемые имена) — pymorphy3 сам вернёт None,
        тогда отдаём форму словаря.
        """
        if not replacement:
            return replacement
        rep_parse = self.morph.best(replacement)
        try:
            form = rep_parse.inflect(source_parse.tag.grammemes)
        except (ValueError, TypeError):
            form = None
        return form.word if form is not None else replacement

    def _collect_unknown(self, token: str, start: int, text: str,
                         unknown: list[str], seen: set[str]) -> None:
        """Кандидаты в «пропущенные слова»: с заглавной буквы, не аббревиатура.

        Слово с заглавной буквы в НАЧАЛЕ предложения («Встречал», «Подписал»)
        считаем пропущенным только если pymorphy3 определяет его как имя
        собственное (имя/фамилия/отчество/топоним) — иначе это обычное слово,
        просто начало предложения, и список превратился бы в мусор.
        """
        if len(token) < 2 or not token[0].isupper():
            return
        if token.isupper() and len(token) <= 2:
            return  # инициалы «И», «В»
        parse = self.morph.best(token)
        if "Abbr" in parse.tag:
            return  # «США», «ООН» и т.п.

        i = start - 1
        while i >= 0 and text[i] in " \t":
            i -= 1
        sentence_start = i < 0 or text[i] in ".!?\n\r…:;"
        if sentence_start and not ({"Name", "Surn", "Patr", "Geox"} & set(parse.tag.grammemes)):
            return  # «Встречал», «Подписал» — обычные слова в начале предложения

        if token in seen:
            return
        seen.add(token)
        unknown.append(token)

    # ------------------------------------------------------------------ инициалы

    def _replace_initial(self, token: str) -> str | None:
        """«И.И.» → «С.С.»: каждый инициал, соответствующий имени в словаре,
        заменяем на первую букву замены этого имени.

        Детерминированность: среди ключей словаря, начинающихся на букву
        инициала и являющихся именами (тег Name), выбираем первый в
        алфавитном порядке.
        """
        if not any(ch in UPPER_INITIALS for ch in token):
            return None
        letter_map: dict[str, str | None] = {}
        changed = False
        for ch in token:
            if ch not in UPPER_INITIALS:
                continue
            low = ch.lower()
            if low not in letter_map:
                letter_map[low] = self._initial_for_letter(low)
            if letter_map[low] is not None:
                changed = True
        if not changed:
            return None
        out = []
        for ch in token:
            repl = letter_map.get(ch.lower())
            out.append(repl if (ch in UPPER_INITIALS and repl) else ch)
        return "".join(out)

    def _initial_for_letter(self, letter: str) -> str | None:
        candidates = sorted(
            k for k in self.mapping if k.startswith(letter) and self.morph.is_first_name(k)
        )
        if not candidates:
            return None
        replacement = self.mapping[candidates[0]]
        return replacement[0].upper() if replacement else None

    # ------------------------------------------------------------------ дефисы

    def _replace_hyphen(self, token: str) -> str | None:
        """Сначала пробуем сматчить всё слово целиком (напр. «Санкт-Петербург»
        целиком есть в словарях pymorphy), иначе заменяем части по отдельности
        в форме словаря (грамматика частей не восстанавливается надёжно)."""
        parse = self.morph.best(token)
        lemma = parse.normal_form.lower()
        if lemma in self.mapping:
            replacement = self.mapping[lemma]
            inflected = self._inflect_like(replacement, parse)
            return restore_capitalization(token, inflected)

        parts = token.split("-")
        new_parts: list[str] = []
        changed = False
        for part in parts:
            p_parse = self.morph.best(part)
            p_lemma = p_parse.normal_form.lower()
            if p_lemma in self.mapping:
                repl = self.mapping[p_lemma]
                new_parts.append(restore_capitalization(part, repl))
                changed = True
            else:
                new_parts.append(part)
        return "-".join(new_parts) if changed else None

    # ------------------------------------------------------------------ применение

    @staticmethod
    def _apply_spans(text: str, spans: list[tuple[int, int, str]]) -> str:
        if not spans:
            return text
        out: list[str] = []
        pos = 0
        for start, end, new in sorted(spans, key=lambda s: s[0]):
            out.append(text[pos:start])
            out.append(new)
            pos = end
        out.append(text[pos:])
        return "".join(out)

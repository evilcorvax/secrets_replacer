"""Тесты морфологической замены: склонения, регистр, дефисы, инициалы,
границы слов, детерминированность, список неизвестных."""
import pytest

from core.morphology import Morphology
from core.replacer import TextReplacer, restore_capitalization

MORPH = Morphology.shared()
IVANOV = {"иванов": "петров"}


def replacer(mapping=None):
    return TextReplacer(MORPH, mapping if mapping is not None else IVANOV)


# ------------------------------------------------------------------ склонения

class TestInflection:
    def test_dative_case(self):
        # Иванову передали → Петрову передали (дательный падеж)
        assert replacer().replace_text("Иванову передали документы").text == "Петрову передали документы"

    def test_genitive_case(self):
        assert replacer().replace_text("нет Иванова").text == "нет Петрова"

    def test_instrumental_case(self):
        assert replacer().replace_text("с Ивановым").text == "с Петровым"

    def test_nominative(self):
        assert replacer().replace_text("Иванов подписал").text == "Петров подписал"

    def test_lower_case_middle(self):
        assert replacer().replace_text("встречал иванова").text == "встречал петрова"


# ------------------------------------------------------------------ регистр

class TestCase:
    def test_all_caps(self):
        assert replacer().replace_text("Встречал ИВАНОВА").text == "Встречал ПЕТРОВА"

    def test_sentence_start_capital(self):
        assert replacer().replace_text("Иванов ушёл").text == "Петров ушёл"

    def test_restore_capitalization_helper(self):
        assert restore_capitalization("ИВАНОВА", "петрова") == "ПЕТРОВА"
        assert restore_capitalization("Иванова", "петрова") == "Петрова"
        assert restore_capitalization("иванова", "петрова") == "петрова"


# ------------------------------------------------------------------ дефисы

class TestHyphen:
    def test_hyphen_whole_word(self):
        r = replacer({"санкт-петербург": "петроград"})
        out = r.replace_text("в Санкт-Петербурге встреча").text
        # либо целиком просклонялось, либо осталась форма словаря — главное, заменилось
        assert "Петроград" in out or "петроград" in out

    def test_hyphen_parts(self):
        r = replacer({"собирать": "молчать", "тянуть": "ждать"})
        assert r.replace_text("собирать-тянуть").text == "молчать-ждать"

    def test_hyphen_part_case(self):
        r = replacer({"санкт": "нижний", "петербург": "новгород"})
        assert r.replace_text("Санкт-Петербург").text == "Нижний-Новгород"


# ------------------------------------------------------------------ инициалы

class TestInitials:
    def test_initials_replaced_by_name(self):
        # имя «Иван» → «Сергей»: инициал И → С
        r = replacer({"иван": "сергей", "иванов": "петров"})
        assert r.replace_text("И.И. Иванов").text == "С.С. Петров"

    def test_initials_with_space(self):
        r = replacer({"иван": "сергей", "иванов": "петров"})
        assert r.replace_text("И. И. Иванов").text == "С. С. Петров"

    def test_initials_unknown_letter_kept(self):
        # буква «В» не соответствует ни одному имени в словаре — инициал не трогаем
        r = replacer({"иван": "сергей", "иванов": "петров"})
        assert r.replace_text("В.И. Иванов").text == "В.С. Петров"


# ------------------------------------------------------------------ границы

class TestBoundaries:
    def test_no_replace_inside_latin(self):
        assert replacer().replace_text("HelloИванов").text == "HelloИванов"

    def test_no_replace_glued_digits(self):
        assert replacer().replace_text("Иванов2").text == "Иванов2"

    def test_email_untouched(self):
        assert replacer().replace_text("пишите ivanov@mail.ru").text == "пишите ivanov@mail.ru"

    def test_numbers_untouched(self):
        assert replacer().replace_text("договор 123/45").text == "договор 123/45"


# ------------------------------------------------------------------ детерминированность

class TestDeterminism:
    def test_same_input_same_output(self):
        text = "Иванов дал Иванову документ Иванова."
        assert replacer().replace_text(text).text == replacer().replace_text(text).text

    def test_fixed_mapping(self):
        # одинаковый оригинал всегда даёт одинаковую замену
        assert replacer().replace_text("Иванов").text == "Петров"
        assert replacer().replace_text("Иванов").text == "Петров"


# ------------------------------------------------------------------ неизвестные слова

class TestUnknown:
    def test_unknown_capitalized_collected(self):
        result = replacer().replace_text("Иванов встретил Сидорова в Москве")
        assert "Сидорова" in result.unknown
        assert "Москве" in result.unknown
        assert "Иванов" not in result.unknown  # был заменён

    def test_unknown_skips_abbr(self):
        result = replacer().replace_text("в США Иванов")
        assert "США" not in result.unknown

    def test_unknown_skips_lowercase(self):
        result = replacer().replace_text("Иванов подписал договор")
        assert result.unknown == []

    def test_unknown_skips_sentence_start_verbs(self):
        # «Встречал» — глагол в начале предложения, не имя собственное
        result = replacer().replace_text("Иванова встретили. Встречал ИВАНОВА.")
        assert "Встречал" not in result.unknown

    def test_unknown_keeps_sentence_start_surnames(self):
        result = replacer().replace_text("подписан. Сидорова ушла")
        assert "Сидорова" in result.unknown


# ------------------------------------------------------------------ критерий приёмки №1 (текстовая часть)

class TestAcceptanceText:
    def test_acceptance_example(self):
        text = "Иванов подписал договор. Иванову передали документы. Встречал ИВАНОВА."
        assert replacer().replace_text(text).text == (
            "Петров подписал договор. Петрову передали документы. Встречал ПЕТРОВА."
        )

"""Тесты .txt: автодетект кодировок, сохранение исходной кодировки."""
import pytest

from core.txt_processor import detect_encoding, read_txt, write_txt


class TestDetect:
    def test_utf8(self):
        assert detect_encoding("привет".encode("utf-8")) == "utf-8"

    def test_utf8_bom(self):
        assert detect_encoding("привет".encode("utf-8-sig")) == "utf-8-sig"

    def test_utf16(self):
        assert detect_encoding("привет".encode("utf-16")) == "utf-16"

    def test_cp1251(self):
        assert detect_encoding("привет".encode("cp1251")) == "cp1251"


class TestRoundTrip:
    def test_utf8_roundtrip(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_bytes("Иванов подписал".encode("utf-8"))
        text, enc = read_txt(p)
        assert text == "Иванов подписал" and enc == "utf-8"
        out = tmp_path / "b.txt"
        write_txt(out, text + "!", enc)
        assert out.read_bytes() == "Иванов подписал!".encode("utf-8")

    def test_cp1251_preserved(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_bytes("Иванов подписал".encode("cp1251"))
        text, enc = read_txt(p)
        assert enc == "cp1251"
        out = tmp_path / "b.txt"
        write_txt(out, text.replace("Иванов", "Петров"), enc)
        assert out.read_bytes() == "Петров подписал".encode("cp1251")

    def test_utf16_preserved(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_bytes("Иванов подписал".encode("utf-16"))
        text, enc = read_txt(p)
        assert enc == "utf-16"
        out = tmp_path / "b.txt"
        write_txt(out, text, enc)
        assert out.read_bytes() == "Иванов подписал".encode("utf-16")

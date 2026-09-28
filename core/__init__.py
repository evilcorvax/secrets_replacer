from .morphology import Morphology
from .replacer import ReplaceResult, TextReplacer, restore_capitalization
from .dictionary import ReplacementDictionary, DictEntry, ImportReport
from .docx_processor import process_docx_file, process_document, replace_in_paragraph, extract_text
from .txt_processor import read_txt, write_txt, detect_encoding

__all__ = [
    "Morphology", "TextReplacer", "ReplaceResult", "restore_capitalization",
    "ReplacementDictionary", "DictEntry", "ImportReport",
    "process_docx_file", "process_document", "replace_in_paragraph", "extract_text",
    "read_txt", "write_txt", "detect_encoding",
]

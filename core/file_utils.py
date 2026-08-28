"""
core/file_utils.py
Fayl kengaytmasiga emas, balki HAQIQIY baytlar tarkibiga (magic number) qarab
fayl turini aniqlaydi. Bu foydalanuvchi noto'g'ri kengaytma bilan yuklagan
fayllarni ("kitob.pdf" deb nomlangan, lekin aslida .docx bo'lgan fayl kabi)
avtomatik tuzatish uchun ishlatiladi.
"""

import io
import zipfile


def sniff_file_type(data: bytes, fallback_ext: str = "") -> str:
    """
    Fayl baytlarining boshiga (magic number) qarab haqiqiy turini qaytaradi.
    Aniqlab bo'lmasa, fallback_ext (fayl nomidan olingan kengaytma) qaytariladi.
    """
    if not data:
        return fallback_ext.lower()

    if data[:4] == b"%PDF":
        return "pdf"

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    if data[:3] == b"\xff\xd8\xff":
        return "jpg"

    if data[:4] == b"PK\x03\x04":
        # ZIP-asosidagi format: oddiy .zip, yoki Office Open XML (docx/pptx/xlsx)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                if any(n.startswith("word/") for n in names):
                    return "docx"
                if any(n.startswith("ppt/") for n in names):
                    return "pptx"
                if any(n.startswith("xl/") for n in names):
                    return "xlsx"
        except zipfile.BadZipFile:
            pass
        return "zip"

    return fallback_ext.lower()
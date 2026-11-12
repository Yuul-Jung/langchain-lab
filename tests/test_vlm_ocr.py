"""제3장 vlm_ocr 오프라인 회귀 테스트 (LM Studio·Tesseract 불필요)."""
import base64
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import vlm_ocr


def tiny_png() -> bytes:
    def chunk(name, data):
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes((255, 128, 0)) * 4 for _ in range(4))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class PayloadTests(unittest.TestCase):
    def test_png_becomes_base64_data_uri(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "page.png"
            p.write_bytes(tiny_png())
            uri = vlm_ocr.image_data_uri(p)
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), tiny_png())

    def test_file_url_is_rejected_before_sending(self):
        with self.assertRaises(ValueError):
            vlm_ocr.build_payload("file:///home/user/page.png")

    def test_payload_has_text_then_image(self):
        content = vlm_ocr.build_payload("data:image/png;base64,AAAA")["messages"][0]["content"]
        self.assertEqual([c["type"] for c in content], ["text", "image_url"])


class ErrorExplanationTests(unittest.TestCase):
    def test_context_overflow(self):
        body = ('{"error":"... request (4100 tokens) exceeds the available context size '
                '(4096 tokens), try increasing it ... exceed_context_size_error"}')
        msg = vlm_ocr.explain_http_error(body)
        self.assertIn("4100", msg)
        self.assertIn("--context-length", msg)

    def test_file_url_error(self):
        msg = vlm_ocr.explain_http_error('{"error":"\'url\' field must be a base64 encoded image."}')
        self.assertIn("base64", msg)

    def test_broken_image(self):
        self.assertIn("손상", vlm_ocr.explain_http_error("Failed to load image or audio file"))


class CompareTests(unittest.TestCase):
    def test_identifier_extraction(self):
        ids = vlm_ocr.identifiers("EmbeddingModel 과 gpt-4o-mini, BM25 그리고 일반 word")
        self.assertEqual(ids, {"EmbeddingModel", "gpt-4o-mini", "BM25"})

    def test_ocr_misread_counts_as_similar(self):
        state, detail = vlm_ocr.check_term("QuestionAnswerAdvisor", "QuestionAnswerAdvisar 호출")
        self.assertEqual(state, "유사")
        self.assertIn("QuestionAnswerAdvisar", detail)

    def test_prefix_is_not_treated_as_typo(self):
        # 원문에 VectorStore만 있으면 PgVectorStore는 확인되지 않아야 한다.
        state, _ = vlm_ocr.check_term("PgVectorStore", "VectorStore 검색")
        self.assertEqual(state, "없음")

    def test_missed_excludes_ocr_misreads_of_vlm_terms(self):
        vlm = "OpenAI 의 gpt-4o-mini 를 호출"
        ocr = {"psm3": "OpenAl gpt-40-mini SearchRequest",
               "psm6": "OpenAl gpt-40-mini SearchRequest"}
        res = vlm_ocr.compare_page(vlm, ocr)
        self.assertEqual(res["missed"], ["SearchRequest"])
        self.assertTrue(all(r["confirmed"] for r in res["rows"]))

    def test_markdown_report(self):
        res = vlm_ocr.compare_page("ChatClient", {"psm6": "ChatClient"})
        md = vlm_ocr.render_markdown({116: res}, ["psm6"])
        self.assertIn("## 116쪽", md)
        self.assertIn("| `ChatClient` | 일치 | 확인 |", md)


if __name__ == "__main__":
    unittest.main()

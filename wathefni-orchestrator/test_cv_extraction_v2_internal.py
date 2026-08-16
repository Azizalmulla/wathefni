"""Tests for Wathefni internal V2 extractor + routing helpers."""

from __future__ import annotations

import unittest

import cv_extraction_v2 as cv2
import cv_extraction_v2_internal as internal


SAMPLE = """
Jane Doe
jane@example.com | +965 50000000 | Kuwait

Professional Summary
Results-oriented analyst with experience in finance operations.

Experience
Financial Analyst – Acme Corp
Jan 2020 – Present
- Built monthly forecasts
Accountant at Beta LLC
2018 – 2019
- Managed AP/AR

Education
Bachelor of Science in Accounting
Gulf University
2014 – 2018
GPA: 3.5/4.0

Skills
Excel, SQL, Python, Financial modeling

Languages: Arabic, English

Selected Publications & Reports
Market liquidity review 2023

Professional Development
Online Courses: IFRS Bootcamp

Awards
Dean List – Gulf University – 2018
"""


class InternalExtractorTests(unittest.TestCase):
    def test_outputs_v2_schema_sections(self):
        payload = internal.extract_internal_v2(extracted_text=SAMPLE)
        self.assertEqual(payload["schema_version"], "cv-extraction-v2")
        self.assertGreaterEqual(len(payload["employment"]), 2)
        self.assertGreaterEqual(len(payload["education"]), 1)
        self.assertTrue(any(s.get("name") == "Excel" for s in payload["skills"]))
        langs = [x.get("language") for x in payload["languages"]]
        self.assertTrue(any("Arabic" in (l or "") for l in langs))
        self.assertTrue(any("English" in (l or "") for l in langs))
        self.assertGreaterEqual(len(payload["publications"]), 1)
        self.assertGreaterEqual(len(payload["training_courses"]), 1)
        self.assertGreaterEqual(len(payload["awards_honors"]), 1)
        # Skills must not swallow publications.
        self.assertFalse(any("publication" in (s.get("name") or "").lower() for s in payload["skills"]))

    def test_semantic_heading_aliases(self):
        self.assertEqual(internal.classify_heading("Career History"), "employment")
        self.assertEqual(internal.classify_heading("Academic Background"), "education")
        self.assertEqual(internal.classify_heading("الجوائز"), "awards_honors")
        self.assertEqual(internal.classify_heading("Community Service"), "volunteer_work")
        self.assertEqual(internal.classify_heading("Professional Development"), "training_courses")

    def test_validate_internal_payload(self):
        payload = internal.extract_internal_v2(extracted_text=SAMPLE)
        result = cv2.validate_v2_payload(payload, source_text=SAMPLE)
        self.assertTrue(result["ok"])
        self.assertEqual(result["payload"]["schema_version"], "cv-extraction-v2")

    def test_force_internal_routing(self):
        run = cv2.run_v2_extraction(
            local_path=None,
            mime_type="text/plain",
            extracted_text=SAMPLE,
            force_internal=True,
        )
        self.assertEqual(run["path"], "wathefni_internal_fallback")
        self.assertEqual(run["extractor_version"], internal.INTERNAL_EXTRACTOR_VERSION)
        self.assertTrue(run["ok"])
        self.assertGreaterEqual(len(run["payload"]["employment"]), 2)

    def test_chat_model_is_pinned(self):
        self.assertNotIn("latest", cv2.MISTRAL_ANNOTATION_CHAT_MODEL)
        self.assertEqual(cv2.MISTRAL_OCR_MODEL_PIN, "mistral-ocr-4-0")


if __name__ == "__main__":
    unittest.main()

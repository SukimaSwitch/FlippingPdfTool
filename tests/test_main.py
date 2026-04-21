import unittest
from tempfile import NamedTemporaryFile

import fitz

from src.main import CandidateBlock, build_url_template, extract_sku, match_figures_to_descriptions, resolve_sku_text
from src.main import FigureMatch, add_links_to_pdf


class MainPipelineTests(unittest.TestCase):
    def test_build_url_template_from_domain(self) -> None:
        self.assertEqual(
            build_url_template("www.lillianvernon.com", None),
            "https://www.lillianvernon.com/sku/{sku}",
        )

    def test_extract_sku_prefers_labeled_value(self) -> None:
        text = "Holiday Plaid Kitchen Towels SKU: HPT-44218 only $19.99"
        self.assertEqual(extract_sku(text), "HPT-44218")

    def test_extract_sku_supports_alpha_code_before_price(self) -> None:
        text = "Hard leather cover. 456 pages. TRESBNDTAN $249.99"
        self.assertEqual(extract_sku(text), "TRESBNDTAN")

    def test_extract_sku_prefers_price_adjacent_code_over_no_noise(self) -> None:
        text = "TREASURED LANDS Eng Thanks - BM NO QTIVOND ... 12x10\". TRESBNDTAN $249.99"
        self.assertEqual(extract_sku(text), "TRESBNDTAN")

    def test_extract_sku_ignores_price_like_tokens(self) -> None:
        text = "Only $9.99 each or 3 for $25.00"
        self.assertIsNone(extract_sku(text))

    def test_resolve_sku_text_prefers_pdf_text(self) -> None:
        sku, source, selected_text = resolve_sku_text(
            "Beer tasting set 818394 $89.99",
            ["Beer tasting set 818934 $89.99"],
            ["Beer tasting set 818954 $89.99"],
        )
        self.assertEqual(sku, "818934")
        self.assertEqual(source, "pdf")
        self.assertEqual(selected_text, "Beer tasting set 818934 $89.99")

    def test_resolve_sku_text_uses_regional_ocr_before_page_ocr(self) -> None:
        sku, source, selected_text = resolve_sku_text(
            "Beer tasting set 818394 $89.99",
            [],
            ["Beer tasting set 818934 $89.99"],
        )
        self.assertEqual(sku, "818934")
        self.assertEqual(source, "regional-ocr")
        self.assertEqual(selected_text, "Beer tasting set 818934 $89.99")

    def test_match_figures_to_descriptions_prefers_nearby_text_with_sku(self) -> None:
        figure = CandidateBlock(
            block_id="figure-1",
            block_type="LAYOUT_FIGURE",
            text="",
            bbox={"Left": 0.10, "Top": 0.20, "Width": 0.25, "Height": 0.18},
            page_number=1,
        )
        nearby_description = CandidateBlock(
            block_id="text-1",
            block_type="LAYOUT_TEXT",
            text="Snowflake Tray Item 55281 only $24.99",
            bbox={"Left": 0.09, "Top": 0.39, "Width": 0.27, "Height": 0.05},
            page_number=1,
        )
        far_description = CandidateBlock(
            block_id="text-2",
            block_type="LAYOUT_TEXT",
            text="Unrelated gift basket Item 99881 only $39.99",
            bbox={"Left": 0.62, "Top": 0.14, "Width": 0.22, "Height": 0.06},
            page_number=1,
        )

        matches = match_figures_to_descriptions(
            page_index=0,
            figures=[figure],
            text_candidates=[far_description, nearby_description],
            url_template="https://example.com/products/{sku}",
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].sku, "55281")
        self.assertEqual(matches[0].url, "https://example.com/products/55281")

    def test_match_figures_to_descriptions_uses_each_description_once(self) -> None:
        figure_one = CandidateBlock(
            block_id="figure-1",
            block_type="LAYOUT_FIGURE",
            text="",
            bbox={"Left": 0.05, "Top": 0.05, "Width": 0.30, "Height": 0.20},
            page_number=1,
        )
        figure_two = CandidateBlock(
            block_id="figure-2",
            block_type="LAYOUT_FIGURE",
            text="",
            bbox={"Left": 0.05, "Top": 0.35, "Width": 0.30, "Height": 0.20},
            page_number=1,
        )
        text_one = CandidateBlock(
            block_id="text-1",
            block_type="LAYOUT_TEXT",
            text="American flag throw 819496 $69.99",
            bbox={"Left": 0.05, "Top": 0.27, "Width": 0.32, "Height": 0.04},
            page_number=1,
        )
        text_two = CandidateBlock(
            block_id="text-2",
            block_type="LAYOUT_TEXT",
            text="Craft beer flight set 818994 $89.99",
            bbox={"Left": 0.05, "Top": 0.57, "Width": 0.32, "Height": 0.04},
            page_number=1,
        )

        matches = match_figures_to_descriptions(
            page_index=0,
            figures=[figure_one, figure_two],
            text_candidates=[text_one, text_two],
            url_template="https://example.com/products/{sku}",
        )

        self.assertEqual([match.sku for match in matches], ["819496", "818994"])

    def test_add_links_to_pdf_includes_figure_and_description(self) -> None:
        doc = fitz.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((60, 60), "Sample catalog page")

        links_added = add_links_to_pdf(
            doc,
            [
                FigureMatch(
                    page_index=0,
                    figure_bbox={"Left": 0.10, "Top": 0.15, "Width": 0.20, "Height": 0.18},
                    description_text="Snowflake Tray Item 55281 only $24.99",
                    description_bbox={"Left": 0.09, "Top": 0.36, "Width": 0.28, "Height": 0.05},
                    sku="55281",
                    url="https://example.com/products/55281",
                    score=2.1,
                )
            ],
        )

        with NamedTemporaryFile(suffix=".pdf") as temp_file:
            doc.save(temp_file.name)
            doc.close()
            reopened = fitz.open(temp_file.name)
            links = list(reopened[0].get_links())

            self.assertEqual(links_added, 2)
            self.assertEqual(len(links), 2)
            self.assertEqual({link["uri"] for link in links}, {"https://example.com/products/55281"})

            link_rects = {
                tuple(round(value, 2) for value in (link["from"].x0, link["from"].y0, link["from"].x1, link["from"].y1))
                for link in links
            }
            self.assertEqual(
                link_rects,
                {
                    (60.0, 120.0, 180.0, 264.0),
                    (54.0, 288.0, 222.0, 328.0),
                },
            )
            reopened.close()


if __name__ == "__main__":
    unittest.main()
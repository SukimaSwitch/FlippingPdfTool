# FlippingPdfTool

A Python CLI application that renders catalog PDFs to JPG, identifies product figures and nearby descriptions, extracts SKUs, and adds product links back onto the figure regions in the PDF.

The pipeline now processes one page at a time, prints a live progress bar in the terminal, and can resume previously completed pages from saved page summaries.

## Installation

1. Clone the repository:
	```bash
	git clone https://github.com/SukimaSwitch/FlippingPdfTool.git
	```
2. Navigate to the project directory:
	```bash
	cd FlippingPdfTool
	```
3. Install dependencies with `pip install -r requirements.txt`.
4. Configure AWS credentials with permission to call Amazon Textract.
5. Optionally set `AWS_REGION`, `TEXTRACT_ADAPTER_ID`, and `TEXTRACT_ADAPTER_VERSION`.

## Usage

Run the pipeline with a PDF URL or a local PDF path:

```bash
python src/main.py "https://example.com/catalog.pdf" --domain www.lillianvernon.com --debug-overlays
```

For larger PDFs, process a bounded page range and keep the run resumable:

```bash
python src/main.py "/home/xzhang/Workspace/Temp/Current Spring 2026 Sale.pdf" --domain www.lillianvernon.com --page-start 1 --page-end 25 --skip-existing
```

You can also let the script prompt for the PDF input:

```bash
python src/main.py
```

## CLI Options

- `--domain`: Destination domain used to build product URLs as `https://<domain>/sku/<sku>`. Default: `www.currentcatalog.com`
- `--output-dir`: Directory where rendered page images and the linked PDF are written. Default: `extracted_images`
- `--figure-info-dir`: Directory where Textract JSON, overlays, and run summaries are written. Default: `figure_info`
- `--dpi`: Render DPI for the intermediate JPG files. Default: `220`
- `--url-template`: Optional full product URL template that must contain `{sku}`. If set, it overrides `--domain`
- `--aws-region`: AWS region for Textract
- `--textract-adapter-id`: Optional Textract adapter ID
- `--textract-adapter-version`: Optional Textract adapter version
- `--page-start`: First 1-based page number to process. Default: `1`
- `--page-end`: Last 1-based page number to process. Default: process through the final page
- `--max-pages`: Maximum number of pages to process after the page range is applied
- `--resume-run-id`: Resume a previous run directory by ID
- `--skip-existing`: Restore completed pages from existing per-page summaries instead of reprocessing them
- `--keep-rendered-pages`: Keep intermediate rendered JPG files after each page is processed
- `--textract-retries`: Retry count for Textract requests. Default: `3`
- `--debug-overlays`: Writes annotated JPG overlays that show figure and description matches

## Output

Each run creates a unique subdirectory under `extracted_images/` and `figure_info/` unless `--resume-run-id` is used.

- Rendered page JPG files are written to `extracted_images/<run-id>/pages/` when `--keep-rendered-pages` or `--debug-overlays` is enabled
- The linked PDF is written to `extracted_images/<run-id>/linked_<input-name>.pdf`
- Per-page Textract responses are written to `figure_info/<run-id>/page_###_textract.json`
- Per-page processing summaries are written to `figure_info/<run-id>/page_###_summary.json`
- Match details and counts are written to `figure_info/<run-id>/run_summary.json`
- If `--debug-overlays` is enabled, annotated page overlays are written to `figure_info/<run-id>/page_###_overlay.jpg`

## Notes

- The pipeline matches `LAYOUT_FIGURE` blocks to nearby `LAYOUT_TEXT`, `LAYOUT_TITLE`, and `LAYOUT_LIST` blocks using page geometry.
- SKU extraction first tries PDF-native text from the matched page region and falls back to OCR text when the PDF has no selectable text.
- For image-only PDFs, the pipeline performs a second-pass regional OCR on high-DPI crops around each matched description to improve SKU accuracy.
- SKU extraction is regex-based and can be tuned in `src/main.py` if your catalog format differs.
- If Textract does not return figure blocks for a page, the script falls back to OpenCV-based image region detection.
- Textract calls are retried automatically up to the configured retry limit.
- The terminal prints a live page progress bar with cumulative match and link counts.
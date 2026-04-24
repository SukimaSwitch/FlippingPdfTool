- [x] Verify that the copilot-instructions.md file in the .github directory is created.

- [x] Clarify Project Requirements

- [x] Scaffold the Project

- [x] Customize the Project

- [x] Install Required Extensions

- [x] Compile the Project

- [x] Create and Run Task

- [x] Launch the Project

- [x] Ensure Documentation is Complete

- Work through each checklist item systematically.
- Keep communication concise and focused.
- Follow development best practices.

## Active Technologies
- Python 3.14 container runtime for the worker and helper entrypoints + boto3, requests, PyMuPDF, Pillow, OpenCV, NumPy, AWS Textract, AWS Step Functions, ECS/Fargate, SES or SNS, Secrets Manager (001-automate-pdf-linking)
- Amazon S3 for source/output PDFs and processing artifacts, DynamoDB for durable processing-job state, local ephemeral container storage for intermediate page images (001-automate-pdf-linking)

## Recent Changes
- 001-automate-pdf-linking: Added Python 3.14 container runtime for the worker and helper entrypoints + boto3, requests, PyMuPDF, Pillow, OpenCV, NumPy, AWS Textract, AWS Step Functions, ECS/Fargate, SES or SNS, Secrets Manager

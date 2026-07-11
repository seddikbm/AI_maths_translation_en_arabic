# MathTrans

MathTrans is an English <-> Arabic mathematical translation system. It combines a fine-tuned Meta NLLB model, LaTeX-aware preprocessing, OCR-based PDF extraction, a FastAPI backend, and a React/Vite frontend.

The goal is to translate mathematical text and PDF documents while preserving equations, symbols, and LaTeX-like expressions.

## Features

- Text translation in both directions: English to Arabic and Arabic to English.
- PDF translation with embedded-text extraction and OCR fallback.
- LaTeX/math protection using placeholders such as `<MATH_0>`.
- Local model inference with a fine-tuned NLLB-200 1.3B model.
- Optional OpenAI translation backend for comparison or fallback.
- React interface with text mode, PDF upload, progress display, preview, and download.
- Docker Compose setup for backend and frontend.

## Project Structure

```text
.
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- config.py
|   |   |-- routers/
|   |   |-- services/
|   |   `-- utils/
|   |-- tests/
|   |-- Dockerfile
|   `-- requirements.txt
|-- data/
|   |-- phase1_final_dataset.jsonl
|   `-- phase2_latex_dataset.jsonl
|-- frontend/
|   |-- src/
|   |-- Dockerfile
|   |-- package.json
|   `-- vite.config.ts
|-- MathTrans_Phase1_and_Phase2.ipynb
|-- scrape_arxiv_math.py
|-- docker-compose.yml
|-- requirements.txt
`-- README.md
```

Model weights are expected outside this inner project folder:

```text
../models/
|-- phase2_final/
`-- nougat/
```

This matches the Docker Compose volume:

```yaml
../models:/app/models
```

## Main Components

### Backend

The backend is a FastAPI service.

Important files:

- `backend/app/main.py`: FastAPI app, CORS, router registration, health endpoint.
- `backend/app/routers/translate.py`: text translation endpoint.
- `backend/app/routers/document.py`: PDF translation endpoint.
- `backend/app/services/model_service.py`: local, OpenAI, and mock translation backends.
- `backend/app/services/ocr_service.py`: embedded PDF text extraction, Nougat OCR, and Tesseract fallback.
- `backend/app/services/latex_handler.py`: protects and restores math expressions.
- `backend/app/services/pdf_builder.py`: builds translated PDF output.

API endpoints:

```text
GET  /health
POST /api/translate
POST /api/translate/document
```

### Frontend

The frontend is a Vite + React + TypeScript app.

Important files:

- `frontend/src/App.tsx`: main workspace and mode switch.
- `frontend/src/components/TextTranslator.tsx`: text translation panel.
- `frontend/src/components/DocumentTranslator.tsx`: PDF upload panel.
- `frontend/src/components/ResultViewer.tsx`: translated text/PDF preview.
- `frontend/src/services/api.ts`: API calls.

### Training And Data

The training notebook is:

```text
MathTrans_Phase1_and_Phase2.ipynb
```

It documents a phase-based strategy:

1. Phase 1: fine-tune on general English-Arabic mathematical sentence pairs.
2. Phase 2: continue domain adaptation with LaTeX-placeholder data.

The scraper:

```text
scrape_arxiv_math.py
```

collects arXiv mathematical content, extracts LaTeX-aware segments, replaces math with placeholders, translates with OpenAI, validates output, and writes bilingual JSONL pairs.

## Requirements

### Docker

Recommended for running the full app:

- Docker
- Docker Compose

### Local Development

Backend:

- Python 3.11 or newer recommended
- Tesseract installed locally if testing scanned-PDF OCR outside Docker

Frontend:

- Node.js 22 or compatible
- npm

The current frontend has `node_modules` installed locally, but it is ignored by git and should be reinstalled after cloning.

## Environment Variables

Common backend variables:

```env
TRANSLATION_BACKEND=local
MODEL_PATH=/app/models/phase2_final
MODEL_NAME=facebook/nllb-200-1.3B
NOUGAT_MODEL_NAME=/app/models/nougat
ARABIC_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
CORS_ORIGINS=http://localhost:3000
MAX_PDF_PAGES=25
```

Optional OpenAI backend:

```env
TRANSLATION_BACKEND=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

Supported translation backends:

- `local`: uses the fine-tuned local NLLB model.
- `openai`: uses the OpenAI API.
- `mock`: returns predictable mock translations for tests.
- `auto`: currently resolves to local inference.

Do not commit `.env` files.

## Run With Docker Compose

From the project root:

```powershell
docker compose up --build
```

Then open:

```text
Frontend: http://localhost:3000
Backend:  http://localhost:8000
Health:   http://localhost:8000/health
```

The backend container expects model files at:

```text
../models/phase2_final
../models/nougat
```

## Run Locally

### Backend

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Run the API:

```powershell
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

For quick local testing without loading the large model:

```powershell
$env:TRANSLATION_BACKEND="mock"
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open:

```text
http://localhost:3000
```

Use `npm.cmd` on Windows PowerShell to avoid execution-policy issues with `npm.ps1`.

## API Examples

Text translation:

```powershell
Invoke-RestMethod `
  -Uri http://localhost:8000/api/translate `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"text":"If $x > 0$, then $x^2 > 0$.","direction":"en2ar"}'
```

PDF translation is available through the frontend, or by sending multipart form data to:

```text
POST /api/translate/document
```

Required form fields:

- `file`: PDF upload.
- `direction`: `en2ar` or `ar2en`.

## Testing

Backend tests:

```powershell
python -m pytest backend\tests -q
```

Frontend production build:

```powershell
cd frontend
npm.cmd run build
```

Current verification status:

- Backend tests pass.
- Frontend build passes.

## Dataset Generation

To generate or extend Phase 2 data, configure an OpenAI API key in `.env`, then run:

```powershell
python scrape_arxiv_math.py `
  --output data/phase2_latex_dataset.jsonl `
  --max-papers 150 `
  --max-pairs 20000 `
  --openai-model gpt-4o-mini
```

The scraper uses arXiv/ar5iv HTML when available and falls back to arXiv source extraction. It keeps only records with math placeholders and writes bidirectional pairs.

## Model Notes

The local translation model is a fine-tuned NLLB-200 1.3B model saved in Hugging Face format.

Expected local model folder:

```text
../models/phase2_final
```

Expected OCR model folder:

```text
../models/nougat
```

Model weights are large and should not be committed directly to git. Use external storage, release artifacts, Hugging Face Hub, or Git LFS if model versioning is required.

## GitHub Setup

If this folder is not already its own git repository:

```powershell
git init
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git checkout -b codex/mathtrans-current-version
git add .
git commit -m "Add MathTrans current version"
git push -u origin codex/mathtrans-current-version
```

Before committing, check what will be staged:

```powershell
git status --short
```

Make sure `.env`, model weights, `node_modules`, build output, and cache folders are not included.

## Known Notes

- Local CPU inference with the 1.3B model can be slow and memory-heavy.
- Scanned Arabic PDFs rely on Tesseract OCR fallback.
- Scientific English PDFs may use Nougat OCR when embedded text is unavailable.
- The project data files are included in `data/`; model weights are not.
- PowerShell may display Arabic text incorrectly in the terminal even when files are valid UTF-8.

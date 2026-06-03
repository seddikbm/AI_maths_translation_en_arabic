# MathTrans — Implementation Task Tracker

## Phase 1: Supplementary Training Notebook
- `[x]` Create `MathTrans_Phase1_Clean.ipynb` - continue training from Phase 1 final model on `dataset_cleaned.jsonl`
  - `[x]` Install deps, mount drive, setup
  - `[x]` Load dataset + inspect 3 random examples
  - `[x]` Load Phase 1 final model + apply fresh LoRA
  - `[x]` Tokenize + inspect
  - `[x]` Training loop (all checkpoints, predict_with_generate=True)
  - `[x]` Cell 7: 3 random examples comparison (base vs fine-tuned)
  - `[x]` Cell 8: Per-checkpoint chrF++/BLEU bar chart (100 examples, train & val separately)
  - `[x]` Cell 9: Training curves (loss, val loss, chrF++, BLEU)

## Phase 2: ArXiv Scraping Pipeline
- `[x]` Create `scrape_arxiv_math.py` - LangGraph agent for ar5iv HTML scraping
  - `[x]` ArXiv search + HTML fetch
  - `[x]` LaTeX placeholder replacement
  - `[x]` GPT-4o-mini translation
  - `[x]` Bilingual pair formatting
  - `[x]` Target: 15K-20K pairs

## Phase 3: Phase 2 Training Notebook
- `[x]` Create `MathTrans_Phase2_LaTeX.ipynb`
  - `[x]` Load Phase 1 supplementary model
  - `[x]` Train on LaTeX-placeholder data
  - `[x]` 3 examples output comparison
  - `[x]` Per-checkpoint chrF++/BLEU (100 examples)
  - `[x]` Training curves

## Phase 4: FastAPI Backend
- `[x]` Create backend structure
  - `[x]` main.py, config, routers
  - `[x]` model_service.py (translation)
  - `[x]` ocr_service.py (Nougat EN + Tesseract AR)
  - `[x]` latex_handler.py
  - `[x]` pdf_builder.py
  - `[x]` Dockerfile

## Phase 5: React + TypeScript Frontend
- `[x]` Create frontend with Vite + React + TS
  - `[x]` Components
  - `[x]` API integration
  - `[x]` Modern UI
  - `[x]` Dockerfile

## Phase 6: Docker Compose + Integration
- `[x]` docker-compose.yml
- `[x]` Updated requirements.txt

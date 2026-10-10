# Smart Waste

Smart Waste is a five-page, responsive waste-guidance site built with plain HTML, CSS, and JavaScript, plus a FastAPI service for image analysis. A vision model describes the item and visible condition; a separate JSON-backed decision engine turns that description into a reasoned disposal suggestion.

## Project layout

```text
frontend/
  index.html
  explore.html
  how-it-works.html
  about.html
  faqs.html
  style.css
  script.js
  assets/tree-canopy.jpg
backend/
  main.py
  decision_engine.py
  waste_rules.json
  requirements.txt
```

## Run locally on Windows

From the project root, create an environment and install the backend dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
```

Enter a vision API key into the current PowerShell session and start the server:

```powershell
$env:VISION_API_KEY = Read-Host "Vision API key"
.\.venv\Scripts\python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The FastAPI app serves the frontend and `/api/analyze` from the same origin. API reference documentation is available at `/api/docs` while the server is running.

## Vision provider settings

The server uses a Chat Completions-compatible vision endpoint. `VISION_API_KEY` is required and stays on the backend. The default endpoint is `https://api.openai.com/v1/chat/completions`, and the default model is `gpt-6-astra`. Set these process environment variables before starting the server to use another compatible provider or model:

- `VISION_API_URL`: full Chat Completions endpoint URL
- `VISION_MODEL`: vision-capable model name
- `SMART_WASTE_MAX_IMAGE_BYTES`: upload limit in bytes; defaults to 8 MiB

The provider must accept image data URLs and return a JSON object with `item`, `material`, `condition`, and `confidence` (`high`, `medium`, or `low`). The API sends images only to fulfill the scan request, keeps no image archive, and relies on the selected provider’s own processing and retention terms.

## Before public deployment

Serve the app behind HTTPS, store the provider key in your hosting platform’s secret manager, and configure request rate limits and spend limits at the edge. Review `backend/waste_rules.json` against the municipalities and collection services you intend to support; the included rules are general guidance and deliberately ask users to confirm local acceptance.

"""Smart Waste API and static site server."""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError

from decision_engine import recommend_disposal

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MAX_IMAGE_BYTES = int(os.getenv("SMART_WASTE_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MIME_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class VisionFinding(BaseModel):
    item: str = Field(min_length=1, max_length=120)
    material: str = Field(min_length=1, max_length=120)
    condition: str = Field(min_length=1, max_length=160)
    confidence: Literal["high", "medium", "low"]


class AnalysisResult(VisionFinding):
    context: str
    recommendation: str
    reason: str
    preparation: str
    needs_review: bool


def _vision_configuration() -> tuple[str, str, str]:
    api_key = os.getenv("VISION_API_KEY", "").strip()
    endpoint = os.getenv("VISION_API_URL", "https://api.openai.com/v1/chat/completions").strip()
    model = os.getenv("VISION_MODEL", "gpt-6-astra").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Image analysis is not configured yet. Add VISION_API_KEY to the backend environment and restart the server.",
        )
    return api_key, endpoint, model


async def _identify_image(image_bytes: bytes, content_type: str) -> VisionFinding:
    api_key, endpoint, model = _vision_configuration()
    encoded = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "Inspect the uploaded waste item. Identify only what is visually supported by the image. "
        "Return one JSON object with exactly these string fields: item, material, condition, confidence. "
        "Use a short everyday item name, the most likely material (say mixed or unknown when needed), "
        "and a visible condition such as empty and clean, food-contaminated, damaged, or full. "
        "Do not guess hidden contents, recycling rules, or a location-specific disposal decision. "
        "Set confidence to high, medium, or low based on how clearly one item and its material can be seen. "
        "If the image is not a waste item or is too unclear, use item 'Unclear item', material 'Unknown', "
        "condition 'Not clear from the image', and confidence 'low'."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a careful visual waste-item identifier. Return valid JSON only."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}},
                ],
            },
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=8.0)) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            provider_body = response.json()
            content = provider_body["choices"][0]["message"]["content"]
            print("Gemini response content type:", type(content).__name__)
        print("Gemini response content:", repr(content)[:1000])
        finding_data = json.loads(content)
        return VisionFinding.model_validate(finding_data)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="The image analysis service took too long. Please try again.") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise HTTPException(status_code=503, detail="Image analysis is busy right now. Please try again shortly.") from exc
        print("Gemini API error:", exc.response.status_code, repr(exc.response.text[:1000]))
        raise HTTPException(status_code=502, detail="The image analysis service could not complete this scan.") from exc
    except (httpx.RequestError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="The image analysis service returned an unusable result. Please try again.") from exc


app = FastAPI(
    title="Smart Waste API",
    description="Visual waste identification with transparent, rule-based disposal guidance.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)
app.add_middleware(GZipMiddleware, minimum_size=900)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "smart-waste",
        "vision_configured": "true" if os.getenv("VISION_API_KEY", "").strip() else "false",
    }


@app.post("/api/analyze", response_model=AnalysisResult)
async def analyze_image(
    image: UploadFile = File(..., description="A JPG, PNG, or WEBP image of one waste item"),
    context: str = Form("Not sure"),
) -> AnalysisResult:
    content_type = (image.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Choose a JPG, PNG, or WEBP image.")

    try:
        image_bytes = await image.read(MAX_IMAGE_BYTES + 1)
    finally:
        await image.close()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="The selected image is empty.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Choose an image smaller than 8 MB.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as uploaded_image:
            if uploaded_image.format != MIME_FORMATS[content_type]:
                raise HTTPException(status_code=415, detail="The image contents do not match the selected file type.")
            uploaded_image.verify()
        with Image.open(io.BytesIO(image_bytes)) as uploaded_image:
            if uploaded_image.width * uploaded_image.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="This image has too many pixels. Please choose a smaller image.")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail="That file could not be read as a valid image.") from exc

    finding = await _identify_image(image_bytes, content_type)
    guidance = recommend_disposal(
        item=finding.item,
        material=finding.material,
        condition=finding.condition,
        context=context[:80],
        confidence=finding.confidence,
    )
    return AnalysisResult(**(finding.model_dump() | guidance))


if not FRONTEND.is_dir():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND}")

app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")

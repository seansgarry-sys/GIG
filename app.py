from __future__ import annotations

import io
import json
import shutil
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus, urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.middleware.sessions import SessionMiddleware

from config import FILTER_STATUSES, VALID_STATUSES, settings
from database import (
    clear_requests,
    delete_gallery_image,
    delete_request,
    get_stats,
    init_db,
    insert_gallery_image,
    insert_request,
    list_gallery_images,
    list_requests,
    update_request_status,
)

BASE_DIR = Path(__file__).resolve().parent
SOURCE_MEDIA_DIR = BASE_DIR / "media"
SOURCE_GALLERY_DIR = SOURCE_MEDIA_DIR / "gallery"
MEDIA_DIR = settings.data_dir / "media"
GALLERY_DIR = MEDIA_DIR / "gallery"
settings.data_dir.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)
GALLERY_DIR.mkdir(parents=True, exist_ok=True)

LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "0.0.0.0"}


def format_datetime(value: str | None) -> str:
    if not value:
        return ""

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value

    return parsed.strftime("%b %d, %I:%M %p").replace(" 0", " ")


def format_currency(value: float | int | None) -> str:
    if value in (None, ""):
        return "$0"

    amount = float(value)
    if amount.is_integer():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def normalize_filter(status_value: str | None) -> str:
    if status_value in VALID_STATUSES:
        return status_value
    return "All"


def normalized_public_url(url: str) -> str:
    return f"{url.rstrip('/')}/"


def is_local_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in LOCAL_HOSTNAMES


def public_home_url(request: Request | None = None) -> str:
    configured_url = settings.base_url.strip()

    if request is not None:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").strip()
        forwarded_host = request.headers.get("x-forwarded-host", "").strip()
        request_scheme = forwarded_proto or request.url.scheme
        request_host_value = forwarded_host or request.headers.get("host", "") or request.url.netloc
        request_url = f"{request_scheme}://{request_host_value}/" if request_host_value else str(request.url_for("home"))
        request_host = (request.url.hostname or "").lower()

        if configured_url and not is_local_url(configured_url):
            return normalized_public_url(configured_url)

        if configured_url and is_local_url(configured_url) and request_host not in LOCAL_HOSTNAMES:
            return normalized_public_url(request_url)

        if configured_url:
            return normalized_public_url(configured_url)

        return normalized_public_url(request_url)

    if configured_url:
        return normalized_public_url(configured_url)

    return "http://127.0.0.1:8000/"


def public_path_url(request: Request, path: str) -> str:
    return f"{public_home_url(request).rstrip('/')}{path}"


def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin"))


def fallback_gallery_filenames(limit: int = 6) -> list[str]:
    candidates: dict[str, Path] = {}

    for directory in (GALLERY_DIR, SOURCE_GALLERY_DIR):
        if not directory.exists():
            continue

        for file_path in directory.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            candidates[file_path.name] = file_path

    ordered = sorted(
        candidates.values(),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [path.name for path in ordered[:limit]]


def public_background_images(limit: int = 6) -> list[dict[str, Any]]:
    images = list_gallery_images(limit=limit)
    if images:
        return images

    return [
        {
            "filename": filename,
            "original_name": filename,
            "created_at": "",
        }
        for filename in fallback_gallery_filenames(limit=limit)
    ]


def background_image_urls(request: Request, limit: int = 6) -> list[str]:
    return [
        f"/media/gallery/{quote(image['filename'])}"
        for image in public_background_images(limit=limit)
    ]


def bootstrap_gallery_images() -> None:
    if not SOURCE_GALLERY_DIR.exists():
        return

    existing_images = {image["filename"] for image in list_gallery_images(limit=None)}
    copy_to_data_dir = settings.data_dir.resolve() != BASE_DIR.resolve()

    for source_file in SOURCE_GALLERY_DIR.iterdir():
        if not source_file.is_file():
            continue

        if source_file.name in existing_images:
            continue

        if copy_to_data_dir:
            destination = GALLERY_DIR / source_file.name
            if not destination.exists():
                shutil.copy2(source_file, destination)

        insert_gallery_image(filename=source_file.name, original_name=source_file.name)
        existing_images.add(source_file.name)


def ultimate_guitar_search_url(song_title: str, artist: str = "") -> str:
    query = " ".join(part for part in [song_title.strip(), artist.strip(), "ultimate guitar chords"] if part)
    return f"https://www.ultimate-guitar.com/search.php?search_type=title&value={quote_plus(query)}"


def booking_context(
    request: Request,
    *,
    error: str | None = None,
    form_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    web3forms_enabled = bool(settings.web3forms_access_key)
    return {
        "request": request,
        "error": error,
        "form_values": form_values or {},
        "web3forms_enabled": web3forms_enabled,
        "web3forms_access_key": settings.web3forms_access_key,
        "booking_form_action": "https://api.web3forms.com/submit" if web3forms_enabled else "/api/booking/new",
        "booking_success_url": public_path_url(request, "/book/success"),
    }


def build_booking_message(
    *,
    contact_name: str,
    contact_email: str,
    contact_phone: str,
    event_date: str,
    venue_location: str,
    budget: str,
    event_details: str,
) -> str:
    return "\n".join(
        [
            f"New booking inquiry for {settings.performer_name}",
            "",
            f"Contact name: {contact_name}",
            f"Contact email: {contact_email}",
            f"Phone: {contact_phone or 'Not provided'}",
            f"Event date: {event_date or 'Not provided'}",
            f"Venue / city: {venue_location}",
            f"Budget: {budget or 'Not provided'}",
            "",
            "Event details:",
            event_details,
        ]
    )


def send_booking_email(
    *,
    contact_name: str,
    contact_email: str,
    contact_phone: str,
    event_date: str,
    venue_location: str,
    budget: str,
    event_details: str,
) -> None:
    if settings.web3forms_access_key:
        web3forms_payload = {
            "access_key": settings.web3forms_access_key,
            "subject": settings.booking_subject,
            "from_name": f"{settings.performer_name} Booking Form",
            "email": contact_email,
            "replyto": contact_email,
            "contact_name": contact_name,
            "contact_phone": contact_phone or "Not provided",
            "event_date": event_date or "Not provided",
            "venue_location": venue_location,
            "budget": budget or "Not provided",
            "event_details": event_details,
        }
        request = UrlRequest(
            "https://api.web3forms.com/submit",
            data=urlencode(web3forms_payload).encode("utf-8"),
            headers={"Accept": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=20) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            message = "That booking request did not send cleanly. Please try again in a moment."
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
                message = error_body.get("body", {}).get("message") or error_body.get("message") or message
            except Exception:
                pass
            raise RuntimeError(message) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("That booking request did not send cleanly. Please try again in a moment.") from exc

        if not response_body.get("success", False):
            message = response_body.get("body", {}).get("message") or response_body.get("message") or "That booking request did not send cleanly. Please try again in a moment."
            raise RuntimeError(message)

        return

    required_settings = [
        settings.smtp_host,
        settings.smtp_username,
        settings.smtp_password,
        settings.smtp_from_email,
    ]
    if not all(required_settings):
        raise RuntimeError(
            f"Booking requests are almost ready. For now, please email me directly at {settings.booking_email}."
        )

    message = EmailMessage()
    message["Subject"] = settings.booking_subject
    message["From"] = settings.smtp_from_email
    message["To"] = settings.booking_email
    message["Reply-To"] = contact_email
    message.set_content(
        build_booking_message(
            contact_name=contact_name,
            contact_email=contact_email,
            contact_phone=contact_phone,
            event_date=event_date,
            venue_location=venue_location,
            budget=budget,
            event_details=event_details,
        )
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_use_tls:
                server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except smtplib.SMTPException as exc:
        raise RuntimeError(
            f"That one did not send cleanly. Please try again or email me directly at {settings.booking_email}."
        ) from exc


async def save_gallery_upload(upload: UploadFile) -> tuple[str, str]:
    original_name = upload.filename or "gig-photo"

    try:
        image = Image.open(upload.file)
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a valid JPG, PNG, or WEBP image.",
        ) from exc

    image.thumbnail((2200, 2200))
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:10]}.jpg"
    destination = GALLERY_DIR / filename
    image.save(destination, format="JPEG", quality=88, optimize=True)
    await upload.close()

    return filename, original_name


def remove_gallery_file(filename: str) -> None:
    gallery_root = GALLERY_DIR.resolve()
    target = (gallery_root / filename).resolve()
    if gallery_root not in target.parents:
        return
    if target.exists():
        target.unlink()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        stale_connections: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(payload)
            except Exception:
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(connection)


manager = ConnectionManager()
app = FastAPI(title=settings.site_title)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals.update(
    site_title=settings.site_title,
    performer_name=settings.performer_name,
    asset_version=settings.asset_version,
    venmo_url=settings.venmo_url,
    instagram_url=settings.instagram_url,
    booking_email=settings.booking_email,
    booking_subject=settings.booking_subject,
    ultimate_guitar_search_url=ultimate_guitar_search_url,
)
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["currency"] = format_currency


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    bootstrap_gallery_images()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "background_urls": background_image_urls(request),
        },
    )


@app.get("/request", response_class=HTMLResponse)
async def request_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "request.html",
        {
            "request": request,
            "background_urls": background_image_urls(request),
        },
    )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/book", response_class=HTMLResponse)
async def book_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "book.html", booking_context(request))


@app.get("/request/success", response_class=HTMLResponse)
async def request_success(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "request_success.html", {"request": request})


@app.get("/book/success", response_class=HTMLResponse)
async def book_success(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "book_success.html", {"request": request})


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if is_admin(request):
        return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(request, "admin_login.html", {"request": request, "error": None})


@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request, password: str = Form(...)):
    if password == settings.admin_password:
        request.session["is_admin"] = True
        return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "admin_login.html",
        {"request": request, "error": "Incorrect password. Try again."},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@app.get("/admin/logout")
async def admin_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    active_filter = normalize_filter(status_filter)
    selected_status = None if active_filter == "All" else active_filter
    requests = list_requests(selected_status)
    stats = get_stats()

    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "request": request,
            "requests": requests,
            "stats": stats,
            "filters": FILTER_STATUSES,
            "active_filter": active_filter,
            "visible_count": len(requests),
            "gallery_images": list_gallery_images(limit=12),
        },
    )


@app.get("/api/requests")
async def api_requests(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
) -> JSONResponse:
    if not is_admin(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    active_filter = normalize_filter(status_filter)
    selected_status = None if active_filter == "All" else active_filter
    return JSONResponse(
        {
            "requests": list_requests(selected_status),
            "stats": get_stats(),
            "active_filter": active_filter,
        }
    )


@app.post("/api/request/new")
async def api_new_request(
    request: Request,
    requester_name: str = Form(...),
    song_title: str = Form(...),
    artist: str = Form(""),
    note: str = Form(""),
    claimed_tip_amount: str = Form(""),
):
    requester_name = requester_name.strip()
    song_title = song_title.strip()
    artist = artist.strip()
    note = note.strip()

    if not requester_name or not song_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requester name and song title are required.",
        )

    tip_amount: float | None = None
    if claimed_tip_amount.strip():
        try:
            tip_amount = round(float(claimed_tip_amount), 2)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Claimed tip amount must be a number.",
            ) from exc
        if tip_amount < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Claimed tip amount cannot be negative.",
            )

    created_request = insert_request(
        requester_name=requester_name,
        song_title=song_title,
        artist=artist,
        note=note,
        claimed_tip_amount=tip_amount,
    )
    await manager.broadcast({"type": "refresh", "request_id": created_request["id"]})

    wants_json = "application/json" in request.headers.get("accept", "").lower()
    if wants_json:
        return JSONResponse({"ok": True, "request": created_request}, status_code=status.HTTP_201_CREATED)

    return RedirectResponse("/request/success", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/api/request/{request_id}/status")
async def api_update_status(
    request: Request,
    request_id: int,
    new_status: str = Form(..., alias="status"),
    redirect_to: str = Form("/admin/dashboard"),
):
    if not is_admin(request):
        wants_json = "application/json" in request.headers.get("accept", "").lower()
        if wants_json:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

    updated = update_request_status(request_id, new_status)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    await manager.broadcast({"type": "refresh", "request_id": request_id})

    wants_json = "application/json" in request.headers.get("accept", "").lower()
    if wants_json:
        return JSONResponse({"ok": True, "request": updated})

    return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/request/{request_id}/delete")
async def admin_delete_request(
    request: Request,
    request_id: int,
    redirect_to: str = Form("/admin/dashboard"),
) -> RedirectResponse:
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    deleted = delete_request(request_id)
    if deleted is not None:
        await manager.broadcast({"type": "refresh", "request_id": request_id})

    return RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/requests/reset")
async def admin_reset_requests(request: Request) -> RedirectResponse:
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    removed = clear_requests()
    if removed:
        await manager.broadcast({"type": "refresh", "request_id": None})

    return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/api/booking/new", response_class=HTMLResponse)
async def api_new_booking(
    request: Request,
    contact_name: str = Form(..., alias="name"),
    contact_email: str = Form(..., alias="email"),
    contact_phone: str = Form("", alias="phone"),
    event_date: str = Form(""),
    venue_location: str = Form(...),
    budget: str = Form(""),
    event_details: str = Form(..., alias="message"),
    botcheck: str = Form(""),
):
    if botcheck.strip():
        return RedirectResponse("/book/success", status_code=status.HTTP_303_SEE_OTHER)

    form_values = {
        "contact_name": contact_name.strip(),
        "contact_email": contact_email.strip(),
        "contact_phone": contact_phone.strip(),
        "event_date": event_date.strip(),
        "venue_location": venue_location.strip(),
        "budget": budget.strip(),
        "event_details": event_details.strip(),
    }

    if not form_values["contact_name"] or not form_values["contact_email"] or not form_values["venue_location"] or not form_values["event_details"]:
        return templates.TemplateResponse(
            request,
            "book.html",
            booking_context(
                request,
                error="A few details are still missing. Fill in the main bits and send it again.",
                form_values=form_values,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        send_booking_email(**form_values)
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request,
            "book.html",
            booking_context(request, error=str(exc), form_values=form_values),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception:
        return templates.TemplateResponse(
            request,
            "book.html",
            booking_context(
                request,
                error="That booking request hit a snag. Please try again in a moment.",
                form_values=form_values,
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return RedirectResponse("/book/success", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/gallery/upload")
async def admin_gallery_upload(
    request: Request,
    image: UploadFile = File(...),
) -> RedirectResponse:
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    filename, original_name = await save_gallery_upload(image)
    insert_gallery_image(filename=filename, original_name=original_name)
    return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/gallery/{image_id}/delete")
async def admin_gallery_delete(request: Request, image_id: int) -> RedirectResponse:
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    image = delete_gallery_image(image_id)
    if image is not None:
        remove_gallery_file(image["filename"])

    return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "qr.html",
        {"request": request, "public_url": public_home_url(request)},
    )


@app.get("/qr.png")
async def qr_png(request: Request) -> StreamingResponse:
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(public_home_url(request))
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    headers = {"Content-Disposition": 'inline; filename="tonight-gig-qr.png"'}
    return StreamingResponse(buffer, media_type="image/png", headers=headers)


@app.websocket("/ws/admin")
async def admin_websocket(websocket: WebSocket) -> None:
    session = websocket.scope.get("session", {})
    if not session.get("is_admin"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

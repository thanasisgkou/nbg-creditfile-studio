"""CreditFile Studio HTTP API and application lifecycle."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from .config import ROOT, Settings
from .store import CaseStore, LOCK, now
from . import bulletin as bulletin
from .bulletin_pdf import render_pdf
from .bulk_review import accept_selected, eligibility
from .checks import source_list
from .schema import LABELS, MONEY, QUESTIONS
from .extraction import process_case, PROMPT_VERSION
from .intake import discover, prepare_name

log = logging.getLogger(__name__)


class StudioStore(CaseStore):
    """Atomic Studio writes tolerate short Windows scanner/read locks."""

    def save(self, path: Path, value: dict) -> None:
        temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as output:
                json.dump(value, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            for attempt in range(8):
                try:
                    temp.replace(path)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(min(0.05 * 2**attempt, 0.4))
        finally:
            temp.unlink(missing_ok=True)


class Command(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    expected: str


class Review(Command):
    kind: Literal["application", "financials"]
    field: str
    decision: Literal["accepted", "corrected", "unresolved"]
    comment: str = ""
    corrected: str | None = None
    sources: list[dict] = Field(default_factory=list)


class Bulk(Command):
    selected: list[tuple[str, str]]


class Resolution(Command):
    check_id: str
    basis: str
    reason: str
    sources: list[dict]


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")


def create_app(root: Path | None = None, settings: Settings | None = None) -> FastAPI:
    # Windows registry associations can classify .mjs as text/plain.
    # Module workers require a JavaScript MIME type, regardless of OS settings.
    mimetypes.init()
    mimetypes.add_type("application/javascript", ".mjs")
    settings = replace(settings or Settings.load(), prompt_version=PROMPT_VERSION)
    root = (root or settings.data_dir / "cases").resolve()
    store = StudioStore(root)
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="studio")
    jobs: dict[str, dict] = {}
    job_lock = threading.RLock()
    app = FastAPI(title="CreditFile Studio", version="1.0.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.state.store = store
    app.state.executor = executor

    def has_pending_analyses():
        with job_lock:
            return any(j["state"] in {"queued", "running"} for j in jobs.values())

    app.state.has_pending_analyses = has_pending_analyses
    job_dir = root.parent / "jobs"
    job_dir.mkdir(exist_ok=True)
    for path in job_dir.glob("*.json"):
        job = json.loads(path.read_text(encoding="utf-8"))
        if job["state"] in {"queued", "running"}:
            job.update(
                state="interrupted",
                detail="Η προηγούμενη εκτέλεση διακόπηκε. Ελέγξτε τις αναλύσεις πριν δοκιμάσετε ξανά.",
            )
            store.save(path, job)
        jobs[job["id"]] = job

    @app.middleware("http")
    async def local_writes(request: Request, call_next):
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            # Vite dev proxy retains its browser origin.
            if not (os.environ.get("STUDIO_DEV") == "1" and origin == "http://127.0.0.1:5173"):
                return JSONResponse({"detail": "Μη έγκυρη προέλευση αιτήματος."}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse(
            {"detail": "Ο φάκελος ή η έκδοση δεν είναι διαθέσιμα."}, status_code=404
        )

    def metadata(cid):
        return json.loads((store.folder(cid) / "case.json").read_text(encoding="utf-8"))

    def case_summary(case):
        runs = store.runs(case["id"])
        report = bulletin.preview(store, case["id"], runs[0]["id"]) if runs else None
        return {
            **case,
            "run_id": runs[0]["id"] if runs else None,
            "summary": {
                "pending": report["pending_count"],
                "reviewed": report["reviewed_count"],
                "conflicts": sum(
                    not c["resolution"] and c["status"] != "NOT_CHECKED"
                    for c in report["conflicts"]
                ),
                "draft": report["draft"],
                "state": report["state"],
            }
            if report
            else None,
        }

    def workspace(cid, rid):
        exported = store.export(cid, rid)
        report = bulletin.preview(store, cid, rid)
        fields = []
        for doc in exported["documents"]:
            for name, value in doc["fields"].items():
                eligible, reason = eligibility(value)
                fields.append(
                    {
                        **value,
                        "id": doc["type"] + "." + name,
                        "name": name,
                        "label": LABELS.get(name, name),
                        "kind": doc["type"],
                        "money": name in MONEY,
                        "sources": source_list(value),
                        "eligible": eligible,
                        "eligibility_reason": reason,
                    }
                )
        versions = [
            {**v, "stale": bulletin.is_stale(store, v)} for v in bulletin.versions(store, cid)
        ]
        return {
            "case": metadata(cid),
            "run_id": rid,
            "fields": fields,
            "report": report,
            "runs": [
                {"id": r["id"], "created": r["created"], "mode": r["result"].get("mode")}
                for r in store.runs(cid)
            ],
            "mode": exported.get("mode"),
            "errors": exported.get("errors", []),
            "reviews": exported["review_events"],
            "versions": versions,
            "questions": QUESTIONS,
            "execution_mode": settings.execution_mode,
        }

    def command(cid, rid, req, action):
        """Persist intent before effects; uncertain commands are never blindly replayed."""
        with LOCK:
            path = store.folder(cid) / "studio-commands.json"
            records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            payload = bulletin.digest(req.model_dump())
            old = records.get(req.request_id)
            if old:
                if old["payload"] != payload or old["run"] != rid:
                    raise HTTPException(409, "Το αναγνωριστικό χρησιμοποιήθηκε για άλλη ενέργεια.")
                if old["state"] == "done":
                    return old["result"]
                raise HTTPException(
                    409,
                    "Η ενέργεια έχει ήδη υποβληθεί. Ανανεώστε για να δείτε το αποθηκευμένο αποτέλεσμα.",
                )
            if bulletin.fingerprint(store, cid, rid) != req.expected:
                raise HTTPException(409, "Τα στοιχεία άλλαξαν. Ανανεώστε πριν αποθηκεύσετε ξανά.")
            records[req.request_id] = {
                "payload": payload,
                "run": rid,
                "state": "started",
                "created": now(),
            }
            store.save(path, records)
            result = action()
            records[req.request_id].update(state="done", result=result)
            store.save(path, records)
            return result

    @app.get("/api/v1/health")
    def health():
        return {
            "status": "ok",
            "application": "creditfile-studio",
            "storage": "local",
            "execution_mode": settings.execution_mode,
        }

    @app.get("/api/v1/cases")
    def cases():
        rows = []
        for c in store.cases():
            try:
                rows.append(case_summary(c))
            except (ValueError, KeyError, OSError):
                rows.append(
                    {
                        **c,
                        "run_id": None,
                        "summary": None,
                        "error": "Χρειάζεται έλεγχος συμβατότητας.",
                    }
                )
        return rows

    @app.get("/api/v1/cases/{cid}")
    def case(cid: str):
        return case_summary(metadata(cid))

    @app.get("/api/v1/cases/{cid}/runs/{rid}")
    def run(cid: str, rid: str):
        with LOCK:
            return workspace(cid, rid)

    async def bounded(file: UploadFile, limit=settings.max_mb * 1024 * 1024):
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"Μέγιστο μέγεθος PDF: {settings.max_mb} MB.")
        return data

    @app.post("/api/v1/discover")
    async def discover_files(files: list[UploadFile] = File(...)):
        if len(files) > 30:
            raise ValueError("Επίλεξε έως 30 PDF.")
        items = [{"name": f.filename or "document.pdf", "content": await bounded(f)} for f in files]
        result = discover(items, settings)
        return {
            "files": [{k: i[k] for k in ("id", "name", "kind", "status")} for i in result["items"]],
            "warnings": result["warnings"],
        }

    @app.post("/api/v1/cases")
    async def create_case(
        name: str = Form(""),
        synthetic: bool = Form(...),
        application: UploadFile = File(...),
        financials: UploadFile = File(...),
    ):
        if not synthetic:
            raise ValueError("Επιβεβαίωσε ότι χρησιμοποιείς συνθετικά δεδομένα.")
        inputs = [
            {"type": kind, "name": f.filename or kind + ".pdf", "content": await bounded(f)}
            for kind, f in [("application", application), ("financials", financials)]
        ]
        naming = prepare_name(inputs, settings)
        case_name = name.strip() or naming["suggested_name"] or "Νέος φάκελος · " + uuid4().hex[:8]
        with LOCK:
            return {"id": store.create(case_name, inputs)}

    @app.get("/api/v1/cases/{cid}/documents/{kind}")
    def pdf(cid: str, kind: str, run: str | None = None):
        inputs = store.analysis_inputs(cid, run) if run else store.inputs(cid)
        item = next((d for d in inputs if d["type"] == kind), None)
        if item is None:
            raise HTTPException(404, "Δεν βρέθηκε το έγγραφο.")
        return Response(item["content"], media_type="application/pdf")

    @app.get("/api/v1/cases/{cid}/runs/{rid}/blocks")
    def blocks(cid: str, rid: str, kind: str):
        doc = next(
            (d for d in store.raw_run(cid, rid)["result"]["documents"] if d["type"] == kind), None
        )
        if doc is None:
            raise HTTPException(404, "Δεν βρέθηκε το έγγραφο.")
        return [
            {
                "document_id": doc["id"],
                "document_name": doc["name"],
                "page": b["page"],
                "block_id": b["block_id"],
                "quote": b["text"],
            }
            for b in doc["blocks"]
        ]

    @app.post("/api/v1/cases/{cid}/runs/{rid}/review")
    def review(cid: str, rid: str, req: Review):
        def save():
            store.review(
                cid, rid, req.kind, req.field, req.decision, req.comment, req.corrected, req.sources
            )
            return {"saved": True}

        return command(cid, rid, req, save)

    @app.post("/api/v1/cases/{cid}/runs/{rid}/bulk")
    def bulk(cid: str, rid: str, req: Bulk):
        return command(
            cid,
            rid,
            req,
            lambda: {"count": accept_selected(store, cid, rid, req.selected, req.expected)},
        )

    @app.post("/api/v1/cases/{cid}/runs/{rid}/resolve")
    def resolve(cid: str, rid: str, req: Resolution):
        def save():
            bulletin.resolve(store, cid, rid, req.check_id, req.reason, req.sources, req.basis)
            return {"saved": True}

        return command(cid, rid, req, save)

    @app.post("/api/v1/cases/{cid}/replace/{kind}")
    async def replace_pdf(
        cid: str,
        kind: str,
        file: UploadFile = File(...),
        expected: str = Form(...),
        synthetic: bool = Form(...),
    ):
        content = await bounded(file)
        with job_lock:
            if any(
                j["case_id"] == cid and j["state"] in {"queued", "running"} for j in jobs.values()
            ):
                raise HTTPException(409, "Περιμένετε να ολοκληρωθεί η ανάλυση.")
            store.replace_document(
                cid, kind, file.filename or kind + ".pdf", content, settings, expected, synthetic
            )
        return {"saved": True}

    def save_job(job):
        store.save(job_dir / (job["id"] + ".json"), job)

    @app.post("/api/v1/cases/{cid}/analyses")
    def analyze(cid: str):
        if settings.execution_mode != "live":
            raise HTTPException(409, "Οι νέες κλήσεις AI είναι απενεργοποιημένες.")
        with job_lock:
            for j in jobs.values():
                if j["case_id"] == cid and j["state"] in {"queued", "running"}:
                    return j
            inputs = store.inputs(cid)
            naming = prepare_name(inputs, settings)
            job = {
                "id": uuid4().hex,
                "case_id": cid,
                "state": "queued",
                "progress": 0,
                "detail": "Προετοιμασία",
                "created": now(),
            }
            jobs[job["id"]] = job
            save_job(job)

            def worker():
                try:
                    from .providers import create_model

                    def progress(value, stage, detail):
                        with job_lock:
                            job.update(state="running", progress=value, stage=stage, detail=detail)
                            save_job(job)

                    result = process_case(
                        cid, inputs, create_model(settings), settings, progress=progress
                    )
                    progress(96, "save", "Αποθήκευση στοιχείων και πηγών")
                    with LOCK:
                        rid = store.save_run(cid, result)
                        if naming["suggested_name"]:
                            case = metadata(cid)
                            case["name"] = naming["suggested_name"]
                            store.save(store.folder(cid) / "case.json", case)
                    with job_lock:
                        job.update(
                            state="failed" if result["status"] == "failed" else "complete",
                            progress=100,
                            detail="Η εξαγωγή απέτυχε. Αποθηκεύτηκαν τα διαγνωστικά της ανάλυσης."
                            if result["status"] == "failed"
                            else "Η ανάλυση αποθηκεύτηκε.",
                            run_id=rid,
                        )
                except OSError:
                    log.exception("Studio storage failed")
                    job.update(
                        state="failed",
                        detail="Δεν ήταν δυνατή η αποθήκευση στον δίσκο. Ελέγξτε τα δικαιώματα και τον διαθέσιμο χώρο πριν επαναλάβετε.",
                    )
                except Exception:
                    log.exception("Studio analysis failed")
                    job.update(
                        state="failed",
                        detail="Η ανάλυση δεν ολοκληρώθηκε. Ελέγξτε τη σύνδεση και τις ρυθμίσεις AI πριν επαναλάβετε.",
                    )
                finally:
                    with job_lock:
                        save_job(job)

            executor.submit(worker)
            return dict(job)

    @app.get("/api/v1/cases/{cid}/jobs")
    def case_jobs(cid: str):
        metadata(cid)
        with job_lock:
            return sorted(
                [dict(j) for j in jobs.values() if j["case_id"] == cid],
                key=lambda j: j["created"],
                reverse=True,
            )

    @app.get("/api/v1/cases/{cid}/runs/{rid}/chats")
    def chats(cid: str, rid: str):
        return store.chats(cid, rid)

    @app.post("/api/v1/cases/{cid}/runs/{rid}/chat")
    def chat(cid: str, rid: str, req: Question):
        from . import chat
        from .providers import create_model
        from .questions import answer_predefined
        from .chat_workflow import workflow_intent, answer_workflow

        if not req.question.strip():
            raise ValueError("Γράψτε την ερώτησή σας.")
        with LOCK:
            sessions = store.chats(cid, rid)
            for session in sessions:
                previous = next(
                    (t for t in session["turns"] if t.get("studio_request_id") == req.request_id),
                    None,
                )
                if previous:
                    if previous["question"] != req.question:
                        raise HTTPException(409, "Το αναγνωριστικό χρησιμοποιήθηκε ήδη.")
                    return {"session_id": session["id"], "turn": previous}
            journal_path = store.folder(cid) / ("studio-chat-requests-" + rid + ".json")
            journal = (
                json.loads(journal_path.read_text(encoding="utf-8"))
                if journal_path.exists()
                else {}
            )
            if req.request_id in journal:
                raise HTTPException(
                    409, "Η ερώτηση έχει ήδη υποβληθεί. Ανανεώστε το ιστορικό πριν επαναλάβετε."
                )
            sid = req.session_id
            if sid and not any(s["id"] == sid for s in sessions):
                raise ValueError("Η συνομιλία δεν ανήκει σε αυτή την ανάλυση.")
            journal[req.request_id] = {"state": "submitted", "created": now()}
            store.save(journal_path, journal)
            sid = sid or store.new_chat(cid, rid)
            turns = next((s["turns"] for s in sessions if s["id"] == sid), [])
        run = store.run(cid, rid)
        with LOCK:
            report = bulletin.preview(store, cid, rid)
            if any(d["requires_reanalysis"] for d in report["documents"]):
                raise HTTPException(
                    409, "Αντικαταστάθηκε έγγραφο. Ολοκλήρωσε πρώτα τη νέα ανάλυση."
                )
            workflow_turn = (
                answer_workflow(req.question, report, store.export(cid, rid))
                if workflow_intent(req.question, turns)
                else None
            )
        index = next(
            (i for i, q in enumerate(QUESTIONS) if q.casefold() == req.question.strip().casefold()),
            None,
        )
        if workflow_turn is not None:
            turn = workflow_turn
        elif index is not None:
            answer = answer_predefined(run["result"], index, run["reviews"])
            claims = [{"text": c["text"], "sources": c["evidence"]} for c in answer["claims"]]
            turn = {
                "case_id": cid,
                "run_id": rid,
                "question": req.question,
                "claims": claims,
                "sources": [s for c in claims for s in c["sources"]],
                "mode": "predefined",
                "status": "answered" if claims else "not_found",
                "unanswered": answer["unanswered"],
                "error": None,
                "calls": [],
                "seconds": 0,
            }
        else:
            if settings.execution_mode != "live":
                raise HTTPException(
                    409,
                    "Οι νέες ερωτήσεις AI είναι απενεργοποιημένες. Οι έτοιμες ερωτήσεις είναι διαθέσιμες.",
                )
            model = create_model(chat.chat_settings(settings))
            turn = chat.ask(
                cid,
                run,
                store.analysis_inputs(cid, rid),
                req.question,
                turns,
                model,
                reviewed=store.export(cid, rid),
                conversational=True,
            )
        turn["studio_request_id"] = req.request_id
        store.append_chat(cid, rid, sid, turn)
        return {"session_id": sid, "turn": turn}

    @app.get("/api/v1/cases/{cid}/runs/{rid}/preview.pdf")
    def preview_pdf(cid: str, rid: str):
        report = bulletin.preview(store, cid, rid)
        # The PDF renderer expects issuance metadata. Supply display-only
        # metadata on this detached report; never call issue or persist it.
        report["issued_at"] = now()
        report["version"] = str(report["version"]) + " (ΠΡΟΕΠΙΣΚΟΠΗΣΗ)"
        report["example_notice"] = (
            "ΠΡΟΕΠΙΣΚΟΠΗΣΗ — ΔΕΝ ΕΧΕΙ ΕΚΔΟΘΕΙ. "
            "Η ημερομηνία παρακάτω αφορά τη δημιουργία αυτής της προεπισκόπησης. "
            "Για αποθηκευμένη έκδοση χρησιμοποιήστε την ενέργεια Έκδοση δελτίου."
        )
        return Response(render_pdf(report, studio=True), media_type="application/pdf")

    @app.post("/api/v1/cases/{cid}/runs/{rid}/issue")
    def issue(cid: str, rid: str, req: Command):
        return command(
            cid,
            rid,
            req,
            lambda: {
                "version": bulletin.issue(store, cid, rid, req.expected, studio=True)["version"]
            },
        )

    @app.get("/api/v1/cases/{cid}/versions/{version}/{kind}")
    def version_file(cid: str, version: int, kind: str):
        snapshot = next((v for v in bulletin.versions(store, cid) if v["version"] == version), None)
        if snapshot is None or kind not in {
            "bulletin.pdf",
            "snapshot.json",
            "application.pdf",
            "financials.pdf",
        }:
            raise HTTPException(404, "Δεν βρέθηκε η έκδοση.")
        return FileResponse(bulletin.version_folder(store, snapshot) / kind)

    @app.get("/api/v1/cases/{cid}/runs/{rid}/export")
    def export(cid: str, rid: str):
        return JSONResponse(
            store.export(cid, rid),
            headers={"Content-Disposition": 'attachment; filename="reviewed.json"'},
        )

    @app.get("/api/v1/cases/{cid}/runs/{rid}/handoff")
    def handoff(cid: str, rid: str):
        from .handoff import summary, markdown

        with LOCK:
            report = summary(
                store.export(cid, rid), metadata(cid)["name"], bulletin.preview(store, cid, rid)
            )
        return Response(
            markdown(report),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="handoff.md"'},
        )

    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (dist / "branding").exists():
        app.mount("/branding", StaticFiles(directory=dist / "branding"), name="branding")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Άγνωστο API endpoint.")
        if path.startswith(("assets/", "branding/")) or "." in path.rsplit("/", 1)[-1]:
            raise HTTPException(404, "Το αρχείο δεν βρέθηκε.")
        if not (dist / "index.html").exists():
            return Response("Build frontend first: npm run build", status_code=503)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app

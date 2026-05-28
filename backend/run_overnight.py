"""Phase 7 — the overnight batch runner. Entry point.

    python -m backend.run_overnight

Walks PDF_INPUT_DIR, processes each Bauwerksbuch through the pipeline, and records
every run in `extraction_jobs`. Properties:
  - Idempotent: a PDF already completed (by sha256) is skipped on re-run.
  - Error-isolated: one bad PDF fails its own job; the batch continues.
  - Observable: each job row carries status, live step message, timing, tokens,
    and any error.

Exit code is non-zero if any job failed (useful for cron/CI alerting).
"""
import hashlib
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from backend import config, pipeline
from backend.db.client import get_client


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def discover(pdf_dir: Path) -> list[Path]:
    return sorted(pdf_dir.glob("*.pdf"))


def _already_completed(client, sha: str) -> bool:
    resp = (client.table("extraction_jobs").select("id")
            .eq("pdf_sha256", sha).eq("status", "completed").limit(1).execute())
    return bool(resp.data)


def _create_job(client, pdf: Path, sha: str) -> str:
    row = {
        "pdf_filename": pdf.name,
        "pdf_size_bytes": pdf.stat().st_size,
        "pdf_sha256": sha,
        "status": "processing",
        "status_message": "gestartet",
        "started_at": _now().isoformat(),
    }
    resp = client.table("extraction_jobs").insert(row).execute()
    return resp.data[0]["id"]


def _update_status(client, job_id: str, message: str) -> None:
    client.table("extraction_jobs").update({"status_message": message}).eq("id", job_id).execute()


def _complete_job(client, job_id: str, bridge_id: str, usage: dict, started: datetime) -> None:
    duration_ms = int((_now() - started).total_seconds() * 1000)
    client.table("extraction_jobs").update({
        "status": "completed",
        "status_message": "fertig",
        "bridge_id": bridge_id,
        "completed_at": _now().isoformat(),
        "extraction_duration_ms": duration_ms,
        "llm_model": usage.get("model"),
        "llm_input_tokens": usage.get("input_tokens"),
        "llm_output_tokens": usage.get("output_tokens"),
    }).eq("id", job_id).execute()


def _fail_job(client, job_id: str, exc: Exception, started: datetime) -> None:
    duration_ms = int((_now() - started).total_seconds() * 1000)
    client.table("extraction_jobs").update({
        "status": "failed",
        "status_message": "fehlgeschlagen",
        "error_message": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"[:8000],
        "completed_at": _now().isoformat(),
        "extraction_duration_ms": duration_ms,
    }).eq("id", job_id).execute()


def main() -> int:
    # Windows consoles default to cp1252, which can't encode many characters in
    # the German status text. Force UTF-8 so logging never crashes the batch.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    client = get_client()   # raises early if credentials are missing
    pdfs = discover(config.PDF_INPUT_DIR)

    if not pdfs:
        print(f"No PDFs found in {config.PDF_INPUT_DIR}")
        return 0

    print(f"Found {len(pdfs)} PDF(s) in {config.PDF_INPUT_DIR}\n")
    succeeded, skipped, failed = [], [], []

    for pdf in pdfs:
        sha = _sha256(pdf)
        if _already_completed(client, sha):
            print(f"[SKIP] {pdf.name}  (already completed)")
            skipped.append(pdf.name)
            continue

        print(f"[>] {pdf.name}")
        started = _now()
        job_id = _create_job(client, pdf, sha)
        try:
            bridge_id, usage = pipeline.run(
                pdf, job_id=job_id,
                on_step=lambda msg: _update_status(client, job_id, msg),
            )
            _complete_job(client, job_id, bridge_id, usage, started)
            tok = f"{usage.get('input_tokens')}->{usage.get('output_tokens')} tok"
            print(f"   [OK] bridge {bridge_id}  ({tok})")
            succeeded.append(pdf.name)
        except Exception as exc:   # error isolation — one bad PDF never aborts the run
            _fail_job(client, job_id, exc, started)
            print(f"   [FAIL] {type(exc).__name__}: {exc}")
            failed.append((pdf.name, str(exc)))

    print("\n" + "=" * 60)
    print(f"Done. {len(succeeded)} succeeded, {len(skipped)} skipped, {len(failed)} failed.")
    for name, err in failed:
        print(f"  FAILED  {name}: {err}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

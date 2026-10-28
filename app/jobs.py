"""Hintergrund-Aufträge mit Fortschrittsanzeige.

Die Sprachsynthese kann auf einem Laptop ohne Grafikkarte mehrere Minuten
dauern. Damit der Browser nicht blockiert, läuft sie in einem eigenen Thread
und meldet ihren Fortschritt (0–100 %) an die Oberfläche.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional


class JobCancelled(Exception):
    """Wird ausgelöst, wenn ein Auftrag abgebrochen wurde."""


class Job:
    def __init__(self, kind: str) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status = "wartet"       # wartet | laeuft | fertig | fehler | abgebrochen
        self.progress = 0
        self.stage = "Wartet …"
        self.error: Optional[str] = None
        self.result: Dict[str, Any] = {}
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self.cancelled = False
        self._lock = threading.Lock()

    def update(self, progress: Optional[int] = None, stage: Optional[str] = None) -> None:
        with self._lock:
            if self.cancelled:
                raise JobCancelled()
            if progress is not None:
                self.progress = max(0, min(100, int(progress)))
            if stage:
                self.stage = stage

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "kind": self.kind,
                "status": self.status,
                "progress": self.progress,
                "stage": self.stage,
                "error": self.error,
                "result": self.result,
                "created_at": self.created_at,
            }


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        job = Job(kind)
        with self._lock:
            # alte Aufträge begrenzen (nur Speicher, keine Dateien)
            if len(self._jobs) > 40:
                for old_id in list(self._jobs)[:20]:
                    if self._jobs[old_id].status in ("fertig", "fehler", "abgebrochen"):
                        self._jobs.pop(old_id, None)
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def start(self, job: Job, target: Callable[[Job], Dict[str, Any]]) -> None:
        def runner() -> None:
            job.status = "laeuft"
            try:
                result = target(job) or {}
                job.result = result
                job.progress = 100
                job.stage = "Fertig"
                job.status = "fertig"
            except JobCancelled:
                job.status = "abgebrochen"
                job.stage = "Abgebrochen"
            except Exception as exc:  # ehrliche Fehlermeldung nach außen geben
                job.status = "fehler"
                job.error = str(exc)
                job.stage = "Fehlgeschlagen"
                job.result = {"trace": traceback.format_exc(limit=6)}
            finally:
                pass

        thread = threading.Thread(target=runner, name=f"job-{job.id}", daemon=True)
        thread.start()

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        job.cancelled = True
        if job.status == "wartet":
            job.status = "abgebrochen"
        return True


jobs = JobManager()

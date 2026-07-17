"""Background job management: one generation job per project at a time."""

import threading


class Job:
    def __init__(self, name: str):
        self.name = name
        self.status = "running"
        self.log: list[str] = []
        self.total = 0
        self.completed = 0
        self.current = ""
        self.results: list[dict] = []

    def progress(self, current: str, completed: int | None = None, total: int | None = None):
        self.current = current
        if completed is not None:
            self.completed = completed
        if total is not None:
            self.total = total

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "log": self.log[-30:],
            "total": self.total,
            "completed": self.completed,
            "current": self.current,
            "results": self.results,
        }


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Job | None:
        return self._jobs.get(key)

    def start(self, key: str, name: str, fn) -> bool:
        """Start a background job. *fn* receives ``(log, job)`` where *log*
        is ``job.log.append`` (shorthand) and *job* is the :class:`Job`
        instance for structured progress updates."""
        with self._lock:
            existing = self._jobs.get(key)
            if existing and existing.status == "running":
                return False
            job = Job(name)
            self._jobs[key] = job

        def runner():
            try:
                fn(job.log.append, job)
                job.status = "done"
            except Exception as exc:
                job.log.append(str(exc))
                job.status = "failed"

        threading.Thread(target=runner, daemon=True).start()
        return True

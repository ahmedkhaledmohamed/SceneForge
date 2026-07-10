"""Background job management: one generation job per project at a time.
Carried over from the htmx UI — the contract (run in a thread, append to
a log buffer, 409 on conflict) is unchanged; only the rendering moved."""

import threading


class Job:
    def __init__(self, name: str):
        self.name = name
        self.status = "running"  # running | done | failed
        self.log: list[str] = []

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "log": self.log[-30:]}


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Job | None:
        return self._jobs.get(key)

    def start(self, key: str, name: str, fn) -> bool:
        with self._lock:
            existing = self._jobs.get(key)
            if existing and existing.status == "running":
                return False
            job = Job(name)
            self._jobs[key] = job

        def runner():
            try:
                fn(job.log.append)
                job.status = "done"
            except Exception as exc:  # surfaced via GET .../job
                job.log.append(str(exc))
                job.status = "failed"

        threading.Thread(target=runner, daemon=True).start()
        return True

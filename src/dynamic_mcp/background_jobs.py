"""Background job management for long-running bash and bpftrace processes."""

import asyncio
import logging
import os
import secrets
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BackgroundJob:
    job_id: str
    label: str          # "bash" | "bpftrace"
    command_desc: str
    process: asyncio.subprocess.Process
    start_time: float
    stdout_chunks: List[str] = field(default_factory=list)
    stderr_chunks: List[str] = field(default_factory=list)
    status: str = "running"   # "running" | "completed" | "killed" | "error"
    exit_code: Optional[int] = None
    _reader_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _script_path: Optional[str] = field(default=None, repr=False)


class BackgroundJobManager:
    """Manages long-running background processes for bash and bpftrace."""

    def __init__(self):
        self._jobs: Dict[str, BackgroundJob] = {}
        self._bpftrace_path: Optional[str] = self._find_bpftrace()

    def _find_bpftrace(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["which", "bpftrace"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _new_job_id(self) -> str:
        return secrets.token_hex(6)

    async def _drain(self, job: BackgroundJob) -> None:
        """Background task: read stdout/stderr line-by-line until process exits."""
        async def read_stream(stream, chunks):
            while True:
                line = await stream.readline()
                if not line:
                    break
                chunks.append(line.decode(errors="replace"))

        try:
            await asyncio.gather(
                read_stream(job.process.stdout, job.stdout_chunks),
                read_stream(job.process.stderr, job.stderr_chunks),
            )
            job.exit_code = await job.process.wait()
            if job.status == "running":
                job.status = "completed"
        except Exception as e:
            logger.warning(f"Job {job.job_id} drain error: {e}")
            job.status = "error"
        finally:
            if job._script_path:
                try:
                    os.unlink(job._script_path)
                except Exception:
                    pass
                job._script_path = None

    async def start_bash(
        self,
        command: str,
        working_dir: Optional[str] = None,
    ) -> str:
        """Start a bash command in the background. Returns job_id."""
        process = await asyncio.create_subprocess_exec(
            "bash", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )
        job_id = self._new_job_id()
        desc = command[:80] + ("…" if len(command) > 80 else "")
        job = BackgroundJob(
            job_id=job_id,
            label="bash",
            command_desc=desc,
            process=process,
            start_time=time.monotonic(),
        )
        job._reader_task = asyncio.create_task(self._drain(job))
        self._jobs[job_id] = job
        logger.info(f"Background bash job {job_id} started: {desc!r}")
        return job_id

    async def start_bpftrace(
        self,
        script: str,
        use_sudo: bool = True,
    ) -> str:
        """Start a bpftrace script in the background. Returns job_id."""
        if not self._bpftrace_path:
            raise RuntimeError("bpftrace not available on this system")

        # Write script to a temp file that persists until the job finishes
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".bt", delete=False
        )
        tmp.write(script)
        tmp.flush()
        tmp.close()
        script_path = tmp.name

        cmd = [self._bpftrace_path, script_path]
        if use_sudo:
            cmd = ["sudo", "-n"] + cmd

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception:
            os.unlink(script_path)
            raise

        job_id = self._new_job_id()
        desc = script.split("\n")[0][:80]
        job = BackgroundJob(
            job_id=job_id,
            label="bpftrace",
            command_desc=desc,
            process=process,
            start_time=time.monotonic(),
            _script_path=script_path,
        )
        job._reader_task = asyncio.create_task(self._drain(job))
        self._jobs[job_id] = job
        logger.info(f"Background bpftrace job {job_id} started")
        return job_id

    def get_output(self, job_id: str) -> dict:
        """Return current accumulated output and status for a job."""
        job = self._jobs.get(job_id)
        if job is None:
            return {"error": f"Unknown job_id: {job_id}"}
        elapsed = time.monotonic() - job.start_time
        return {
            "job_id": job_id,
            "label": job.label,
            "command_desc": job.command_desc,
            "status": job.status,
            "elapsed_s": round(elapsed, 1),
            "exit_code": job.exit_code,
            "stdout": "".join(job.stdout_chunks),
            "stderr": "".join(job.stderr_chunks),
        }

    async def kill_job(self, job_id: str) -> bool:
        """Terminate a running job. Returns True if it was running."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status != "running":
            return False
        job.status = "killed"
        try:
            job.process.terminate()
            await asyncio.wait_for(job.process.wait(), timeout=3)
        except asyncio.TimeoutError:
            job.process.kill()
        except Exception as e:
            logger.warning(f"Error killing job {job_id}: {e}")
        return True

    def list_jobs(self) -> List[dict]:
        """Return summary list of all jobs."""
        result = []
        for job in self._jobs.values():
            elapsed = time.monotonic() - job.start_time
            result.append({
                "job_id": job.job_id,
                "label": job.label,
                "command_desc": job.command_desc,
                "status": job.status,
                "elapsed_s": round(elapsed, 1),
                "exit_code": job.exit_code,
            })
        return result

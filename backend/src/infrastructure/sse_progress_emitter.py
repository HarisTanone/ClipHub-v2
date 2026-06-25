"""SSEProgressEmitter — manages SSE connections and emits pipeline progress events."""
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Optional

logger = logging.getLogger(__name__)


class SSEProgressEmitter:
    """Manages SSE connections and emits pipeline progress events.
    
    Features:
    - Per-job event broadcasting to all connected clients
    - Max 10 connections per job_id
    - Heartbeat ping every 15 seconds
    - Event types: step_start, step_complete, job_done
    """

    MAX_CONNECTIONS_PER_JOB = 10
    HEARTBEAT_INTERVAL = 15  # seconds
    TOTAL_STEPS = 14

    def __init__(self):
        # job_id -> list of asyncio.Queue
        self._connections: Dict[str, list] = defaultdict(list)
        # job_id -> final event (for late-connecting clients)
        self._final_states: Dict[str, dict] = {}

    @property
    def connection_count(self) -> Dict[str, int]:
        """Get current connection counts per job."""
        return {k: len(v) for k, v in self._connections.items()}

    def is_job_completed(self, job_id: str) -> bool:
        """Check if job has reached terminal state."""
        return job_id in self._final_states

    def get_final_state(self, job_id: str) -> Optional[dict]:
        """Get final state for already-completed job."""
        return self._final_states.get(job_id)

    def can_connect(self, job_id: str) -> bool:
        """Check if more connections are allowed for this job."""
        return len(self._connections[job_id]) < self.MAX_CONNECTIONS_PER_JOB

    async def connect(self, job_id: str) -> AsyncGenerator[str, None]:
        """SSE stream generator with heartbeat.
        
        Args:
            job_id: The job to subscribe to.
            
        Yields:
            SSE-formatted strings (event + data lines).
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._connections[job_id].append(queue)

        try:
            # If job already completed, emit final state and close
            if job_id in self._final_states:
                yield self._format_event("job_done", self._final_states[job_id])
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=self.HEARTBEAT_INTERVAL)
                    yield self._format_event(event["type"], event["data"])

                    # Close connection after job_done
                    if event["type"] == "job_done":
                        return
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield ": ping\n\n"
        finally:
            if queue in self._connections[job_id]:
                self._connections[job_id].remove(queue)
            # Cleanup empty job entries
            if not self._connections[job_id]:
                del self._connections[job_id]

    def emit(self, job_id: str, event_type: str, data: dict) -> None:
        """Broadcast event to all connected clients for job_id.
        
        Args:
            job_id: Target job.
            event_type: One of step_start, step_complete, job_done.
            data: Event payload dict.
        """
        event = {"type": event_type, "data": data}

        # Store final state for late-connecting clients
        if event_type == "job_done":
            self._final_states[job_id] = data

        # Broadcast to all connected queues
        for queue in self._connections.get(job_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("sse_queue_full", extra={"job_id": job_id})

    def emit_step_start(self, job_id: str, step_number: int, step_name: str) -> None:
        """Emit step_start event."""
        self.emit(job_id, "step_start", {
            "job_id": job_id,
            "step_number": step_number,
            "step_name": step_name,
            "total_steps": self.TOTAL_STEPS,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def emit_step_complete(self, job_id: str, step_number: int, step_name: str, duration_seconds: float) -> None:
        """Emit step_complete event."""
        self.emit(job_id, "step_complete", {
            "job_id": job_id,
            "step_number": step_number,
            "step_name": step_name,
            "total_steps": self.TOTAL_STEPS,
            "duration_seconds": round(duration_seconds, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def emit_job_done(self, job_id: str, final_status: str, total_duration_seconds: float, clips_count: int) -> None:
        """Emit job_done event."""
        self.emit(job_id, "job_done", {
            "job_id": job_id,
            "final_status": final_status,
            "total_duration_seconds": round(total_duration_seconds, 2),
            "clips_count": clips_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @staticmethod
    def _format_event(event_type: str, data: dict) -> str:
        """Format as SSE text."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

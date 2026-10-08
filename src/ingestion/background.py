"""Coleta AIS contínua em background para o runtime Streamlit.

O serviço mantém a rede fora do thread principal do Streamlit. O estado é
somente leitura para a UI; observações são entregues por uma Queue limitada.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from src.ingestion.aisstream import AISStreamProvider
from src.ingestion.models import AISObservation


@dataclass(frozen=True)
class BackgroundIngestionSnapshot:
    running: bool
    queued_messages: int
    messages_received: int
    started_at: datetime | None
    last_error: str | None
    worker_cycles: int


class AISBackgroundService:
    """Worker daemon que mantém a ingestão real AIS ativa e resiliente."""

    def __init__(
        self,
        provider: AISStreamProvider,
        *,
        queue_maxsize: int = 10000,
        reconnect_window_seconds: float = 30.0,
    ) -> None:
        self.provider = provider
        self.queue: queue.Queue[AISObservation] = queue.Queue(maxsize=max(100, queue_maxsize))
        self.reconnect_window_seconds = max(5.0, float(reconnect_window_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._started_at: datetime | None = None
        self._last_error: str | None = None
        self._worker_cycles = 0

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._started_at = datetime.now(timezone.utc)
            self._last_error = None
            self._thread = threading.Thread(
                target=self._run,
                name="mie-ais-ingestion",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.1, timeout))

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def drain(self, max_items: int = 1000) -> list[AISObservation]:
        """Retira observações sem bloquear a UI."""
        items: list[AISObservation] = []
        for _ in range(max(1, int(max_items))):
            try:
                items.append(self.queue.get_nowait())
            except queue.Empty:
                break
        self.provider.set_queue_size(self.queue.qsize())
        return items

    def snapshot(self) -> BackgroundIngestionSnapshot:
        return BackgroundIngestionSnapshot(
            running=self.running,
            queued_messages=self.queue.qsize(),
            messages_received=self.provider.status.messages_received,
            started_at=self._started_at,
            last_error=self._last_error,
            worker_cycles=self._worker_cycles,
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            self._worker_cycles += 1
            try:
                # O provider já implementa heartbeat, reconexão com backoff e
                # validação. Um ciclo curto evita prender o worker em uma
                # conexão morta indefinidamente.
                for observation in self.provider.stream(
                    self._stop,
                    duration_seconds=self.reconnect_window_seconds,
                ):
                    if self._stop.is_set():
                        break
                    try:
                        self.queue.put(observation, timeout=0.25)
                    except queue.Full:
                        # A prioridade é continuar consumindo o WebSocket para
                        # evitar backpressure no fornecedor. A perda local fica
                        # visível pelo tamanho máximo da fila.
                        continue
                    self.provider.set_queue_size(self.queue.qsize())
            except Exception as exc:  # pragma: no cover - defesa operacional
                self._last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(min(2.0, self.reconnect_window_seconds / 10.0))

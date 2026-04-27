from enum import Enum
import threading
import logging

logger = logging.getLogger(__name__)

class EngineStatus(Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"

class GlobalEngineState:
    """
    Gestiona el estado de ejecución global del bot.
    Permite pausar, reanudar o detener completamente el bucle principal de forma thread-safe.
    """
    def __init__(self):
        self._status = EngineStatus.RUNNING
        self._lock = threading.Lock()

    @property
    def status(self) -> EngineStatus:
        with self._lock:
            return self._status

    def pause(self) -> None:
        with self._lock:
            if self._status == EngineStatus.RUNNING:
                self._status = EngineStatus.PAUSED
                logger.info("Estado del motor cambiado a PAUSADO")

    def resume(self) -> None:
        with self._lock:
            if self._status == EngineStatus.PAUSED:
                self._status = EngineStatus.RUNNING
                logger.info("Estado del motor cambiado a EN EJECUCIÓN (RUNNING)")

    def stop(self) -> None:
        with self._lock:
            self._status = EngineStatus.STOPPED
            logger.info("Estado del motor cambiado a DETENIDO (STOPPED). Preparando apagado...")

    def is_running(self) -> bool:
        return self.status == EngineStatus.RUNNING

    def is_paused(self) -> bool:
        return self.status == EngineStatus.PAUSED

    def is_stopped(self) -> bool:
        return self.status == EngineStatus.STOPPED

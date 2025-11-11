# -*- coding: utf-8 -*-
"""
Worker de Hilos (QRunnable).

Este archivo define el 'Worker' genérico que se utiliza para ejecutar
cualquier tarea de larga duración (BD, scraping, Excel) en un hilo
separado, evitando que la GUI se congele.


"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

# Importar el logger
from src.utils.logger import configurar_logger

logger = configurar_logger(__name__)


class WorkerSignals(QObject):
    """
    Define las señales disponibles para un worker.
    Hereda de QObject para poder emitir señales de Qt.

    Señales:
        finished: Se emite cuando la tarea termina (con o sin error).
        error: Se emite si ocurre una excepción (pasa el objeto Exception).
        result: Se emite si la tarea devuelve un resultado (pasa el objeto).
        progress: Se emite para reportar el progreso (pasa un string).
    """

    finished = Signal()
    error = Signal(Exception)
    result = Signal(object)
    progress = Signal(str)


class Worker(QRunnable):
    """
    Worker genérico que hereda de QRunnable.

    Está diseñado para ejecutarse en el QThreadPool global.
    Su trabajo es ejecutar una 'task' (función) y emitir
    señales de WorkerSignals con el resultado.
    """

    def __init__(
        self,
        task: Callable[..., Any],
        needs_progress_signal: bool,
        *args,
        **kwargs,
    ):
        """
        Inicializa el worker.

        Args:
            task (Callable): La función que se ejecutará en el hilo
                             (ej. self.db_service.obtener_datos_tab1).
            needs_progress_signal (bool): Si es True, el worker
                                          inyectará la señal de progreso
                                          como primer argumento de la tarea.
            *args: Argumentos posicionales para la 'task'.
            **kwargs: Argumentos clave-valor para la 'task'.
        """
        super().__init__()
        self.task = task
        self.needs_progress_signal = needs_progress_signal
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()  # noqa: F821
    def run(self):
        """
        El método principal que se ejecuta en el hilo secundario.

        NO crea ninguna sesión de BD aquí.
        Simplemente ejecuta la tarea asignada.
        """
        logger.debug(f"Hilo (QRunnable) iniciando tarea: {self.task.__name__}")

        try:
            task_args = self.args

            # --- Inyección del Callback de Progreso ---
            # Si la tarea lo necesita (ej. ETLService),
            # inyectamos el método .emit() de la señal de progreso
            # como el primer argumento.
            if self.needs_progress_signal:
                # (self.signals.progress.emit,) es una tupla
                task_args = (self.signals.progress.emit,) + self.args

            # ----------------------------------------------

            # Ejecutar la tarea (ej. self.db_service.obtener_datos_tab1())
            resultado = self.task(*task_args, **self.kwargs)

            # Si la tarea devolvió algo, lo emitimos en la señal 'result'
            if resultado is not None:
                self.signals.result.emit(resultado)

        except Exception as e:
            # Si la tarea falla, emitimos la señal 'error'
            logger.error(f"Error en el hilo (QRunnable): {e}", exc_info=True)
            self.signals.error.emit(e)
        finally:
            # En todos los casos, emitimos la señal 'finished'
            self.signals.finished.emit()
            logger.debug(f"Hilo (QRunnable) finalizó tarea: {self.task.__name__}")

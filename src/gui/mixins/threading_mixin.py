# -*- coding: utf-8 -*-
"""
Mixin para la gestión de Hilos (Threading).

(v7.8 - Corrección de set_ui_busy)
- Se actualiza 'set_ui_busy' para que deshabilite los
  nuevos botones ('actions_menu_button') en lugar de los antiguos.
"""

from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtCore import Slot
from typing import Callable

from src.gui.gui_worker import Worker
from src.utils.logger import configurar_logger
from src.utils.exceptions import (
    EtlError,
    ScrapingFase1Error,
    DatabaseLoadError,
    DatabaseTransformError,
    ScrapingFase2Error,
    RecalculoError
)

logger = configurar_logger(__name__)


class ThreadingMixin:
    """
    Este Mixin maneja toda la lógica de creación de hilos (workers),
    gestión de señales (progreso, error, finalizado) y
    el bloqueo/desbloqueo de la GUI.
    """

    @Slot(str)
    def on_progress_update(self, message: str):
        self.statusBar().showMessage(message)

    def start_task(
        self,
        task: Callable,
        on_result: Callable,
        on_error: Callable,
        on_finished: Callable,
        on_progress: Callable | None = None,
        task_args: tuple = (),
        task_kwargs: dict = {},
    ):
        """Inicia un nuevo worker en el QThreadPool."""
        self.set_ui_busy(True)
        self.last_error = None
        needs_progress = on_progress is not None
        
        worker = Worker(task, needs_progress, *task_args, **task_kwargs)
        
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.finished.connect(on_finished)
        if on_progress:
            worker.signals.progress.connect(on_progress)
            
        worker.signals.finished.connect(lambda: self.on_worker_finished(worker))
        
        self.running_workers.append(worker)
        self.thread_pool.start(worker)

    @Slot(Worker)
    def on_worker_finished(self, worker_to_remove: Worker):
        """Limpia el worker de la lista cuando ha terminado."""
        logger.debug(f"Worker {worker_to_remove.task.__name__} terminado. Limpiando...")
        try:
            self.running_workers.remove(worker_to_remove)
        except ValueError:
            logger.warning(f"No se pudo encontrar el worker en la lista para eliminar.")

    def set_ui_busy(self, busy: bool):
        """Bloquea o desbloquea los botones principales de la GUI."""
        self.is_task_running = busy
        
        # --- ¡AQUÍ ESTÁ LA CORRECCIÓN! ---
        # Deshabilitamos los únicos dos botones que existen en la barra principal.
        self.refresh_button.setEnabled(not busy)
        self.actions_menu_button.setEnabled(not busy)
        # --- FIN DE LA CORRECCIÓN ---
        
        if busy:
            self.statusBar().showMessage("Procesando tarea en segundo plano...")
        else:
            self.statusBar().showMessage("Listo.", 2000)
            
        QApplication.processEvents()

    @Slot(Exception)
    def on_task_error(self, error: Exception):
        """
        Slot que se llama cuando un hilo emite un error.
        Muestra la alerta de error personalizada.
        """
        logger.critical(f"Error en el hilo de trabajo: {error}")
        self.last_error = error

        titulo = "Error de Tarea"
        
        if isinstance(error, ScrapingFase1Error):
            titulo = "Error en Scraping (Fase 1)"
            mensaje = (
                "La tarea falló al intentar obtener el listado de CAs.\n\n"
                f"Detalle: {error}\n\n"
                "Posibles causas:\n"
                "- No hay conexión a internet.\n"
                "- El sitio web de Mercado Público cambió su API (revisar X-Api-Key o URLs)."
            )
        
        elif isinstance(error, DatabaseLoadError):
            titulo = "Error en Base de Datos (Load)"
            mensaje = (
                "La tarea falló al intentar guardar los datos crudos en la BD.\n\n"
                f"Detalle: {error}\n\n"
                "Posibles causas:\n"
                "- La base de datos está desconectada o llena.\n"
                "- Un campo en el JSON de la API cambió (ej. 'nombre' ahora es 'name')."
            )

        elif isinstance(error, DatabaseTransformError):
            titulo = "Error en Base de Datos (Transform)"
            mensaje = (
                "La tarea falló al calcular los nuevos puntajes.\n\n"
                f"Detalle: {error}\n\n"
                "Posibles causas:\n"
                "- Error en la lógica del ScoreEngine.\n"
                "- Error al leer datos de la BD para recalcular."
            )

        elif isinstance(error, ScrapingFase2Error):
            titulo = "Error en Scraping (Fase 2)"
            mensaje = (
                "La tarea falló al intentar obtener el detalle de las fichas.\n\n"
                f"Detalle: {error}\n\n"
                "Posibles causas:\n"
                "- El sitio está bloqueando el scraping (Error 403).\n"
                "- La API de la ficha cambió (revisar la DevTool)."
            )

        elif isinstance(error, RecalculoError):
            titulo = "Error en Recálculo"
            mensaje = (
                "La tarea de Recálculo de Puntajes falló.\n\n"
                f"Detalle: {error}\n\n"
                "Posibles causas:\n"
                "- Error al leer las nuevas reglas de la BD.\n"
                "- Error al guardar los nuevos puntajes."
            )

        else:
            titulo = "Error Inesperado"
            mensaje = (
                "Ocurrió un error inesperado en la tarea en segundo plano:\n\n"
                f"{error}"
            )
        
        QMessageBox.critical(self, titulo, mensaje)
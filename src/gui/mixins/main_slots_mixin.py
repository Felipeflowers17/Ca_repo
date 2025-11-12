# -*- coding: utf-8 -*-
"""
Mixin para los Slots (acciones) de los botones principales.
(v7.0 - Piloto Automático)
- Añadidos slots 'auto' para los QTimers.
- 'reglas_actualizadas' renombrado a 'on_settings_changed'.
"""

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Slot 
import datetime # <-- ¡NUEVA IMPORTACIÓN!

from src.gui.gui_scraping_dialog import ScrapingDialog
from src.gui.gui_settings_dialog import GuiSettingsDialog
from src.utils.logger import configurar_logger

logger = configurar_logger(__name__)


class MainSlotsMixin:
    """
    Este Mixin maneja las acciones disparadas por los
    botones principales de la barra de herramientas
    (Scraping, Exportar, Recalcular, Configuración).
    """

    @Slot()
    def on_open_scraping_dialog(self):
        # ... (sin cambios)
        if self.is_task_running:
            return
        dialog = ScrapingDialog(self)
        dialog.start_scraping.connect(self.on_start_full_scraping)
        dialog.exec()

    @Slot(dict)
    def on_start_full_scraping(self, config: dict):
        # ... (sin cambios)
        logger.info(f"Recibida configuración de scraping: {config}")
        task_to_run = None
        if config["mode"] == "to_db":
            task_to_run = self.etl_service.run_etl_live_to_db
        elif config["mode"] == "to_json":
            task_to_run = self.etl_service.run_etl_live_to_json
        
        if task_to_run is None:
            return
            
        self.start_task(
            task=task_to_run,
            on_result=lambda: logger.info("Proceso ETL completo OK"),
            on_error=self.on_task_error,
            on_finished=self.on_scraping_completed,
            on_progress=self.on_progress_update,
            task_args=(config,),
        )

    @Slot()
    def on_scraping_completed(self):
        # ... (sin cambios)
        self.set_ui_busy(False)
        if self.last_error:
            logger.warning("Proceso de Scraping finalizado con errores.")
        else:
            QMessageBox.information(self, "Proceso Completado", "La tarea de scraping ha finalizado.")
        self.on_load_data_thread()

    @Slot()
    def on_exportar_excel_thread(self):
        # ... (sin cambios)
        if self.is_task_running:
            return
        logger.info("Solicitud de exportar Excel (con hilos)...")
        self.last_export_path = None
        self.start_task(
            task=self.excel_service.generar_reporte_excel,
            on_result=lambda path: setattr(self, 'last_export_path', path),
            on_error=self.on_task_error,
            on_finished=self.on_export_excel_completed,
        )

    @Slot()
    def on_export_excel_completed(self):
        # ... (sin cambios)
        self.set_ui_busy(False)
        if self.last_error:
            logger.error("La exportación a Excel falló.")
        elif self.last_export_path:
            logger.info("Exportación a Excel finalizada.")
            QMessageBox.information(self, "Exportación Exitosa", f"Reporte guardado en:\n{self.last_export_path}")

    @Slot()
    def on_open_settings_dialog(self):
        """Abre el diálogo de configuración de reglas."""
        if self.is_task_running:
            return
        logger.debug("Abriendo diálogo de configuración...")
        # --- ¡NUEVO! Pasamos el settings_manager ---
        dialog = GuiSettingsDialog(self.db_service, self.settings_manager, self)
        # --- ¡SEÑAL RENOMBRADA! ---
        dialog.settings_changed.connect(self.on_settings_changed)
        dialog.exec()

    @Slot()
    def on_settings_changed(self):
        """
        Se llama cuando el diálogo de settings confirma cambios
        (en keywords O automatización).
        """
        logger.info("Configuración actualizada por el usuario.")
        try:
            # 1. Recargar reglas del ScoreEngine (por si cambiaron keywords)
            self.score_engine.recargar_reglas()
            logger.info("Reglas de ScoreEngine recargadas.")
            
            # 2. Recargar configuración de timers (por si cambió automatización)
            self.reload_timers_config() # Este método está en gui_main.py
            
            QMessageBox.information(
                self, "Configuración Actualizada",
                "La configuración de reglas y/o automatización se ha guardado.\n"
                "Los cambios en los timers se aplicarán de inmediato."
            )
        except Exception as e:
            logger.error(f"Error al aplicar nueva configuración: {e}")
            QMessageBox.critical(self, "Error", f"No se pudieron aplicar los cambios:\n{e}")

    @Slot()
    def on_run_recalculate_thread(self):
        # ... (sin cambios)
        if self.is_task_running:
            return
        confirm = QMessageBox.question(
            self, "Confirmar Recálculo",
            "Esto recalculará los puntajes de Fase 1 para todas las CAs...",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.No:
            return
        logger.info("Iniciando recálculo total de puntajes (con hilo)...")
        self.start_task(
            task=self.etl_service.run_recalculo_total_fase_1,
            on_result=lambda: logger.info("Recálculo completado OK"),
            on_error=self.on_task_error,
            on_finished=self.on_recalculate_finished,
            on_progress=self.on_progress_update,
        )

    @Slot()
    def on_recalculate_finished(self):
        # ... (sin cambios)
        self.set_ui_busy(False)
        if self.last_error:
            logger.warning("Proceso de Recálculo finalizado con errores.")
        else:
            QMessageBox.information(self, "Proceso Completado", "Se han recalculado todos los puntajes.")
        self.on_load_data_thread()

    @Slot()
    def on_run_fase2_update_thread(self, skip_confirm=False): # <-- ¡Argumento añadido!
        """
        Inicia el hilo de actualización de fichas (Fase 2) para
        las pestañas 2, 3 y 4.
        """
        if self.is_task_running:
            return
        
        # Si no es automático, pedir confirmación
        if not skip_confirm:
            confirm = QMessageBox.question(
                self, "Confirmar Actualización de Fichas",
                "Esto buscará en la web las fichas de todas las CAs en las pestañas...",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.No:
                return

        logger.info("Iniciando actualización de Fichas Fase 2 (con hilo)...")
        self.start_task(
            task=self.etl_service.run_fase2_update,
            on_result=lambda: logger.info("Actualización de Fichas completada OK"),
            on_error=self.on_task_error,
            on_finished=self.on_fase2_update_finished,
            on_progress=self.on_progress_update,
        )

    @Slot()
    def on_fase2_update_finished(self):
        # ... (sin cambios)
        self.set_ui_busy(False)
        if self.last_error:
            logger.warning("Proceso de Actualización de Fichas finalizado con errores.")
        else:
            # No mostrar pop-up si fue automático (sería molesto)
            if not self.is_task_running_auto: # (Necesitamos añadir este flag)
                 QMessageBox.information(self, "Proceso Completado", "Se han actualizado las fichas seleccionadas.")
        self.on_load_data_thread()

    # ---
    # --- ¡NUEVOS MÉTODOS PARA PILOTO AUTOMÁTICO! ---
    # ---
    
    @Slot()
    def on_start_full_scraping_auto(self):
        """
        Slot para el QTimer de Fase 1.
        Inicia el scraping de Fase 1-2 sin confirmación.
        """
        logger.info("PILOTO AUTOMÁTICO: Disparado Timer (Fase 1 - Búsqueda Diaria)")
        
        # El "Guardia" que previene bloqueos
        if self.is_task_running:
            logger.warning("PILOTO AUTOMÁTICO (Fase 1): Omitido. Otra tarea ya está en ejecución.")
            return

        # Configuración para buscar CAs del día anterior
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        config = {
            "mode": "to_db",
            "date_from": yesterday,
            "date_to": today,
            "max_paginas": 100 # Un límite alto para asegurar todo
        }
        
        logger.info("PILOTO AUTOMÁTICO (Fase 1): Iniciando tarea...")
        self.start_task(
            task=self.etl_service.run_etl_live_to_db,
            on_result=lambda: logger.info("PILOTO AUTOMÁTICO (Fase 1): Proceso ETL completo OK"),
            on_error=self.on_task_error,
            on_finished=self.on_auto_task_finished, # Un 'finished' silencioso
            on_progress=self.on_progress_update,
            task_args=(config,),
        )

    @Slot()
    def on_run_fase2_update_thread_auto(self):
        """
        Slot para el QTimer de Fase 2.
        Inicia la actualización de fichas sin confirmación.
        """
        logger.info("PILOTO AUTOMÁTICO: Disparado Timer (Fase 2 - Actualización Fichas)")
        
        # El "Guardia" que previene bloqueos
        if self.is_task_running:
            logger.warning("PILOTO AUTOMÁTICO (Fase 2): Omitido. Otra tarea ya está en ejecución.")
            return

        logger.info("PILOTO AUTOMÁTICO (Fase 2): Iniciando tarea...")
        self.start_task(
            task=self.etl_service.run_fase2_update,
            on_result=lambda: logger.info("PILOTO AUTOMÁTICO (Fase 2): Actualización de Fichas OK"),
            on_error=self.on_task_error,
            on_finished=self.on_auto_task_finished, # Un 'finished' silencioso
            on_progress=self.on_progress_update,
        )

    @Slot()
    def on_auto_task_finished(self):
        """
        Callback 'finished' silencioso para tareas automáticas.
        Solo limpia los flags y refresca los datos, sin pop-ups.
        """
        self.set_ui_busy(False)
        if self.last_error:
            logger.warning(f"PILOTO AUTOMÁTICO: Tarea finalizada con errores: {self.last_error}")
        else:
            logger.info("PILOTO AUTOMÁTICO: Tarea finalizada exitosamente.")
        
        # Siempre refrescar los datos al terminar
        self.on_load_data_thread()
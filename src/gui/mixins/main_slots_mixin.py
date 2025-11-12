# -*- coding: utf-8 -*-
"""
Mixin para los Slots (acciones) de los botones principales.
(v6.3 - Añadido slot para actualizar fichas de Fase 2)
"""

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Slot 

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
        # ... (el resto del archivo es idéntico)
        if self.is_task_running:
            return
        dialog = ScrapingDialog(self)
        dialog.start_scraping.connect(self.on_start_full_scraping)
        dialog.exec()

    @Slot(dict)
    def on_start_full_scraping(self, config: dict):
        """Inicia el hilo de scraping/ETL."""
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
        """Se llama al finalizar el hilo de scraping."""
        self.set_ui_busy(False)
        if self.last_error:
            logger.warning("Proceso de Scraping finalizado con errores.")
        else:
            QMessageBox.information(self, "Proceso Completado", "La tarea de scraping ha finalizado.")
        # Refresca los datos en todas las pestañas
        self.on_load_data_thread()

    @Slot()
    def on_exportar_excel_thread(self):
        """Inicia el hilo de exportación a Excel."""
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
        """Se llama al finalizar la exportación de Excel."""
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
        dialog = GuiSettingsDialog(self.db_service, self)
        dialog.reglas_actualizadas.connect(self.on_reglas_actualizadas)
        dialog.exec()

    @Slot()
    def on_reglas_actualizadas(self):
        """Se llama cuando el diálogo de settings confirma cambios."""
        logger.info("Reglas actualizadas por el usuario. Recargando ScoreEngine...")
        try:
            self.score_engine.recargar_reglas()
            QMessageBox.information(
                self, "Reglas Actualizadas",
                "Las reglas de puntuación se han actualizado.\n"
                "Se recomienda ejecutar un 'Recálculo de Puntajes'."
            )
        except Exception as e:
            logger.error(f"Error al recargar reglas del ScoreEngine: {e}")
            QMessageBox.critical(self, "Error", f"No se pudieron recargar las reglas:\n{e}")

    @Slot()
    def on_run_recalculate_thread(self):
        """Inicia el hilo de recálculo de puntajes."""
        if self.is_task_running:
            return
            
        confirm = QMessageBox.question(
            self, "Confirmar Recálculo",
            "Esto recalculará los puntajes de Fase 1 para todas las CAs "
            "que no estén en seguimiento (favoritas/ofertadas).\n\n"
            "Esta operación puede tardar varios segundos.\n"
            "¿Desea continuar?",
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
        """Se llama al finalizar el hilo de recálculo."""
        self.set_ui_busy(False)
        if self.last_error:
            logger.warning("Proceso de Recálculo finalizado con errores.")
        else:
            QMessageBox.information(self, "Proceso Completado", "Se han recalculado todos los puntajes.")
        # Refresca los datos en todas las pestañas
        self.on_load_data_thread()

    # ---
    # --- ¡NUEVOS MÉTODOS PARA LA MEJORA 3! ---
    # ---
    @Slot()
    def on_run_fase2_update_thread(self):
        """
        Inicia el hilo de actualización de fichas (Fase 2) para
        las pestañas 2, 3 y 4.
        """
        if self.is_task_running:
            return
        
        confirm = QMessageBox.question(
            self, "Confirmar Actualización de Fichas",
            "Esto buscará en la web las fichas de todas las CAs en las pestañas "
            "'Relevantes', 'Seguimiento' y 'Ofertadas' para actualizar sus datos (descripción, productos) y puntajes.\n\n"
            "Esta operación puede tardar varios minutos.\n"
            "¿Desea continuar?",
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
        """Se llama al finalizar el hilo de actualización de fichas."""
        self.set_ui_busy(False)
        if self.last_error:
            logger.warning("Proceso de Actualización de Fichas finalizado con errores.")
        else:
            QMessageBox.information(self, "Proceso Completado", "Se han actualizado las fichas seleccionadas.")
        # Refresca los datos en todas las pestañas
        self.on_load_data_thread()
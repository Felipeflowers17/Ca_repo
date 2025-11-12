# -*- coding: utf-8 -*-
"""
Ventana Principal de la Aplicación (MainWindow).

Versión (Fase 8.1 - Piloto Automático Corregido)
- Corregida la importación de 'db.db_service' a 'src.db.db_service'.
"""

import sys
from typing import List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QStatusBar, QTableView, QLineEdit,
    QMenu, QMessageBox
)
from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QAction, QStandardItemModel

# Importaciones de Lógica de Negocio (Servicios)
from src.gui.gui_worker import Worker
from src.utils.logger import configurar_logger
from src.utils.settings_manager import SettingsManager
from src.db.session import SessionLocal

# ---
# --- ¡LÍNEA CORREGIDA! ---
# ---
from src.db.db_service import DbService # <-- Antes decía 'from db.db_service...'
# ---
# ---
from src.logic.etl_service import EtlService
from src.logic.excel_service import ExcelService
from src.logic.score_engine import ScoreEngine
from src.scraper.scraper_service import ScraperService

# Importamos los 5 Mixins
from .mixins.threading_mixin import ThreadingMixin
from .mixins.main_slots_mixin import MainSlotsMixin
from .mixins.data_loader_mixin import DataLoaderMixin
from .mixins.context_menu_mixin import ContextMenuMixin
from .mixins.table_manager_mixin import TableManagerMixin


logger = configurar_logger(__name__)


class MainWindow(
    QMainWindow,
    ThreadingMixin,
    MainSlotsMixin,
    DataLoaderMixin,
    ContextMenuMixin,
    TableManagerMixin
):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Monitor de Compras Ágiles (v3.0 Dinámico)")
        self.setGeometry(100, 100, 1200, 700)

        self.thread_pool = QThreadPool.globalInstance()
        self.running_workers: List['Worker'] = []
        self.is_task_running = False
        self.last_error: Exception | None = None
        self.last_export_path: str | None = None

        try:
            self.settings_manager = SettingsManager()
            
            self.db_service = DbService(SessionLocal)
            self.scraper_service = ScraperService()
            self.excel_service = ExcelService(self.db_service)
            self.score_engine = ScoreEngine(self.db_service) 
            self.etl_service = EtlService(
                self.db_service, self.scraper_service, self.score_engine
            )
        except Exception as e:
            logger.critical(f"Error al inicializar los servicios: {e}")
            QMessageBox.critical(
                self, "Error Crítico de Inicialización",
                f"No se pudieron iniciar los servicios de la aplicación.\n"
                f"Verifique la configuración (.env) y la conexión a la BD.\n\nError: {e}",
            )
            sys.exit(1)

        # --- Declaraciones de atributos (para el type-checker) ---
        self.refresh_button: QPushButton | None = None
        self.actions_menu_button: QPushButton | None = None
        self.action_update_fichas: QAction | None = None
        self.table_tab1: QTableView | None = None
        self.table_tab2: QTableView | None = None
        self.table_tab3: QTableView | None = None
        self.table_tab4: QTableView | None = None
        self.model_tab1: QStandardItemModel | None = None
        self.model_tab2: QStandardItemModel | None = None
        self.model_tab3: QStandardItemModel | None = None
        self.model_tab4: QStandardItemModel | None = None
        self.search_tab1: QLineEdit | None = None
        self.search_tab2: QLineEdit | None = None
        self.search_tab3: QLineEdit | None = None
        self.search_tab4: QLineEdit | None = None

        # --- Declaración de Timers ---
        self.timer_fase1: QTimer | None = None
        self.timer_fase2: QTimer | None = None
        
        self._setup_ui()
        self._connect_signals()
        
        # --- Iniciar timers después de conectar señales ---
        self._setup_timers()

        logger.info("Ventana principal (GUI) inicializada.")
        self.on_load_data_thread() # Carga inicial de datos

    def _setup_ui(self):
        """Crea todos los widgets de la interfaz."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Panel de Botones ---
        button_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refrescar Datos")
        self.refresh_button.setFixedHeight(40)
        button_layout.addWidget(self.refresh_button)

        button_layout.addStretch()

        self.actions_menu_button = QPushButton("Acciones ▾")
        self.actions_menu_button.setFixedHeight(40)
        
        self.actions_menu = QMenu(self)
        
        self.action_scrape = QAction("Iniciar Nuevo Scraping...", self)
        self.actions_menu.addAction(self.action_scrape)
        
        self.action_update_fichas = QAction("Actualizar Fichas (Tabs 2-4)", self)
        self.actions_menu.addAction(self.action_update_fichas)
        
        self.action_export = QAction("Exportar Reporte Excel", self)
        self.actions_menu.addAction(self.action_export)
        
        self.actions_menu.addSeparator()

        self.config_submenu = QMenu("Configuración", self)
        
        self.action_open_settings = QAction("Configuración y Automatización...", self)
        self.config_submenu.addAction(self.action_open_settings)
        
        self.action_recalculate = QAction("Recalcular Puntajes", self)
        self.config_submenu.addAction(self.action_recalculate)
        
        self.actions_menu.addMenu(self.config_submenu)
        
        self.actions_menu_button.setMenu(self.actions_menu)

        button_layout.addWidget(self.actions_menu_button)
        main_layout.addLayout(button_layout)
        # --- Fin Panel de Botones ---

        # --- Sistema de Pestañas (QTabWidget) ---
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        (
            self.tab_candidatas, self.search_tab1, self.model_tab1, self.table_tab1,
        ) = self._crear_pestaña_tabla("Filtrar por Código, Nombre u Organismo...", "tab1_simple")
        self.tabs.addTab(self.tab_candidatas, "CAs Candidatas (Fase 1)")

        (
            self.tab_relevantes, self.search_tab2, self.model_tab2, self.table_tab2,
        ) = self._crear_pestaña_tabla("Filtrar por Código, Nombre u Organismo...", "tab2_detallada")
        self.tabs.addTab(self.tab_relevantes, "CAs Relevantes (Fase 2)")

        (
            self.tab_seguimiento, self.search_tab3, self.model_tab3, self.table_tab3,
        ) = self._crear_pestaña_tabla("Filtrar por Código, Nombre u Organismo...", "tab3_detallada")
        self.tabs.addTab(self.tab_seguimiento, "CAs en Seguimiento (Favoritos)")

        (
            self.tab_ofertadas, self.search_tab4, self.model_tab4, self.table_tab4,
        ) = self._crear_pestaña_tabla("Filtrar por Código, Nombre u Organismo...", "tab4_detallada")
        self.tabs.addTab(self.tab_ofertadas, "CAs Ofertadas")

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Listo.")

    def _connect_signals(self):
        """Conecta todas las señales de la GUI a sus slots."""
        
        self.refresh_button.clicked.connect(self.on_load_data_thread)
        
        # Acciones del Menú
        self.action_scrape.triggered.connect(self.on_open_scraping_dialog)
        self.action_update_fichas.triggered.connect(self.on_run_fase2_update_thread)
        self.action_export.triggered.connect(self.on_exportar_excel_thread)
        self.action_open_settings.triggered.connect(self.on_open_settings_dialog)
        self.action_recalculate.triggered.connect(self.on_run_recalculate_thread)
        
        # Barras de búsqueda
        self.search_tab1.textChanged.connect(self.on_search_tab1_changed)
        self.search_tab2.textChanged.connect(self.on_search_tab2_changed)
        self.search_tab3.textChanged.connect(self.on_search_tab3_changed)
        self.search_tab4.textChanged.connect(self.on_search_tab4_changed)

        # Menú contextual
        self.table_tab1.customContextMenuRequested.connect(self.mostrar_menu_contextual)
        self.table_tab2.customContextMenuRequested.connect(self.mostrar_menu_contextual)
        self.table_tab3.customContextMenuRequested.connect(self.mostrar_menu_contextual)
        self.table_tab4.customContextMenuRequested.connect(self.mostrar_menu_contextual)
    
    def _setup_timers(self):
        """Configura e inicia los QTimers para tareas automáticas."""
        logger.info("Configurando timers de automatización...")
        
        # --- Timer 1: Búsqueda de Nuevas CAs (Fase 1) ---
        self.timer_fase1 = QTimer(self)
        self.timer_fase1.timeout.connect(self.on_start_full_scraping_auto)
        
        # --- Timer 2: Actualización de CAs (Fase 2) ---
        self.timer_fase2 = QTimer(self)
        self.timer_fase2.timeout.connect(self.on_run_fase2_update_thread_auto)

        # Cargar la configuración e iniciar/detener los timers
        self.reload_timers_config()

    def reload_timers_config(self):
        """Lee la config y (re)inicia los timers. Se llama al inicio y al cambiar settings."""
        try:
            # Recargar la configuración del archivo
            self.settings_manager.load_settings()
            
            # Configurar Timer 1 (Fase 1)
            intervalo_f1_horas = self.settings_manager.get_setting("auto_fase1_intervalo_horas")
            if intervalo_f1_horas > 0:
                intervalo_ms = intervalo_f1_horas * 60 * 60 * 1000 # horas a ms
                self.timer_fase1.start(intervalo_ms)
                logger.info(f"Timer (Fase 1) iniciado. Se ejecutará cada {intervalo_f1_horas} horas.")
            else:
                self.timer_fase1.stop()
                logger.info("Timer (Fase 1) detenido (intervalo 0).")

            # Configurar Timer 2 (Fase 2)
            intervalo_f2_min = self.settings_manager.get_setting("auto_fase2_intervalo_minutos")
            if intervalo_f2_min > 0:
                intervalo_ms = intervalo_f2_min * 60 * 1000 # minutos a ms
                self.timer_fase2.start(intervalo_ms)
                logger.info(f"Timer (Fase 2) iniciado. Se ejecutará cada {intervalo_f2_min} minutos.")
            else:
                self.timer_fase2.stop()
                logger.info("Timer (Fase 2) detenido (intervalo 0).")

        except Exception as e:
            logger.error(f"Error al configurar o (re)iniciar timers: {e}")

# --- PUNTO DE ENTRADA DE LA GUI ---

def run_gui():
    logger.info("Iniciando la aplicación Qt...")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
# -*- coding: utf-8 -*-
"""
Diálogo de Configuración de Reglas.

Este archivo define el QDialog (ventana emergente) que permite
al usuario gestionar las reglas de puntuación (Keywords y Organismos).
Implementa la GUI para la Idea #2.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QLineEdit,
    QTabWidget,
    QWidget,
    QTableWidget,
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QTableWidgetItem,
)
from PySide6.QtCore import Signal, Slot, Qt

from src.utils.logger import configurar_logger
from src.db.db_service import DbService
# Importar los modelos necesarios para type hinting
from src.db.db_models import CaKeyword, CaOrganismo, CaOrganismoPrioritario

logger = configurar_logger(__name__)


class GuiSettingsDialog(QDialog):
    """
    Ventana de diálogo modal para gestionar las reglas de puntuación.
    """

    # Señal que se emite si se realiza un cambio
    reglas_actualizadas = Signal()

    def __init__(self, db_service: DbService, parent: QWidget | None = None):
        """
        Inicializa el diálogo.

        Args:
            db_service: La instancia del servicio de BD (inyectada).
            parent: El widget padre (usualmente la MainWindow).
        """
        super().__init__(parent)
        self.setWindowTitle("Configuración del Motor de Puntuación")
        self.setModal(True)
        self.setMinimumSize(700, 500)

        self.db_service = db_service
        self.reglas_han_cambiado = False # Flag para saber si emitir la señal

        # --- Layout Principal ---
        layout = QVBoxLayout(self)

        # --- Sistema de Pestañas ---
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Crear las dos pestañas
        self.tab_keywords = self._crear_tab_keywords()
        self.tab_organismos = self._crear_tab_organismos()

        self.tabs.addTab(self.tab_keywords, "Gestión de Keywords")
        self.tabs.addTab(self.tab_organismos, "Gestión de Organismos Prioritarios")

        # --- Botón de Cierre ---
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.on_close)
        layout.addWidget(button_box)

        # Cargar los datos iniciales
        try:
            self._load_all_data()
        except Exception as e:
            logger.error(f"Error fatal al cargar datos para el diálogo: {e}")
            QMessageBox.critical(self, "Error de Carga", f"No se pudieron cargar los datos de configuración desde la BD:\n{e}")

    @Slot()
    def on_close(self):
        """Se llama al presionar 'Cerrar'."""
        if self.reglas_han_cambiado:
            self.reglas_actualizadas.emit()
        self.reject() # Cierra el diálogo

    def _load_all_data(self):
        """Carga los datos en ambas tablas."""
        self._load_keywords_table()
        self._load_organismos_table()
        self._load_organismos_combobox()

    # --- Pestaña de Keywords ---

    def _crear_tab_keywords(self) -> QWidget:
        """Crea el widget de la pestaña de Keywords."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Columna Izquierda (Tabla)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Keywords Actuales:"))

        self.keywords_table = QTableWidget()
        self.keywords_table.setColumnCount(4) # ID (oculto), Keyword, Tipo, Puntos
        self.keywords_table.setHorizontalHeaderLabels(["ID", "Keyword", "Tipo", "Puntos"])
        self.keywords_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.keywords_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.keywords_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.keywords_table.setColumnHidden(0, True) # Ocultar el ID
        left_layout.addWidget(self.keywords_table)

        self.kw_delete_button = QPushButton("Eliminar Keyword Seleccionada")
        self.kw_delete_button.clicked.connect(self._on_delete_keyword)
        left_layout.addWidget(self.kw_delete_button)

        # Columna Derecha (Añadir)
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Añadir Nueva Keyword:"))

        right_layout.addWidget(QLabel("Palabra (ej. 'notebook', 'servicio'):"))
        self.kw_input = QLineEdit()
        right_layout.addWidget(self.kw_input)

        right_layout.addWidget(QLabel("Tipo de Keyword:"))
        self.kw_tipo_combo = QComboBox()
        self.kw_tipo_combo.addItem("Título Positivo (Suma)", "titulo_pos")
        self.kw_tipo_combo.addItem("Título Negativo (Resta)", "titulo_neg")
        self.kw_tipo_combo.addItem("Producto (Suma)", "producto")
        right_layout.addWidget(self.kw_tipo_combo)

        right_layout.addWidget(QLabel("Puntos (ej. 5 o -10):"))
        self.kw_puntos_spin = QSpinBox()
        self.kw_puntos_spin.setRange(-100, 100)
        self.kw_puntos_spin.setValue(5)
        right_layout.addWidget(self.kw_puntos_spin)

        self.kw_add_button = QPushButton("Añadir Keyword")
        self.kw_add_button.clicked.connect(self._on_add_keyword)
        right_layout.addWidget(self.kw_add_button)

        right_layout.addStretch()

        layout.addLayout(left_layout, 3)
        layout.addLayout(right_layout, 1)
        return widget

    def _load_keywords_table(self):
        """Recarga la tabla de keywords desde la BD."""
        self.keywords_table.setRowCount(0)
        try:
            keywords = self.db_service.get_all_keywords()
            self.keywords_table.setRowCount(len(keywords))
            for row, kw in enumerate(keywords):
                self.keywords_table.setItem(row, 0, QTableWidgetItem(str(kw.keyword_id)))
                self.keywords_table.setItem(row, 1, QTableWidgetItem(kw.keyword))
                self.keywords_table.setItem(row, 2, QTableWidgetItem(kw.tipo))
                self.keywords_table.setItem(row, 3, QTableWidgetItem(str(kw.puntos)))
        except Exception as e:
            logger.error(f"Error al cargar keywords: {e}")
            QMessageBox.critical(self, "Error", f"No se pudieron cargar las keywords: {e}")

    @Slot()
    def _on_add_keyword(self):
        """Se llama al hacer clic en 'Añadir Keyword'."""
        keyword = self.kw_input.text().strip().lower()
        tipo = self.kw_tipo_combo.currentData()
        puntos = self.kw_puntos_spin.value()

        if not keyword:
            QMessageBox.warning(self, "Error", "El campo 'Keyword' no puede estar vacío.")
            return

        try:
            self.db_service.add_keyword(keyword, tipo, puntos)
            self.reglas_han_cambiado = True
            self.kw_input.clear()
            self._load_keywords_table() # Recargar la tabla
        except Exception as e:
            logger.error(f"Error al añadir keyword: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo añadir la keyword (¿ya existe?):\n{e}")

    @Slot()
    def _on_delete_keyword(self):
        """Se llama al hacer clic en 'Eliminar Keyword'."""
        selected_items = self.keywords_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "Seleccione una fila para eliminar.")
            return

        row = selected_items[0].row()
        keyword_id_text = self.keywords_table.item(row, 0).text()
        keyword_id = int(keyword_id_text)
        keyword_texto = self.keywords_table.item(row, 1).text()

        confirm = QMessageBox.question(
            self,
            "Confirmar",
            f"¿Está seguro de que quiere eliminar la keyword '{keyword_texto}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.db_service.delete_keyword(keyword_id)
                self.reglas_han_cambiado = True
                self._load_keywords_table() # Recargar la tabla
            except Exception as e:
                logger.error(f"Error al eliminar keyword: {e}")
                QMessageBox.critical(self, "Error", f"No se pudo eliminar la keyword:\n{e}")

    # --- Pestaña de Organismos ---

    def _crear_tab_organismos(self) -> QWidget:
        """Crea el widget de la pestaña de Organismos."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Columna Izquierda (Tabla)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Organismos Prioritarios Actuales:"))

        self.org_table = QTableWidget()
        self.org_table.setColumnCount(3) # ID (oculto), Organismo, Puntos
        self.org_table.setHorizontalHeaderLabels(["ID", "Nombre Organismo", "Puntos"])
        self.org_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.org_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.org_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.org_table.setColumnHidden(0, True) # Ocultar el ID
        left_layout.addWidget(self.org_table)

        self.org_delete_button = QPushButton("Eliminar Organismo Seleccionado")
        self.org_delete_button.clicked.connect(self._on_delete_organismo)
        left_layout.addWidget(self.org_delete_button)

        # Columna Derecha (Añadir)
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Añadir Organismo Prioritario:"))

        right_layout.addWidget(QLabel("Seleccione Organismo:"))
        self.org_combo = QComboBox()
        self.org_combo.setEditable(True) # Permite buscar escribiendo
        right_layout.addWidget(self.org_combo)

        right_layout.addWidget(QLabel("Puntos (ej. 4):"))
        self.org_puntos_spin = QSpinBox()
        self.org_puntos_spin.setRange(0, 100)
        self.org_puntos_spin.setValue(4)
        right_layout.addWidget(self.org_puntos_spin)

        self.org_add_button = QPushButton("Añadir Organismo")
        self.org_add_button.clicked.connect(self._on_add_organismo)
        right_layout.addWidget(self.org_add_button)

        right_layout.addStretch()

        layout.addLayout(left_layout, 3)
        layout.addLayout(right_layout, 1)
        return widget

    def _load_organismos_table(self):
        """Recarga la tabla de organismos prioritarios desde la BD."""
        self.org_table.setRowCount(0)
        try:
            organismos = self.db_service.get_all_priority_organisms()
            self.org_table.setRowCount(len(organismos))
            for row, org in enumerate(organismos):
                self.org_table.setItem(row, 0, QTableWidgetItem(str(org.org_prio_id)))
                nombre = org.organismo.nombre if org.organismo else f"ID Desconocido ({org.organismo_id})"
                self.org_table.setItem(row, 1, QTableWidgetItem(nombre))
                self.org_table.setItem(row, 2, QTableWidgetItem(str(org.puntos)))
        except Exception as e:
            logger.error(f"Error al cargar organismos prioritarios: {e}")
            QMessageBox.critical(self, "Error", f"No se pudieron cargar los organismos: {e}")

    def _load_organismos_combobox(self):
        """Carga TODOS los organismos en el ComboBox de selección."""
        self.org_combo.clear()
        self.org_combo.addItem("--- Seleccione un organismo ---", None)
        try:
            # ¡Esto funciona gracias al volcado masivo que hicimos!
            organismos = self.db_service.get_all_organisms()
            for org in organismos:
                self.org_combo.addItem(org.nombre, org.organismo_id)
        except Exception as e:
            logger.error(f"Error al cargar ComboBox de organismos: {e}")

    @Slot()
    def _on_add_organismo(self):
        """Se llama al hacer clic en 'Añadir Organismo'."""
        organismo_id = self.org_combo.currentData()
        puntos = self.org_puntos_spin.value()

        if organismo_id is None:
            QMessageBox.warning(self, "Error", "Debe seleccionar un organismo de la lista.")
            return

        try:
            self.db_service.add_priority_organism(organismo_id, puntos)
            self.reglas_han_cambiado = True
            self._load_organismos_table() # Recargar la tabla
        except Exception as e:
            logger.error(f"Error al añadir organismo prioritario: {e}")
            QMessageBox.critical(self, "Error", f"No se pudo añadir el organismo (¿ya es prioritario?):\n{e}")

    @Slot()
    def _on_delete_organismo(self):
        """Se llama al hacer clic en 'Eliminar Organismo'."""
        selected_items = self.org_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "Seleccione una fila para eliminar.")
            return

        row = selected_items[0].row()
        org_prio_id_text = self.org_table.item(row, 0).text()
        org_prio_id = int(org_prio_id_text)
        org_texto = self.org_table.item(row, 1).text()

        confirm = QMessageBox.question(
            self,
            "Confirmar",
            f"¿Está seguro de que quiere eliminar '{org_texto}' de la lista de prioritarios?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.db_service.delete_priority_organism(org_prio_id)
                self.reglas_han_cambiado = True
                self._load_organismos_table() # Recargar la tabla
            except Exception as e:
                logger.error(f"Error al eliminar organismo prioritario: {e}")
                QMessageBox.critical(self, "Error", f"No se pudo eliminar el organismo:\n{e}")
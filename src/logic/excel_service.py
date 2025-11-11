# -*- coding: utf-8 -*-
"""
Servicio de Exportación a Excel.

(Versión 7.0 - Añadida fecha_cierre_segundo_llamado)
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from src.db.db_models import CaLicitacion

if TYPE_CHECKING:
    from src.db.db_service import DbService

from src.utils.logger import configurar_logger

logger = configurar_logger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
EXPORTS_DIR = BASE_DIR / "data" / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


class ExcelService:
    def __init__(self, db_service: "DbService"):
        self.db_service = db_service
        logger.info("ExcelService inicializado.")

    def _convertir_a_dataframe(self, licitaciones: list[CaLicitacion]) -> pd.DataFrame:
        """Helper para convertir la lista de objetos SQLAlchemy a un DataFrame."""
        datos = []
        for ca in licitaciones:
            
            fecha_cierre_ingenua = None
            if ca.fecha_cierre:
                fecha_cierre_ingenua = ca.fecha_cierre.replace(tzinfo=None)
            
            # --- ¡NUEVO CAMBIO! (Tu Punto 3) ---
            # Hacemos lo mismo para la nueva fecha
            fecha_cierre_2_ingenua = None
            if ca.fecha_cierre_segundo_llamado:
                fecha_cierre_2_ingenua = ca.fecha_cierre_segundo_llamado.replace(tzinfo=None)
            # --- FIN NUEVO CAMBIO ---

            datos.append(
                {
                    "Score": ca.puntuacion_final,
                    "Código CA": ca.codigo_ca,
                    "Nombre": ca.nombre,
                    "Descripcion": ca.descripcion,
                    "Organismo": ca.organismo.nombre if ca.organismo else "N/A",
                    "Dirección Entrega": ca.direccion_entrega,
                    "Estado": ca.estado_ca_texto,
                    "Fecha Publicación": ca.fecha_publicacion,
                    "Fecha Cierre": fecha_cierre_ingenua,
                    "Fecha Cierre 2do Llamado": fecha_cierre_2_ingenua, # <-- NUEVA
                    "Proveedores": ca.proveedores_cotizando,
                    "Productos": str(ca.productos_solicitados) if ca.productos_solicitados else None,
                    "Favorito": ca.seguimiento.es_favorito if ca.seguimiento else False,
                    "Ofertada": ca.seguimiento.es_ofertada if ca.seguimiento else False,
                }
            )

        if not datos:
            columnas = [
                "Score", "Código CA", "Nombre", "Descripcion", "Organismo", 
                "Dirección Entrega", "Estado", "Fecha Publicación", "Fecha Cierre",
                "Fecha Cierre 2do Llamado", "Proveedores", "Productos", 
                "Favorito", "Ofertada"
            ]
            return pd.DataFrame(columns=columnas)

        return pd.DataFrame(datos)

    def generar_reporte_excel(self) -> str:
        """
        Genera un reporte Excel con el contenido de las 4 pestañas.
        """
        logger.info("Iniciando generación de reporte Excel...")

        try:
            datos_tab1 = self.db_service.obtener_datos_tab1_candidatas()
            datos_tab2 = self.db_service.obtener_datos_tab2_relevantes()
            datos_tab3 = self.db_service.obtener_datos_tab3_seguimiento()
            datos_tab4 = self.db_service.obtener_datos_tab4_ofertadas()
        except Exception as e:
            logger.error(f"Error al obtener datos de la BD para Excel: {e}")
            raise e

        df_tab1 = self._convertir_a_dataframe(datos_tab1)
        df_tab2 = self._convertir_a_dataframe(datos_tab2)
        df_tab3 = self._convertir_a_dataframe(datos_tab3)
        df_tab4 = self._convertir_a_dataframe(datos_tab4)
        
        # --- ¡CAMBIO! ---
        # Quitamos columnas de la Pestaña 1 que no queremos
        columnas_tab_1 = [
            "Score", "Código CA", "Nombre", "Organismo", "Dirección Entrega",
            "Estado", "Fecha Publicación", "Fecha Cierre", "Proveedores"
        ]
        df_tab1 = df_tab1[columnas_tab_1]
        
        # Dejamos las columnas detalladas para las otras pestañas
        columnas_detalladas = [
            "Score", "Código CA", "Nombre", "Descripcion", "Organismo",
            "Dirección Entrega", "Estado", "Fecha Publicación", "Fecha Cierre",
            "Fecha Cierre 2do Llamado", "Productos", "Proveedores",
            "Favorito", "Ofertada"
        ]
        df_tab2 = df_tab2[columnas_detalladas]
        df_tab3 = df_tab3[columnas_detalladas]
        df_tab4 = df_tab4[columnas_detalladas]
        # --- FIN CAMBIO ---

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"Reporte_Compras_Agiles_{timestamp}.xlsx"
        ruta_salida = EXPORTS_DIR / nombre_archivo

        try:
            with pd.ExcelWriter(ruta_salida, engine="openpyxl") as writer:
                df_tab1.to_excel(writer, sheet_name="Candidatas", index=False)
                df_tab2.to_excel(writer, sheet_name="Relevantes", index=False)
                df_tab3.to_excel(writer, sheet_name="Seguimiento", index=False)
                df_tab4.to_excel(writer, sheet_name="Ofertadas", index=False)

            logger.info(f"Reporte Excel generado exitosamente en: {ruta_salida}")
            return str(ruta_salida)

        except Exception as e:
            logger.error(f"Error al escribir el archivo Excel: {e}", exc_info=True)
            raise e
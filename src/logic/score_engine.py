# -*- coding: utf-8 -*-
"""
Motor de Puntuación (Score Engine)

Versión (Fase 5.3 - Corrección de Importación Circular)
- Importa UMBRALES desde config.config
- Utiliza TYPE_CHECKING para evitar importaciones circulares.
"""

from src.utils.logger import configurar_logger
from src.db.db_models import CaKeyword, CaOrganismoPrioritario

# --- ¡CAMBIO DE IMPORTACIÓN! ---
# Importamos UMBRALES desde config.config
from config.config import UMBRAL_FASE_1

# Importamos el resto de constantes de score_config
from config.score_config import (
    PUNTOS_SEGUNDO_LLAMADO,
    PUNTOS_ALERTA_URGENCIA,
    PUNTOS_KEYWORD_PRODUCTO,
    KEYWORDS_PRODUCTOS_ALTO_VALOR
)
# --- FIN CAMBIO ---

from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.db_service import DbService

logger = configurar_logger(__name__)


class ScoreEngine:
    """
    Clase de servicio que maneja toda la lógica de puntuación.
    """

    def __init__(self, db_service: "DbService"):
        self.db_service = db_service
        logger.info("ScoreEngine inicializado (MODO DINÁMICO).")

        self.reglas_keywords: Dict[str, List[CaKeyword]] = {}
        self.reglas_organismos: Dict[str, int] = {}
        
        try:
            self.recargar_reglas()
        except Exception as e:
            logger.critical(f"Error fatal al cargar reglas iniciales desde la BD: {e}", exc_info=True)


    def recargar_reglas(self):
        logger.info("ScoreEngine: Recargando reglas desde la Base de Datos...")
        
        self.reglas_keywords = {}
        self.reglas_organismos = {}

        try:
            keywords_db = self.db_service.get_all_keywords()
            for kw in keywords_db:
                tipo = kw.tipo
                if tipo not in self.reglas_keywords:
                    self.reglas_keywords[tipo] = []
                self.reglas_keywords[tipo].append(kw)
            logger.info(f"Cargadas {len(keywords_db)} keywords dinámicas.")
        except Exception as e:
            logger.error(f"Error al cargar keywords desde la BD: {e}", exc_info=True)

        try:
            organismos_db = self.db_service.get_all_priority_organisms()
            for org_prio in organismos_db:
                if org_prio.organismo and org_prio.organismo.nombre:
                    nombre_norm = self._normalizar_texto(org_prio.organismo.nombre)
                    if nombre_norm:
                        self.reglas_organismos[nombre_norm] = org_prio.puntos
            logger.info(f"Cargados {len(self.reglas_organismos)} organismos prioritarios.")
        except Exception as e:
            logger.error(f"Error al cargar organismos desde la BD: {e}", exc_info=True)

    def _normalizar_texto(self, texto: str | None) -> str:
        if not texto:
            return ""
        return texto.lower().strip()

    def calcular_puntuacion_fase_1(self, licitacion_raw: dict) -> int:
        puntaje = 0
        
        nombre_norm = self._normalizar_texto(licitacion_raw.get("nombre"))
        organismo_norm = self._normalizar_texto(licitacion_raw.get("organismo_comprador"))
        estado_norm = self._normalizar_texto(licitacion_raw.get("estado_ca_texto"))
        
        if not nombre_norm:
            return 0

        if organismo_norm in self.reglas_organismos:
            puntaje += self.reglas_organismos[organismo_norm]
            
        if "segundo llamado" in estado_norm:
            puntaje += PUNTOS_SEGUNDO_LLAMADO
        if "alerta urgencia" in estado_norm:
            puntaje += PUNTOS_ALERTA_URGENCIA
            
        for kw_obj in self.reglas_keywords.get('titulo_pos', []):
            if kw_obj.keyword in nombre_norm:
                puntaje += kw_obj.puntos
                
        for kw_obj in self.reglas_keywords.get('titulo_neg', []):
            if kw_obj.keyword in nombre_norm:
                puntaje += kw_obj.puntos
        
        puntaje_final = max(0, puntaje)
        
        if puntaje_final >= UMBRAL_FASE_1:
            logger.debug(f"Fase 1 OK (Dinámico): '{nombre_norm}' | Score: {puntaje_final}")
        
        return puntaje_final

    def calcular_puntuacion_fase_2(self, datos_ficha: dict) -> int:
        puntaje = 0
        
        productos_raw = datos_ficha.get("productos_solicitados", [])
        if not productos_raw:
            return 0
            
        texto_productos = " ".join(
            self._normalizar_texto(item.get("nombre", "") + " " + item.get("descripcion", ""))
            for item in productos_raw
        )
        
        if not texto_productos:
            return 0
            
        if any(keyword in texto_productos for keyword in KEYWORDS_PRODUCTOS_ALTO_VALOR):
            puntaje += PUNTOS_KEYWORD_PRODUCTO
        
        logger.debug(f"Fase 2 | Texto Productos: '{texto_productos[:50]}...' | Score: {puntaje}")
        return max(0, puntaje)
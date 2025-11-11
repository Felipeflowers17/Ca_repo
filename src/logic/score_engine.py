# -*- coding: utf-8 -*-
"""
Motor de Puntuación (Score Engine)

Versión (Fase 7.2 - Corrige Error 'dict' en Recálculo)
- revierte calcular_puntuacion_fase_1 para aceptar un 'dict' (licitacion_raw).
- Añade un mapa de (nombre_organismo -> organismo_id) para traducir.
"""

from src.utils.logger import configurar_logger
from src.db.db_models import (
    CaKeyword, 
    CaOrganismoRegla,      
    TipoReglaOrganismo,  
    CaOrganismo, # <-- Importación añadida
)

from config.config import UMBRAL_FASE_1
from config.score_config import (
    PUNTOS_SEGUNDO_LLAMADO,
    PUNTOS_ALERTA_URGENCIA,
    PUNTOS_KEYWORD_PRODUCTO,
    KEYWORDS_PRODUCTOS_ALTO_VALOR
)

from typing import Dict, List, TYPE_CHECKING, Set, Optional # <-- 'Optional' añadido

if TYPE_CHECKING:
    from src.db.db_service import DbService
    # Ya no pasamos el objeto CaLicitacion
    # from src.db.db_models import CaLicitacion 

logger = configurar_logger(__name__)


class ScoreEngine:
    """
    Clase de servicio que maneja toda la lógica de puntuación.
    """

    def __init__(self, db_service: "DbService"):
        self.db_service = db_service
        logger.info("ScoreEngine inicializado (MODO DINÁMICO).")

        self.reglas_keywords: Dict[str, List[CaKeyword]] = {}
        
        self.reglas_prioritarias: Dict[int, int] = {}
        self.reglas_no_deseadas: Set[int] = set()
        
        # --- ¡NUEVO MAPA DE TRADUCCIÓN! ---
        # { "nombre normalizado": organismo_id }
        self.organismo_name_to_id_map: Dict[str, int] = {}
        
        try:
            self.recargar_reglas()
        except Exception as e:
            logger.critical(f"Error fatal al cargar reglas iniciales desde la BD: {e}", exc_info=True)


    def recargar_reglas(self):
        """
        Recarga todas las reglas (Keywords, Organismos y Mapa de Nombres) desde la BD.
        """
        logger.info("ScoreEngine: Recargando reglas desde la Base de Datos...")
        
        # Reseteo de reglas
        self.reglas_keywords = {}
        self.reglas_prioritarias = {}
        self.reglas_no_deseadas = set()
        self.organismo_name_to_id_map = {} # <-- Resetear mapa

        # 1. Cargar Keywords
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

        # 2. Cargar Reglas de Organismos (por ID)
        try:
            organismos_reglas_db = self.db_service.get_all_organismo_reglas()
            
            for regla in organismos_reglas_db:
                if not regla.organismo_id:
                    continue
                
                if regla.tipo == TipoReglaOrganismo.PRIORITARIO:
                    self.reglas_prioritarias[regla.organismo_id] = regla.puntos
                elif regla.tipo == TipoReglaOrganismo.NO_DESEADO:
                    self.reglas_no_deseadas.add(regla.organismo_id)

            logger.info(f"Cargadas {len(self.reglas_prioritarias)} reglas de organismos prioritarios.")
            logger.info(f"Cargadas {len(self.reglas_no_deseadas)} reglas de organismos no deseados.")
            
        except Exception as e:
            logger.error(f"Error al cargar reglas de organismos desde la BD: {e}", exc_info=True)

        # 3. Cargar Mapa de Nombres de Organismos
        try:
            # Usamos el método que ya existe en db_service
            all_organismos = self.db_service.get_all_organisms()
            for org in all_organismos:
                if org.nombre and org.organismo_id:
                    nombre_norm = self._normalizar_texto(org.nombre)
                    if nombre_norm:
                        self.organismo_name_to_id_map[nombre_norm] = org.organismo_id
            logger.info(f"Cargado mapa de {len(self.organismo_name_to_id_map)} nombres de organismos.")
        except Exception as e:
            logger.error(f"Error al cargar mapa de nombres de organismos: {e}", exc_info=True)


    def _normalizar_texto(self, texto: str | None) -> str:
        if not texto:
            return ""
        return texto.lower().strip()

    # --- ¡MÉTODO CORREGIDO! ---
    def calcular_puntuacion_fase_1(self, licitacion_raw: dict) -> int:
        """
        Calcula el puntaje Fase 1.
        NOTA: Acepta un 'dict' crudo (como en la v_original) y usa el
        mapa 'organismo_name_to_id_map' para traducir el nombre a ID.
        """
        
        # 1. Obtener el nombre del organismo y normalizarlo
        # (Usa "organismo_comprador" como en tu 'score_engine.py' original)
        organismo_nombre_norm = self._normalizar_texto(licitacion_raw.get("organismo_comprador"))
        
        # 2. Buscar el ID del organismo usando el mapa
        organismo_id: Optional[int] = None
        if organismo_nombre_norm:
            organismo_id = self.organismo_name_to_id_map.get(organismo_nombre_norm)

        # 3. Lógica de "No Deseado" (Mata-todo)
        # Si el ID fue encontrado Y está en la lista de no deseados
        if organismo_id is not None and organismo_id in self.reglas_no_deseadas:
            logger.debug(f"Fase 1 SKIP (No Deseado): '{licitacion_raw.get('nombre')}' | Org: {organismo_nombre_norm}")
            return -9999
        
        # Si pasa el filtro, calculamos el puntaje normal.
        puntaje = 0
        
        nombre_norm = self._normalizar_texto(licitacion_raw.get("nombre"))
        estado_norm = self._normalizar_texto(licitacion_raw.get("estado_ca_texto"))
        
        if not nombre_norm:
            return 0 # Si no tiene nombre, no se puede puntuar

        # 4. Lógica de "Prioritario"
        # Si el ID fue encontrado Y es prioritario, suma puntos.
        if organismo_id is not None and organismo_id in self.reglas_prioritarias:
            puntaje += self.reglas_prioritarias[organismo_id]
            
        # --- Lógica de Puntuación Estándar (sin cambios) ---
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
        
        # Aseguramos que el puntaje no sea negativo (a menos que sea -9999)
        puntaje_final = max(0, puntaje)
        
        if puntaje_final >= UMBRAL_FASE_1:
            logger.debug(f"Fase 1 OK (Dinámico): '{nombre_norm}' | Score: {puntaje_final}")
        
        return puntaje_final

    def calcular_puntuacion_fase_2(self, datos_ficha: dict) -> int:
        # --- (Sin cambios para esta mejora) ---
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
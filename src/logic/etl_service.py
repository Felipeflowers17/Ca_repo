import time
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, TYPE_CHECKING
from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from src.db.db_service import DbService
    from src.scraper.scraper_service import ScraperService
    from src.logic.score_engine import ScoreEngine

from config.config import MODO_HEADLESS, HEADERS_API
from src.utils.logger import configurar_logger

# --- ¡NUEVO! ---
# Importamos nuestras excepciones personalizadas
from src.utils.exceptions import (
    ScrapingFase1Error,
    DatabaseLoadError,
    DatabaseTransformError,
    ScrapingFase2Error,
    RecalculoError
)
# --- FIN NUEVO ---

logger = configurar_logger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]
EXPORTS_DIR = BASE_DIR / "data" / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


class EtlService:
    """
    Clase de servicio que orquesta los flujos de ETL.
    """

    def __init__(
        self,
        db_service: "DbService",
        scraper_service: "ScraperService",
        score_engine: "ScoreEngine",
    ):
        self.db_service = db_service
        self.scraper_service = scraper_service
        self.score_engine = score_engine
        logger.info("EtlService inicializado (dependencias inyectadas).")

    def _transform_puntajes_fase_1(self, progress_callback: Callable[[str], None]):
        logger.info("Iniciando (Transform) Fase 1...")
        
        # --- ¡CAMBIO! ---
        # Envolvemos la lógica en un try/except
        try:
            licitaciones_a_puntuar = (
                self.db_service.obtener_candidatas_para_recalculo_fase_1()
            )
            
            if not licitaciones_a_puntuar:
                logger.info("No hay CAs nuevas para puntuar (Fase 1).")
                return

            progress_callback(f"Puntuando {len(licitaciones_a_puntuar)} CAs nuevas...")
            logger.info(f"Se puntuarán {len(licitaciones_a_puntuar)} CAs nuevas...")
            
            lista_para_actualizar = []
            for licitacion in licitaciones_a_puntuar:
                item_raw = {
                    'nombre': licitacion.nombre,
                    'estado_ca_texto': licitacion.estado_ca_texto,
                    'organismo_comprador': licitacion.organismo.nombre if licitacion.organismo else ""
                }
                
                puntaje = self.score_engine.calcular_puntuacion_fase_1(item_raw)
                lista_para_actualizar.append((licitacion.ca_id, puntaje))
                
            self.db_service.actualizar_puntajes_fase_1_en_lote(lista_para_actualizar)
            logger.info("Transformación (T) Fase 1 completada. Puntajes actualizados.")

        except Exception as e:
            logger.error(f"Error en (Transform) Fase 1: {e}", exc_info=True)
            # Lanzamos nuestra excepción personalizada
            raise DatabaseTransformError(f"Error al calcular puntajes (Transform): {e}") from e
        # --- FIN CAMBIO ---

    def run_etl_live_to_db(
        self,
        progress_callback: Callable[[str], None],
        config: dict,
    ):
        date_from = config["date_from"]
        date_to = config["date_to"]
        max_paginas = config["max_paginas"]

        logger.info(f"Iniciando ETL (a BD)... Rango: {date_from} a {date_to}")
        progress_callback("Iniciando Fase 1 (Listado - Extract)...")

        # --- 1. EXTRACT (Fase 1) ---
        # --- ¡CAMBIO! ---
        try:
            filtros_fase_1 = {
                'date_from': date_from.strftime('%Y-%m-%d'),
                'date_to': date_to.strftime('%Y-%m-%d')
            }
            datos_crudos = self.scraper_service.run_scraper_listado(
                progress_callback, filtros_fase_1, max_paginas
            )
        except Exception as e:
            logger.critical(f"ETL (a BD) falló en (Extract): {e}")
            progress_callback(f"Error Crítico en Fase 1: {e}")
            raise ScrapingFase1Error(f"Fallo el scraping de listado (Fase 1): {e}") from e
        # --- FIN CAMBIO ---

        if not datos_crudos:
            logger.info("Fase 1 (Extract) no retornó datos. Terminando.")
            progress_callback("Fase 1 no encontró CAs.")
            return

        # --- 2. LOAD (Fase 1) ---
        # --- ¡CAMBIO! ---
        try:
            progress_callback(f"Cargando {len(datos_crudos)} CAs crudas a la BD...")
            self.db_service.insertar_o_actualizar_licitaciones_raw(datos_crudos)
        except Exception as e:
            logger.critical(f"ETL (a BD) falló en (Load): {e}")
            progress_callback(f"Error Crítico al cargar en BD: {e}")
            raise DatabaseLoadError(f"Fallo al guardar en BD (Load): {e}") from e
        # --- FIN CAMBIO ---
            
        # --- 3. TRANSFORM (Fase 1) ---
        # (Ya tiene su propio try/except dentro de la función)
        self._transform_puntajes_fase_1(progress_callback)


        # --- 4. OBTENER CANDIDATAS PARA FASE 2 ---
        progress_callback("Obteniendo candidatas para Fase 2...")
        try:
            candidatas = self.db_service.obtener_candidatas_para_fase_2()
        except Exception as e:
            logger.error(f"Error al obtener candidatas de la BD: {e}")
            progress_callback(f"Error de BD: {e}")
            # Usamos un error genérico aquí, ya que no es un fallo crítico del ETL
            raise e

        if not candidatas:
            logger.info("ETL (a BD) finalizado. No hay candidatas nuevas para Fase 2.")
            progress_callback("Proceso finalizado. No hay CAs nuevas para Fase 2.")
            return

        # --- 5. ELT (Fase 2) ---
        logger.info(f"Iniciando Fase 2 para {len(candidatas)} CAs.")
        progress_callback(f"Iniciando Fase 2. {len(candidatas)} CAs por procesar...")
        
        # --- ¡CAMBIO! ---
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=MODO_HEADLESS, slow_mo=500)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit(537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='es-CL'
                )
                page = context.new_page()
                page.set_extra_http_headers(HEADERS_API)
                
                exitosas = 0
                total = len(candidatas)
                for i, licitacion in enumerate(candidatas):
                    codigo_ca = licitacion.codigo_ca
                    puntos_fase_1 = licitacion.puntuacion_final
                    
                    logger.info(f"--- [Fase 2] Procesando {i+1}/{total}: {codigo_ca} ---")
                    
                    datos_ficha = self.scraper_service.scrape_ficha_detalle_api(
                        page, codigo_ca, progress_callback
                    )
                    
                    if datos_ficha is None:
                        logger.error(f"No se pudieron obtener datos para {codigo_ca}.")
                        continue
                    
                    puntos_fase_2 = self.score_engine.calcular_puntuacion_fase_2(datos_ficha)
                    puntuacion_total = (puntos_fase_1 or 0) + puntos_fase_2
                    
                    self.db_service.actualizar_ca_con_fase_2(
                        codigo_ca, datos_ficha, puntuacion_total
                    )
                    
                    exitosas += 1
                    time.sleep(1) 
                context.close()
                browser.close()
        except Exception as e:
            logger.critical(f"Fallo en el bucle de scraping Fase 2: {e}")
            progress_callback(f"Error Crítico en Fase 2: {e}")
            raise ScrapingFase2Error(f"Fallo el scraping de fichas (Fase 2): {e}") from e
        finally:
            logger.info(f"Resumen Fase 2: {exitosas}/{total} procesadas.")
        # --- FIN CAMBIO ---

        progress_callback("Proceso ETL (a BD) Completo.")
        logger.info("Proceso ETL (a BD) Completo.")

    def run_etl_live_to_json(
        self,
        progress_callback: Callable[[str], None],
        config: dict,
    ):
        # ... (Este método no necesita cambios, pero
        # por consistencia también le ponemos el try/except)
        
        date_from = config["date_from"]
        date_to = config["date_to"]
        max_paginas = config["max_paginas"]

        logger.info(f"Iniciando ETL (a JSON)... Rango: {date_from} a {date_to}")
        progress_callback(f"Iniciando Scraping (a JSON)...")

        try:
            filtros_fase_1 = {
                'date_from': date_from.strftime('%Y-%m-%d'),
                'date_to': date_to.strftime('%Y-%m-%d')
            }
            datos_crudos = self.scraper_service.run_scraper_listado(
                progress_callback, filtros_fase_1, max_paginas
            )
        except Exception as e:
            logger.critical(f"ETL (a JSON) falló en Fase 1 (Scraping): {e}")
            progress_callback(f"Error Crítico en Fase 1: {e}")
            raise ScrapingFase1Error(f"Fallo el scraping de listado (Fase 1): {e}") from e
            
        if not datos_crudos:
            logger.info("Fase 1 no retornó datos. Terminando.")
            progress_callback("Fase 1 no encontró CAs.")
            return

        # ... (el resto del guardado de JSON)
        # ...

    def run_recalculo_total_fase_1(
        self, 
        progress_callback: Callable[[str], None]
    ):
        logger.info("--- INICIANDO RECALCULO TOTAL DE PUNTAJES ---")
        
        # --- ¡CAMBIO! ---
        try:
            progress_callback("Recargando reglas desde la BD...")
            self.score_engine.recargar_reglas()
            logger.info("Reglas recargadas en ScoreEngine.")
            
            progress_callback("Obteniendo todas las CAs de Fase 1...")
            licitaciones_a_puntuar = (
                self.db_service.obtener_todas_candidatas_fase_1_para_recalculo()
            )
            
            if not licitaciones_a_puntuar:
                logger.info("No se encontraron CAs para recalcular.")
                progress_callback("No hay CAs para recalcular.")
                return

            logger.info(f"Se recalcularán {len(licitaciones_a_puntuar)} CAs...")
            progress_callback(f"Recalculando {len(licitaciones_a_puntuar)} CAs...")
            
            lista_para_actualizar = []
            for licitacion in licitaciones_a_puntuar:
                
                if licitacion.seguimiento and (
                    licitacion.seguimiento.es_favorito or licitacion.seguimiento.es_ofertada
                ):
                    continue 

                item_raw = {
                    'nombre': licitacion.nombre,
                    'estado_ca_texto': licitacion.estado_ca_texto,
                    'organismo_comprador': licitacion.organismo.nombre if licitacion.organismo else ""
                }
                
                puntaje = self.score_engine.calcular_puntuacion_fase_1(item_raw)
                
                lista_para_actualizar.append((licitacion.ca_id, puntaje))
                
            progress_callback("Guardando nuevos puntajes en la BD...")
            self.db_service.actualizar_puntajes_fase_1_en_lote(lista_para_actualizar)
            
            logger.info("--- RECALCULO TOTAL COMPLETADO ---")
            progress_callback("¡Recálculo completado!")

        except Exception as e:
            logger.error(f"Error en el Recálculo Total: {e}", exc_info=True)
            progress_callback(f"Error en recálculo: {e}")
            raise RecalculoError(f"Fallo el proceso de recálculo: {e}") from e
        # --- FIN CAMBIO ---
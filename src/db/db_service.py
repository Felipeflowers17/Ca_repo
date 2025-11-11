# -*- coding: utf-8 -*-
"""
Servicio de Base de Datos (DbService).

(Versión 7.0 - Guarda fecha_cierre_segundo_llamado)
"""

from typing import List, Dict, Callable, Tuple
from sqlalchemy.orm import sessionmaker, Session, joinedload
from sqlalchemy import select, join

from .db_models import (
    Base,
    CaLicitacion,
    CaSeguimiento,
    CaOrganismo,
    CaSector,
    CaKeyword,
    CaOrganismoPrioritario,
)

from config.config import UMBRAL_FASE_1, UMBRAL_FINAL_RELEVANTE
from src.utils.logger import configurar_logger

logger = configurar_logger(__name__)


class DbService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory
        logger.info("DbService inicializado.")

    # --- 1. Métodos de Lógica ELT (Usados por EtlService) ---

    def _get_or_create_organismo_sector(
        self, session: Session, nombre_organismo: str, nombre_sector: str
    ) -> CaOrganismo:
        # ... (Sin cambios) ...
        if not nombre_sector:
            nombre_sector = "No Especificado"
        nombre_sector_norm = nombre_sector.strip()
        nombre_organismo_norm = nombre_organismo.strip()
        stmt_sector = select(CaSector).where(CaSector.nombre == nombre_sector_norm)
        sector = session.scalars(stmt_sector).first()
        if not sector:
            logger.info(f"Creando nuevo Sector: {nombre_sector_norm}")
            sector = CaSector(nombre=nombre_sector_norm)
            session.add(sector)
            session.flush()
        if not nombre_organismo_norm:
            nombre_organismo_norm = "Organismo No Especificado"
        stmt_org = select(CaOrganismo).where(CaOrganismo.nombre == nombre_organismo_norm)
        organismo = session.scalars(stmt_org).first()
        if not organismo:
            logger.info(f"Creando nuevo Organismo: {nombre_organismo_norm} (Sector: {sector.nombre})")
            organismo = CaOrganismo(nombre=nombre_organismo_norm, sector_id=sector.sector_id)
            session.add(organismo)
            session.flush()
        return organismo

    def insertar_o_actualizar_licitaciones_raw(self, compras: List[Dict]):
        # ... (Sin cambios) ...
        logger.info(f"Iniciando (ELT) Carga de {len(compras)} CAs crudas...")
        codigos_procesados = set()
        nuevos_inserts = 0
        actualizaciones = 0
        omitidos_duplicados = 0
        with self.session_factory() as session:
            try:
                for item in compras:
                    codigo = item.get("codigo", item.get("id"))
                    if not codigo:
                        omitidos_duplicados += 1
                        continue
                    if codigo in codigos_procesados:
                        omitidos_duplicados += 1
                        continue
                    codigos_procesados.add(codigo)
                    nombre_org_raw = item.get("organismo", "No Especificado")
                    nombre_sec_raw = item.get("unidad", "No Especificado")
                    organismo_db = self._get_or_create_organismo_sector(
                        session, nombre_org_raw, nombre_sec_raw
                    )
                    stmt = select(CaLicitacion).where(CaLicitacion.codigo_ca == codigo)
                    licitacion_existente = session.scalars(stmt).first()
                    if licitacion_existente:
                        licitacion_existente.proveedores_cotizando = item.get("cantidad_provedores_cotizando")
                        licitacion_existente.estado_ca_texto = item.get("estado")
                        licitacion_existente.fecha_cierre = item.get("fecha_cierre")
                        actualizaciones += 1
                    else:
                        nueva_licitacion = CaLicitacion(
                            codigo_ca=codigo,
                            nombre=item.get("nombre"),
                            monto_clp=item.get("monto_disponible_CLP"),
                            fecha_publicacion=item.get("fecha_publicacion"),
                            fecha_cierre=item.get("fecha_cierre"),
                            proveedores_cotizando=item.get("cantidad_provedores_cotizando"),
                            estado_ca_texto=item.get("estado"),
                            organismo_id=organismo_db.organismo_id,
                            puntuacion_final=0,
                        )
                        session.add(nueva_licitacion)
                        nuevos_inserts += 1
                session.commit()
                logger.info(f"Carga (L) exitosa: {nuevos_inserts} nuevos, {actualizaciones} actualizados.")
            except Exception as e:
                logger.error(f"Error al hacer commit en lote (Carga): {e}", exc_info=True)
                session.rollback()
                raise e
            finally:
                logger.info(f"Procesadas {len(codigos_procesados)} CAs únicas.")

    def obtener_candidatas_para_recalculo_fase_1(self) -> List[CaLicitacion]:
        # ... (Sin cambios) ...
        with self.session_factory() as session:
            stmt = select(CaLicitacion).where(
                CaLicitacion.puntuacion_final == 0,
                CaLicitacion.descripcion.is_(None)
            ).options(
                joinedload(CaLicitacion.organismo),
                joinedload(CaLicitacion.seguimiento)
            )
            return session.scalars(stmt).all()

    def obtener_todas_candidatas_fase_1_para_recalculo(self) -> List[CaLicitacion]:
        # ... (Sin cambios) ...
        with self.session_factory() as session:
            stmt = select(CaLicitacion).where(
                CaLicitacion.descripcion.is_(None)
            ).options(
                joinedload(CaLicitacion.organismo),
                joinedload(CaLicitacion.seguimiento)
            )
            return session.scalars(stmt).all()
    
    def actualizar_puntajes_fase_1_en_lote(self, actualizaciones: List[Tuple[int, int]]):
        # ... (Sin cambios) ...
        if not actualizaciones:
            logger.info("No hay puntajes para actualizar.")
            return
        with self.session_factory() as session:
            try:
                session.bulk_update_mappings(
                    CaLicitacion,
                    [
                        {"ca_id": ca_id, "puntuacion_final": puntaje}
                        for ca_id, puntaje in actualizaciones
                    ]
                )
                session.commit()
                logger.info(f"Actualizados {len(actualizaciones)} puntajes de Fase 1.")
            except Exception as e:
                logger.error(f"Error en la actualización de puntajes en lote: {e}")
                session.rollback()
                raise

    def obtener_candidatas_para_fase_2(self) -> List[CaLicitacion]:
        # ... (Sin cambios) ...
        with self.session_factory() as session:
            stmt = (
                select(CaLicitacion)
                .filter(
                    CaLicitacion.puntuacion_final >= UMBRAL_FASE_1,
                    CaLicitacion.descripcion.is_(None)
                )
                .order_by(CaLicitacion.fecha_cierre.asc())
            )
            candidatas = session.scalars(stmt).all()
            logger.info(f"Se encontraron {len(candidatas)} CAs para procesar en Fase 2.")
            return candidatas

    def actualizar_ca_con_fase_2(
        self, codigo_ca: str, datos_fase_2: Dict, puntuacion_total: int
    ):
        """Actualiza una CA específica con los datos de Fase 2."""
        with self.session_factory() as session:
            try:
                stmt = select(CaLicitacion).where(CaLicitacion.codigo_ca == codigo_ca)
                licitacion = session.scalars(stmt).first()
                
                if not licitacion:
                    logger.error(f"[Fase 2] No se encontró CA {codigo_ca} para actualizar.")
                    return

                licitacion.descripcion = datos_fase_2.get("descripcion")
                licitacion.productos_solicitados = datos_fase_2.get("productos_solicitados")
                licitacion.direccion_entrega = datos_fase_2.get("direccion_entrega")
                licitacion.puntuacion_final = puntuacion_total
                
                # --- ¡NUEVO CAMBIO! (Tu Punto 3) ---
                licitacion.fecha_cierre_segundo_llamado = datos_fase_2.get("fecha_cierre_p2")
                # --- FIN NUEVO CAMBIO ---
                
                session.commit()
                logger.debug(f"[Fase 2] CA {codigo_ca} actualizada. Score: {puntuacion_total}")
            except Exception as e:
                logger.error(f"[Fase 2] Error al actualizar CA {codigo_ca}: {e}")
                session.rollback()
                raise

    # --- 2. Métodos de Lectura para la GUI (Refresco de Pestañas) ---

    def obtener_datos_tab1_candidatas(self) -> List[CaLicitacion]:
        # ... (Sin cambios) ...
        logger.debug(f"GUI: Obteniendo datos Pestaña 1 (Score >= {UMBRAL_FASE_1})")
        with self.session_factory() as session:
            stmt = (
                select(CaLicitacion)
                .options(
                    joinedload(CaLicitacion.seguimiento), 
                    joinedload(CaLicitacion.organismo).joinedload(CaOrganismo.sector)
                ) 
                .filter(CaLicitacion.puntuacion_final >= UMBRAL_FASE_1)
                .order_by(CaLicitacion.puntuacion_final.desc())
            )
            return session.scalars(stmt).all()

    def obtener_datos_tab2_relevantes(self) -> List[CaLicitacion]:
        # ... (Sin cambios) ...
        logger.debug(f"GUI: Obteniendo datos Pestaña 2 (Score >= {UMBRAL_FINAL_RELEVANTE})")
        with self.session_factory() as session:
            stmt = (
                select(CaLicitacion)
                .options(
                    joinedload(CaLicitacion.seguimiento),
                    joinedload(CaLicitacion.organismo).joinedload(CaOrganismo.sector)
                )
                .filter(CaLicitacion.puntuacion_final >= UMBRAL_FINAL_RELEVANTE)
                .order_by(CaLicitacion.puntuacion_final.desc())
            )
            return session.scalars(stmt).all()

    def obtener_datos_tab3_seguimiento(self) -> List[CaLicitacion]:
        # ... (Sin cambios) ...
        logger.debug("GUI: Obteniendo datos Pestaña 3 (Favoritos)")
        with self.session_factory() as session:
            stmt = (
                select(CaLicitacion)
                .options(
                    joinedload(CaLicitacion.seguimiento),
                    joinedload(CaLicitacion.organismo).joinedload(CaOrganismo.sector)
                )
                .join(CaSeguimiento, CaLicitacion.ca_id == CaSeguimiento.ca_id)
                .filter(CaSeguimiento.es_favorito == True)
                .order_by(CaLicitacion.fecha_cierre.asc())
            )
            return session.scalars(stmt).all()

    def obtener_datos_tab4_ofertadas(self) -> List[CaLicitacion]:
        # ... (Sin cambios) ...
        logger.debug("GUI: Obteniendo datos Pestaña 4 (Ofertadas)")
        with self.session_factory() as session:
            stmt = (
                select(CaLicitacion)
                .options(
                    joinedload(CaLicitacion.seguimiento),
                    joinedload(CaLicitacion.organismo).joinedload(CaOrganismo.sector)
                )
                .join(CaSeguimiento, CaLicitacion.ca_id == CaSeguimiento.ca_id)
                .filter(CaSeguimiento.es_ofertada == True)
                .order_by(CaLicitacion.fecha_cierre.asc())
            )
            return session.scalars(stmt).all()

    # --- 3. Métodos de Acción para la GUI (Menú Contextual) ---

    def _gestionar_seguimiento(self, ca_id: int, es_favorito: bool | None, es_ofertada: bool | None):
        # ... (Sin cambios) ...
        with self.session_factory() as session:
            try:
                seguimiento = session.get(CaSeguimiento, ca_id)
                if seguimiento:
                    if es_favorito is not None:
                        seguimiento.es_favorito = es_favorito
                    if es_ofertada is not None:
                        seguimiento.es_ofertada = es_ofertada
                        if es_ofertada: 
                            seguimiento.es_favorito = True
                elif es_favorito or es_ofertada:
                    nuevo_seguimiento = CaSeguimiento(
                        ca_id=ca_id,
                        es_favorito=es_favorito or es_ofertada,
                        es_ofertada=es_ofertada if es_ofertada is not None else False,
                    )
                    session.add(nuevo_seguimiento)
                session.commit()
            except Exception as e:
                logger.error(f"Error al gestionar seguimiento para CA {ca_id}: {e}")
                session.rollback()
                raise

    def gestionar_favorito(self, ca_id: int, es_favorito: bool):
        # ... (Sin cambios) ...
        self._gestionar_seguimiento(ca_id, es_favorito=es_favorito, es_ofertada=None)

    def gestionar_ofertada(self, ca_id: int, es_ofertada: bool):
        # ... (Sin cambios) ...
        self._gestionar_seguimiento(ca_id, es_favorito=None, es_ofertada=es_ofertada)

    def eliminar_ca_definitivamente(self, ca_id: int):
        # ... (Sin cambios) ...
        logger.debug(f"GUI: Eliminación definitiva de CA ID: {ca_id}")
        with self.session_factory() as session:
            try:
                licitacion = session.get(CaLicitacion, ca_id)
                if licitacion:
                    session.delete(licitacion)
                    session.commit()
                    logger.info(f"CA {ca_id} eliminada permanentemente.")
                else:
                    logger.warning(f"No se encontró CA {ca_id} para eliminar.")
            except Exception as e:
                logger.error(f"Error en eliminación definitiva de CA {ca_id}: {e}")
                session.rollback()
                raise

    # --- 4. Métodos de Gestión de Reglas (para la GUI de Configuración) ---
    # ... (Sin cambios en todos estos métodos) ...
    def get_all_keywords(self) -> List[CaKeyword]:
        with self.session_factory() as session:
            return session.scalars(select(CaKeyword).order_by(CaKeyword.tipo, CaKeyword.keyword)).all()

    def add_keyword(self, keyword: str, tipo: str, puntos: int) -> CaKeyword:
        with self.session_factory() as session:
            try:
                nueva_keyword = CaKeyword(
                    keyword=keyword.lower().strip(), tipo=tipo, puntos=puntos
                )
                session.add(nueva_keyword)
                session.commit()
                logger.info(f"Keyword añadida: {nueva_keyword}")
                session.refresh(nueva_keyword) 
                return nueva_keyword
            except Exception as e:
                logger.error(f"Error al añadir keyword '{keyword}': {e}")
                session.rollback()
                raise e

    def delete_keyword(self, keyword_id: int):
        with self.session_factory() as session:
            try:
                keyword = session.get(CaKeyword, keyword_id)
                if keyword:
                    session.delete(keyword)
                    session.commit()
                    logger.info(f"Keyword eliminada: (ID: {keyword_id})")
                else:
                    logger.warning(f"No se encontró keyword con ID {keyword_id} para eliminar.")
            except Exception as e:
                logger.error(f"Error al eliminar keyword ID {keyword_id}: {e}")
                session.rollback()
                raise e
    
    def get_all_priority_organisms(self) -> List[CaOrganismoPrioritario]:
        with self.session_factory() as session:
            stmt = select(CaOrganismoPrioritario).options(joinedload(CaOrganismoPrioritario.organismo))
            return session.scalars(stmt).all()

    def add_priority_organism(self, organismo_id: int, puntos: int) -> CaOrganismoPrioritario:
        with self.session_factory() as session:
            try:
                nuevo_prio = CaOrganismoPrioritario(
                    organismo_id=organismo_id, puntos=puntos
                )
                session.add(nuevo_prio)
                session.commit()
                logger.info(f"Organismo Prioritario añadido: (ID: {organismo_id})")
                session.refresh(nuevo_prio)
                return nuevo_prio
            except Exception as e:
                logger.error(f"Error al añadir organismo prioritario ID {organismo_id}: {e}")
                session.rollback()
                raise e

    def delete_priority_organism(self, org_prio_id: int):
        with self.session_factory() as session:
            try:
                prio = session.get(CaOrganismoPrioritario, org_prio_id)
                if prio:
                    session.delete(prio)
                    session.commit()
                    logger.info(f"Organismo Prioritario eliminado: (ID: {org_prio_id})")
                else:
                    logger.warning(f"No se encontró org. prioritario ID {org_prio_id} para eliminar.")
            except Exception as e:
                logger.error(f"Error al eliminar org. prioritario ID {org_prio_id}: {e}")
                session.rollback()
                raise e
    
    def get_all_organisms(self) -> List[CaOrganismo]:
        with self.session_factory() as session:
            return session.scalars(select(CaOrganismo).order_by(CaOrganismo.nombre)).all()
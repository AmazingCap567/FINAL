# -*- coding: utf-8 -*-
"""
scripts/actualizar_interfaz.py
================================
Puente entre el pipeline real (outputs/analisis, outputs/interfaz,
motor/datos/eventos_intervencion.py) y la interfaz visual estatica
Peru_SBS.html.

Este script NO entrena modelos, NO recalcula predicciones y NO modifica
metodologias. Unicamente:

  1. Localiza y valida los outputs reales generados por
     scripts/run_evaluacion.py y scripts/run_prediccion.py.
  2. Lee esos outputs con pandas.
  3. Reconstruye, para cada ECR, el ranking de los 4 modelos comparables
     usando EXACTAMENTE la metodologia de
     motor/modelos/comparacion/seleccion.py (mismos pesos, mismo
     criterio de normalizacion) -- no se inventa un criterio nuevo.
  4. Extrae, de los archivos brutos de clasificacion SBS
     (data/clasificaciones/*.xls), el historial real de calificacion de
     las entidades con evento de intervencion confirmado (para el
     grafico de evolucion historica). Si una entidad no tiene ninguna
     fila en esos archivos, se deja constancia explicita (no se inventa
     una serie).
  5. Serializa todo a JSON y lo inyecta en Peru_SBS.html, reemplazando
     UNICAMENTE el contenido entre los marcadores:
         <!-- DATA_START --> ... <!-- DATA_END -->
     El resto del archivo (estructura visual, componentes, estilos)
     queda intacto.

Ejecucion:
    python scripts/actualizar_interfaz.py

Salida:
    Peru_SBS.html actualizado (autocontenido) + log en consola con
    trazabilidad (archivos procesados, filas, advertencias).
"""

from __future__ import annotations
import os
import re
import sys
import json
import glob
import datetime as dt

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor import config
from motor.datos import eventos_intervencion
from motor.modelos.comparacion import seleccion

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALISIS_DIR = os.path.join(BASE_DIR, "outputs", "analisis")
INTERFAZ_DIR = os.path.join(BASE_DIR, "outputs", "interfaz")
CLASIF_DIR = os.path.join(BASE_DIR, "data", "clasificaciones")
HTML_PATH = os.path.join(BASE_DIR, "Peru_SBS.html")

CORTE_OBJETIVO = "SEP2026"

MODELOS_COMPARABLES = ["1-HistGB", "2-MLPOrdinal", "3-RegresionOrdinal", "4-LightGBM"]
MODELOS_LABEL = {
    "1-HistGB": "HistGradientBoosting",
    "2-MLPOrdinal": "MLP Ordinal Multi-task",
    "3-RegresionOrdinal": "Regresión Logística Ordinal",
    "4-LightGBM": "LightGBM",
}

LOG_LINES = []


def log(msg, level="INFO"):
    line = f"[{level}] {msg}"
    print(line)
    LOG_LINES.append(line)


def fail(msg):
    log(msg, level="ERROR")
    raise SystemExit(f"actualizar_interfaz.py: DETENIDO -> {msg}")


def require_file(path, componente):
    if not os.path.exists(path):
        fail(f"Archivo faltante: {path} | Ubicacion esperada: {os.path.dirname(path)} | "
             f"Componente afectado: {componente}")
    return path


# ---------------------------------------------------------------------------
# 1. METRICAS DE MODELOS POR ECR (holdout MAR2026) + RANKING REAL
# ---------------------------------------------------------------------------
def cargar_metricas_por_ecr():
    """Lee outputs/analisis/metricas_holdout_<ECR>.csv para cada ECR con
    archivo disponible, aplica seleccion.construir_ranking() (metodologia
    real del proyecto) y arma la tabla comparativa modelo x ECR."""
    resultado = {}
    ecrs_con_metricas = []
    for ecr in config.ECR_LIST:
        path = os.path.join(ANALISIS_DIR, f"metricas_holdout_{ecr}.csv")
        if not os.path.exists(path):
            log(f"Sin metricas de holdout para ECR={ecr} (no existe {os.path.basename(path)}); "
                f"se omite del comparativo de modelos.", level="WARN")
            continue
        df = pd.read_csv(path, index_col=0)
        faltantes = [m for m in MODELOS_COMPARABLES if m not in df.index]
        if faltantes:
            log(f"ECR={ecr}: faltan filas de modelo {faltantes} en {os.path.basename(path)}.", level="WARN")
        df_modelos = df.loc[[m for m in MODELOS_COMPARABLES if m in df.index]].copy()
        df_modelos = df_modelos.rename(columns={"ordinal_mae": "mae_ordinal"})
        ranking, ganador = seleccion.construir_ranking(df_modelos)
        resultado[ecr] = {
            "ganador": ganador,
            "modelos": {
                idx: {
                    "n": None if pd.isna(row.get("n")) else int(row.get("n")),
                    "accuracy": _r(row.get("accuracy")),
                    "accuracy_pm1": _r(row.get("accuracy_pm1")),
                    "f1_macro": _r(row.get("f1_macro")),
                    "mae_ordinal": _r(row.get("mae_ordinal")),
                    "weighted_kappa": _r(row.get("weighted_kappa")),
                    "puntaje": _r(row.get("puntaje")),
                }
                for idx, row in ranking.iterrows()
            },
        }
        ecrs_con_metricas.append(ecr)
        log(f"ECR={ecr}: ranking construido sobre {len(ranking)} modelos "
            f"(holdout n={int(df_modelos['n'].max()) if 'n' in df_modelos else '?'}). Ganador: {ganador}.")

    ecrs_sin_metricas = [e for e in config.ECR_LIST if e not in ecrs_con_metricas]
    if ecrs_sin_metricas:
        log(f"ECR sin metricas de holdout disponibles: {ecrs_sin_metricas} "
            f"(no se construye grafico de desempeño por ECR para estos).", level="WARN")
    return resultado, ecrs_con_metricas, ecrs_sin_metricas


def _r(v, nd=4):
    if v is None or (isinstance(v, float) and (pd.isna(v) or np.isnan(v))):
        return None
    return round(float(v), nd)


def cargar_ganador_por_ecr():
    path = require_file(os.path.join(ANALISIS_DIR, "modelo_ganador_por_ecr.csv"),
                         "Modelos de predicción (badge de ganador oficial por ECR)")
    df = pd.read_csv(path)
    return dict(zip(df["ECR"], df["MODELO_GANADOR"]))


def calcular_resumen_modelos(metricas_por_ecr):
    """Promedia el puntaje compuesto de cada modelo a traves de las ECR en
    las que compitio, para el resumen global de las 4 tarjetas de modelo.
    No es una metrica nueva: es el promedio simple del mismo 'puntaje'
    que seleccion.py calcula por ECR."""
    acumulado = {m: [] for m in MODELOS_COMPARABLES}
    for ecr, bloque in metricas_por_ecr.items():
        for modelo, met in bloque["modelos"].items():
            if met["puntaje"] is not None:
                acumulado[modelo].append(met["puntaje"])
    resumen = {}
    for modelo, puntajes in acumulado.items():
        resumen[modelo] = {
            "label": MODELOS_LABEL[modelo],
            "puntaje_promedio": _r(sum(puntajes) / len(puntajes)) if puntajes else None,
            "n_ecr": len(puntajes),
        }
    return resumen


# ---------------------------------------------------------------------------
# 2. PREDICCIONES SEP2026 (outputs/interfaz)
# ---------------------------------------------------------------------------
def cargar_predicciones():
    path = require_file(
        os.path.join(INTERFAZ_DIR, f"predicciones_{CORTE_OBJETIVO}_TODAS.xlsx"),
        "Predicción de septiembre (tabla y KPIs)",
    )
    df = pd.read_excel(path)
    requeridas = ["ENTITY_NAME", "ENTITY_TYPE", "ECR", "FECHA_BASE", "FECHA_TARGET",
                  "RATING_ANTERIOR", "RATING_PREDICHO", "CAMBIO_ORDINAL",
                  "ALERTA_DOWNGRADE_FUERTE", "ALERTA_INTERVENCION_HISTORICA"]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        fail(f"Columnas faltantes en {os.path.basename(path)}: {faltantes}")

    df["FECHA_BASE"] = pd.to_datetime(df["FECHA_BASE"]).dt.strftime("%Y-%m-%d")
    df["FECHA_TARGET"] = pd.to_datetime(df["FECHA_TARGET"]).dt.strftime("%Y-%m-%d")

    filas = df.to_dict(orient="records")
    for f in filas:
        f["CAMBIO_ORDINAL"] = int(f["CAMBIO_ORDINAL"])
        f["ALERTA_DOWNGRADE_FUERTE"] = bool(f["ALERTA_DOWNGRADE_FUERTE"])
        f["ALERTA_INTERVENCION_HISTORICA"] = bool(f["ALERTA_INTERVENCION_HISTORICA"])

    log(f"Predicciones {CORTE_OBJETIVO} cargadas: {len(filas)} filas (entidad x ECR) desde "
        f"{os.path.basename(path)}.")
    return filas


# ---------------------------------------------------------------------------
# 3. ENTIDADES EXCLUIDAS POR INTERVENCION + HISTORIAL REAL DE CALIFICACION
# ---------------------------------------------------------------------------
def cargar_entidades_excluidas():
    path = os.path.join(ANALISIS_DIR, f"entidades_excluidas_por_intervencion_{CORTE_OBJETIVO}.csv")
    if not os.path.exists(path):
        log(f"No existe {path}; se asume 0 entidades excluidas para {CORTE_OBJETIVO}.", level="WARN")
        return []
    df = pd.read_csv(path)
    log(f"Entidades excluidas de la predicción {CORTE_OBJETIVO} por intervención SBS confirmada: {len(df)} "
        f"({os.path.basename(path)}).")
    return df.to_dict(orient="records")


def _limpiar_rating(valor):
    """Quita las flechas de tendencia (↑ ↓) que agrega el HTML fuente de la
    SBS y devuelve (rating_limpio, es_valido_segun_config)."""
    if pd.isna(valor):
        return None, False
    txt = str(valor).strip()
    for arrow in ("↑", "↓", "\u2191", "\u2193"):
        txt = txt.replace(arrow, "")
    txt = txt.strip()
    if not txt or txt.upper() in config.INVALID_RATING_TOKENS:
        return txt or None, False
    return txt, txt in config.RATING_MASTER_ORDINAL


def cargar_historial_real_intervenidas(eventos):
    """Recorre TODOS los archivos brutos data/clasificaciones/*.xls y arma,
    para cada entidad con evento de intervencion, su serie real de rating
    por ECR y por corte. Si una entidad no aparece en ningun archivo, se
    devuelve con historial vacio y advertencia explicita (nunca se
    inventa una serie)."""
    if not os.path.isdir(CLASIF_DIR):
        log(f"No existe carpeta {CLASIF_DIR}; no se puede construir historial real de "
            f"entidades intervenidas.", level="WARN")
        return {}

    archivos = sorted(glob.glob(os.path.join(CLASIF_DIR, "*.xls")))
    if not archivos:
        log(f"Carpeta {CLASIF_DIR} sin archivos .xls; sin historial de intervenidas.", level="WARN")
        return {}

    # Nombre normalizado (tal como esta en eventos_intervencion.py) -> lista de
    # alias de texto que pueden aparecer en los archivos brutos de la SBS
    # (abreviados / con variaciones). Se listan los alias observados
    # realmente en los archivos, no se inventan variantes adicionales.
    ALIAS = {
        "CRAC RAIZ": ["CRAC RAIZ", "EDPYME RAIZ"],
        "AMERIKA FINANCIERA": ["AMERIKA FINANC"],
        "CMAC SULLANA": ["CMAC SULLANA"],
        "FINANCIERA CREDINKA": ["FINANC. CREDINKA", "FINANCIERA CREDINKA"],
    }

    ecr_cols = {
        "APOYO": "Apoyo y Asociados Internacionales",
        "CLASS": "Class y Asociados S.A.",
        "JCR": "JCR Latino America",
        "MICRORATE": "Microrate",
        "MOODYS": "Moodys Local PE Clasificadora de Riesgo",
        "PCR": "PCR (Pacific Credit Rating)",
    }

    historial = {norm: {"series": [], "archivos_con_dato": 0} for norm in ALIAS}

    for archivo in archivos:
        corte = os.path.splitext(os.path.basename(archivo))[0]  # p.ej. MAR2022
        try:
            tablas = pd.read_html(archivo)
        except Exception as e:
            log(f"No se pudo leer {archivo}: {e}", level="WARN")
            continue
        t = tablas[0]
        if "Entidad" not in t.columns:
            continue
        for norm, alias_list in ALIAS.items():
            patron = "|".join(alias_list)
            mask = t["Entidad"].astype(str).str.upper().str.contains(patron, na=False)
            if not mask.any():
                continue
            fila = t[mask].iloc[0]
            punto = {"corte": corte}
            tuvo_dato = False
            for ecr, col in ecr_cols.items():
                if col not in t.columns:
                    continue
                rating, valido = _limpiar_rating(fila[col])
                if rating is not None:
                    punto[ecr] = {"rating": rating, "ordinal": config.RATING_MASTER_ORDINAL.get(rating)
                                  if valido else None, "valido": valido}
                    tuvo_dato = True
            if tuvo_dato:
                historial[norm]["series"].append(punto)
                historial[norm]["archivos_con_dato"] += 1

    for norm, bloque in historial.items():
        bloque["series"].sort(key=lambda p: p["corte"])
        if bloque["archivos_con_dato"] == 0:
            log(f"Sin historial real de clasificación en data/clasificaciones/ para '{norm}'. "
                f"El dashboard debe mostrar 'Información no disponible' para esta entidad "
                f"(no se inventa una serie).", level="WARN")
        else:
            log(f"Historial real de clasificación reconstruido para '{norm}': "
                f"{bloque['archivos_con_dato']} cortes con dato.")

    return historial


def construir_eventos(historial):
    eventos = []
    for ev in eventos_intervencion.EVENTOS_INTERVENCION:
        norm = ev["ENTITY_NAME_NORM"]
        bloque = historial.get(norm, {"series": []})
        eventos.append({
            **ev,
            "FECHA_EVENTO": ev["FECHA_EVENTO"],
            "historial": bloque["series"],
        })
    return eventos


# ---------------------------------------------------------------------------
# 4. VALIDACION
# ---------------------------------------------------------------------------
def validar(payload):
    problemas = []
    if not payload["predicciones"]:
        problemas.append("0 filas de predicción SEP2026.")
    if not payload["metricas_por_ecr"]:
        problemas.append("0 ECR con métricas de modelos.")
    if not payload["ganador_por_ecr"]:
        problemas.append("0 ECR con modelo ganador asignado.")
    tipos_pred = {f["ENTITY_TYPE"] for f in payload["predicciones"]}
    if not tipos_pred.issubset(set(config.ENTITY_TYPES)):
        problemas.append(f"Tipos de entidad inesperados en predicciones: {tipos_pred - set(config.ENTITY_TYPES)}")
    if problemas:
        fail("Validación posterior a la generación falló: " + " | ".join(problemas))
    log("Validación de datos: OK (predicciones, métricas de modelos, ganadores por ECR, "
        "tipos de entidad consistentes con motor.config).")


# ---------------------------------------------------------------------------
# 5. INYECCION EN EL HTML (entre marcadores, sin tocar el resto)
# ---------------------------------------------------------------------------
DATA_START = "/* DATA_START */"
DATA_END = "/* DATA_END */"


def inyectar_en_html(payload):
    require_file(HTML_PATH, "Peru_SBS.html (destino final)")
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    if DATA_START not in html or DATA_END not in html:
        fail(f"No se encontraron los marcadores {DATA_START} / {DATA_END} en Peru_SBS.html. "
             f"No se puede actualizar de forma segura sin ellos.")

    bloque_js = (
        f"{DATA_START}\n"
        f"const REAL_METRICAS_POR_ECR = {json.dumps(payload['metricas_por_ecr'], ensure_ascii=False)};\n"
        f"const REAL_GANADOR_POR_ECR = {json.dumps(payload['ganador_por_ecr'], ensure_ascii=False)};\n"
        f"const REAL_RESUMEN_MODELOS = {json.dumps(payload['resumen_modelos'], ensure_ascii=False)};\n"
        f"const REAL_ECRS_CON_METRICAS = {json.dumps(payload['ecrs_con_metricas'], ensure_ascii=False)};\n"
        f"const REAL_ECRS_SIN_METRICAS = {json.dumps(payload['ecrs_sin_metricas'], ensure_ascii=False)};\n"
        f"const REAL_PREDICCIONES_SEP2026 = {json.dumps(payload['predicciones'], ensure_ascii=False)};\n"
        f"const REAL_ENTIDADES_EXCLUIDAS = {json.dumps(payload['entidades_excluidas'], ensure_ascii=False)};\n"
        f"const REAL_EVENTOS_INTERVENCION = {json.dumps(payload['eventos_intervencion'], ensure_ascii=False)};\n"
        f"const REAL_CORTE_OBJETIVO = {json.dumps(CORTE_OBJETIVO)};\n"
        f"const REAL_MODELOS_LABEL = {json.dumps(MODELOS_LABEL, ensure_ascii=False)};\n"
        f"const REAL_ACTUALIZADO_EN = {json.dumps(dt.datetime.now().strftime('%Y-%m-%d %H:%M'))};\n"
        f"{DATA_END}"
    )

    patron = re.compile(re.escape(DATA_START) + r".*?" + re.escape(DATA_END), re.DOTALL)
    nuevo_html, n = patron.subn(lambda m: bloque_js, html)
    if n != 1:
        fail(f"Se esperaba exactamente 1 bloque DATA_START/DATA_END, se encontraron {n}.")

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(nuevo_html)
    log(f"Peru_SBS.html actualizado (bloque de datos reemplazado, {len(bloque_js)} bytes de JSON embebido).")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    log("=" * 70)
    log(f"ACTUALIZACION DE INTERFAZ -> {CORTE_OBJETIVO}")
    log("=" * 70)

    metricas_por_ecr, ecrs_con_metricas, ecrs_sin_metricas = cargar_metricas_por_ecr()
    ganador_por_ecr = cargar_ganador_por_ecr()
    resumen_modelos = calcular_resumen_modelos(metricas_por_ecr)
    predicciones = cargar_predicciones()
    entidades_excluidas = cargar_entidades_excluidas()
    historial = cargar_historial_real_intervenidas(eventos_intervencion.EVENTOS_INTERVENCION)
    eventos = construir_eventos(historial)

    payload = {
        "metricas_por_ecr": metricas_por_ecr,
        "ganador_por_ecr": ganador_por_ecr,
        "resumen_modelos": resumen_modelos,
        "ecrs_con_metricas": ecrs_con_metricas,
        "ecrs_sin_metricas": ecrs_sin_metricas,
        "predicciones": predicciones,
        "entidades_excluidas": entidades_excluidas,
        "eventos_intervencion": eventos,
    }

    validar(payload)
    inyectar_en_html(payload)

    log("-" * 70)
    log("RESUMEN DE TRAZABILIDAD")
    log(f"  ECR con métricas de modelos: {ecrs_con_metricas}")
    log(f"  ECR sin métricas de modelos: {ecrs_sin_metricas}")
    log(f"  Filas de predicción {CORTE_OBJETIVO}: {len(predicciones)}")
    log(f"  Entidades únicas en predicción: {len({p['ENTITY_NAME'] for p in predicciones})}")
    log(f"  Entidades excluidas por intervención: {len(entidades_excluidas)}")
    log(f"  Eventos de intervención (motor/datos/eventos_intervencion.py): {len(eventos)}")
    sin_hist = [e['ENTITY_NAME_NORM'] for e in eventos if not e['historial']]
    if sin_hist:
        log(f"  Entidades intervenidas SIN historial real de clasificación disponible: {sin_hist}", level="WARN")
    log("=" * 70)
    return payload


if __name__ == "__main__":
    main()

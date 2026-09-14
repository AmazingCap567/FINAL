# -*- coding: utf-8 -*-
"""
eventos_intervencion.py
========================
Tabla CURADA MANUALMENTE de eventos reales de intervencion/disolucion/
fusion de entidades supervisadas por la SBS, verificados contra fuentes
externas (resoluciones SBS publicadas en El Peruano y cobertura de prensa
especializada). Esta NO es una lista teorica ni inventada: cada fila tiene
su resolucion SBS y fecha real.

Por que existe esta tabla en vez de derivar "fracaso" de la propia serie
financiera: se verifico que la senal "la entidad deja de aparecer en el
panel financiero" NO es confiable. De los casos reales documentados aqui,
2 (CMAC Sullana y Financiera Credinka) SIGUIERON reportando datos
financieros despues de ser intervenidas (el reporte contable continua
durante el proceso de traspaso de cartera a la entidad ganadora del
concurso), por lo que una heuristica de "discontinuidad de panel" los
habria pasado por alto. Ademas, esa misma heuristica genera FALSOS
POSITIVOS: Compartamos Financiera y Crediscotia Financiera tambien "dejan
de aparecer" con su nombre original, pero por conversion a banco y cambio
de razon social respectivamente -- no por fracaso (ver
config.FINANCIAL_ENTITY_CONTINUITY_RENAMES para el caso de Crediscotia).

AUDITORIA 2026-09: se detecto que 4 entidades (Deutsche Bank Peru, CRAC
Cajamarca, CRAC Sipan, Financiera TFC S.A.) seguian recibiendo una fila de
prediccion en la proyeccion SEP2026 pese a llevar entre 5 y 10 anios sin
reportar dato financiero ni aparecer en ninguna clasificacion SBS
(GAP_MESES de 61 a 123 meses en outputs/interfaz/). La causa: estas 4
salidas del mercado NO estaban en esta tabla (build_inference_rows toma el
ULTIMO dato financiero disponible de cada entidad sin ventana de lookback,
confiando en excluir_posteriores_a_intervencion para filtrar salidas
conocidas). Se verificaron y se agregaron las 4:
  - Deutsche Bank Peru: disolucion voluntaria real (igual naturaleza que
    Amerika Financiera).
  - CRAC Sipan: disolucion voluntaria real.
  - Financiera TFC S.A.: intervencion y liquidacion real (mismo tipo de
    evento que CMAC Sullana / Financiera Credinka).
  - CRAC Cajamarca: caso DISTINTO a los otros 3 -- NO fracaso ni
    disolucion, sino FUSION POR ABSORCION (Financiera Credinka absorbe a
    CRAC Cajamarca en 2016; CRAC Cajamarca se extingue como entidad
    juridica y dataset separado). No se modelo como
    config.FINANCIAL_ENTITY_CONTINUITY_RENAMES porque ese diccionario es
    para una MISMA entidad que cambia de nombre dentro de su propia serie
    financiera (sin traslape, como Crediscotia -> Santander Consumer);
    aqui en cambio una entidad (CRAC Cajamarca) desaparece dentro del
    balance de OTRA entidad preexistente (Financiera Credinka) que ya
    tiene su propia serie financiera independiente -- fusionar sus
    ENTITY_ID corromperia el historial de Credinka. Se resuelve entonces
    con el mismo mecanismo de esta tabla (fecha limite de prediccion
    futura), marcando TIPO_EVENTO="FUSION_POR_ABSORCION" en vez de una
    intervencion/disolucion. Nota: la entidad absorbente, Financiera
    Credinka, ya esta excluida de la proyeccion SEP2026 por su propia
    intervencion posterior (sep-2024, ver mas abajo), asi que el efecto
    practico es el mismo (ninguna de las dos genera prediccion futura),
    pero la razon registrada es la correcta para cada una.

Con solo 8 eventos en ~10 anios y ~49 entidades, esta tabla NO se usa para
entrenar un clasificador binario supervisado clasico (la muestra es
demasiado chica para que cualquier metrica de un modelo asi sea
estadisticamente significativa). Se usa para:
  (a) marcar la fecha a partir de la cual una entidad intervenida/disuelta/
      absorbida deja de ser elegible para generar predicciones futuras
      (ver dataset_builder.excluir_posteriores_a_intervencion), y
  (b) como conjunto de validacion CUALITATIVA del SCORE_DETERIORO (el
      proxy continuo de downgrades fuertes de rating, ver
      motor/features/riesgo.py): si el score no se eleva para los casos de
      intervencion/disolucion por deterioro en los cortes previos al
      evento, es una senal de que el proxy no esta funcionando (no aplica
      a CRAC Cajamarca, que no fue un caso de deterioro).
"""

from __future__ import annotations
import pandas as pd


# Clave: nombre normalizado de la entidad tal como queda en el universo
# financiero (ver motor.utils.normalize_entity_name), para poder cruzarlo
# directamente con ENTITY_NAME_NORM del registro de entidades.
EVENTOS_INTERVENCION = [
    {
        "ENTITY_NAME_NORM": "CRAC RAIZ",
        "TIPO_ENTIDAD": "CRAC",
        "FECHA_EVENTO": "2023-08-10",
        "TIPO_EVENTO": "INTERVENCION_Y_LIQUIDACION",
        "RESOLUCION_SBS": "Res. SBS N.° 2646-2023 (intervencion) / N.° 2672-2023 (disolucion)",
        "DESCRIPCION": "Intervenida por deterioro acelerado de solvencia; disuelta y en liquidacion.",
        "FUENTE": "El Peruano, 11-ago-2023; SBS FAQ CRAC Raiz.",
    },
    {
        "ENTITY_NAME_NORM": "AMERIKA FINANCIERA",
        "TIPO_ENTIDAD": "FINANCIERA",
        "FECHA_EVENTO": "2022-08-26",
        "TIPO_EVENTO": "DISOLUCION_VOLUNTARIA",
        "RESOLUCION_SBS": "Acuerdo de Junta General de Accionistas (sujeto a autorizacion SBS conforme Res. SBS N.° 455-99)",
        "DESCRIPCION": "Fallo el proyecto de fusion con Banco Pichincha; accionistas aprobaron disolucion y liquidacion.",
        "FUENTE": "Revista Gan@Más, ago-2022.",
    },
    {
        "ENTITY_NAME_NORM": "CMAC SULLANA",
        "TIPO_ENTIDAD": "CMAC",
        "FECHA_EVENTO": "2024-07-11",
        "TIPO_EVENTO": "INTERVENCION_Y_LIQUIDACION",
        "RESOLUCION_SBS": "Res. SBS N.° 2477-2024 (intervencion) / N.° 2497-2024 (disolucion)",
        "DESCRIPCION": "Intervenida por deterioro acelerado de solvencia (patrimonio); cartera transferida a CMAC Piura.",
        "FUENTE": "El Peruano, 15-jul-2024; Infobae, 14-jul-2024.",
    },
    {
        "ENTITY_NAME_NORM": "FINANCIERA CREDINKA",
        "TIPO_ENTIDAD": "FINANCIERA",
        "FECHA_EVENTO": "2024-09-19",
        "TIPO_EVENTO": "INTERVENCION",
        "RESOLUCION_SBS": "Res. SBS N.° 3341-2024",
        "DESCRIPCION": "Intervenida por acelerado deterioro de solvencia (reduccion de patrimonio de 59.53% en 12 meses); cartera transferida via concurso por invitacion.",
        "FUENTE": "Gestion, 19-sep-2024; El Comercio, 19-sep-2024.",
    },
    {
        "ENTITY_NAME_NORM": "DEUTSCHE BANK PERU",
        "TIPO_ENTIDAD": "BANCO",
        "FECHA_EVENTO": "2016-06-12",
        "TIPO_EVENTO": "DISOLUCION_VOLUNTARIA",
        "RESOLUCION_SBS": "Res. SBS N.° 3722-2016 (disolucion voluntaria y liquidacion)",
        "DESCRIPCION": "Deutsche Bank anuncio en oct-2015 el retiro de sus operaciones de banca en 10 paises "
                        "(incluido Peru); la SBS autorizo la disolucion voluntaria y liquidacion de la "
                        "subsidiaria local. No operaba banca minorista: intermediacion corporativa, trading de "
                        "renta fija/moneda extranjera y derivados.",
        "FUENTE": "El Peruano, Res. SBS N.° 3722-2016; Semana Economica, jul-2016.",
    },
    {
        "ENTITY_NAME_NORM": "CRAC SIPAN",
        "TIPO_ENTIDAD": "CRAC",
        "FECHA_EVENTO": "2021-09-28",
        "TIPO_EVENTO": "DISOLUCION_VOLUNTARIA",
        "RESOLUCION_SBS": "Res. SBS N.° 2844-2021",
        "DESCRIPCION": "Disolucion voluntaria y liquidacion ordenada, aprobada por la SBS tras deterioro "
                        "financiero agravado por la pandemia (morosidad de 87.04% a jul-2021). A diferencia de "
                        "una intervencion forzosa, la entidad demostro capacidad de devolver el integro de los "
                        "depositos (no se uso el Fondo de Seguro de Depositos).",
        "FUENTE": "RPP, 28-sep-2021; Caretas, sep-2021; Infomercado, 13-oct-2021.",
    },
    {
        "ENTITY_NAME_NORM": "FINANCIERA TFC S.A.",
        "TIPO_ENTIDAD": "FINANCIERA",
        "FECHA_EVENTO": "2019-12-12",
        "TIPO_EVENTO": "INTERVENCION_Y_LIQUIDACION",
        "RESOLUCION_SBS": "Res. SBS N.° 5826-2019 (intervencion) / N.° 5855-2019 (disolucion), ambas notificadas "
                          "12-dic-2019",
        "DESCRIPCION": "Intervenida por reduccion de mas del 50% de su patrimonio efectivo en 12 meses; "
                        "dispuesta su disolucion y liquidacion. El proceso fue objeto de una medida cautelar "
                        "judicial (jul-2020 a abr-2022) que suspendio temporalmente la liquidacion sin revertir "
                        "el Regimen de Intervencion; la entidad nunca volvio a operar con normalidad.",
        "FUENTE": "Gestion, 12-dic-2019; El Peruano Res. SBS N.° 5826-2019/5855-2019; tfc.com.pe/situacion-juridica.",
    },
    {
        "ENTITY_NAME_NORM": "CRAC CAJAMARCA",
        "TIPO_ENTIDAD": "CRAC",
        "FECHA_EVENTO": "2016-07-27",
        "TIPO_EVENTO": "FUSION_POR_ABSORCION",
        "RESOLUCION_SBS": "Res. SBS N.° 4169-2016 (27-jul-2016)",
        "DESCRIPCION": "NO es un fracaso ni una liquidacion: Financiera Credinka S.A. absorbe a CRAC Cajamarca "
                        "por fusion (acordada mar-2016, autorizada por la SBS jul-2016). CRAC Cajamarca se "
                        "extingue como entidad juridica y como serie financiera independiente; su cartera y "
                        "clientes pasan a Financiera Credinka. Se excluye de la proyeccion futura porque, como "
                        "entidad separada, deja de existir desde esa fecha (no porque haya quebrado).",
        "FUENTE": "Gestion, 02-ago-2016; Semana Economica, ago-2016; El Peruano Res. SBS N.° 4169-2016; "
                  "SMV - Fundamento clasificacion Financiera Credinka jun-2017.",
    },
]


# ---------------------------------------------------------------------------
# tabla_eventos
# ---------------------------------------------------------------------------
# Que hace: devuelve la tabla de eventos como DataFrame, con FECHA_EVENTO
# ya convertida a datetime.
# ---------------------------------------------------------------------------
def tabla_eventos() -> pd.DataFrame:
    df = pd.DataFrame(EVENTOS_INTERVENCION)
    df["FECHA_EVENTO"] = pd.to_datetime(df["FECHA_EVENTO"])
    return df


# ---------------------------------------------------------------------------
# fecha_limite_por_entidad
# ---------------------------------------------------------------------------
# Que hace: construye {ENTITY_NAME_NORM: fecha_evento} para las entidades
# con evento de intervencion conocido.
# Para que sirve: dataset_builder lo usa para NO generar filas de
# prediccion futura para una entidad despues de su fecha de intervencion,
# aunque el panel financiero siga teniendo datos posteriores (que
# corresponden al proceso de liquidacion/traspaso, no a la entidad
# operando con normalidad).
# ---------------------------------------------------------------------------
def fecha_limite_por_entidad() -> dict[str, pd.Timestamp]:
    df = tabla_eventos()
    return dict(zip(df["ENTITY_NAME_NORM"], df["FECHA_EVENTO"]))

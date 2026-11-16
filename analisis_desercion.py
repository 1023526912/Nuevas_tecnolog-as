import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
import seaborn as sns

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

RAW = Path(__file__).parent / "Data" / "raw" / "datos_estudiantes.csv"
PROCESSED = Path(__file__).parent / "Data" / "processed"
GRAFICOS = PROCESSED / "graficos"

# Valores válidos de cada columna categórica (la forma correcta de escribirlos).
VALIDOS = {
    "programa": ["Administración de Empresas", "Contaduría Pública", "Derecho", "Psicología",
                 "Ingeniería de Sistemas", "Ingeniería Industrial", "Enfermería", "Diseño Gráfico"],
    "jornada": ["Diurna", "Nocturna", "Fin de semana"],
    "genero": ["Femenino", "Masculino"],
    "ciudad_procedencia": ["Bogotá", "Medellín", "Cali", "Bucaramanga", "Rionegro",
                           "Barranquilla", "Otra ciudad"],
}

DECISIONES = []
MOSTRAR = False


def registrar(paso, columna, accion, filas, justificacion):
    """Guarda una decisión para la tabla de decisiones. Ya está escrita: solo úsala."""
    DECISIONES.append({
        "paso": paso, "columna": columna, "accion": accion,
        "filas_afectadas": int(filas), "justificacion": justificacion,
    })


def explorar(df):
    """Paso 1 de la guía: primera mirada al dataset.

    Muestra la forma, los tipos y los nulos de cada columna, las estadísticas
    numéricas, y los valores de las columnas programa, jornada, genero y estado.
    Pregunta: ¿alguna columna numérica aparece como texto? ¿Por qué crees que pasa?
    """
    print("\n1. Exploración:", df.shape)
    df.info()
    print(df.describe().round(3).to_string())
    for columna in [*VALIDOS, "estado"]:
        print(f"\n{columna}:")
        print(df[columna].map(repr).value_counts().to_string())


def auditar(df):
    """Paso 2 de la guía: buscar problemas sin corregirlos todavía.

    Revisa: nulos reales, faltantes disfrazados ('-', 999), valores imposibles
    (edad, promedio, horas), duplicados y formatos de fecha.
    Pregunta: ¿cuál de estos problemas afecta más el análisis? ¿Por qué?
    """
    print("\n2. Nulos originales por columna:")
    print(df.isnull().sum().to_string())
    asistencia = df["asistencia_pct"].astype("string").str.strip()
    horas = df["horas_trabajo_semana"].astype("string").str.strip()
    fechas = df["fecha_matricula"].astype("string")
    medidas = {
        "Guiones en asistencia": asistencia.eq("-").sum(),
        "Guiones en horas": horas.eq("-").sum(),
        "Distancias 999": df["distancia_km"].eq(999).sum(),
        "Asistencias con %": asistencia.str.contains("%", regex=False).sum(),
        "Duplicados exactos": df.duplicated().sum(),
        "Identificadores repetidos": df["id_estudiante"].duplicated().sum(),
        "Edades fuera de 15–60": ((df["edad"] < 15) | (df["edad"] > 60)).sum(),
        "Promedios mayores a 5": df["promedio_acumulado"].gt(5).sum(),
        "Horas mayores a 100": pd.to_numeric(horas, errors="coerce").gt(100).sum(),
        "Fechas AAAA-MM-DD": fechas.str.fullmatch(r"\d{4}-\d{2}-\d{2}").sum(),
        "Fechas DD/MM/AAAA": fechas.str.fullmatch(r"\d{2}/\d{2}/\d{4}").sum(),
    }
    print(pd.Series(medidas).to_string())
    print("\nMotivos de retiro vacíos por estado:")
    print(df["motivo_retiro"].isna().groupby(df["estado"]).sum().to_string())


def convertir_numericos(df):
    """Paso 3 de la guía: columnas que deberían ser numéricas, pero llegan como texto.

    Pistas: quitar el símbolo % con str.replace; reemplazar '-' por nulo;
    convertir con pd.to_numeric(..., errors="coerce"); reemplazar 999 por nulo en distancia_km.
    Registra cada conversión con registrar().
    """
    for columna in ("asistencia_pct", "horas_trabajo_semana"):
        texto = df[columna].astype("string").str.strip()
        if columna == "asistencia_pct":
            registrar("3. Conversión", columna, "Quitar %", texto.str.contains("%", regex=False).sum(),
                      "El símbolo expresa la unidad. Se conserva la escala de 0 a 100.")
            texto = texto.str.replace("%", "", regex=False)
        guiones = texto.eq("-")
        registrar("3. Conversión", columna, "Reconocer guiones como faltantes", guiones.sum(),
                  "El guion representa un dato ausente y debe distinguirse de cero.")
        texto = texto.mask(guiones)
        numerico = pd.to_numeric(texto, errors="coerce").astype(float)
        registrar("3. Conversión", columna, "Convertir a número", numerico.notna().sum(),
                  "El tipo numérico permite calcular promedios, cuartiles y rangos.")
        fallos = texto.notna() & numerico.isna()
        if fallos.any():
            registrar("3. Conversión", columna, "Marcar textos no convertibles", fallos.sum(),
                      "Las entradas sin interpretación numérica quedan pendientes de confirmación.")
        df[columna] = numerico
    distancia = pd.to_numeric(df["distancia_km"], errors="coerce")
    centinela = distancia.eq(999)
    df["distancia_km"] = distancia.mask(centinela)
    registrar("3. Conversión", "distancia_km", "Cambiar 999 por nulo", centinela.sum(),
              "La guía identifica 999 como código de dato faltante.")
    return df


def unificar_categorias(df):
    """Paso 4 de la guía: errores tipográficos en columnas categóricas.

    Pistas: primero df[col].str.strip().str.lower(); después .replace(diccionario)
    con las variantes que encontraste con value_counts(). Los valores correctos están en VALIDOS.
    Pregunta: ¿qué variantes son el mismo valor? ¿Hay alguna que no debas unificar?
    """
    variantes = {
        "programa": {"ingenieria de sistemas": "Ingeniería de Sistemas", "psicologia": "Psicología"},
        "genero": {"f": "Femenino", "m": "Masculino"},
        "ciudad_procedencia": {"bogota": "Bogotá", "medellin": "Medellín"},
    }
    for columna, validos in VALIDOS.items():
        original = df[columna].astype("string")
        normalizado = original.str.strip().str.lower()
        mapa = {valor.lower(): valor for valor in validos}
        mapa.update(variantes.get(columna, {}))
        limpio = normalizado.replace(mapa)
        cambios = original.ne(limpio).fillna(False)
        registrar("4. Categorías", columna, "Unificar escrituras", cambios.sum(),
                  "Se consolidan las variantes de espacios, mayúsculas, tildes o abreviaturas de una misma categoría.")
        print(f"\n{columna}: variantes normalizadas y categorías finales")
        print(normalizado.value_counts().to_string())
        print("Cambios por escritura original:", original[cambios].map(repr).value_counts().to_dict())
        print(limpio.value_counts(dropna=False).to_string())
        df[columna] = limpio
    return df


def convertir_fechas(df):
    """Paso 5 de la guía: fechas escritas en dos formatos.

    Pista: intenta el formato AAAA-MM-DD y luego DD/MM/AAAA, cada uno con errors="coerce",
    y junta los resultados con fillna(). Registra cuántas fechas tenían el segundo formato.
    """
    texto = df["fecha_matricula"].astype("string").str.strip()
    iso = pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
    dia_mes = pd.to_datetime(texto, format="%d/%m/%Y", errors="coerce")
    registrar("5. Fechas", "fecha_matricula", "Convertir fechas ISO", iso.notna().sum(),
              "El formato explícito conserva el orden año, mes y día.")
    registrar("5. Fechas", "fecha_matricula", "Convertir fechas DD/MM/AAAA", dia_mes.notna().sum(),
              "El formato explícito conserva el orden día, mes y año.")
    df["fecha_matricula"] = iso.fillna(dia_mes)
    fallos = texto.notna() & df["fecha_matricula"].isna()
    if fallos.any():
        registrar("5. Fechas", "fecha_matricula", "Conservar fechas no interpretables como nulas",
                  fallos.sum(), "No hay evidencia para reconstruir estas fechas.")
    return df


def eliminar_duplicados(df):
    """Paso 6 de la guía: filas repetidas.

    Pregunta: ¿podrían existir dos estudiantes distintos con todos los datos iguales?
    Pista: duplicated() y drop_duplicates(), con reset_index(drop=True).
    """
    registrar("6. Duplicados", "Todas", "Eliminar duplicados exactos", df.duplicated().sum(),
              "Se conserva la primera aparición de cada fila completa. El ID distingue a estudiantes con perfiles iguales.")
    return df.drop_duplicates().reset_index(drop=True)


def tratar_faltantes(df):
    """Paso 7 de la guía: decidir qué hacer con los nulos reales.

    Preguntas:
    - ¿Puedes inventar una nota? ¿Qué pasa si imputas el promedio?
    - Para ciudad o tipo de colegio, ¿conviene eliminar la fila o marcar el dato como 'Sin dato'?
    - motivo_retiro tiene muchos nulos. ¿Son errores? (Pista: ¿para quiénes aplica esa columna?)
    """
    columna = "promedio_acumulado"
    registrar("7. Faltantes", columna, "Eliminar filas sin promedio", df[columna].isna().sum(),
              "Imputar calificaciones alteraría la distribución y los promedios por jornada.")
    df = df.dropna(subset=[columna]).copy()
    for columna in ("ciudad_procedencia", "tipo_colegio"):
        registrar("7. Faltantes", columna, "Etiquetar como Sin dato", df[columna].isna().sum(),
                  "Se conserva al estudiante sin asignarle una categoría desconocida.")
        df[columna] = df[columna].fillna("Sin dato")
    for columna, razon in {
        "asistencia_pct": "Se conserva la fila y se excluye del cálculo por cuartiles al faltar la asistencia.",
        "distancia_km": "No existe información suficiente para estimar la distancia individual.",
        "motivo_retiro": "El motivo solo aplica a desertores. Los motivos desconocidos también deben permanecer vacíos.",
    }.items():
        registrar("7. Faltantes", columna, "Conservar nulos", df[columna].isna().sum(), razon)
    return df


def tratar_imposibles(df):
    """Paso 8 de la guía: valores que no pueden existir.

    Preguntas:
    - La escala del promedio es de 0 a 5. ¿Qué harías con un 45?
    - Una edad de 150 años es un error. ¿Qué valor pondrías en su lugar?
    - Si el estudiante no trabaja, ¿cuántas horas de trabajo tiene? ¿Cómo lo aplicas en código?
    """
    promedio = df["promedio_acumulado"]
    otra_escala = promedio.gt(5) & promedio.le(100)
    df.loc[otra_escala, "promedio_acumulado"] = promedio[otra_escala] / 20
    registrar("8. Rangos", "promedio_acumulado", "Convertir de 0–100 a 0–5", otra_escala.sum(),
              "La guía plantea una mezcla de escalas. Se interpreta el bloque 45–78 como notas sobre 100.")
    fuera = ~df["promedio_acumulado"].between(0, 5)
    if fuera.any():
        registrar("8. Rangos", "promedio_acumulado", "Excluir notas no recuperables", fuera.sum(),
                  "Las notas fuera de ambas escalas no tienen una conversión respaldada.")
        df = df.loc[~fuera].copy()

    edad = df["edad"]
    invalida = (edad < 15) | (edad > 60)
    mediana_edad = edad[~invalida].median()
    df.loc[invalida, "edad"] = np.nan
    df["edad"] = df["edad"].fillna(mediana_edad)
    registrar("8. Rangos", "edad", f"Imputar mediana válida ({mediana_edad:g})", invalida.sum(),
              "La guía usa 15 a 60 años. La mediana se obtiene solo de edades dentro de ese rango.")

    columna = "horas_trabajo_semana"
    sin_empleo = df["trabaja"].eq("no") & (df[columna].isna() | df[columna].ne(0))
    df.loc[sin_empleo, columna] = 0
    registrar("8. Rangos", columna, "Asignar 0 a quienes no trabajan", sin_empleo.sum(),
              "Si no hay trabajo, las horas semanales de trabajo son cero.")
    imposibles = df[columna].gt(100) | df[columna].lt(0)
    df.loc[imposibles, columna] = np.nan
    registrar("8. Rangos", columna, "Marcar horas fuera de 0–100 como nulas", imposibles.sum(),
              "Se aplica el umbral del taller para excluir registros inválidos.")
    empleados = df["trabaja"].eq("sí")
    faltantes = empleados & df[columna].isna()
    mediana_horas = df.loc[empleados, columna].median()
    df.loc[faltantes, columna] = mediana_horas
    registrar("8. Rangos", columna, f"Imputar mediana de quienes trabajan ({mediana_horas:g})",
              faltantes.sum(), "Se estima solo con horas válidas de estudiantes que trabajan.")
    return df


def crear_variables(df):
    """Paso 9 de la guía: variables nuevas para el análisis.

    Crea:
    - desertor: True si estado es 'desertor', False si no.
    - cuartil_asistencia: divide asistencia_pct en cuatro grupos iguales con pd.qcut.
    Pregunta: ¿por qué conviene usar cuartiles y no valores exactos de asistencia?
    """
    df["desertor"] = df["estado"].eq("desertor")
    df["cuartil_asistencia"], cortes = pd.qcut(
        df["asistencia_pct"], 4, labels=["Q1", "Q2", "Q3", "Q4"], retbins=True
    )
    registrar("9. Variables", "desertor", "Crear indicador booleano", len(df),
              "La media del indicador equivale a la proporción de desertores.")
    registrar("9. Variables", "cuartil_asistencia", "Agrupar en cuartiles", df["cuartil_asistencia"].notna().sum(),
              "Los grupos comparan niveles de asistencia con tamaños parecidos y mantienen juntos los valores iguales.")
    print(f"\n9. Desertores: {df['desertor'].sum():,} de {len(df):,} ({df['desertor'].mean():.2%})")
    print("Cortes de asistencia:", cortes)
    return df


def guardar_grafico(fig, nombre):
    GRAFICOS.mkdir(parents=True, exist_ok=True)
    fig.savefig(GRAFICOS / nombre, dpi=170)
    if MOSTRAR:
        plt.show()
    plt.close(fig)


def resumen_tasas(df, grupo):
    return df.groupby(grupo, observed=True).agg(
        tasa=("desertor", "mean"), desertores=("desertor", "sum"),
        estudiantes=("id_estudiante", "size")
    )


def etiquetas_tasa(tabla):
    return [f"{fila.tasa:.1%}  (n={fila.estudiantes:,})" for fila in tabla.itertuples()]


def grafico_faltantes(df):
    """Gráfico 1: mapa de faltantes del dataset original.

    Pista: sns.heatmap(df.isnull(), cbar=False)
    """
    fig, ax = plt.subplots(figsize=(13, 5.6), layout="constrained")
    sns.heatmap(df.isnull(), cbar=False, yticklabels=False,
                cmap=ListedColormap(["#e5edf5", "#bf3b53"]), ax=ax)
    ax.set(title="Faltantes del dataset original", ylabel="Filas en el orden del CSV")
    ax.tick_params(axis="x", labelrotation=52)
    for etiqueta in ax.get_xticklabels():
        etiqueta.set_ha("right")
    ax.legend(handles=[Patch(color="#e5edf5", label="Con dato"),
                       Patch(color="#bf3b53", label="Nulo real")], loc="upper right",
              bbox_to_anchor=(1, 1.075), ncol=2, frameon=False)
    guardar_grafico(fig, "mapa_faltantes.png")


def grafico_distribuciones(antes, despues):
    """Gráfico 2: boxplots de promedio_acumulado y edad, antes y después de limpiar.

    Pregunta: ¿qué cambió en cada distribución? ¿Por qué?
    """
    fig, ejes = plt.subplots(2, 2, figsize=(10, 7), layout="constrained")
    fig.suptitle("Promedio y edad antes y después de la limpieza", fontsize=15, fontweight="bold")
    for fila, (columna, unidad) in enumerate([("promedio_acumulado", "Promedio"), ("edad", "Años")]):
        for ax, datos, etapa, color in zip(ejes[fila], (antes, despues),
                                          ("Antes", "Después"), ("#bd5770", "#318789")):
            sns.boxplot(y=datos[columna], ax=ax, color=color, fliersize=2)
            ax.set(title=f"{unidad} · {etapa}", ylabel=unidad)
            ax.grid(axis="y", alpha=0.22)
    guardar_grafico(fig, "distribuciones_antes_despues.png")


def grafico_tasa_programa(df):
    """Gráfico 3: tasa de deserción por programa.

    Pista: df.groupby("programa")["desertor"].mean()
    """
    tabla = resumen_tasas(df, "programa").sort_values("tasa")
    fig, ax = plt.subplots(figsize=(11, 5.8), layout="constrained")
    barras = ax.barh(tabla.index, tabla["tasa"], color="#2e668f")
    ax.bar_label(barras, labels=etiquetas_tasa(tabla), padding=5)
    ax.set(title="Tasa de deserción por programa", xlabel="Desertores / estudiantes", xlim=(0, tabla["tasa"].max() + 0.14))
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.grid(axis="x", alpha=0.22)
    ax.set_axisbelow(True)
    guardar_grafico(fig, "tasa_desercion_por_programa.png")


def grafico_tasa_asistencia(df):
    """Gráfico 4: tasa de deserción por cuartil de asistencia.

    Pista: df.groupby("cuartil_asistencia", observed=True)["desertor"].mean()
    """
    tabla = resumen_tasas(df, "cuartil_asistencia").sort_index()
    fig, ax = plt.subplots(figsize=(9, 5.5), layout="constrained")
    barras = ax.bar(tabla.index.astype(str), tabla["tasa"],
                   color=["#1e476d", "#27618a", "#347c9f", "#418e97"][:len(tabla)])
    ax.bar_label(barras, labels=etiquetas_tasa(tabla), padding=6)
    ax.set(title="Tasa de deserción por cuartil de asistencia",
           xlabel="Cuartil de asistencia (Q1 = más baja)", ylabel="Desertores / estudiantes",
           ylim=(0, tabla["tasa"].max() + 0.10))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    guardar_grafico(fig, "tasa_desercion_por_asistencia.png")


def responder_preguntas(df):
    """Paso 10 de la guía: las cinco preguntas de la institución.

    Cada pregunta debe imprimir el resultado con el número de estudiantes por grupo.
    Pregunta 1: ¿Qué programa presenta la tasa de deserción más alta?
    Pregunta 2: ¿Hay diferencia en la deserción entre becados y no becados?
    Pregunta 3: ¿Qué jornada tiene el menor promedio acumulado?
    Pregunta 4: ¿Cuántas materias reprobadas tienen en promedio los desertores frente a los activos?
                (Excluye a los graduados.)
    Pregunta 5: ¿La deserción aumenta conforme baja la asistencia?
                (Usa cuartil_asistencia.)
    """
    programas = resumen_tasas(df, "programa").sort_values("tasa", ascending=False)
    beca = resumen_tasas(df, "beca")
    jornada = df.groupby("jornada").agg(
        promedio=("promedio_acumulado", "mean"), estudiantes=("id_estudiante", "size")
    ).sort_values("promedio")
    comparables = df[df["estado"].isin(["activo", "desertor"])]
    reprobadas = comparables.groupby("estado").agg(
        promedio=("materias_reprobadas", "mean"), estudiantes=("id_estudiante", "size")
    )
    asistencia = df.groupby("cuartil_asistencia", observed=True).agg(
        tasa=("desertor", "mean"), desertores=("desertor", "sum"),
        estudiantes=("id_estudiante", "size"), asistencia_promedio=("asistencia_pct", "mean")
    ).sort_index()
    print("\n10. Preguntas del taller")
    for numero, (pregunta, tabla) in enumerate([
        ("Tasa por programa", programas), ("Tasa según beca", beca),
        ("Promedio acumulado por jornada", jornada), ("Materias reprobadas por estado", reprobadas),
        ("Tasa y asistencia promedio por cuartil", asistencia),
    ], 1):
        salida = tabla.copy()
        if "tasa" in salida:
            salida["tasa"] = salida["tasa"].map("{:.2%}".format)
        print(f"\n{numero}. {pregunta}\n{salida.round(3).to_string()}")
    print(f"\nRegistros sin asistencia, fuera de los cuartiles: {df['asistencia_pct'].isna().sum()}")


def guardar(df):
    """Paso 11 de la guía: guardar el dataset limpio y la tabla de decisiones. Ya está escrito."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED / "dataset_limpio.csv", index=False)
    pd.DataFrame(DECISIONES).to_csv(PROCESSED / "decisiones.csv", index=False)
    print(f"\nDataset limpio guardado: {df.shape[0]} filas, {df.shape[1]} columnas.")


def main():
    global MOSTRAR
    parser = argparse.ArgumentParser(description="Taller de retención estudiantil")
    parser.add_argument("--mostrar", action="store_true", help="Abrir las figuras en un entorno gráfico")
    MOSTRAR = parser.parse_args().mostrar
    if not MOSTRAR:
        plt.switch_backend("Agg")
    DECISIONES.clear()
    original = pd.read_csv(RAW)
    df = original.copy()

    explorar(df)
    auditar(df)
    grafico_faltantes(df)

    df = convertir_numericos(df)
    df = unificar_categorias(df)
    df = convertir_fechas(df)
    df = eliminar_duplicados(df)
    df = tratar_faltantes(df)
    df = tratar_imposibles(df)
    df = crear_variables(df)

    grafico_distribuciones(original, df)
    grafico_tasa_programa(df)
    grafico_tasa_asistencia(df)

    responder_preguntas(df)
    print("\nTabla de decisiones:")
    print(pd.DataFrame(DECISIONES))
    guardar(df)


if __name__ == "__main__":
    main()

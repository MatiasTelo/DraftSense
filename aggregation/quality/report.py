"""El Informe de Calidad de Datos (`docs/27-validacion-confiabilidad.md` §9).

**Es determinista y entra en CA-408**, igual que los CSV: no lleva fecha de generación ni nada que
dependa del reloj —la única fecha es `exported_at`—, las tablas van en un orden fijo y los números
con formato fijo. Si se agrega algo que dependa del orden de un `dict` armado desde la base, o un
`str(float)`, dos corridas iguales darían dos informes distintos y nada fallaría hasta el test.

Está en español (decisión del 07/11/2026); los identificadores quedan en inglés y en código, como
en los CSV.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from aggregation.fits import DimensionResult
from aggregation.load import Dataset
from aggregation.params import RunParams
from aggregation.quality import agreement, metrics, segments
from aggregation.quality.data import Extra
from aggregation.quality.segments import Size
from aggregation.writers import Written

KIND = "quality_report"


@dataclass(frozen=True, slots=True)
class SegmentFits:
    """Una (variable, dimensión): el tamaño de cada segmento y el ajuste de los calculables."""

    sizes: Mapping[str, Size]
    fits: Mapping[str, DimensionResult]


@dataclass(frozen=True, slots=True)
class Inputs:
    data: Dataset
    params: RunParams
    results: metrics.Results
    #: El bootstrap por respondedor de cada dimensión, en el orden de `data.dimensions`.
    by_respondent: Sequence[DimensionResult]
    #: `variable → código de dimensión → SegmentFits`.
    segments: Mapping[str, Mapping[str, SegmentFits]]
    extra: Extra
    csvs: Sequence[Written]


# ------------------------------------------------------------------------------ formato fijo


def f3(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def pct(part: int, whole: int) -> str:
    return "—" if whole == 0 else f"{100 * part / whole:.1f} %"


def median(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return [*lines, ""]


# --------------------------------------------------------------------------------- secciones


def build(inputs: Inputs) -> str:
    data, params, results, extra = inputs.data, inputs.params, inputs.results, inputs.extra
    agreements = agreement.compute(data)
    retests = metrics.retest(extra)
    honeypots = metrics.honeypots(extra, data.champions)
    coverage = metrics.coverage(data)
    magnitudes = metrics.magnitudes(data, results)
    reports = results.reports()
    everything = metrics.concentration(data.rows)
    pairwise = metrics.concentration(metrics.decisive(data.rows))
    rank_comparisons = {
        code: segments.comparisons(fit.fits, segments.names("rank"), data.pool)
        for code, fit in inputs.segments.get("rank", {}).items()
    }
    triggered = segments.triggered(rank_comparisons)
    wide = metrics.wide_peaks(data, results, params.support_thresholds)
    uneven = metrics.uneven_traits(data, results)

    out: list[str] = [f"# Informe de Calidad de Datos — v{data.patch_version}", ""]

    # 1. Encabezado ----------------------------------------------------------------------------
    out += [
        f"Ventana de parches **{params.patch_window}**, exportada el "
        f"**{params.exported_at.isoformat()}**. Especificación: "
        "`docs/27-validacion-confiabilidad.md`.",
        "",
        f"Un archivo `v{data.patch_version}` mezcla las respuestas de todos los parches de la "
        "ventana, con decaimiento por recencia (ADR-004): "
        + ", ".join(f"`{p}`" for p in extra.patches)
        + ".",
        "",
        "## Parámetros de la corrida",
        "",
    ]
    record = params.as_record()
    out += table(
        ["Parámetro", "Valor"],
        [[f"`{k}`", f"`{json.dumps(record[k], sort_keys=True)}`"] for k in sorted(record)],
    )
    out += ["## Archivos de esta entrega", ""]
    out += table(
        ["Archivo", "Filas", "SHA-256"],
        [[f"`{w.file_name}`", str(w.rows), f"`{w.sha256}`"] for w in inputs.csvs],
    )

    # 2. Hallazgos -----------------------------------------------------------------------------
    findings: list[str] = []
    for a in agreements:
        if a.reading == "no confiable":
            findings.append(
                f"Alfa no confiable en `{a.magnitude}`: {f3(a.result.value)} (27 §2.4)."
            )
    for r in reports:
        if r.failed:
            findings.append(
                f"`{r.name}` salió `insufficient` entero: {r.discarded} de {r.attempts} "
                "remuestreos descartados (25 §4.2)."
            )
        if r.components > 1:
            findings.append(f"`{r.name}` tiene el grafo partido en {r.components} componentes.")
    if pairwise.index is not None and pairwise.index > metrics.CONCENTRATION_LIMIT:
        findings.append(
            f"El decil más activo aporta {pct(pairwise.top_rows, pairwise.rows)} de las "
            "comparaciones del tipo 1: corresponde un ADR que reemplace 26 §3.2 (25 §4.7). Se "
            "decide con los datos del piloto."
        )
    if len(triggered) >= segments.TRIGGER_DIMENSIONS:
        findings.append(
            f"ρ(`low`, `high`) < {segments.TRIGGER_RHO:.2f} en {len(triggered)} dimensiones "
            f"({', '.join(f'`{c}`' for c in triggered)}): la medición depende del rango; se "
            "propone la salida por segmento como trabajo futuro (25 §3.10)."
        )
    for h in honeypots:
        if h.suspicious:
            findings.append(
                f"Honeypot sospechosa `{h.question_id}` ({h.label}): quienes la fallan son "
                "igual o más consistentes en el retest que quienes la aprueban (27 §4.3)."
            )
    for version, count in extra.active_honeypots:
        if count == 0:
            findings.append(
                f"El parche `{version}` no tiene honeypots activas: el trust de quienes "
                "respondieron en él quedó congelado (ADR-024)."
            )
    if uneven:
        findings.append(
            "`proportion_n` distinto entre atributos de "
            + ", ".join(uneven)
            + ": hubo un cambio de catálogo en la ventana o un error (25 §5.6)."
        )
    out += ["## Hallazgos", ""]
    out += [f"- {f}" for f in findings] if findings else ["Sin hallazgos."]
    out += [""]

    # 3. Lo que entró y lo que no ----------------------------------------------------------------
    e = extra.excluded
    included = len(data.rows)
    out += ["## Lo que entró y lo que no", ""]
    out += table(
        ["Respuestas de la ventana", "Cantidad", "%"],
        [
            ["Total", str(e.window), pct(e.window, e.window)],
            ["Retests (25 §1.3)", str(e.retest), pct(e.retest, e.window)],
            ["Honeypots (25 §1.3)", str(e.honeypot), pct(e.honeypot, e.window)],
            ["De respondedores marcados por huella", str(e.flagged), pct(e.flagged, e.window)],
            [
                f"De respondedores con trust < {params.min_trust:.3f}",
                str(e.trust),
                pct(e.trust, e.window),
            ],
            ["**Entraron a la corrida**", f"**{included}**", pct(included, e.window)],
        ],
    )
    out += [
        f"{everything.respondents} respondedores aportan las {everything.rows} filas de la "
        "corrida. En el tipo 1 cada comparación de un ranking es una fila (27 §1.2).",
        "",
    ]

    # 4. Muestra -----------------------------------------------------------------------------
    omitted, total = metrics.omitted_onboarding(data, extra.people)
    out += [
        "## Muestra",
        "",
        f"**{omitted} de {total} respondedores ({pct(omitted, total)}) no declararon ninguno de "
        "los tres datos.** Todo análisis por segmento de abajo cubre al resto (25 §3.9).",
        "",
    ]
    for title, rows in metrics.sample(data, extra.people).items():
        out += [f"### {title}", ""]
        out += table(
            ["Valor", "Respondedores", "% resp.", "Respuestas", "% respuestas"],
            [
                [
                    r.value if r.value == "(no dijo)" else f"`{r.value}`",
                    str(r.respondents),
                    pct(r.respondents, everything.respondents),
                    str(r.responses),
                    pct(r.responses, everything.rows),
                ]
                for r in rows
            ],
        )

    # 5. Acuerdo -------------------------------------------------------------------------------
    out += [
        "## Acuerdo inter-anotador",
        "",
        "Alfa de Krippendorff por magnitud, sin ponderar, sobre las filas de la corrida, con "
        "`unknown` afuera (27 §2). Umbrales: ≥ 0.800 confiable, 0.667–0.800 tentativo, < 0.667 "
        "no confiable. **Sólo se reporta: los CSV no cambian.**",
        "",
    ]
    out += table(
        ["Magnitud", "Escala", "α", "Unidades", "Valores", "Lectura"],
        [
            [
                f"`{a.magnitude}`",
                a.scale,
                f3(a.result.value),
                str(a.result.units),
                str(a.result.pairable),
                a.reading,
            ]
            for a in agreements
        ],
    )
    out += [
        "Alfa mide acuerdo, no validez: una comunidad entera puede coincidir en algo equivocado. "
        "Y un alfa bajo en una magnitud de opinión no es necesariamente ruido: hay matchups "
        "genuinamente discutidos.",
        "",
    ]

    # 6. Test-retest -----------------------------------------------------------------------------
    out += [
        "## Test-retest",
        "",
        "Con las reglas de 22 §4, sobre los respondedores no marcados de la ventana, sin filtro "
        "de trust (27 §1.1).",
        "",
    ]
    out += table(
        ["Tipo", "Pares", "Consistentes", "Tasa"],
        [
            [r.label, str(r.pairs), str(r.consistent), f3(metrics.rate(r.consistent, r.pairs))]
            for r in retests
        ],
    )

    # 7. Honeypots -----------------------------------------------------------------------------
    attempts = sum(h.attempts for h in honeypots)
    passed = sum(h.passed for h in honeypots)
    out += [
        "## Honeypots",
        "",
        f"*Pass rate* global: **{f3(metrics.rate(passed, attempts))}** ({passed} de {attempts} "
        "intentos; `unknown` no es intento). Población: no marcados, sin filtro de trust.",
        "",
    ]
    out += table(
        ["Parche", "Honeypots activas"],
        [[f"`{v}`", str(c)] for v, c in extra.active_honeypots],
    )
    seg_names = [*segments.RANK_SEGMENTS, segments.UNDECLARED]
    out += table(
        ["Honeypot", "Intentos", "Pass rate", *(f"`{s}`" for s in seg_names)],
        [
            [
                f"`{h.question_id}` {h.label}",
                str(h.attempts),
                f3(metrics.rate(h.passed, h.attempts)),
                *(f"{f3(metrics.rate(ok, n))} ({n})" for _, n, ok in h.by_segment),
            ]
            for h in honeypots
        ],
    )
    out += [
        f"Cruce con el test-retest para las de {extra.settings.honeypot_min_attempts} intentos o "
        "más (27 §4.3): sospechosa si quienes la fallan son igual o más consistentes que quienes "
        "la aprueban.",
        "",
    ]
    crossed = [h for h in honeypots if h.failers is not None and h.passers is not None]
    out += (
        table(
            ["Honeypot", "Consistencia de quienes fallan", "De quienes aprueban", "Sospechosa"],
            [
                [
                    f"`{h.question_id}` {h.label}",
                    f"{f3(metrics.rate(*h.failers))} ({h.failers[1]})",
                    f"{f3(metrics.rate(*h.passers))} ({h.passers[1]})",
                    "sí" if h.suspicious else "no",
                ]
                for h in crossed
                if h.failers is not None and h.passers is not None
            ],
        )
        if crossed
        else ["Ninguna llega al piso de intentos.", ""]
    )

    # 8. Cobertura -----------------------------------------------------------------------------
    out += ["## Cobertura", "", "### Por par", ""]
    out += table(
        ["Magnitud", "Pares posibles", "Observados", "%", "Mín", "Mediana", "Máx"],
        [
            [
                f"`{c.magnitude}`",
                str(c.possible),
                str(c.observed),
                pct(c.observed, c.possible),
                *(
                    (str(c.spread[0]), median(c.spread[1]), str(c.spread[2]))
                    if c.spread is not None
                    else ("—", "—", "—")
                ),
            ]
            for c in coverage
        ],
    )
    out += [
        "En las duplas el par es la dupla, no el enfrentamiento entre dos (27 §5.1).",
        "",
        "### Por nivel de soporte",
        "",
    ]
    out += table(
        ["Magnitud", "`solid`", "`limited`", "`insufficient`"],
        [[f"`{m.name}`", *(str(x) for x in m.support())] for m in magnitudes],
    )
    out += ["### Conectividad y remuestreos", ""]
    out += table(
        ["Ajuste", "Comparaciones", "Componentes", "Remuestreos", "Descartados", "Resultado"],
        [
            [
                f"`{r.name}`",
                str(r.comparisons),
                str(r.components),
                str(r.attempts),
                str(r.discarded),
                "`insufficient`" if r.failed else "ok",
            ]
            for r in reports
        ],
    )
    out += [
        "### Chequeos de consistencia",
        "",
        "- Picos con la `n` de `solid` y un intervalo más ancho, posible distribución bimodal "
        "(20 §3): " + (", ".join(wide) if wide else "ninguno") + ".",
        "- `proportion_n` distinto entre los atributos de un campeón: "
        + (", ".join(uneven) if uneven else "ninguno")
        + ".",
        "",
    ]

    # 9. Incertidumbre -------------------------------------------------------------------------
    out += ["## Incertidumbre", "", "### Ancho medio del intervalo", ""]
    out += table(
        ["Magnitud", "Unidad", "Ancho medio"],
        [[f"`{m.name}`", m.unit, f3(m.mean_width())] for m in magnitudes],
    )
    out += [
        "### Las dos versiones del bootstrap (25 §4.7)",
        "",
        "Sobre comparaciones es el que se publica en los CSV; por respondedor, sólo acá.",
        "",
    ]
    versions: list[list[str]] = []
    for comparison, by_person in zip(results.dimensions, inputs.by_respondent, strict=True):
        base = metrics.Magnitude("", "", [comparison.estimates[c] for c in data.pool])
        clustered = metrics.Magnitude("", "", [by_person.estimates[c] for c in data.pool])
        narrow, honest = base.mean_width(), clustered.mean_width()
        ratio = None if narrow is None or honest is None or narrow == 0 else honest / narrow
        versions.append(
            [
                f"`{comparison.code}`",
                f3(narrow),
                "no calculable" if by_person.report.failed else f3(honest),
                f3(ratio),
            ]
        )
    out += table(["Dimensión", "Comparaciones", "Por respondedor", "Cociente"], versions)
    out += [
        "### Índice de concentración",
        "",
    ]
    out += table(
        ["Sobre", "Respondedores", "Decil más activo", "Filas", "Aporta", "Índice"],
        [
            [
                "todas las filas (25 §3.4)",
                str(everything.respondents),
                str(everything.top),
                str(everything.rows),
                str(everything.top_rows),
                f3(everything.index),
            ],
            [
                "comparaciones decisivas del tipo 1 (25 §4.7)",
                str(pairwise.respondents),
                str(pairwise.top),
                str(pairwise.rows),
                str(pairwise.top_rows),
                f3(pairwise.index),
            ],
        ],
    )
    over = pairwise.index is not None and pairwise.index > metrics.CONCENTRATION_LIMIT
    out += [
        f"Criterio de 25 §4.7: más de {metrics.CONCENTRATION_LIMIT:.2f} ⇒ ADR. "
        + ("**Se cumple.**" if over else "No se cumple.")
        + " La decisión se toma con los datos del piloto (27 §6.3).",
        "",
    ]

    # 10. Datos declarados ---------------------------------------------------------------------
    out += [
        "## Estabilidad por segmento",
        "",
        f"25 §3.5: las 8 dimensiones re-ajustadas por segmento con los mismos parámetros. Piso: "
        f"{extra.settings.segment_min_respondents} respondedores y "
        f"{extra.settings.segment_min_comparisons} comparaciones decisivas en la dimensión.",
        "",
    ]
    titles = {"rank": "Rango", "hours": "Horas por semana"}
    for variable, by_code in inputs.segments.items():
        order = segments.names(variable)
        out += [f"### {titles[variable]}", ""]
        out += table(
            ["Dimensión", *(f"`{s}`" for s in order)],
            [
                [
                    f"`{code}`",
                    *(
                        f"{fit.sizes[s].respondents} / {fit.sizes[s].comparisons}"
                        + ("" if fit.sizes[s].calculable else " — no calculable")
                        for s in order
                    ),
                ]
                for code, fit in by_code.items()
            ],
        )
        out += ["Cada celda: respondedores / comparaciones.", ""]
        compared = [
            [
                f"`{code}`",
                f"`{c.first}` – `{c.second}`",
                str(c.common),
                f3(c.rho),
                f3(c.mean_abs_diff),
                str(c.support_changes),
            ]
            for code, fit in by_code.items()
            for c in segments.comparisons(fit.fits, order, data.pool)
        ]
        out += (
            table(
                ["Dimensión", "Segmentos", "Campeones", "ρ", "Dif. media", "Cambian soporte"],
                compared,
            )
            if compared
            else ["Ningún par de segmentos calculables.", ""]
        )
    out += [
        f"Disparador de 25 §3.10 (ρ(`low`, `high`) < {segments.TRIGGER_RHO:.2f} en "
        f"{segments.TRIGGER_DIMENSIONS} o más dimensiones): "
        + ("**se cumple**" if len(triggered) >= segments.TRIGGER_DIMENSIONS else "no se cumple")
        + f" ({len(triggered)}).",
        "",
        "## Cobertura por rol",
        "",
    ]
    out += table(
        ["Magnitud", "Respuestas", "De mains del rol", "Sin rol declarado"],
        [
            [
                f"`{r.magnitude}`",
                str(r.responses),
                pct(r.mains, r.responses),
                pct(r.undeclared, r.responses),
            ]
            for r in metrics.role_coverage(data, extra.people)
        ],
    )
    buckets, rho, declared = metrics.trust_by_hours(extra)
    out += [
        "## Trust por horas",
        "",
        "Población: no marcados de la ventana, sin filtro de trust.",
        "",
    ]
    out += table(
        ["Horas", "n", "Mín", "P25", "Mediana", "P75", "Máx"],
        [
            [
                b.bucket if b.bucket == "(no dijo)" else f"`{b.bucket}`",
                str(b.n),
                *((f3(q) for q in b.quantiles) if b.quantiles else ("—",) * 5),
            ]
            for b in buckets
        ],
    )
    out += [
        f"ρ de Spearman entre el orden del bucket y el trust: **{f3(rho)}** ({declared} "
        "respondedores que declararon). Se espera una relación positiva y suave (25 §3.7).",
        "",
    ]

    # 11. Huella -------------------------------------------------------------------------------
    flagged = sum(1 for p in extra.people.values() if p.flagged)
    out += [
        "## Huella",
        "",
        f"{flagged} respondedores marcados por huella con actividad en la ventana; "
        f"{extra.excluded.flagged} respuestas suyas quedaron fuera de la corrida. Umbral: más de "
        f"{extra.settings.fingerprint_max_identities} identidades nuevas por huella en 24 horas. "
        "**Una parte puede ser una red compartida con equipos clonados** (22 §6.3).",
        "",
    ]

    # 12. Advertencias -------------------------------------------------------------------------
    out += [
        "## Advertencias de lectura",
        "",
        "- `_norm` no es comparable entre exportaciones: su referencia es el mínimo y el máximo "
        "del pool de esta corrida. Para comparar entre parches, la columna en log-odds (26 §2.5).",
        "- En `champion_traits`, la proporción es **entre quienes marcaron al menos un atributo** "
        "(ADR-027).",
        "- El idioma en que se contestó no se registra: no hay análisis por idioma (ADR-028).",
        "- Los intervalos publicados suponen comparaciones independientes; la sección de "
        "incertidumbre muestra cuánto más anchos salen por respondedor (25 §4.7).",
        "- La vida media, `σ` y los umbrales de `_support` publican el valor usado, sin análisis "
        "de sensibilidad: se calibran con el piloto (27 §9.3).",
    ]
    return "\n".join(out) + "\n"


def write(text: str, patch: str, out: Path) -> Written:
    """El archivo y su SHA-256, calculado sobre los bytes escritos. `row_count` son las líneas y
    `column_count` 0, porque `exports` exige las dos y un Markdown no es una tabla (27 §9.1)."""
    data = text.encode("utf-8")
    name = f"data_quality_report_v{patch}.md"
    path = out / name
    path.write_bytes(data)
    return Written(
        kind=KIND,
        file_name=name,
        sha256=hashlib.sha256(data).hexdigest(),
        rows=text.count("\n"),
        columns=0,
        path=path,
    )

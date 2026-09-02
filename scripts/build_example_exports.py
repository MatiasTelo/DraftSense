# -*- coding: utf-8 -*-
"""Genera los tres CSV de ejemplo de DraftSense.

Los valores son SINTETICOS y plausibles, no medidos. Lo que si es real:
la forma del archivo, el orden y la cantidad de columnas, la formula de la
curva de poder, el intervalo de Wilson y los umbrales de support_level
definidos en 26-esquema-de-salida.md seccion 2.4.
"""
import csv, math, os

OUT = "draftsense/docs/examples"
PATCH_WINDOW = "16.18..16.20"
EXPORTED_AT = "2026-10-24"
SIGMA = 7.5
Z = 1.96

DIMS = ["engage", "poke", "pick", "peel", "mobility", "scaling", "cc", "waveclear"]
TRAITS = ["engage", "poke", "pick", "peel", "front_to_back", "dive", "split_push"]
LANE_ROLES = ["top", "mid", "adc"]


def ci(value, n, k):
    """IC 95% simetrico de ancho k/sqrt(n): aproximacion del bootstrap."""
    if n == 0:
        return None, None, None
    w = k / math.sqrt(n)
    return round(value - w / 2, 3), round(value + w / 2, 3), w


def wilson(p, n):
    if n == 0:
        return None, None, None
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    lo, hi = max(0.0, c - h), min(1.0, c + h)
    return round(lo, 3), round(hi, 3), hi - lo


def support(kind, n, width):
    if n == 0 or width is None:
        return "insufficient"
    t = {
        "dimension": ((25, 0.60), (10, 1.20)),
        "peak": ((20, 4.00), (10, 8.00)),
        "lane": ((20, 0.60), (8, 1.20)),
        "synergy": ((15, 0.80), (6, 1.50)),
        "trait": ((20, 0.25), (10, 0.45)),
    }[kind]
    if n >= t[0][0] and width <= t[0][1]:
        return "solid"
    if n >= t[1][0] and width <= t[1][1]:
        return "limited"
    return "insufficient"


def f3(x):
    return "" if x is None else "%.3f" % x


# champion_id, riot_key, display_name, roles, pool_tier
CHAMPS = [
    (9, "Jhin", "Jhin", ["adc"], 1),
    (12, "Alistar", "Alistar", ["support"], 1),
    (18, "Darius", "Darius", ["top"], 1),
    (25, "Garen", "Garen", ["top"], 1),
    (30, "Karma", "Karma", ["support", "mid"], 1),
    (34, "Kayle", "Kayle", ["top", "mid"], 1),
    (41, "Lucian", "Lucian", ["adc", "mid"], 1),
    (48, "Nami", "Nami", ["support"], 1),
    (55, "Ziggs", "Ziggs", ["mid"], 2),
    (61, "Syndra", "Syndra", ["mid"], 1),
    (72, "Zed", "Zed", ["mid"], 1),
    (77, "Ivern", "Ivern", ["jungle"], 3),
    (88, "Sejuani", "Sejuani", ["jungle"], 1),
]

DIMVAL = {
    "Jhin": dict(engage=-1.18, poke=1.06, pick=0.88, peel=-0.44, mobility=-0.92, scaling=0.41, cc=0.34, waveclear=0.28),
    "Alistar": dict(engage=1.42, poke=-1.35, pick=0.62, peel=1.28, mobility=0.15, scaling=-0.88, cc=1.63, waveclear=-1.38),
    "Darius": dict(engage=0.71, poke=-0.62, pick=0.94, peel=-0.85, mobility=-1.12, scaling=-0.34, cc=0.28, waveclear=-0.21),
    "Garen": dict(engage=0.44, poke=-1.02, pick=0.35, peel=-0.58, mobility=-0.31, scaling=-0.52, cc=0.11, waveclear=0.62),
    "Karma": dict(engage=-0.35, poke=0.94, pick=-0.12, peel=1.05, mobility=0.38, scaling=-0.21, cc=0.22, waveclear=0.44),
    "Kayle": dict(engage=-1.24, poke=0.22, pick=-0.86, peel=0.31, mobility=-0.18, scaling=2.01, cc=-0.74, waveclear=0.86),
    "Lucian": dict(engage=-0.42, poke=0.58, pick=0.51, peel=-0.62, mobility=1.12, scaling=-0.66, cc=-0.48, waveclear=0.35),
    "Nami": dict(engage=-0.28, poke=0.42, pick=0.18, peel=1.34, mobility=-0.55, scaling=0.12, cc=0.96, waveclear=-0.72),
    "Ziggs": dict(engage=-0.91, poke=1.44, pick=-0.38, peel=-0.66, mobility=-0.72, scaling=0.34, cc=0.12, waveclear=1.68),
    "Syndra": dict(engage=-0.22, poke=1.28, pick=1.02, peel=-0.31, mobility=-0.44, scaling=0.94, cc=0.68, waveclear=0.72),
    "Zed": dict(engage=0.18, poke=0.34, pick=1.71, peel=-1.24, mobility=1.58, scaling=0.22, cc=-1.02, waveclear=0.18),
    "Ivern": dict(engage=None, poke=None, pick=None, peel=0.34, mobility=None, scaling=None, cc=0.51, waveclear=None),
    "Sejuani": dict(engage=1.28, poke=-0.94, pick=0.44, peel=0.72, mobility=0.24, scaling=0.18, cc=1.51, waveclear=-0.38),
}

BASE_N = {"Jhin": 71, "Alistar": 132, "Darius": 118, "Garen": 84, "Karma": 63,
          "Kayle": 97, "Lucian": 88, "Nami": 69, "Ziggs": 31, "Syndra": 104,
          "Zed": 126, "Ivern": 6, "Sejuani": 58}

DIM_N_FACTOR = {"engage": 1.12, "poke": 0.86, "pick": 0.78, "peel": 0.74,
                "mobility": 0.92, "scaling": 0.88, "cc": 0.99, "waveclear": 0.41}

UNKNOWN = {
    ("Alistar", "waveclear"): 0.34, ("Nami", "waveclear"): 0.31,
    ("Karma", "waveclear"): 0.22, ("Alistar", "scaling"): 0.17,
    ("Sejuani", "waveclear"): 0.19, ("Ivern", "peel"): 0.28,
    ("Ivern", "cc"): 0.24, ("Jhin", "mobility"): 0.14,
}

PEAK = {"Jhin": (22, 44), "Alistar": (14, 38), "Darius": (12, 51), "Garen": (13, 29),
        "Karma": (16, 21), "Kayle": (31, 47), "Lucian": (15, 36), "Nami": (18, 17),
        "Ziggs": (19, 12), "Syndra": (24, 33), "Zed": (17, 42), "Ivern": (None, 4),
        "Sejuani": (20, 26)}

LANE = {
    "Jhin": {"adc": (-0.18, 34)},
    "Darius": {"top": (0.82, 47)},
    "Garen": {"top": (0.34, 38)},
    "Karma": {"mid": (0.12, 9)},
    "Kayle": {"top": (-0.88, 41), "mid": (-0.62, 14)},
    "Lucian": {"adc": (0.64, 29), "mid": (0.28, 11)},
    "Ziggs": {"mid": (-0.24, 16)},
    "Syndra": {"mid": (0.46, 44)},
    "Zed": {"mid": (0.71, 52)},
}

SYNERGY_MEAN = {"Jhin": (0.18, 12), "Alistar": (0.74, 11), "Karma": (0.61, 9),
                "Lucian": (0.44, 13), "Nami": (0.92, 14), "Sejuani": (0.38, 7),
                "Darius": (0.22, 5), "Zed": (-0.31, 4), "Syndra": (-0.12, 3),
                "Garen": (None, 0), "Kayle": (None, 0), "Ziggs": (None, 0),
                "Ivern": (None, 0)}

TRAITVAL = {
    "Alistar": dict(engage=.91, poke=.04, pick=.34, peel=.77, front_to_back=.52, dive=.61, split_push=.02),
    "Darius": dict(engage=.58, poke=.06, pick=.44, peel=.08, front_to_back=.41, dive=.29, split_push=.72),
    "Garen": dict(engage=.46, poke=.04, pick=.38, peel=.11, front_to_back=.34, dive=.22, split_push=.81),
    "Jhin": dict(engage=.05, poke=.78, pick=.62, peel=.09, front_to_back=.74, dive=.06, split_push=.12),
    "Karma": dict(engage=.18, poke=.71, pick=.21, peel=.82, front_to_back=.58, dive=.34, split_push=.07),
    "Kayle": dict(engage=.04, poke=.28, pick=.06, peel=.38, front_to_back=.88, dive=.12, split_push=.78),
    "Lucian": dict(engage=.22, poke=.54, pick=.48, peel=.12, front_to_back=.61, dive=.44, split_push=.18),
    "Nami": dict(engage=.24, poke=.48, pick=.32, peel=.86, front_to_back=.64, dive=.28, split_push=.03),
    "Sejuani": dict(engage=.89, poke=.07, pick=.41, peel=.58, front_to_back=.62, dive=.74, split_push=.05),
    "Syndra": dict(engage=.16, poke=.82, pick=.68, peel=.14, front_to_back=.58, dive=.22, split_push=.21),
    "Zed": dict(engage=.12, poke=.34, pick=.88, peel=.04, front_to_back=.18, dive=.62, split_push=.68),
    "Ziggs": dict(engage=.07, poke=.91, pick=.12, peel=.09, front_to_back=.72, dive=.04, split_push=.38),
    "Ivern": dict(engage=None, poke=None, pick=None, peel=None, front_to_back=None, dive=None, split_push=None),
}

TRAIT_N = {"Alistar": 64, "Darius": 58, "Garen": 41, "Jhin": 47, "Karma": 38,
           "Kayle": 52, "Lucian": 44, "Nami": 36, "Sejuani": 33, "Syndra": 49,
           "Zed": 55, "Ziggs": 24, "Ivern": 0}


def build_champion_features():
    header = ["champion_id", "riot_key", "display_name", "roles", "pool_tier",
              "patch_window", "exported_at"]
    for d in DIMS:
        header += [d, d + "_ci_low", d + "_ci_high", d + "_n", d + "_support",
                   d + "_unknown_rate", d + "_norm"]
    header += ["peak_minute", "peak_minute_ci_low", "peak_minute_ci_high",
               "peak_minute_n", "peak_minute_support",
               "power_at_5", "power_at_10", "power_at_15", "power_at_20", "power_at_25"]
    for r in LANE_ROLES:
        p = "lane_strength_" + r
        header += [p, p + "_ci_low", p + "_ci_high", p + "_n", p + "_support"]
    header += ["synergy_mean", "synergy_mean_n", "synergy_mean_support"]
    for t in TRAITS:
        p = "trait_" + t
        header += [p, p + "_ci_low", p + "_ci_high", p + "_n", p + "_support"]
    assert len(header) == 126, len(header)

    norm_range = {}
    for d in DIMS:
        vals = [DIMVAL[c[1]][d] for c in CHAMPS if DIMVAL[c[1]][d] is not None]
        norm_range[d] = (min(vals), max(vals))

    rows = []
    for cid, key, name, roles, tier in CHAMPS:
        row = [cid, key, name, "|".join(roles), tier, PATCH_WINDOW, EXPORTED_AT]

        for d in DIMS:
            v = DIMVAL[key][d]
            if v is None:
                row += ["", "", "", 0, "insufficient", "", ""]
                continue
            n = max(0, int(round(BASE_N[key] * DIM_N_FACTOR[d])))
            lo, hi, w = ci(v, n, 3.92)
            ur = UNKNOWN.get((key, d), round(0.03 + 0.09 * ((cid * 7 + len(d)) % 5) / 4, 2))
            nlo, nhi = norm_range[d]
            row += [f3(v), f3(lo), f3(hi), n, support("dimension", n, w),
                    "%.2f" % ur, "%.3f" % ((v - nlo) / (nhi - nlo))]

        pk, pn = PEAK[key]
        if pk is None:
            row += ["", "", "", pn, "insufficient", "", "", "", "", ""]
        else:
            w = 24 / math.sqrt(pn)
            row += [pk, int(round(pk - w / 2)), int(round(pk + w / 2)), pn,
                    support("peak", pn, w)]
            row += ["%.2f" % math.exp(-((t - pk) ** 2) / (2 * SIGMA ** 2))
                    for t in (5, 10, 15, 20, 25)]

        for r in LANE_ROLES:
            e = LANE.get(key, {}).get(r)
            if e is None:
                row += ["", "", "", 0, "insufficient"]
            else:
                v, n = e
                lo, hi, w = ci(v, n, 3.20)
                row += [f3(v), f3(lo), f3(hi), n, support("lane", n, w)]

        sv, sn = SYNERGY_MEAN[key]
        if sv is None:
            row += ["", sn, "insufficient"]
        else:
            _, _, w = ci(sv, sn, 4.20)
            row += [f3(sv), sn, support("synergy", sn, w)]

        tn = TRAIT_N[key]
        for t in TRAITS:
            p = TRAITVAL[key][t]
            if p is None or tn == 0:
                row += ["", "", "", tn, "insufficient"]
            else:
                lo, hi, w = wilson(p, tn)
                row += ["%.3f" % p, f3(lo), f3(hi), tn, support("trait", tn, w)]

        assert len(row) == 126, (key, len(row))
        rows.append(row)
    return header, rows


# (a_id, a_key, b_id, b_key, role, advantage, n)
MATCHUPS = [
    (18, "Darius", 25, "Garen", "top", 0.340, 41),
    (18, "Darius", 34, "Kayle", "top", 0.720, 27),
    (25, "Garen", 34, "Kayle", "top", 0.510, 18),
    (30, "Karma", 61, "Syndra", "mid", -0.440, 9),
    (34, "Kayle", 55, "Ziggs", "mid", -0.180, 7),
    (34, "Kayle", 72, "Zed", "mid", -0.630, 22),
    (41, "Lucian", 61, "Syndra", "mid", -0.120, 12),
    (55, "Ziggs", 61, "Syndra", "mid", -0.150, 19),
    (55, "Ziggs", 72, "Zed", "mid", -0.480, 14),
    (61, "Syndra", 72, "Zed", "mid", -0.280, 23),
    (9, "Jhin", 41, "Lucian", "adc", -0.410, 31),
    (30, "Karma", 34, "Kayle", "mid", 0.190, 0),
    (41, "Lucian", 72, "Zed", "mid", -0.350, 0),
]


def build_matchups():
    header = ["champion_a_id", "champion_a_key", "champion_b_id", "champion_b_key",
              "role", "advantage", "advantage_ci_low", "advantage_ci_high",
              "n_responses", "support", "is_observed", "patch_window"]
    assert len(header) == 12
    rows = []
    for aid, akey, bid, bkey, role, adv, n in MATCHUPS:
        observed = n > 0
        if observed:
            lo, hi, w = ci(adv, n, 2.20)
            sup = support("lane", n, w)
        else:
            lo, hi = round(adv - 0.62, 3), round(adv + 0.62, 3)
            sup = "insufficient"
        rows.append([aid, akey, bid, bkey, role, f3(adv), f3(lo), f3(hi), n, sup,
                     str(observed).lower(), PATCH_WINDOW])
    return header, rows


# (a_id, a_key, b_id, b_key, ctx, synergy, syn_n, lane, lane_n)
DUOS = [
    (9, "Jhin", 30, "Karma", "bot", 0.240, 11, -0.350, 6),
    (9, "Jhin", 48, "Nami", "bot", 0.680, 9, 0.210, 5),
    (30, "Karma", 41, "Lucian", "bot", 0.870, 13, 0.540, 8),
    (41, "Lucian", 48, "Nami", "bot", 1.120, 22, 0.860, 14),
    (12, "Alistar", 41, "Lucian", "bot", 0.930, 16, 0.720, 11),
    (9, "Jhin", 12, "Alistar", "bot", -0.180, 7, -0.240, 4),
    (12, "Alistar", 9, "Jhin", "bot", None, 0, None, 0),
    (18, "Darius", 88, "Sejuani", "top_jungle", 0.610, 8, None, 0),
    (25, "Garen", 88, "Sejuani", "top_jungle", 0.340, 5, None, 0),
    (61, "Syndra", 88, "Sejuani", "mid_jungle", 0.480, 6, None, 0),
    (72, "Zed", 88, "Sejuani", "mid_jungle", -0.220, 0, None, 0),
]


def build_duos():
    header = ["champion_a_id", "champion_a_key", "champion_b_id", "champion_b_key",
              "duo_context",
              "synergy", "synergy_ci_low", "synergy_ci_high", "synergy_n",
              "synergy_support", "synergy_is_observed",
              "lane_strength", "lane_strength_ci_low", "lane_strength_ci_high",
              "lane_strength_n", "lane_strength_support", "lane_strength_is_observed",
              "patch_window"]
    assert len(header) == 18, len(header)
    rows = []
    for aid, akey, bid, bkey, ctx, syn, sn, lane, ln in DUOS:
        if aid == 12 and bid == 9:
            continue
        row = [aid, akey, bid, bkey, ctx]
        if syn is None:
            row += ["", "", "", 0, "insufficient", "false"]
        elif sn == 0:
            row += [f3(syn), f3(syn - 0.79), f3(syn + 0.79), 0, "insufficient", "false"]
        else:
            lo, hi, w = ci(syn, sn, 4.20)
            row += [f3(syn), f3(lo), f3(hi), sn, support("synergy", sn, w), "true"]
        if lane is None or ln == 0:
            row += ["", "", "", 0, "insufficient", "false"]
        else:
            lo, hi, w = ci(lane, ln, 4.20)
            row += [f3(lane), f3(lo), f3(hi), ln, support("synergy", ln, w), "true"]
        row.append(PATCH_WINDOW)
        assert len(row) == 18, len(row)
        rows.append(row)
    return header, rows


def write(name, header, rows):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    print("%-38s %3d filas x %3d columnas" % (name, len(rows), len(header)))


if __name__ == "__main__":
    import sys
    OUT = sys.argv[1]
    write("champion_features_v16.20.csv", *build_champion_features())
    write("matchup_matrix_v16.20.csv", *build_matchups())
    write("duo_features_v16.20.csv", *build_duos())

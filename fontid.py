#!/usr/bin/env python3
"""
Spike Fase A.0 — Aproximación de fuentes tipográficas (Google Fonts).

NO identifica fuentes: aproxima. Encuentra la alternativa más cercana
dentro de Google Fonts. Ver docs/superpowers/specs/2026-06-05-font-identification-design.md

Uso:
    python fontid.py logo.png --region x0,y0,x1,y1 --text "mente"
"""

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vectorize import load_image_bgr

# ═══════════════════════════════════════════════════════════════════
# 1. SEGMENTACIÓN (sin fusión vertical — límite declarado del spike:
#    parte minúsculas con punto i/j y acentos; las palabras del caso
#    motivador no los tienen. La fusión es requisito de Fase A.)
# ═══════════════════════════════════════════════════════════════════

def _tight(mask):
    """Recorta una máscara booleana a su contenido."""
    ys, xs = np.where(mask)
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def segment_glyphs(crop_bgr, min_area=4):
    """Binariza (Otsu directo — SIN clean_binary_mask, que destruye
    serifas/puntos por diseño) y devuelve las máscaras de los glifos
    como componentes conexos ordenados por x."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    flag = cv2.THRESH_BINARY_INV if np.mean(gray) > 127 else cv2.THRESH_BINARY
    _, binary = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        comps.append((x, labels[y:y + h, x:x + w] == i))
    comps.sort(key=lambda t: t[0])
    return [m for _, m in comps]


def _x_overlap(a, b):
    """Fracción de solape horizontal entre dos intervalos (x0, x1)."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if hi <= lo:
        return 0.0
    return (hi - lo) / min(a[1] - a[0], b[1] - b[0])


def segment_glyphs_with_boxes(crop_bgr, min_area=4, overlap_frac=0.5):
    """Segmentación Fase A: componentes conexos + fusión vertical.

    Como segment_glyphs_fused pero devuelve (masks, boxes) donde
    boxes = [(x0, y0, x1, y1)] ABSOLUTAS dentro del crop — la posición
    vertical real que la clasificación necesita (las máscaras tight no
    conservan dónde estaba el glifo).

    Componentes cuyo rango x se solapa ≥ overlap_frac con otro (punto de
    la i/j, acentos) se fusionan en un solo glifo (spec, hecho runtime 5:
    sin esto 'integrative' da 13 componentes para 11 letras).
    """
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    flag = cv2.THRESH_BINARY_INV if np.mean(gray) > 127 else cv2.THRESH_BINARY
    _, binary = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    boxes = []  # (x0, x1, y0, y1, comp_ids)  — orden interno del algoritmo
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        boxes.append([x, x + w, y, y + h, [i]])
    boxes.sort(key=lambda b: b[0])

    fused = []
    for b in boxes:
        if fused and _x_overlap((fused[-1][0], fused[-1][1]), (b[0], b[1])) >= overlap_frac:
            prev = fused[-1]
            prev[0] = min(prev[0], b[0]); prev[1] = max(prev[1], b[1])
            prev[2] = min(prev[2], b[2]); prev[3] = max(prev[3], b[3])
            prev[4].extend(b[4])
        else:
            fused.append(b)

    masks, out_boxes = [], []
    for x0, x1, y0, y1, ids in fused:
        masks.append(np.isin(labels[y0:y1, x0:x1], ids))
        out_boxes.append((x0, y0, x1, y1))   # reordenado a orden estándar (x0,y0,x1,y1)
    return masks, out_boxes


def segment_glyphs_fused(crop_bgr, min_area=4, overlap_frac=0.5):
    """Wrapper de compatibilidad: solo las máscaras."""
    return segment_glyphs_with_boxes(crop_bgr, min_area, overlap_frac)[0]


# ═══════════════════════════════════════════════════════════════════
# 2. RENDER + MATCHING (métrica del spec: factor de escala COMÚN —
#    las proporciones relativas entre glifos sobreviven y los
#    desajustes de tamaño penalizan el IoU. Solo la posición se
#    normaliza (centroide): el tracking es decisión del logo, no
#    de la fuente.)
# ═══════════════════════════════════════════════════════════════════

def render_glyph(ch, font):
    """Renderiza un carácter como máscara booleana recortada, o None."""
    bbox = font.getbbox(ch)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if w <= 0 or h <= 0:
        return None
    img = Image.new("L", (w + 8, h + 8), 0)
    ImageDraw.Draw(img).text((4 - bbox[0], 4 - bbox[1]), ch, fill=255, font=font)
    arr = np.array(img) > 127
    if not arr.any():
        return None
    return _tight(arr)


def _iou_centroid(a, b):
    """IoU de dos máscaras alineadas por centroide en un canvas común
    (tamaño 2*max para que el pegado nunca recorte)."""
    H = 2 * max(a.shape[0], b.shape[0]) + 4
    W = 2 * max(a.shape[1], b.shape[1]) + 4

    def centered(m):
        c = np.zeros((H, W), dtype=bool)
        ys, xs = np.where(m)
        oy = int(round(H / 2 - ys.mean()))
        ox = int(round(W / 2 - xs.mean()))
        c[oy:oy + m.shape[0], ox:ox + m.shape[1]] = m
        return c

    A, B = centered(a), centered(b)
    union = np.logical_or(A, B).sum()
    if union == 0:
        return 0.0
    return float(np.logical_and(A, B).sum() / union)


def match_candidate_detail(crop_glyphs, chars, ttf_path, base_size=96):
    """Score + factor de escala común de una candidata.

    Devuelve (overlap, s) o None si la región es insuficiente (<2 glifos),
    los conteos no cuadran, o el render falla.
    - ≥4 glifos → se descarta el peor IoU (robustez);
    - 2-3 glifos → media simple;
    - <2 glifos → None ("insuficiente para matching").
    El factor s (mediana crop / mediana render) lo necesita el JSON de
    Fase A — requisito de información de Fase B registrado en el spec.
    """
    if len(crop_glyphs) < 2 or len(crop_glyphs) != len(chars):
        return None
    font = ImageFont.truetype(str(ttf_path), base_size)
    rendered = [render_glyph(c, font) for c in chars]
    if any(r is None for r in rendered):
        return None
    crop_med = float(np.median([g.shape[0] for g in crop_glyphs]))
    rend_med = float(np.median([r.shape[0] for r in rendered]))
    if rend_med <= 0 or crop_med <= 0:
        return None
    s = crop_med / rend_med
    ious = []
    for g, r in zip(crop_glyphs, rendered):
        rs = cv2.resize(
            r.astype(np.uint8),
            (max(1, int(round(r.shape[1] * s))), max(1, int(round(r.shape[0] * s)))),
            interpolation=cv2.INTER_AREA) > 0
        if not rs.any():
            return None
        ious.append(_iou_centroid(g, rs))
    ious.sort()
    if len(ious) >= 4:
        ious = ious[1:]
    return float(np.mean(ious)), s


def match_candidate(crop_glyphs, chars, ttf_path, base_size=96):
    """Wrapper de compatibilidad del spike: solo el score."""
    r = match_candidate_detail(crop_glyphs, chars, ttf_path, base_size)
    return None if r is None else r[0]


# ═══════════════════════════════════════════════════════════════════
# 3. DESCARGA DE TTF (hecho runtime 3 del spec: el UA por defecto de
#    urllib entrega TTF directo — el "truco UA legacy" del v1 estaba
#    invertido y NO se usa. Validación antes de cachear + escritura
#    atómica: nunca queda un TTF a medias o corrupto en caché.)
# ═══════════════════════════════════════════════════════════════════

GF_CSS2 = "https://fonts.googleapis.com/css2?family={}"
TTF_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true")


def validate_ttf(path):
    """Magic bytes + apertura efectiva con Pillow. True si es usable."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    if not any(data.startswith(m) for m in TTF_MAGICS):
        return False
    try:
        ImageFont.truetype(str(path), 24)
    except Exception:
        return False
    return True


def download_ttf(family, cache_dir):
    """Descarga el TTF regular de una familia GF a la caché.

    Devuelve la ruta cacheada, o None si la red/validación falla
    (el caller cuenta las omitidas y sigue — spec, tabla de errores).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / (family.replace(" ", "_") + ".ttf")
    if dest.exists():
        return dest
    try:
        url = GF_CSS2.format(urllib.parse.quote_plus(family))
        css = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
        m = re.search(r"url\((https://[^)]+\.ttf)\)", css)
        if not m:
            return None
        data = urllib.request.urlopen(m.group(1), timeout=30).read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    # .tmp por familia: seguro solo en single-process (hecho runtime 7 del
    # spec: OCR/spike secuencial). Si Fase A paraleliza, usar tempfile único.
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(data)
    if not validate_ttf(tmp):
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, dest)  # escritura atómica (spec)
    return dest


# ═══════════════════════════════════════════════════════════════════
# 3b. METADATA DE GOOGLE FONTS Y POOL (Fase A)
# ═══════════════════════════════════════════════════════════════════

CACHE_DIR_DEFAULT = str(Path.home() / ".cache" / "vectorizer-fonts")
GF_METADATA_URL = "https://fonts.google.com/metadata/fonts"
METADATA_TTL_S = 7 * 24 * 3600          # TTL semanal (spec, Caché)
# Categorías Title Case REALES del metadata (hecho runtime 4). El input
# del usuario se normaliza antes de comparar.
POOL_CATEGORIES = ("Serif", "Sans Serif", "Display")


def _normalize_category(cat):
    """'sans-serif' / 'SERIF' / 'sans serif' → forma Title Case real."""
    return cat.replace("-", " ").strip().title()


def fetch_metadata(cache_dir):
    """Metadata de GF con caché TTL semanal. Devuelve familyMetadataList.

    Sin red y sin caché → RuntimeError con mensaje claro. Sin red CON
    caché vencida → usa la caché vencida con warning (mejor que nada).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / "metadata.json"
    tmp = dest.parent / (dest.name + ".tmp")
    fresh = dest.exists() and (time.time() - dest.stat().st_mtime) < METADATA_TTL_S
    if not fresh:
        try:
            raw = urllib.request.urlopen(GF_METADATA_URL, timeout=30).read()
            tmp.write_bytes(raw)
            json.loads(raw.decode("utf-8"))     # valida antes de promover
            os.replace(tmp, dest)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            tmp.unlink(missing_ok=True)
            if not dest.exists():
                raise RuntimeError(
                    "No se pudo descargar la metadata de Google Fonts y no hay "
                    "caché previa. Revisa la red o usa --region/--text con "
                    "--pool-file manual.") from None
            print("  [WARN] metadata GF: sin red; usando caché vencida.",
                  file=sys.stderr)  # stderr: no contaminar --json
    return json.loads(dest.read_text(encoding="utf-8"))["familyMetadataList"]


def build_pool(metadata, pool_size=60, category=None):
    """Pool por popularidad. Default: Serif + Sans Serif + Display.

    `category` (input de usuario, cualquier casing) se normaliza a la
    forma Title Case real del metadata.
    """
    cats = (POOL_CATEGORIES if category is None
            else (_normalize_category(category),))
    fams = [m for m in metadata if m.get("category") in cats]
    fams.sort(key=lambda m: m.get("popularity", 10 ** 9))
    return [m["family"] for m in fams[:pool_size]]


# ═══════════════════════════════════════════════════════════════════
# 3c. PROBING DE PESOS (Fase A — prioridad #1 del gate A.0)
# ═══════════════════════════════════════════════════════════════════

# Sintaxis DISCRETA: GF silencia pesos no disponibles en vez de devolver HTTP 400.
# La sintaxis de rango "300..700" falla con 400 en familias de eje estrecho
# (Lora, EB Garamond solo tienen peso 400) — hallazgo del review 2026-06-05,
# verificado en vivo. Con la lista discreta GF omite lo que no tiene, sin error.
WGHT_RANGE = "300;400;500;600;700"


def parse_weight_css(css):
    """CSS2 → [(wght, url_ttf)] por bloque @font-face (hecho runtime nuevo:
    GF entrega estáticos por peso con descriptores font-weight).

    El patrón requiere el ';' al final del valor para rechazar bloques de
    fuente variable ('font-weight: 300 700;') que de otro modo capturarían
    el primer número de forma incorrecta.
    """
    pairs = []
    for block in css.split("@font-face")[1:]:
        mw = re.search(r"font-weight:\s*(\d+)\s*;", block)
        mu = re.search(r"url\((https://[^)]+\.ttf)\)", block)
        if mw and mu:
            pairs.append((int(mw.group(1)), mu.group(1)))
    return pairs


def download_family_weights(family, cache_dir):
    """Descarga los pesos estáticos 300..700 de una familia (atómico+validado).

    Devuelve [(wght, Path)] de los que existen/validaron. Lista vacía si la
    red falla por completo (el caller cuenta la familia como omitida).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    base = family.replace(" ", "_")
    try:
        url = GF_CSS2.format(urllib.parse.quote_plus(family)) + ":wght@" + WGHT_RANGE
        css = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    out = []
    for wght, ttf_url in parse_weight_css(css):
        dest = cache_dir / f"{base}_{wght}.ttf"
        if not dest.exists():
            try:
                data = urllib.request.urlopen(ttf_url, timeout=30).read()
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            tmp = dest.parent / (dest.name + ".tmp")
            tmp.write_bytes(data)
            if not validate_ttf(tmp):
                tmp.unlink(missing_ok=True)
                continue
            os.replace(tmp, dest)
        out.append((wght, dest))
    return out


def match_family_local(crop_glyphs, chars, weight_paths):
    """Prueba cada (wght, ttf) y conserva el mejor. → (score, wght, s) | None."""
    best = None
    for wght, path in weight_paths:
        r = match_candidate_detail(crop_glyphs, chars, path)
        if r is None:
            continue
        score, s = r
        if best is None or score > best[0]:
            best = (score, wght, s)
    return best


# ═══════════════════════════════════════════════════════════════════
# 4. POOLS, RANKING Y REPORTE
# ═══════════════════════════════════════════════════════════════════

SPIKE_POOL = [
    "Cormorant Garamond", "EB Garamond", "Cormorant SC", "Crimson Pro",
    "Crimson Text", "Sorts Mill Goudy", "Gilda Display", "Playfair Display",
    "Lora", "PT Serif", "Libre Baskerville", "Source Serif 4",
    "Noto Serif Display", "Cardo", "Spectral", "Domine",
    "Frank Ruhl Libre", "Marcellus", "Cinzel", "Old Standard TT",
]
# Controles negativos (sans/display/script): sin ellos la separación del
# cluster serif sería inmedible — son la línea base del gate (spec A.0).
CONTROLES = ["Roboto", "Montserrat", "Oswald", "Pacifico"]

TIE_DELTA = 0.03  # hecho runtime 6 del spec: margen serif-vs-serif real 0.027

CORPUS_NOTE = (
    "Corpus: Google Fonts. Si la fuente original es comercial, esto es la\n"
    "alternativa libre más cercana — no una identificación."
)


def tie_flags(ranked):
    """[(familia, overlap)] ordenado desc → [bool] EMPATE-con-el-líder."""
    if not ranked:
        return []
    leader = ranked[0][1]
    return [i > 0 and (leader - s) < TIE_DELTA for i, (_, s) in enumerate(ranked)]


def rank_region(crop_bgr, text, cache_dir):
    """Devuelve (ranked, controls, skipped, mismatch) para una región.

    mismatch: None, o (n_glifos, n_chars) si la segmentación no cuadra
    con el texto — la región se reporta y no se rankea.
    """
    glyphs = segment_glyphs(crop_bgr)
    chars = [c for c in text if not c.isspace()]
    if len(glyphs) != len(chars):
        return None, None, 0, (len(glyphs), len(chars))
    ranked, controls, skipped = [], [], 0
    for fam in SPIKE_POOL + CONTROLES:
        ttf = download_ttf(fam, cache_dir)
        if ttf is None:
            skipped += 1
            continue
        score = match_candidate(glyphs, chars, ttf)
        if score is None:
            continue
        (controls if fam in CONTROLES else ranked).append((fam, score))
    ranked.sort(key=lambda t: -t[1])
    controls.sort(key=lambda t: -t[1])
    return ranked, controls, skipped, None


def print_region_report(idx, reg):
    cls = reg["classification"]
    print(f"\n[REGIÓN {idx}] \"{reg['text']}\" — {cls['label']} "
          f"(score {cls['score']}, baseline res={cls['baseline_residual']}px, "
          f"var. altura={cls['height_var']}"
          f"{', repetición usada' if cls.get('repeats_used') else ''})")
    if cls["label"] == "handwriting":
        print("  → se vectoriza, no se aproxima (territorio de vectorize.py)")
        return
    if cls["label"] == "uncertain":
        print("  banda incierta — revisa el crop o fuerza con --region/--text")
    rows = reg["rows"]
    if not rows:
        print("  sin candidatas rankeables")
        return
    # Separación por cluster (spec, reporte de dos niveles): el pool mezcla
    # categorías GF, así que el mejor de OTRA categoría es la línea base —
    # no hacen falta controles artificiales como en el spike.
    leader_cat = rows[0].get("category")
    others = [r["overlap"] for r in rows if r.get("category") not in (leader_cat, None)]
    if leader_cat and others:
        sep = rows[0]["overlap"] - max(others)
        band = "OK" if sep > 0.2 else ("MARGINAL" if sep > 0.1 else "DÉBIL")
        print(f"  cluster: {leader_cat} — separación vs mejor de otra "
              f"categoría: {sep:.3f} ({band})")
    ties = tie_flags([(r["family"], r["overlap"]) for r in rows])
    prev = None
    for i, (r, tie) in enumerate(zip(rows[:5], ties[:5]), 1):
        delta = f"   Δ {prev - r['overlap']:.3f}" if prev is not None else ""
        mark = "  → EMPATE con el líder" if tie else ""
        api = "  [API]" if r["api"] else ""
        print(f"  {i}. {r['family']:<24s} overlap {r['overlap']:.3f} "
              f"(wght {r['wght']}){delta}{mark}{api}")
        prev = r["overlap"]
    if reg.get("skipped"):
        print(f"  ({reg['skipped']} candidatas omitidas por red/validación)")


# ═══════════════════════════════════════════════════════════════════
# 4b. RANKING V2, JSON DRAFT Y PREVIEW (Fase A)
# ═══════════════════════════════════════════════════════════════════

DOWNLOAD_WORKERS = 8     # presupuesto del spec: descarga paralela; el OCR
                         # NUNCA se paraleliza (asyncio.run, hecho runtime 5)


def prepare_pool_weights(families, cache_dir):
    """Descarga (paralela, atómica) los pesos de cada familia.
    → dict familia → [(wght, Path)] (vacío = omitida por red)."""
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as ex:
        results = ex.map(lambda f: (f, download_family_weights(f, cache_dir)),
                         families)
    return dict(results)


def rank_families(crop_glyphs, chars, family_weights, api_set):
    """→ filas ordenadas desc: {family, overlap, wght, scale, api}."""
    rows = []
    for fam, weights in family_weights.items():
        if not weights:
            continue
        best = match_family_local(crop_glyphs, chars, weights)
        if best is None:
            continue
        score, wght, s = best
        rows.append({"family": fam, "overlap": round(score, 3), "wght": wght,
                     "scale": round(s, 4), "api": fam in api_set})
    rows.sort(key=lambda r: -r["overlap"])
    return rows


def build_json_draft(regions):
    """Emisión draft (spec Fase B condición 3: NO es contrato hasta que
    Fase B firme sus requisitos). Sin '%', bboxes absolutas, wght y scale
    registrados por candidata."""
    out_regions = []
    for reg in regions:
        rows = reg["rows"]
        ties = tie_flags([(r["family"], r["overlap"]) for r in rows])
        cands = []
        for i, (r, tie) in enumerate(zip(rows, ties)):
            delta = (round(rows[i - 1]["overlap"] - r["overlap"], 3)
                     if i > 0 else None)
            cands.append({**r, "delta_to_next": delta, "tie_with_leader": tie})
        out_regions.append({
            "bbox": list(reg["bbox"]), "text": reg["text"],
            "classification": reg["classification"],
            "candidates": cands, "skipped": reg.get("skipped", 0),
        })
    return {"draft": True,
            "note": ("Emisión draft — el esquema puede cambiar cuando Fase B "
                     "firme sus requisitos de información (ver spec)."),
            "corpus": "Google Fonts",
            "regions": out_regions}


def write_preview(crop_bgr, text, top_rows, out_path, cache_dir, ink=(135, 177, 164)):
    """Tira comparativa: crop original | top-N renders al peso elegido.

    Busca cada TTF como {cache_dir}/{Familia_con_guiones}_{wght}.ttf —
    el nombre exacto que escribe download_family_weights.
    """
    h = crop_bgr.shape[0]
    panels = [crop_bgr]
    for r in top_rows:
        ttf = Path(cache_dir) / f"{r['family'].replace(' ', '_')}_{r['wght']}.ttf"
        if not ttf.exists():
            continue
        font = ImageFont.truetype(str(ttf), max(24, int(h * 0.7)))
        bbox = font.getbbox(text)
        img = Image.new("RGB", (bbox[2] - bbox[0] + 24, bbox[3] - bbox[1] + 24),
                        (255, 255, 255))
        ImageDraw.Draw(img).text((12 - bbox[0], 12 - bbox[1]), text,
                                 fill=ink[::-1], font=font)
        panel = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        panel = cv2.resize(panel, (max(1, int(panel.shape[1] * h / panel.shape[0])), h))
        panels.append(np.full((h, 16, 3), 255, np.uint8))
        panels.append(panel)
    cv2.imwrite(str(out_path), cv2.hconcat(panels))
    return out_path


# ═══════════════════════════════════════════════════════════════════
# 5. CLI
# ═══════════════════════════════════════════════════════════════════

def build_parser():
    p = argparse.ArgumentParser(
        description="Fase A — aproximación de fuentes (Google Fonts). "
                    "NO identifica: aproxima.")
    p.add_argument("input", help="Imagen del logo")
    p.add_argument("--region", action="append",
                   help="x0,y0,x1,y1 (repetible, pareado con --text; "
                        "sin esto, OCR automático — Windows-only)")
    p.add_argument("--text", action="append",
                   help="Texto de la región (repetible, pareado con --region)")
    p.add_argument("--pool", type=int, default=60,
                   help="Tamaño del pool de candidatas (default 60)")
    p.add_argument("--category", default=None,
                   help="Limita el pool a una categoría GF (serif, sans-serif, display)")
    p.add_argument("--api", action="store_true",
                   help="Nominación vía API de Claude (OPT-IN: envía los crops "
                        "a Anthropic; la sola presencia de la key no activa nada)")
    p.add_argument("--json", action="store_true", help="Salida JSON (emisión draft)")
    p.add_argument("--preview", action="store_true",
                   help="Tira PNG comparativa por región (junto al input)")
    p.add_argument("--cache-dir", default=CACHE_DIR_DEFAULT,
                   help="Caché de TTFs y metadata")
    return p


def validate_args(args):
    if (args.region is None) != (args.text is None):
        sys.exit("error: --region y --text van juntos")
    if args.region and len(args.region) != len(args.text):
        sys.exit(f"error: --region ({len(args.region)}) y --text "
                 f"({len(args.text)}) deben ir pareados posicionalmente")


def _manual_regions(img, args):
    regions = []
    for reg, text in zip(args.region, args.text):
        try:
            x0, y0, x1, y1 = (int(v) for v in reg.split(","))
        except ValueError:
            sys.exit(f"error: región inválida {reg!r} (formato x0,y0,x1,y1)")
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            sys.exit(f"error: región {reg!r} fuera de los límites de la imagen "
                     f"{img.shape[1]}x{img.shape[0]}")
        regions.append({"bbox": (x0, y0, x1, y1), "text": text})
    return regions


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # el reporte usa Δ/→/≠; cp1252 crashea
    args = build_parser().parse_args()
    validate_args(args)
    img = load_image_bgr(args.input)
    if img is None:
        raise ValueError(f"No se pudo cargar: {args.input}")

    if args.region:
        raw_regions = _manual_regions(img, args)
        forced = True
    else:
        try:
            raw_regions = detect_regions(img)
        except RuntimeError as e:
            sys.exit(f"error: {e}")
        forced = False
        if not raw_regions:
            sys.exit("sin regiones de texto detectadas — usa --region/--text")

    metadata = fetch_metadata(args.cache_dir)
    pool = build_pool(metadata, pool_size=args.pool, category=args.category)

    api_set = set()
    if args.api:
        crops_png = []
        for reg in raw_regions:
            x0, y0, x1, y1 = reg["bbox"]
            ok, buf = cv2.imencode(".png", img[y0:y1, x0:x1])
            if ok:
                crops_png.append(buf.tobytes())
        nominated = nominate_via_api(crops_png, [r["text"] for r in raw_regions])
        pool, api_set = merge_nominations(pool, nominated)

    family_weights = prepare_pool_weights(pool, args.cache_dir)
    skipped_total = sum(1 for w in family_weights.values() if not w)

    if not args.json:
        print(CORPUS_NOTE)
    results = []
    for i, reg in enumerate(raw_regions, 1):
        x0, y0, x1, y1 = reg["bbox"]
        glyphs, gboxes = segment_glyphs_with_boxes(img[y0:y1, x0:x1])
        chars = [c for c in reg["text"] if not c.isspace()]
        cls = (classify_region(glyphs, reg["text"], boxes=gboxes) if not forced
               else {"label": "type", "score": 1.0, "baseline_residual": 0.0,
                     "height_var": 0.0, "repeats_used": False,
                     "note": "región forzada por el usuario"})
        entry = {"bbox": reg["bbox"], "text": reg["text"],
                 "classification": cls, "rows": [], "skipped": skipped_total}
        if cls["label"] != "handwriting":
            if len(glyphs) != len(chars):
                if not args.json:
                    print(f"\n[REGIÓN {i}] \"{reg['text']}\" — segmentación≠texto "
                          f"({len(glyphs)} glifos vs {len(chars)} chars) — no se rankea.")
                results.append(entry)
                continue
            entry["rows"] = rank_families(glyphs, chars, family_weights, api_set)
            cat_by_family = {m["family"]: m.get("category") for m in metadata}
            for r in entry["rows"]:
                r["category"] = cat_by_family.get(r["family"])
        if not args.json:
            print_region_report(i, entry)
        if args.preview and entry["rows"]:
            out = Path(args.input).with_name(
                Path(args.input).stem + f"_fontid_r{i}.png")
            write_preview(img[y0:y1, x0:x1], reg["text"], entry["rows"][:3],
                          out, args.cache_dir)
            if not args.json:
                print(f"  preview: {out}")
        results.append(entry)

    if not forced and not args.json:
        print("\nAviso: zonas con texto caligráfico pueden no listarse arriba "
              "(el OCR no siempre emite región para handwriting). Usa "
              "--region/--text para forzarlas.")
    if args.json:
        print(json.dumps(build_json_draft(results), ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════
# 3f. NOMINACIÓN API (Fase A — opt-in explícito con --api; la sola
#     presencia de ANTHROPIC_API_KEY no activa nada. La API solo NOMINA:
#     toda verificación es local. Hallazgo Null Vale reconocido: nominar
#     dentro de un pool acotado ES decidir el espacio de búsqueda — por
#     eso el default es sin API y lo nominado se marca [API].)
# ═══════════════════════════════════════════════════════════════════

NOMINATION_MODEL = "claude-haiku-4-5"   # decisión del spec (costo céntimos)
NOMINATION_SCHEMA = {
    "type": "object",
    "properties": {
        "families": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["families"],
    "additionalProperties": False,
}


def nominate_via_api(crop_pngs, texts, max_families=10):
    """UN solo call de visión → hasta 10 nombres de familias GF plausibles.

    Cualquier fallo (SDK ausente, key ausente, error de API) → lista
    vacía con warning. El pipeline local sigue idéntico.
    """
    try:
        import anthropic
    except ImportError:
        print("  [WARN] --api: el paquete 'anthropic' no está instalado "
              "(pip install anthropic). Sigo sin nominación.", file=sys.stderr)
        return []
    content = []
    for png in crop_pngs:
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png",
                                   "data": base64.standard_b64encode(png).decode()}})
    content.append({"type": "text", "text": (
        "Cada imagen es un recorte de texto tipográfico de un logo. Los "
        f"textos son: {texts}. Nombra hasta {max_families} familias de "
        "GOOGLE FONTS (nombres exactos del catálogo) visualmente más "
        "parecidas a la tipografía de los recortes, ordenadas de más a "
        "menos plausible.")})
    try:
        client = anthropic.Anthropic()   # resuelve ANTHROPIC_API_KEY del entorno
        resp = client.messages.create(
            model=NOMINATION_MODEL,
            max_tokens=1024,
            output_config={"format": {"type": "json_schema",
                                      "schema": NOMINATION_SCHEMA}},
            messages=[{"role": "user", "content": content}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        fams = json.loads(text)["families"][:max_families]
        return [f.strip() for f in fams if isinstance(f, str) and f.strip()]
    except Exception as e:
        print(f"  [WARN] --api falló ({type(e).__name__}); sigo sin nominación.",
              file=sys.stderr)
        return []


def merge_nominations(pool, nominated):
    """Nominadas primero (prioridad), sin duplicados. Devuelve además el
    set de familias que entraron SOLO por la API (para marcar [API])."""
    api_only = {f for f in nominated if f not in pool}
    merged = list(dict.fromkeys(list(nominated) + list(pool)))
    return merged, api_only


# ═══════════════════════════════════════════════════════════════════
# 3d. OCR Y REGIONES (Fase A — Windows-only; el flujo manual
#     --region/--text funciona en cualquier SO)
# ═══════════════════════════════════════════════════════════════════

LATIN_PREFIXES = ("en", "es", "fr", "de", "it", "pt", "nl", "ca")
OCR_INSTALL_HINT = (
    "No hay ningún language pack OCR de script latino instalado.\n"
    "Instala uno (PowerShell como admin):\n"
    '  Add-WindowsCapability -Online -Name "Language.OCR~~~es-ES~0.0.1.0"')


def negotiate_ocr_language():
    """Primer recognizer de script latino DISPONIBLE — jamás hardcodear
    'en' (hecho runtime 1: esta máquina solo tiene es-ES/es-MX y lang='en'
    lanza AssertionError).

    Usa winrt (no winsdk) — forma verificada en esta máquina.
    available_recognizer_languages es property, no callable getter.
    """
    from winrt.windows.media.ocr import OcrEngine  # import lazy
    langs = OcrEngine.available_recognizer_languages
    tags = [l.language_tag for l in langs]
    for tag in tags:
        if tag.split("-")[0].lower() in LATIN_PREFIXES:
            return tag
    raise RuntimeError(OCR_INSTALL_HINT + f"\nDisponibles: {tags or 'ninguno'}")


def detect_regions(img_bgr):
    """OCR → una región por LÍNEA detectada (criterio de agrupación
    declarado: líneas distintas suelen ser fuentes distintas en un logo).

    Devuelve [{'bbox': (x0,y0,x1,y1) ABSOLUTAS, 'text': str,
               'word_boxes': [(x0,y0,x1,y1), ...]}].

    API winocr verificada en runtime: recognize_cv2_sync devuelve siempre
    dicts (picklify convierte los objetos winrt). bounding_rect es un dict
    con claves 'x', 'y', 'width', 'height' como floats.

    Limitación documentada (hecho runtime 2): el OCR puede NO emitir
    región para texto caligráfico — el caller imprime el aviso fijo.
    """
    if sys.platform != "win32":
        raise RuntimeError(
            "La detección automática usa el OCR nativo de Windows (winocr) "
            "y es Windows-only. Usa --region/--text en este SO.")
    try:
        import winocr
    except ImportError:
        raise RuntimeError(
            "El flujo automático requiere winocr. Instala con: "
            "pip install winocr  (o usa --region/--text)") from None
    lang = negotiate_ocr_language()
    try:
        result = winocr.recognize_cv2_sync(img_bgr, lang)
    except Exception as e:
        raise RuntimeError(
            f"El OCR falló en runtime ({e}). Fallback: pasa las regiones a "
            "mano con --region/--text.") from None

    regions = []
    # winocr.picklify siempre produce dicts — no hay objetos winrt aquí
    lines = result["lines"] if isinstance(result, dict) else result.lines
    for line in lines:
        words = line["words"] if isinstance(line, dict) else line.words
        boxes = []
        for w in words:
            r = w["bounding_rect"] if isinstance(w, dict) else w.bounding_rect
            x = int(r["x"] if isinstance(r, dict) else r.x)
            y = int(r["y"] if isinstance(r, dict) else r.y)
            ww = int(r["width"] if isinstance(r, dict) else r.width)
            hh = int(r["height"] if isinstance(r, dict) else r.height)
            boxes.append((x, y, x + ww, y + hh))
        if not boxes:
            continue
        text = line["text"] if isinstance(line, dict) else line.text
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        regions.append({"bbox": (x0, y0, x1, y1), "text": text,
                        "word_boxes": boxes})
    return regions


# ═══════════════════════════════════════════════════════════════════
# 3e. CLASIFICACIÓN ESCALAR (Fase A — reframe del spec: un score con
#     dos cortes; 'uncertain' es estado del clasificador, no del mundo)
# ═══════════════════════════════════════════════════════════════════

# Constantes PROVISIONALES (sin corpus de calibración aún — el spec lo
# declara). Las stats crudas se reportan siempre; los cortes solo etiquetan.
CLASSIFY_TYPE_CUT = 0.65        # score ≥ → "type"
CLASSIFY_HAND_CUT = 0.45        # score ≤ → "handwriting"; entre ambos → "uncertain"
_RESIDUAL_NORM_PX = 4.0         # residuo de baseline que ya cuenta como irregular
_HEIGHT_VAR_NORM = 0.35         # variación relativa de altura idem


DESCENDERS = set("gjpqy")
_XHEIGHT_CHARS = set("aceimnorsuvwxz")


def classify_region(glyph_masks, text, boxes=None):
    """Score escalar tipografía↔handwriting con estadísticas crudas.

    Señales (todas crudas en el dict, sin calibración — el spec lo declara):
    1. Residuo de baseline sobre bottoms ABSOLUTOS (requiere boxes),
       excluyendo descendentes (g/j/p/q/y) cuando el texto alinea con los
       glifos — un descendente legítimo no es irregularidad.
    2. Variación relativa de altura sobre chars de x-height cuando el texto
       alinea (mezclar ascendentes con x-height no es irregularidad).
    3. Repetición de formas SOLO si hay letras repetidas.
    Sin boxes (modo degradado, p.ej. tests sintéticos), 1 usa los bottoms
    locales (altura) — declarado en el dict como baseline_mode='local'.
    """
    base = {"label": "uncertain", "score": 0.5, "baseline_residual": 0.0,
            "height_var": 0.0, "repeats_used": False,
            "baseline_mode": "absolute" if boxes else "local"}
    if len(glyph_masks) < 2:
        base["note"] = "región con <2 glifos — señales insuficientes"
        return base

    chars = [c for c in text.lower() if not c.isspace()]
    aligned = len(chars) == len(glyph_masks)

    # --- bottoms y alturas
    if boxes:
        bottoms = np.array([float(b[3]) for b in boxes])
        heights = np.array([float(b[3] - b[1]) for b in boxes])
        xs = np.array([float(b[0]) for b in boxes])
    else:
        bottoms, heights, xs = [], [], []
        x_cursor = 0
        for m in glyph_masks:
            ys, _ = np.where(m)
            bottoms.append(float(np.percentile(ys, 90)))
            heights.append(float(m.shape[0]))
            xs.append(float(x_cursor)); x_cursor += m.shape[1]
        bottoms, heights, xs = map(np.array, (bottoms, heights, xs))

    # --- señal 1: baseline (excluye descendentes si el texto alinea)
    keep = np.ones(len(bottoms), dtype=bool)
    if aligned:
        keep = np.array([c not in DESCENDERS for c in chars])
        if keep.sum() < 2:
            keep = np.ones(len(bottoms), dtype=bool)
    coef = np.polyfit(xs[keep], bottoms[keep], 1)
    dev = bottoms[keep] - np.polyval(coef, xs[keep])
    residual = float(1.4826 * np.median(np.abs(dev - np.median(dev))))

    # --- señal 2: altura (solo x-height chars si el texto alinea)
    hsel = np.ones(len(heights), dtype=bool)
    if aligned:
        hx = np.array([c in _XHEIGHT_CHARS for c in chars])
        if hx.sum() >= 2:
            hsel = hx
    height_var = float(np.std(heights[hsel]) / max(np.mean(heights[hsel]), 1e-6))

    s_base = max(0.0, 1.0 - residual / _RESIDUAL_NORM_PX)
    s_height = max(0.0, 1.0 - height_var / _HEIGHT_VAR_NORM)
    parts = [s_base, s_height]

    # --- señal 3: repetición (igual que antes)
    repeats_used = False
    if aligned:
        idx = defaultdict(list)
        for i, c in enumerate(chars):
            idx[c].append(i)
        rep_ious = []
        for positions in idx.values():
            for a, b in zip(positions, positions[1:]):
                ga, gb = glyph_masks[a], glyph_masks[b]
                gb_r = cv2.resize(gb.astype(np.uint8),
                                  (max(1, ga.shape[1]), max(1, ga.shape[0])),
                                  interpolation=cv2.INTER_AREA) > 0
                rep_ious.append(_iou_centroid(ga, gb_r))
        if rep_ious:
            repeats_used = True
            parts.append(float(np.mean(rep_ious)))

    score = float(np.mean(parts))
    base.update({
        "label": ("type" if score >= CLASSIFY_TYPE_CUT
                  else "handwriting" if score <= CLASSIFY_HAND_CUT
                  else "uncertain"),
        "score": round(score, 3),
        "baseline_residual": round(residual, 2),
        "height_var": round(height_var, 3),
        "repeats_used": repeats_used,
    })
    return base


# ═══════════════════════════════════════════════════════════════════
# 3g. FACHADA DE ANÁLISIS — contrato de Fase B (spec 2026-06-07 §4)
#     UNA sola fuente de forma (ley Halcyon). Las funciones de la
#     tubería NO cambian; esto las compone. El --json sigue siendo
#     emisión draft: el congelamiento espera al primer consumidor.
# ═══════════════════════════════════════════════════════════════════

@dataclass
class RankEntry:
    family: str
    wght: int
    score: float
    tie: bool          # empatada con el líder (Δ < TIE_DELTA)


@dataclass
class RegionAnalysis:
    bbox: tuple                # (x0,y0,x1,y1) ABSOLUTAS en la imagen
    text: str                  # texto OCR (o forzado)
    classification: str        # "type" | "handwriting" | "uncertain"
    class_score: float
    glyph_boxes: list          # [(x0,y0,x1,y1)] ABSOLUTAS (baseline real)
    ranking: list = field(default_factory=list)   # [RankEntry] desc; vacío si no rankeable
    scale_factor: float = 0.0  # scale del líder del matching (0.0 sin ranking)
    # NOTA (junta 2026-06-07, Null Vale): la semántica de scale_factor está
    # atada al pipeline de segmentación de una tinta. Si B.x lo cambia, el
    # campo NO conserva el nombre con otro referente.


def analyze_regions(img_bgr, cache_dir=CACHE_DIR_DEFAULT, pool_size=60,
                    category=None):
    """Fachada Fase B: OCR → segmentación → clasificación → ranking.

    Boxes de glifos convertidas a ABSOLUTAS (las de segment_glyphs_with_boxes
    son relativas al crop). La red (metadata/pool/pesos) solo se toca si hay
    al menos una región type con conteo glifos==chars (rankeable).
    Regiones type con conteo desigual quedan con ranking=[] — el caller
    decide la degradación (spec §7).
    """
    prelim = []
    for reg in detect_regions(img_bgr):
        x0, y0, x1, y1 = reg["bbox"]
        glyphs, gboxes = segment_glyphs_with_boxes(img_bgr[y0:y1, x0:x1])
        abs_boxes = [(int(bx0 + x0), int(by0 + y0), int(bx1 + x0), int(by1 + y0))
                     for bx0, by0, bx1, by1 in gboxes]
        cls = classify_region(glyphs, reg["text"], boxes=gboxes)
        chars = [c for c in reg["text"] if not c.isspace()]
        rankeable = cls["label"] == "type" and len(glyphs) == len(chars)
        prelim.append((reg, glyphs, abs_boxes, cls, chars, rankeable))

    family_weights = {}
    if any(p[5] for p in prelim):
        metadata = fetch_metadata(cache_dir)
        pool = build_pool(metadata, pool_size=pool_size, category=category)
        family_weights = prepare_pool_weights(pool, cache_dir)

    out = []
    for reg, glyphs, abs_boxes, cls, chars, rankeable in prelim:
        ranking, scale = [], 0.0
        if rankeable and family_weights:
            rows = rank_families(glyphs, chars, family_weights, set())
            if rows:
                ties = tie_flags([(r["family"], r["overlap"]) for r in rows])
                ranking = [RankEntry(r["family"], r["wght"], r["overlap"], t)
                           for r, t in zip(rows, ties)]
                scale = rows[0]["scale"]
        out.append(RegionAnalysis(
            bbox=tuple(int(v) for v in reg["bbox"]), text=reg["text"],
            classification=cls["label"], class_score=float(cls["score"]),
            glyph_boxes=abs_boxes, ranking=ranking, scale_factor=scale))
    return out


if __name__ == "__main__":
    main()

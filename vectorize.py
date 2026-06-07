#!/usr/bin/env python3
"""
Vectorizador de imágenes a SVG — dos pipelines:

Handwriting (modos contour/skeleton/both):
  • Color real del trazo (filtro HSV)
  • Limpieza automática de ruido y líneas
  • Skeleton tracing con loops cerrados
  • Agujeros topológicos reales
  • Curvas Bézier cúbicas suaves

Color (--mode color, vía vtracer):
  • Logos, ilustraciones y fotos (posterizadas)
  • Presets logo/drawing/photo + flags de ajuste fino

Dependencias:
    pip install -r requirements.txt
    (opencv-contrib-python, numpy; vtracer solo para --mode color)
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
import sys
import xml.etree.ElementTree as ET


# ═══════════════════════════════════════════════════════════════════
# 0. CARGA DE IMAGEN (política de alpha compartida)
# ═══════════════════════════════════════════════════════════════════

def load_image_bgr(image_path):
    """Carga una imagen como BGR uint8, componiendo alpha sobre blanco.

    cv2.imread por defecto descarta el canal alpha: un PNG transparente
    entra con fondo negro basura. Aquí: IMREAD_UNCHANGED + composición
    sobre blanco. Una sola política para todos los pipelines.
    Devuelve None si la imagen no se puede cargar (igual que cv2.imread).
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.dtype == np.uint16:                    # PNG de 16 bits → 8 bits
        img = (img // 257).astype(np.uint8)
    if img.ndim == 2:                             # escala de grises → BGR
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:                         # BGRA → componer sobre blanco
        alpha = img[:, :, 3:4].astype(np.float64) / 255.0
        bgr = img[:, :, :3].astype(np.float64)
        return (bgr * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    return img


# ═══════════════════════════════════════════════════════════════════
# 1. COLOR REAL DEL TRAZO
# ═══════════════════════════════════════════════════════════════════

def extract_stroke_color(img_bgr, binary_mask):
    """Extrae el color real filtrando por HSV (evita fondo gris)."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]

    strict = np.zeros_like(binary_mask)
    strict[(binary_mask > 0) & ((s > 50) | (v < 200))] = 255

    if cv2.countNonZero(strict) < 20:
        strict = binary_mask

    mean_bgr = cv2.mean(img_bgr, mask=strict)
    r, g, b = int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0])
    return f"#{r:02x}{g:02x}{b:02x}"


# ═══════════════════════════════════════════════════════════════════
# 2. LIMPIEZA
# ═══════════════════════════════════════════════════════════════════

def clean_binary_mask(binary, min_area=12, max_aspect_hline=6.0,
                      min_hline_width_ratio=0.25, border_margin=5):
    h, w = binary.shape
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    cleaned = np.zeros_like(binary)

    for i in range(1, num_labels):
        x, y, bw, bh, area = stats[i]
        aspect = bw / max(bh, 1)

        if area < min_area:
            continue
        if aspect > max_aspect_hline and bw > w * min_hline_width_ratio:
            continue
        if aspect > max_aspect_hline and (y < border_margin or y + bh > h - border_margin):
            continue
        cleaned[labels == i] = 255

    return cleaned


# ═══════════════════════════════════════════════════════════════════
# 3. SKELETONIZACIÓN
# ═══════════════════════════════════════════════════════════════════

def skeletonize_fast(binary):
    img = ((binary > 0).astype(np.uint8)) * 255
    try:
        return cv2.ximgproc.thinning(img, thinningType=cv2.ximgproc.THINNING_GUOHALL)
    except Exception:
        pass
    try:
        from skimage.morphology import skeletonize
        return skeletonize(img.astype(bool)).astype(np.uint8) * 255
    except Exception:
        pass
    return cv2.erode(img, np.ones((2, 2), np.uint8), iterations=1)


# ═══════════════════════════════════════════════════════════════════
# 4. TRACING
# ═══════════════════════════════════════════════════════════════════

def trace_skeleton(skel, min_segment_len=3):
    """Trace skeleton by cutting it at junctions, then tracing each branch.

    Junctions (pixels with 3+ skeleton neighbors) are removed before tracing
    so branches that meet at a crossing each become their own path. After
    tracing, each branch's endpoints are extended to an adjacent junction
    pixel so the rendered strokes visually connect at crossings.
    """
    h, w = skel.shape
    sk = (skel > 0).astype(np.uint8)

    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
    nbr_count = cv2.filter2D(sk, ddepth=cv2.CV_8U, kernel=kernel) * sk
    junctions = (nbr_count >= 3) & (sk == 1)

    sk_cut = sk.copy()
    sk_cut[junctions] = 0

    visited = np.zeros_like(sk_cut, dtype=bool)
    paths = []

    def local_nbrs(y, x, mask):
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx]:
                    out.append((ny, nx))
        return out

    def unvisited_nbrs(y, x):
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and sk_cut[ny, nx] and not visited[ny, nx]:
                    out.append((ny, nx))
        return out

    def adjacent_junction(py, px):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                ny, nx = int(py) + dy, int(px) + dx
                if 0 <= ny < h and 0 <= nx < w and junctions[ny, nx]:
                    return (float(nx), float(ny))
        return None

    num_labels, labels, _, _ = cv2.connectedComponentsWithStats(sk_cut, connectivity=8)

    for comp_id in range(1, num_labels):
        comp_mask = (labels == comp_id)
        comp_ys, comp_xs = np.where(comp_mask)
        if len(comp_ys) < 2:
            continue

        endpoints = [(y, x) for y, x in zip(comp_ys, comp_xs)
                     if len(local_nbrs(y, x, comp_mask)) == 1]

        if endpoints:
            start = endpoints[0]
            is_loop = False
        else:
            start = (comp_ys[0], comp_xs[0])
            is_loop = True

        path = []
        y, x = start
        loop_start = start
        steps = 0
        max_steps = len(comp_ys) + 5
        while steps < max_steps:
            steps += 1
            if not sk_cut[y, x] or visited[y, x]:
                break
            visited[y, x] = True
            path.append((float(x), float(y)))
            nbrs = unvisited_nbrs(y, x)
            if not nbrs:
                if is_loop and len(path) > 4:
                    if abs(y - loop_start[0]) <= 1 and abs(x - loop_start[1]) <= 1:
                        path.append((float(loop_start[1]), float(loop_start[0])))
                break
            if len(nbrs) == 1:
                y, x = nbrs[0]
            else:
                if len(path) >= 2:
                    dx_prev = path[-1][0] - path[-2][0]
                    dy_prev = path[-1][1] - path[-2][1]
                    best = nbrs[0]
                    best_score = -1e9
                    for ny, nx in nbrs:
                        sc = dx_prev * (nx - x) + dy_prev * (ny - y)
                        if sc > best_score:
                            best_score = sc
                            best = (ny, nx)
                    y, x = best
                else:
                    y, x = nbrs[0]

        if path and not is_loop:
            j0 = adjacent_junction(path[0][1], path[0][0])
            if j0 is not None:
                path.insert(0, j0)
            j1 = adjacent_junction(path[-1][1], path[-1][0])
            if j1 is not None:
                path.append(j1)

        if len(path) >= min_segment_len:
            paths.append(path)

    return paths


# ═══════════════════════════════════════════════════════════════════
# 5. SIMPLIFICACIÓN Y BÉZIER
# ═══════════════════════════════════════════════════════════════════

def rdp_simplify(points, epsilon=1.0):
    if len(points) <= 2:
        return points
    pts = np.array(points)
    start, end = pts[0], pts[-1]
    if np.allclose(start, end):
        dists = np.linalg.norm(pts - start, axis=1)
    else:
        cross = np.abs(np.cross(end - start, start - pts))
        dists = cross / np.linalg.norm(end - start)
    idx = np.argmax(dists)
    if dists[idx] > epsilon:
        left = rdp_simplify(pts[:idx + 1].tolist(), epsilon)
        right = rdp_simplify(pts[idx:].tolist(), epsilon)
        return left[:-1] + right
    return [start.tolist(), end.tolist()]


def chaikin_smooth(points, iterations=2):
    pts = np.array(points, dtype=np.float64)
    if len(pts) < 3:
        return pts
    for _ in range(iterations):
        new_pts = [pts[0]]
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            new_pts.extend([p0 * 0.75 + p1 * 0.25, p0 * 0.25 + p1 * 0.75])
        new_pts.append(pts[-1])
        pts = np.array(new_pts)
    return pts


def catmull_rom_to_bezier(points, tension=0.5):
    pts = np.array(points, dtype=np.float64)
    n = len(pts)
    if n < 2:
        return ""
    if n == 2:
        return f"M {pts[0,0]:.2f} {pts[0,1]:.2f} L {pts[1,0]:.2f} {pts[1,1]:.2f}"

    ghost_start = pts[0] - (pts[1] - pts[0]) * 0.5
    ghost_end = pts[-1] + (pts[-1] - pts[-2]) * 0.5
    extended = np.vstack([ghost_start, pts, ghost_end])

    d = f"M {pts[0,0]:.2f} {pts[0,1]:.2f}"
    for i in range(len(extended) - 3):
        p0, p1, p2, p3 = extended[i], extended[i+1], extended[i+2], extended[i+3]
        cp1 = p1 + (p2 - p0) / (6 * tension)
        cp2 = p2 - (p3 - p1) / (6 * tension)
        d += f" C {cp1[0]:.2f} {cp1[1]:.2f} {cp2[0]:.2f} {cp2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f}"
    return d


def points_to_svg_path(points, rdp_eps=1.0, chaikin_iter=2, tension=0.5):
    if len(points) < 2:
        return ""
    simplified = rdp_simplify(points, epsilon=rdp_eps)
    if len(simplified) < 2:
        return ""
    smoothed = chaikin_smooth(simplified, iterations=chaikin_iter)
    return catmull_rom_to_bezier(smoothed, tension=tension)


# ═══════════════════════════════════════════════════════════════════
# 6. AGUJEROS
# ═══════════════════════════════════════════════════════════════════

def _gauss_filter_closed(pts, sigma):
    """Filtro gaussiano CIRCULAR sobre los puntos de un contorno cerrado
    (N,2). Mata el ruido de píxel antes del RDP sin deformar la forma.
    Ganador del barrido de suavizado (calibración 2026-06-07, sigma=2).
    sigma<=0 o contorno corto → passthrough."""
    n = len(pts)
    if n < 8 or sigma <= 0:
        return pts
    radius = max(1, int(3 * sigma))
    xs = np.arange(-radius, radius + 1)
    kernel = np.exp(-(xs ** 2) / (2 * sigma ** 2))
    kernel /= kernel.sum()
    out = np.empty_like(pts, dtype=np.float64)
    for d in range(2):
        col = pts[:, d]
        ext = np.concatenate([col[-radius:], col, col[:radius]])
        out[:, d] = np.convolve(ext, kernel, mode="valid")
    return out


def _smooth_closed_contour(pts, rdp_eps, chaikin_iter, tension, sigma=0.0):
    """RDP + Chaikin + Catmull-Rom on a closed contour. Returns 'd' string without trailing Z.

    sigma>0: gaussian point filter BEFORE RDP (see _gauss_filter_closed)."""
    if len(pts) < 4:
        return ""
    pts = _gauss_filter_closed(np.asarray(pts, dtype=np.float64), sigma)
    simplified = rdp_simplify(pts.tolist(), epsilon=rdp_eps)
    if len(simplified) < 3:
        return ""
    smoothed = chaikin_smooth(simplified, iterations=chaikin_iter)
    if len(smoothed) < 3:
        return ""
    closed = np.vstack([smoothed, smoothed[:1]])
    return catmull_rom_to_bezier(closed, tension=tension)


def trace_contours(binary, rdp_eps=1.0, chaikin_iter=1, tension=0.5,
                   min_outer_area=8, min_hole_area=8, sigma=0.0):
    """Trace ink mask as filled outlines with holes.

    Returns a list of path-data strings; each string is one connected ink blob
    (outer outline plus all interior holes), suitable for rendering with
    fill-rule="evenodd".
    """
    contours, hierarchy = cv2.findContours(
        binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE
    )
    if hierarchy is None or not len(contours):
        return []
    hierarchy = hierarchy[0]

    children = {}
    outers = []
    for i, h in enumerate(hierarchy):
        if h[3] == -1:
            outers.append(i)
        else:
            children.setdefault(h[3], []).append(i)

    paths = []
    for oi in outers:
        if cv2.contourArea(contours[oi]) < min_outer_area:
            continue
        outer_pts = contours[oi].reshape(-1, 2).astype(np.float64)
        d_outer = _smooth_closed_contour(outer_pts, rdp_eps, chaikin_iter, tension, sigma)
        if not d_outer:
            continue
        d_parts = [d_outer + " Z"]
        for hi in children.get(oi, []):
            if cv2.contourArea(contours[hi]) < min_hole_area:
                continue
            hole_pts = contours[hi].reshape(-1, 2).astype(np.float64)
            d_hole = _smooth_closed_contour(hole_pts, rdp_eps, chaikin_iter, tension, sigma)
            if d_hole:
                d_parts.append(d_hole + " Z")
        paths.append(" ".join(d_parts))
    return paths


# ═══════════════════════════════════════════════════════════════════
# 6.5. PIPELINE DE COLOR (vtracer)
# ═══════════════════════════════════════════════════════════════════

SVG_NS = "http://www.w3.org/2000/svg"


def _vtracer_convert(png_bytes,
                     colormode="color", hierarchical="stacked", mode="spline",
                     filter_speckle=4, color_precision=6, layer_difference=16,
                     corner_threshold=60, length_threshold=4.0,
                     max_iterations=10, splice_threshold=45, path_precision=3):
    """Única puerta hacia vtracer. Invoca SIEMPRE en forma 100% posicional.

    NUNCA pasar kwargs a vtracer: el binding PyO3 del wheel cp314 produce
    SIGSEGV (ACCESS_VIOLATION 0xC0000005) con cualquier keyword argument
    en Python 3.14 — mata el proceso sin excepción capturable.
    Verificado 2026-06-05 (spec, hechos runtime 2-4). Orden posicional:
    (img_bytes, img_format, colormode, hierarchical, mode, filter_speckle,
     color_precision, layer_difference, corner_threshold, length_threshold,
     max_iterations, splice_threshold, path_precision)
    """
    try:
        import vtracer
    except ImportError:
        raise RuntimeError(
            "El modo color requiere vtracer. Instala con: pip install vtracer"
        ) from None
    return vtracer.convert_raw_image_to_svg(
        png_bytes, "png", colormode, hierarchical, mode,
        filter_speckle, color_precision, layer_difference,
        corner_threshold, length_threshold, max_iterations,
        splice_threshold, path_precision,
    )


def count_effective_colors(img_bgr, k=16, coverage=0.95, max_side=256,
                           sample_px=10000, seed=42):
    """Cuenta colores efectivos: nº de clusters k-means (LAB) que cubren
    `coverage` de los píxeles, ordenados por población.

    Determinismo obligatorio (spec): semilla fija, KMEANS_PP_CENTERS y
    attempts=3 — con RANDOM_CENTERS el conteo varía entre corridas.
    k=16 para resolver el umbral de preset (12).
    """
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_side:
        s = max_side / max(h, w)
        img_bgr = cv2.resize(img_bgr, (max(1, int(w * s)), max(1, int(h * s))),
                             interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    pixels = lab.reshape(-1, 3).astype(np.float32)
    if len(pixels) > sample_px:
        rng = np.random.default_rng(seed)
        pixels = pixels[rng.choice(len(pixels), sample_px, replace=False)]
    k = min(k, len(pixels))
    cv2.setRNGSeed(seed)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _, labels, _ = cv2.kmeans(pixels, k, None, criteria, 3,
                              cv2.KMEANS_PP_CENTERS)
    counts = np.sort(np.bincount(labels.flatten(), minlength=k))[::-1]
    cum = np.cumsum(counts) / counts.sum()
    return int(np.searchsorted(cum, coverage) + 1)


def choose_preset(img_bgr):
    """≤12 colores efectivos → logo; >12 → photo.

    `drawing` solo se activa manualmente (--preset drawing) — decisión
    intencional del spec: el conteo de color no separa de forma fiable
    una ilustración con gradientes de un logo o una foto.
    """
    n = count_effective_colors(img_bgr)
    preset = "logo" if n <= 12 else "photo"
    print(f"  [PRESET] {preset} ({n} colores efectivos)")
    return preset


COLOR_PRESETS = {
    # spec: tabla de presets. Comunes a los tres: mode=spline,
    # hierarchical=stacked, path_precision=3 (defaults del wrapper).
    "logo":    dict(filter_speckle=8, color_precision=6,
                    layer_difference=48, corner_threshold=45),
    "drawing": dict(filter_speckle=4, color_precision=7,
                    layer_difference=24, corner_threshold=60),
    "photo":   dict(filter_speckle=4, color_precision=8,
                    layer_difference=12, corner_threshold=60),
}


def _write_svg_scaled(svg_text, out_path, orig_w, orig_h, work_w, work_h):
    """Post-proceso del SVG de vtracer (spec, hecho runtime 7).

    vtracer emite el root SIN viewBox → se añade (dims de trabajo) y se
    reescriben width/height (dims originales) — la misma política de
    escala del pipeline handwriting. register_namespace ANTES de parsear
    o ElementTree contamina el roundtrip con prefijos ns0:.
    Si el post-proceso falla: se escribe tal cual CON warning (la
    degradación silenciosa era una contradicción del spec v1).
    """
    out_path = Path(out_path)
    try:
        ET.register_namespace("", SVG_NS)
        root = ET.fromstring(svg_text)
        root.set("width", str(orig_w))
        root.set("height", str(orig_h))
        root.set("viewBox", f"0 0 {work_w} {work_h}")
        ET.ElementTree(root).write(out_path, encoding="utf-8",
                                   xml_declaration=True)
    except ET.ParseError as e:
        print(f"  [WARN] Post-proceso del SVG falló ({e}); "
              f"se escribe sin escalar — dims de vtracer, no originales.")
        out_path.write_text(svg_text, encoding="utf-8")
    return out_path


def vectorize_color(image_path, output_path=None, preset=None, max_dim=1200,
                    **overrides):
    """Vectoriza una imagen a color con vtracer (logos, ilustraciones, fotos).

    preset:
      - None (default): se elige solo — ≤12 colores efectivos → logo, >12 → photo.
      - "logo" | "drawing" | "photo": explícito.
    max_dim: resize previo en memoria si el lado mayor lo supera (0 = sin resize).
    overrides: filter_speckle, color_precision, layer_difference,
               corner_threshold, path_precision — pisan el preset (None = no pisa).
    """
    img = load_image_bgr(image_path)
    if img is None:
        raise ValueError(f"No se pudo cargar: {image_path}")

    orig_h, orig_w = img.shape[:2]
    work = img
    if max_dim and max(orig_w, orig_h) > max_dim:
        s = max_dim / max(orig_w, orig_h)
        work = cv2.resize(img, (int(orig_w * s), int(orig_h * s)),
                          interpolation=cv2.INTER_AREA)
    work_h, work_w = work.shape[:2]

    if preset is None:
        preset = choose_preset(work)
    params = dict(COLOR_PRESETS[preset])
    params.update({k: v for k, v in overrides.items() if v is not None})

    ok, buf = cv2.imencode(".png", work)
    if not ok:
        raise ValueError(f"No se pudo codificar a PNG: {image_path}")
    svg_text = _vtracer_convert(buf.tobytes(), **params)

    out = Path(output_path) if output_path else Path(image_path).with_suffix(".svg")
    _write_svg_scaled(svg_text, out, orig_w, orig_h, work_w, work_h)

    print(f"  [OK] SVG: {out}")
    print(f"       Modo: color | Preset: {preset}")
    return out


# ═══════════════════════════════════════════════════════════════════
# 7. PIPELINE
# ═══════════════════════════════════════════════════════════════════

def _build_skeleton_paths(binary_clean, rdp_epsilon, chaikin, tension):
    skel = skeletonize_fast(binary_clean)
    paths = trace_skeleton(skel)
    out = []
    for path_pts in paths:
        if len(path_pts) < 3:
            continue
        d = points_to_svg_path(path_pts, rdp_eps=rdp_epsilon,
                               chaikin_iter=chaikin, tension=tension)
        if d:
            out.append(d)
    return out


def vectorize(image_path, output_path=None,
              mode="contour",
              blur=3,
              rdp_epsilon=1.0, chaikin=2, tension=0.5,
              stroke_width=2.0, auto_color=True, fallback_color="#1a1a1a"):
    """Vectorize a handwriting image to SVG.

    mode:
      - "contour":  fill ink outline as closed shapes with evenodd holes
                    (best fidelity — preserves stroke thickness).
      - "skeleton": trace centerline as thin strokes.
      - "both":     contour fill + skeleton centerline on top.
    """
    if mode not in ("contour", "skeleton", "both"):
        raise ValueError(f"mode must be contour|skeleton|both, got {mode!r}")

    img = load_image_bgr(image_path)
    if img is None:
        raise ValueError(f"No se pudo cargar: {image_path}")

    orig_h, orig_w = img.shape[:2]
    scale = 1.0
    if max(orig_w, orig_h) > 1200:
        scale = 1200 / max(orig_w, orig_h)
        img = cv2.resize(img, (int(orig_w * scale), int(orig_h * scale)),
                         interpolation=cv2.INTER_AREA)
    work_h, work_w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    background_is_bright = np.mean(gray) > 127

    if blur > 0:
        k = blur * 2 + 1
        gray = cv2.GaussianBlur(gray, (k, k), 0)

    thresh_flag = cv2.THRESH_BINARY_INV if background_is_bright else cv2.THRESH_BINARY
    _, binary = cv2.threshold(gray, 0, 255, thresh_flag | cv2.THRESH_OTSU)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                              np.ones((2, 2), np.uint8), iterations=1)
    binary_clean = clean_binary_mask(binary)

    stroke_color = fallback_color
    if auto_color:
        try:
            stroke_color = extract_stroke_color(img, binary_clean)
        except Exception:
            stroke_color = fallback_color

    contour_paths = []
    skeleton_paths = []
    if mode in ("contour", "both"):
        # Contours operate at the image's native scale; coordinates are in
        # the resized space, so we scale up via the SVG viewBox transform.
        contour_paths = trace_contours(
            binary_clean,
            rdp_eps=max(0.5, rdp_epsilon * 0.75),
            chaikin_iter=max(1, chaikin - 1),
            tension=tension,
        )
    if mode in ("skeleton", "both"):
        skeleton_paths = _build_skeleton_paths(
            binary_clean, rdp_epsilon, chaikin, tension
        )

    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "version": "1.1",
        "width": str(orig_w), "height": str(orig_h),
        "viewBox": f"0 0 {work_w} {work_h}",
    })

    defs = ET.SubElement(svg, "defs")
    style = ET.SubElement(defs, "style")
    style.text = (
        f".ink {{ fill: {stroke_color}; fill-rule: evenodd; "
        f"stroke: none; opacity: 0.95; }} "
        f".stroke {{ fill: none; stroke: {stroke_color}; "
        f"stroke-width: {stroke_width:.2f}; stroke-linecap: round; "
        f"stroke-linejoin: round; stroke-opacity: 0.95; }}"
    )

    if contour_paths:
        g_ink = ET.SubElement(svg, "g", {"class": "ink"})
        for d in contour_paths:
            ET.SubElement(g_ink, "path", {"d": d})

    if skeleton_paths:
        g_skel = ET.SubElement(svg, "g", {"class": "stroke"})
        for d in skeleton_paths:
            ET.SubElement(g_skel, "path", {"d": d})

    out_path = Path(output_path) if output_path else Path(image_path).with_suffix(".svg")
    tree = ET.ElementTree(svg)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)

    print(f"  [OK] SVG: {out_path}")
    print(f"       Color: {stroke_color} | Modo: {mode}")
    print(f"       Contornos: {len(contour_paths)} | Centerlines: {len(skeleton_paths)}")
    return out_path


# ═══════════════════════════════════════════════════════════════════
# 8. MAIN
# ═══════════════════════════════════════════════════════════════════

def build_parser():
    parser = argparse.ArgumentParser(
        description="Vectoriza imágenes a SVG: handwriting (contour/skeleton) "
                    "o color con vtracer (logos, ilustraciones, fotos)"
    )
    parser.add_argument("input", help="Imagen PNG/JPG o directorio")
    parser.add_argument("-o", "--output", help="SVG o directorio de salida")
    parser.add_argument("--mode", choices=("contour", "skeleton", "both", "color"),
                        default="contour",
                        help="contour=relleno fiel | skeleton=línea fina | "
                             "both=ambos | color=vtracer full-color")
    # flags handwriting (solo modos contour/skeleton/both)
    parser.add_argument("--blur", type=int, default=3)
    parser.add_argument("--rdp", type=float, default=1.0)
    parser.add_argument("--chaikin", type=int, default=2)
    parser.add_argument("--tension", type=float, default=0.5)
    parser.add_argument("--width", type=float, default=2.0,
                        help="Stroke width for skeleton mode")
    parser.add_argument("--color", default=None,
                        help="Forzar color hex del trazo (solo handwriting; "
                             "no confundir con --colors, que es del modo color)")
    parser.add_argument("--no-auto-color", action="store_true")
    # flags color (solo modo color)
    parser.add_argument("--preset", choices=("logo", "drawing", "photo"),
                        default=None,
                        help="Preset del modo color (default: auto por "
                             "colores efectivos; drawing solo manual)")
    parser.add_argument("--colors", type=int, default=None,
                        help="color_precision de vtracer")
    parser.add_argument("--speckle", type=int, default=None,
                        help="filter_speckle de vtracer")
    parser.add_argument("--layer-diff", type=int, default=None,
                        help="layer_difference de vtracer")
    parser.add_argument("--corner", type=int, default=None,
                        help="corner_threshold de vtracer")
    parser.add_argument("--path-precision", type=int, default=None,
                        help="Decimales de coordenadas en el SVG")
    parser.add_argument("--max-dim", type=int, default=1200,
                        help="Resize previo del modo color (0 = sin resize)")
    return parser


_HANDWRITING_FLAG_DEFAULTS = {
    "blur": 3, "rdp": 1.0, "chaikin": 2, "tension": 0.5,
    "width": 2.0, "color": None, "no_auto_color": False,
}
_COLOR_FLAG_DEFAULTS = {
    "preset": None, "colors": None, "speckle": None,
    "layer_diff": None, "corner": None, "path_precision": None,
    "max_dim": 1200,
}


def warn_inert_flags(args):
    """Avisa de flags que no aplican al modo activo (spec: nada se ignora
    en silencio). El flag inerte se reporta; no altera el resultado."""
    inert = (_HANDWRITING_FLAG_DEFAULTS if args.mode == "color"
             else _COLOR_FLAG_DEFAULTS)
    for name, default in inert.items():
        if getattr(args, name) != default:
            print(f"  [WARN] --{name.replace('_', '-')} no aplica al modo "
                  f"{args.mode}; ignorado.")


def main():
    args = build_parser().parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None

    warn_inert_flags(args)

    if args.mode == "color":
        try:
            import vtracer  # noqa: F401 — fail fast antes de procesar
        except ImportError:
            print("El modo color requiere vtracer. Instala con: pip install vtracer")
            sys.exit(1)

        def run_one(f, out):
            return vectorize_color(
                f, output_path=out, preset=args.preset, max_dim=args.max_dim,
                filter_speckle=args.speckle, color_precision=args.colors,
                layer_difference=args.layer_diff, corner_threshold=args.corner,
                path_precision=args.path_precision,
            )
    else:
        common = dict(
            mode=args.mode, blur=args.blur,
            rdp_epsilon=args.rdp, chaikin=args.chaikin, tension=args.tension,
            stroke_width=args.width, auto_color=not args.no_auto_color,
            fallback_color=args.color or "#1a1a1a",
        )

        def run_one(f, out):
            return vectorize(f, output_path=out, **common)

    if input_path.is_dir():
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")
        files = sorted([f for f in input_path.iterdir() if f.suffix.lower() in exts])
        if not files:
            print(f"No se encontraron imágenes en {input_path}")
            return
        out_dir = output_path or input_path / "svg_output"
        out_dir.mkdir(exist_ok=True)
        print(f"Procesando {len(files)} imágenes ({args.mode})...\n")
        done, failed = 0, 0
        for i, f in enumerate(files, 1):
            print(f"[{i}/{len(files)}] {f.name}")
            try:
                run_one(f, out_dir / f.with_suffix(".svg").name)
                done += 1
            except Exception as e:
                print(f"   [ERR] {e}")
                failed += 1
            print()
        # Resumen agregado: comportamiento NUEVO de Fase 1 (declarado en spec)
        print(f"Resumen: {done} OK ({args.mode}), {failed} fallos.")
    else:
        run_one(input_path, output_path)


if __name__ == "__main__":
    main()
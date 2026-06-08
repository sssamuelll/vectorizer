#!/usr/bin/env python3
"""recompose.py — Fase B v0.1 (replay puro), orquestador CLI sobre recompose_core.

Logo de UNA tinta → SVG híbrido. El core compartido vive en recompose_core.py;
aquí queda el CLI: parseo de --font, costura/empate, presentación, main.
Spec: docs/superpowers/specs/2026-06-07-recompose-core-extraction-design.md

Superficie de import CERRADA (test AST la vigila):
  recompose_core: lo que main() usa
  fontid:         analyze_regions, CACHE_DIR_DEFAULT
  vectorize:      load_image_bgr, count_effective_colors
"""
import argparse
import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np

from recompose_core import (CALLIG_RDP, CALLIG_CHAIKIN, CALLIG_TENSION,
                            COLOR_WARN_THRESHOLD, MASK_PAD, FontKeyError,
                            SeamDecision, binary_ink_mask, calligraphy_paths,
                            common_scale, compose_svg, glyph_transform,
                            region_glyph_paths, seam_decision)
from fontid import CACHE_DIR_DEFAULT, analyze_regions, download_family_weights
from vectorize import count_effective_colors, extract_stroke_color, load_image_bgr

# exit codes (spec §7) — CLI-only
EXIT_NADA_QUE_RECOMPONER = 2
EXIT_EMPATE_PENDIENTE = 3
EXIT_FONT_KEY = 4


def resolve_ttf(family, wght, cache_dir):
    """TTF de familia:peso — caché primero, descarga on-demand después.
    La familia puede NO estar en el ranking (regla de soberanía: el ojo
    elige fuera del menú — caso Nanum Myeongjo). Peso inexistente →
    FontKeyError con los disponibles."""
    # Sanitizar la clave de caché: rechazar ruta traversal (spec HF5)
    if any(sep in family for sep in ("/", "\\", "..")) or family != family.strip():
        raise FontKeyError(f"nombre de familia inválido: {family!r}")

    cache_dir = Path(cache_dir)
    cached = cache_dir / f"{family.replace(' ', '_')}_{wght}.ttf"
    if cached.exists():
        return cached
    weights = download_family_weights(family, cache_dir)
    for w, path in weights:
        if w == wght:
            return path
    disponibles = sorted(w for w, _ in weights) or "ninguno (¿red caída o familia inexistente en GF?)"
    raise FontKeyError(
        f"peso {wght} no disponible para {family!r}; disponibles: {disponibles}")


def _norm_key(s):
    """Normalización de claves --font: casefold + colapso de espacios."""
    return " ".join(s.casefold().split())


def parse_font_arg(raw):
    """'clave=Familia:wght' → (clave, familia, wght). ValueError si malformado."""
    key, sep, value = raw.partition("=")
    if not sep or not key or ":" not in value:
        raise ValueError(
            f'--font malformado: {raw!r} (esperado "texto=Familia:wght" '
            f'o "#N=Familia:wght")')
    family, _, wght_s = value.rpartition(":")
    if not family or not wght_s.isdigit():
        raise ValueError(f"--font sin peso numérico: {raw!r}")
    return key, family.strip(), int(wght_s)


def resolve_font_choices(font_args, regions):
    """[--font strings] + [RegionAnalysis] → {índice_región: (familia, wght)}.

    Clave por texto: match EXACTO post-normalización. Clave '#N': región
    N (1-based). No-match → FontKeyError con las claves disponibles
    (jamás degradación silenciosa — rompería el replay).
    """
    norm_texts = [_norm_key(r.text) for r in regions]
    out = {}
    for raw in font_args:
        key, family, wght = parse_font_arg(raw)
        if key.startswith("#"):
            idx_s = key[1:]
            if not idx_s.isdigit() or not (1 <= int(idx_s) <= len(regions)):
                raise FontKeyError(
                    f"índice {key!r} fuera de rango (hay {len(regions)} regiones)")
            out[int(idx_s) - 1] = (family, wght)
            continue
        nk = _norm_key(key)
        matches = [i for i, t in enumerate(norm_texts) if t == nk]
        if not matches:
            raise FontKeyError(
                f"--font {key!r} no matchea ninguna región. Disponibles: "
                + ", ".join(repr(r.text) for r in regions))
        if len(matches) > 1:
            raise FontKeyError(
                f"--font {key!r} matchea {len(matches)} regiones — usa #N")
        out[matches[0]] = (family, wght)
    return out


def print_seam_report(regions, decisions):
    """La costura SIEMPRE se reporta (junta: 'la frontera más peligrosa
    era la única sin ceremonia')."""
    print("Costura (qué se recompone vs qué se vectoriza):")
    for i, (r, d) in enumerate(zip(regions, decisions), 1):
        verbo = "recompone" if d.recompose else "vectoriza"
        print(f"  [{i}] \"{r.text}\" → se {verbo} — {d.reason}")


def _render_svg(svg_text):
    """Render BGR del SVG vía resvg_py, o None si no está instalado.
    resvg_py es dependencia OPCIONAL (solo preview)."""
    try:
        import resvg_py
    except ImportError:
        return None
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg_text))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:
        return None
    if arr.shape[2] == 4:
        a = arr[:, :, 3:4].astype(np.float32) / 255.0
        arr = (arr[:, :, :3].astype(np.float32) * a
               + 255.0 * (1 - a)).astype(np.uint8)
    return arr


def write_preview(orig_bgr, svg_text, region_boxes, out_path):
    """Preview = original | render (el original SIEMPRE presente como
    ancla — Iris: sin él es '¿cuál te gusta?' en vez de '¿cuál calza?'),
    más una banda de zoom por región recompuesta. None sin resvg."""
    render = _render_svg(svg_text)
    if render is None:
        print("  [WARN] resvg_py no disponible — preview omitido "
              "(pip install resvg_py)", file=sys.stderr)
        return None
    if render.shape[:2] != orig_bgr.shape[:2]:
        render = cv2.resize(render, (orig_bgr.shape[1], orig_bgr.shape[0]),
                            interpolation=cv2.INTER_AREA)
    sep_v = np.zeros((orig_bgr.shape[0], 4, 3), np.uint8)
    rows = [np.hstack([orig_bgr, sep_v, render])]
    for x0, y0, x1, y1 in region_boxes:
        a, b = orig_bgr[y0:y1, x0:x1], render[y0:y1, x0:x1]
        sep = np.zeros((a.shape[0], 4, 3), np.uint8)
        band = np.hstack([a, sep, b])
        scale = rows[0].shape[1] / band.shape[1]
        band = cv2.resize(band, (rows[0].shape[1],
                                 max(1, int(band.shape[0] * scale))),
                          interpolation=cv2.INTER_AREA if scale < 1
                          else cv2.INTER_CUBIC)
        rows.append(np.zeros((6, rows[0].shape[1], 3), np.uint8))
        rows.append(band)
    out_path = Path(out_path)
    cv2.imwrite(str(out_path), np.vstack(rows))
    return out_path


def print_correction_commands(input_path, regions, choices):
    """Eco sintáctico de una decisión visual (Iris: la superficie es el
    PNG; el comando es la sintaxis). Por región recompuesta: la usada +
    las 3 siguientes del ranking como re-corridas armadas."""
    print("\nCorrección (mira el preview; estas son las re-corridas):")
    for idx, (family, wght) in sorted(choices.items()):
        r = regions[idx]
        print(f"  [{idx + 1}] \"{r.text}\" — usada: {family} {wght}")
        alternativas = [e for e in r.ranking
                        if (e.family, e.wght) != (family, wght)][:3]
        for e in alternativas:
            print(f'      python recompose.py "{input_path}" '
                  f'--font "{r.text}={e.family}:{e.wght}"')


def build_parser():
    p = argparse.ArgumentParser(
        description="Recomposición híbrida v0.1 (replay): caligrafía "
                    "vectorizada + texto desde TTF. Logos de UNA tinta.")
    p.add_argument("input", help="Imagen del logo (PNG/JPG)")
    p.add_argument("-o", "--output", help="SVG de salida "
                   "(default: <input>_recompuesto.svg)")
    p.add_argument("--font", action="append", default=[],
                   metavar='"clave=Familia:wght"',
                   help='Decisión de fuente por región (repetible). Clave = '
                        'texto OCR o #N. Obligatorio si la región tiene empate.')
    p.add_argument("--contour-sigma", type=float, default=2.0,
                   help="Suavizado de caligrafía (default 2.0, calibrado)")
    p.add_argument("--category", default=None,
                   help="Categoría GF del pool (p.ej. serif)")
    p.add_argument("--pool", type=int, default=60)
    p.add_argument("--cache-dir", default=str(CACHE_DIR_DEFAULT))
    return p


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # cp1252 crashea con Δ/→
    args = build_parser().parse_args()

    img = load_image_bgr(args.input)
    if img is None:
        sys.exit(f"error: no se pudo cargar {args.input}")
    h, w = img.shape[:2]

    n_colores = count_effective_colors(img)
    if n_colores > COLOR_WARN_THRESHOLD:
        print(f"  [WARN] imagen con ~{n_colores} colores efectivos — recompose "
              f"asume UNA tinta (§ fuera de alcance v0.1). Continúo, pero el color "
              f"y la máscara pueden no ser fieles.", file=sys.stderr)

    try:
        regions = analyze_regions(img, cache_dir=Path(args.cache_dir),
                                  pool_size=args.pool, category=args.category)
    except RuntimeError as e:
        sys.exit(f"error: {e}")

    if not regions:
        print("Sin regiones de texto detectadas — nada que recomponer.")
        print("Para vectorización pura usa: python vectorize.py", args.input)
        raise SystemExit(EXIT_NADA_QUE_RECOMPONER)

    # resolve choices ANTES de decisions: --font habilita recomposición
    # aunque el ranking esté vacío (offline sovereignty, HF2)
    try:
        choices = resolve_font_choices(args.font, regions)
    except (ValueError, FontKeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(EXIT_FONT_KEY)

    decisions = [seam_decision(r, has_font=(i in choices))
                 for i, r in enumerate(regions)]
    print_seam_report(regions, decisions)

    recomp_idx = [i for i, d in enumerate(decisions) if d.recompose]
    if not recomp_idx:
        print("\nNinguna región supera la costura — nada que recomponer.")
        print("Para vectorización pura usa: python vectorize.py", args.input)
        raise SystemExit(EXIT_NADA_QUE_RECOMPONER)

    # --font sobre región que la costura no recompone: avisar, jamás tragar
    ignoradas = [i for i in choices if i not in recomp_idx]
    for i in ignoradas:
        d = decisions[i]
        print(f"  [WARN] --font para \"{regions[i].text}\" ignorado: "
              f"la región no se recompone ({d.reason})", file=sys.stderr)

    # resolución por región: --font > líder sin empate > ERROR si empate
    pendientes = []
    for i in recomp_idx:
        if i in choices:
            continue
        r = regions[i]
        lider = r.ranking[0]
        empate = len(r.ranking) > 1 and r.ranking[1].tie
        if empate:
            pendientes.append((i, r))
        else:
            choices[i] = (lider.family, lider.wght)
    if pendientes:
        print("\nEmpate sin decisión (Δ<0.03) — el replay exige --font:")
        for i, r in pendientes:
            for e in r.ranking[:4]:
                marca = " (líder)" if e is r.ranking[0] else ""
                print(f'  --font "{r.text}={e.family}:{e.wght}"'
                      f'  # overlap {e.score:.3f}{marca}')
        raise SystemExit(EXIT_EMPATE_PENDIENTE)

    # compositor
    cache_dir = Path(args.cache_dir)
    glyph_pairs = []
    mask_boxes = []
    final_choices = {}
    provenance = []
    for i in recomp_idx:
        r = regions[i]
        family, wght = choices[i]
        try:
            ttf = resolve_ttf(family, wght, cache_dir)
        except FontKeyError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(EXIT_FONT_KEY)
        sha = hashlib.sha256(ttf.read_bytes()).hexdigest()[:16]
        provenance.append(f"{family}:{wght} sha256:{sha}")
        chars = [c for c in r.text if not c.isspace()]
        try:
            glyph_pairs.extend(
                region_glyph_paths(ttf, chars, r.glyph_boxes, family))
        except FontKeyError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(EXIT_FONT_KEY)
        mask_boxes.append(r.bbox)
        final_choices[i] = (family, wght)

    callig = calligraphy_paths(img, mask_boxes, sigma=args.contour_sigma)
    ink = extract_stroke_color(img, binary_ink_mask(img))
    svg_text = compose_svg(w, h, ink, callig, glyph_pairs, provenance=provenance)

    out_path = (Path(args.output) if args.output
                else Path(args.input).with_name(
                    Path(args.input).stem + "_recompuesto.svg"))
    out_path.write_text(svg_text, encoding="utf-8")
    print(f"\n  [OK] SVG híbrido: {out_path}")
    print(f"       Tinta: {ink} | caligrafía: {len(callig)} contornos | "
          f"glifos: {len(glyph_pairs)}")

    preview = write_preview(img, svg_text, mask_boxes,
                            out_path.with_name(out_path.stem + "_preview.png"))
    if preview:
        print(f"     Preview: {preview}")
    print_correction_commands(args.input, regions, final_choices)
    raise SystemExit(0)


if __name__ == "__main__":
    main()

"""Tests de Fase 1 — pipeline de color (vtracer) + fix de alpha.

Fixtures sintéticas generadas in-test con numpy/cv2 (cero binarios commiteados).
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vectorize as vz


# ═══════════════════════════════════════════════════════════════════
# FIXTURES SINTÉTICAS
# ═══════════════════════════════════════════════════════════════════

def make_logo(path, size=400):
    """Logo sintético de 4 colores planos (fondo blanco + 3 figuras)."""
    img = np.full((size, size, 3), 255, np.uint8)
    cv2.rectangle(img, (40, 40), (200, 200), (60, 60, 230), -1)    # rojo
    cv2.rectangle(img, (220, 80), (360, 320), (230, 120, 40), -1)  # azul
    cv2.circle(img, (200, 300), 70, (80, 180, 60), -1)             # verde
    cv2.imwrite(str(path), img)
    return path


# ═══════════════════════════════════════════════════════════════════
# ALPHA (spec: "Política de alpha compartida")
# ═══════════════════════════════════════════════════════════════════

def test_alpha_composites_on_white(tmp_path):
    """PNG transparente compone sobre BLANCO, no sobre negro."""
    rgba = np.zeros((100, 100, 4), np.uint8)             # todo transparente
    rgba[30:70, 30:70] = (0, 0, 255, 255)                # cuadro rojo opaco
    p = tmp_path / "alpha.png"
    cv2.imwrite(str(p), rgba)
    img = vz.load_image_bgr(p)
    assert img.shape == (100, 100, 3)
    assert (img[0, 0] == [255, 255, 255]).all()          # fondo blanco
    assert (img[50, 50] == [0, 0, 255]).all()            # el cuadro sobrevive


def test_load_matches_imread_for_opaque_png(tmp_path):
    """Para imágenes sin alpha el resultado es idéntico a cv2.imread (sin regresión)."""
    p = make_logo(tmp_path / "logo.png")
    assert (vz.load_image_bgr(p) == cv2.imread(str(p))).all()


def test_load_returns_none_for_missing_file(tmp_path):
    assert vz.load_image_bgr(tmp_path / "nope.png") is None

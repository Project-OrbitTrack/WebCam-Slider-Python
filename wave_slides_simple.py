#!/usr/bin/env python3
"""
Wave Slides - Simple: Control slides by waving your hand.
Displays only the slides, no waves or camera preview.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

from config_manager import ConfigManager

cfg = ConfigManager()
cfg.validate()

# ---------------------------------------------------------------- slide loading

IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def natural_key(s):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def find_soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if os.path.exists(p):
            return p
    return None


def pptx_to_pdf(path, outdir):
    soffice = find_soffice()
    if not soffice:
        sys.exit("LibreOffice not found. Install it, or export your deck to PDF and pass that instead.")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pdf = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    if not os.path.exists(pdf):
        sys.exit("PowerPoint conversion failed. Try re-saving the file or exporting to PDF.")
    return pdf


def pdf_to_images(pdf, outdir, width=1600):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    paths = []
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc):
            zoom = width / page.rect.width
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            p = os.path.join(outdir, f"slide_{i:04d}.png")
            pix.save(p)
            paths.append(p)
    return paths


def load_deck(src, workdir):
    """Return a list of image file paths, one per slide."""
    if os.path.isdir(src):
        files = sorted((f for f in os.listdir(src) if f.lower().endswith(IMG_EXT)), key=natural_key)
        return [os.path.join(src, f) for f in files]
    ext = os.path.splitext(src)[1].lower()
    if ext == ".pptx":
        print("Converting slides, one moment...")
        return pdf_to_images(pptx_to_pdf(src, workdir), workdir)
    if ext == ".pdf":
        return pdf_to_images(src, workdir)
    if ext == ".ppt":
        sys.exit("Old .ppt is not supported. Save as .pptx first.")
    if ext in IMG_EXT:
        return [src]
    sys.exit("Unsupported input. Use .pptx, .pdf, an image, or a folder of images.")

# ---------------------------------------------------------------- wave detector

class WaveDetector:
    """Frame differencing on a 64x48 mirrored grayscale image."""

    W, H = 64, 48

    def __init__(self, sens=5):
        self.sens = sens
        self.prev = None
        self.trail = []
        self.last_fire = 0.0
        self.moving = False

    def reset(self):
        self.prev = None
        self.trail = []

    def update(self, frame, now=None):
        """Feed a BGR frame. Returns +1 (next), -1 (previous) or 0."""
        now = time.monotonic() if now is None else now
        small = cv2.resize(frame, (self.W, self.H), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.flip(gray, 1)

        thresh = 40 - self.sens * 2.5
        min_pixels = 90 - self.sens * 6
        cx = None
        if self.prev is not None:
            diff = np.abs(gray.astype(np.int16) - self.prev.astype(np.int16)) > thresh
            count = int(diff.sum())
            if count > min_pixels:
                xs = np.nonzero(diff)[1]
                cx = float(xs.mean()) / self.W
        self.prev = gray
        self.moving = cx is not None

        if cx is not None:
            self.trail.append((now, cx))
        self.trail = [p for p in self.trail if now - p[0] < 0.65]

        if len(self.trail) >= 4 and now - self.last_fire > 0.9:
            travel = self.trail[-1][1] - self.trail[0][1]
            need = 0.34 - self.sens * 0.015
            if abs(travel) > need:
                self.last_fire = now
                self.trail = []
                return 1 if travel > 0 else -1
        return 0

# ---------------------------------------------------------------- main

KEY_NEXT = {ord("n"), ord("d"), ord(" "), 2555904, 65363, 63235, 83}
KEY_PREV = {ord("p"), ord("a"), 2424832, 65361, 63234, 81}


def run(args):
    workdir = tempfile.mkdtemp(prefix="waveslides_")
    try:
        paths = load_deck(args.source, workdir)
        if not paths:
            sys.exit("No slides found.")
        cache = {}

        def get(i):
            if i not in cache:
                cache.clear()
                cache[i] = cv2.imread(paths[i])
            return cache[i]

        win = "Wave Slides"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, cfg.get('window', 'width'), cfg.get('window', 'height'))
        fullscreen = args.fullscreen
        if fullscreen:
            cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        cap = open_camera(args.camera) if not args.no_camera else None
        det = WaveDetector(args.sens)
        idx = 0
        status = "Wave right: next, left: back" if cap else "Keyboard control"
        last_detect = 0.0

        while True:
            if cap is not None and time.monotonic() - last_detect >= 0.045:
                last_detect = time.monotonic()
                ok, frame = cap.read()
                if ok:
                    move = det.update(frame)
                    if move:
                        n = idx + move
                        if 0 <= n < len(paths):
                            idx = n
                            status = "Next" if move > 0 else "Previous"

            try:
                _, _, ww, wh = cv2.getWindowImageRect(win)
            except cv2.error:
                break
            if ww < 100 or wh < 100:
                ww, wh = cfg.get('window', 'width'), cfg.get('window', 'height')

            slide = get(idx)
            sh, sw = slide.shape[:2]
            k = min(ww / sw, wh / sh)
            nw, nh = max(1, int(sw * k)), max(1, int(sh * k))
            resized = cv2.resize(slide, (nw, nh), interpolation=cv2.INTER_AREA)
            
            canvas = np.ones((wh, ww, 3), dtype=np.uint8) * 255
            x0, y0 = (ww - nw) // 2, (wh - nh) // 2
            canvas[y0:y0 + nh, x0:x0 + nw] = resized

            cv2.imshow(win, canvas)

            k = cv2.waitKeyEx(15)
            if k == -1:
                continue
            if k in (ord("q"), 27):
                break
            if k in KEY_NEXT and idx < len(paths) - 1:
                idx += 1
            elif k in KEY_PREV and idx > 0:
                idx -= 1
            elif k == ord("f"):
                fullscreen = not fullscreen
                cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
            elif k in (ord("+"), ord("=")):
                det.sens = min(10, det.sens + 1)
            elif k in (ord("-"), ord("_")):
                det.sens = max(1, det.sens - 1)
            elif k == ord("c"):
                if cap is not None:
                    cap.release()
                    cap = None
                else:
                    cap = open_camera(args.camera)
                    det.reset()
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def open_camera(index):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        sys.exit("Could not open the camera. Check permissions or try --camera 1.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.get('camera', 'width'))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.get('camera', 'height'))
    return cap


def main():
    ap = argparse.ArgumentParser(description="Control slides by waving your hand.")
    ap.add_argument("source", help=".pptx, .pdf, image, or folder of images")
    ap.add_argument("--sens", type=int, default=5, choices=range(1, 11), metavar="1-10", help="sensitivity (default 5)")
    ap.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--no-camera", action="store_true", help="keyboard only")
    args = ap.parse_args()

    run(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Wave Slides (Python): change slides by waving your hand.

Works with any .pptx, .pdf, or folder of images.

Modes
  viewer   (default)  Renders the deck and shows it in a window with a wave backdrop.
  --control           No rendering. Sends Right/Left arrow keypresses to whatever
                      presentation app has focus (PowerPoint, Keynote, Google Slides).

Install
  pip install opencv-python numpy pymupdf
  pip install pyautogui            (only for --control)
  LibreOffice must be installed to open .pptx in viewer mode.

Examples
  python wave_slides.py talk.pptx
  python wave_slides.py handout.pdf --fullscreen --sens 7
  python wave_slides.py ./slide_images/
  python wave_slides.py --control

Keys
  Right / n / d / Space   next          Left / p / a   previous
  f  fullscreen           c  camera on/off
  + / -  sensitivity      q / Esc  quit
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

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
    """Port of the browser version: frame differencing on a 64x48 mirrored grayscale
    image, track the horizontal centre of motion, fire on a big left/right sweep."""

    W, H = 64, 48

    def __init__(self, sens=5):
        self.sens = sens
        self.prev = None
        self.trail = []        # (time, x)
        self.last_fire = 0.0
        self.trace = []        # for the meter
        self.moving = False

    def reset(self):
        self.prev = None
        self.trail = []
        self.trace = []

    def update(self, frame, now=None):
        """Feed a BGR frame. Returns +1 (next), -1 (previous) or 0."""
        now = time.monotonic() if now is None else now
        small = cv2.resize(frame, (self.W, self.H), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.flip(gray, 1)  # mirrored so it matches what you see

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

        self.trace.append(cx if cx is not None else (self.trace[-1] if self.trace else 0.5))
        self.trace = self.trace[-60:]

        if len(self.trail) >= 4 and now - self.last_fire > 0.9:
            travel = self.trail[-1][1] - self.trail[0][1]
            need = 0.34 - self.sens * 0.015
            if abs(travel) > need:
                self.last_fire = now
                self.trail = []
                return 1 if travel > 0 else -1
        return 0

# ---------------------------------------------------------------- drawing

DEEP = (58, 42, 11)      # BGR of #0b2a3a
INK = (31, 22, 6)
SAND = (166, 217, 242)
LAYERS = [((94, 71, 18), 0.55, 1.0), ((128, 98, 26), 0.70, 1.6), ((168, 138, 43), 0.85, 2.2)]


def background(w, h):
    top = np.array(DEEP, np.float32)
    bot = np.array(INK, np.float32)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    col = top * (1 - t) + bot * t
    return np.repeat(col, w, axis=1).astype(np.uint8)


def draw_waves(img, phase, boost):
    h, w = img.shape[:2]
    band = int(h * 0.09)
    base = h - band
    xs = np.arange(0, w + 8, 8)
    for i, (color, alpha, speed) in enumerate(LAYERS):
        ys = base + band * (0.45 + i * 0.12) + np.sin(xs / 110 * speed + phase * speed + i) * band * 0.09 * (1 + boost) * 3
        pts = np.stack([xs, ys], 1).astype(np.int32)
        poly = np.vstack([pts, [[w, h], [0, h]]])
        overlay = img.copy()
        cv2.fillPoly(overlay, [poly], color)
        cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


def compose(slide, size, phase, boost, status, idx, total, cam_thumb, trace, sens):
    w, h = size
    canvas = background(w, h)
    draw_waves(canvas, phase, boost)

    if slide is not None:
        sh, sw = slide.shape[:2]
        k = min(w * 0.96 / sw, h * 0.88 / sh)
        nw, nh = max(1, int(sw * k)), max(1, int(sh * k))
        resized = cv2.resize(slide, (nw, nh), interpolation=cv2.INTER_AREA)
        x0, y0 = (w - nw) // 2, max(4, (int(h * 0.92) - nh) // 2)
        canvas[y0:y0 + nh, x0:x0 + nw] = resized

    # bottom HUD
    bar_h = 34
    cv2.rectangle(canvas, (0, h - bar_h), (w, h), INK, -1)
    cv2.putText(canvas, f"{idx + 1} / {total}", (12, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (244, 246, 234), 1, cv2.LINE_AA)
    cv2.putText(canvas, status, (110, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.5, SAND, 1, cv2.LINE_AA)
    cv2.putText(canvas, f"sens {sens}", (w - 90, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.5, SAND, 1, cv2.LINE_AA)

    # camera thumb + meter, top right
    if cam_thumb is not None:
        th, tw = cam_thumb.shape[:2]
        canvas[8:8 + th, w - tw - 8:w - 8] = cam_thumb
        if len(trace) > 1:
            pts = [(w - tw - 8 + int(i / 59 * tw), 8 + th - int(v * th)) for i, v in enumerate(trace)]
            cv2.polylines(canvas, [np.array(pts, np.int32)], False, SAND, 1, cv2.LINE_AA)
    return canvas

# ---------------------------------------------------------------- main loops

def open_camera(index):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        sys.exit("Could not open the camera. Check permissions or try --camera 1.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    return cap


KEY_NEXT = {ord("n"), ord("d"), ord(" "), 2555904, 65363, 63235, 83}
KEY_PREV = {ord("p"), ord("a"), 2424832, 65361, 63234, 81}


def run_viewer(args):
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
        cv2.resizeWindow(win, 1280, 720)
        fullscreen = args.fullscreen
        if fullscreen:
            cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        cap = open_camera(args.camera) if not args.no_camera else None
        det = WaveDetector(args.sens)
        idx, phase, boost = 0, 0.0, 0.0
        status = "Wave right: next, left: back" if cap else "Camera off"
        thumb = None
        last_detect = 0.0

        while True:
            if cap is not None and time.monotonic() - last_detect >= 0.045:
                last_detect = time.monotonic()
                ok, frame = cap.read()
                if ok:
                    thumb = cv2.flip(cv2.resize(frame, (160, 120)), 1)
                    move = det.update(frame)
                    if det.moving:
                        boost = min(1.5, boost + 0.15)
                    if move:
                        n = idx + move
                        if 0 <= n < len(paths):
                            idx = n
                            status = "Wave right: next slide" if move > 0 else "Wave left: previous slide"
                        boost = 1.5

            try:
                _, _, ww, wh = cv2.getWindowImageRect(win)
            except cv2.error:
                break
            if ww < 100 or wh < 100:
                ww, wh = 1280, 720

            frame_img = compose(get(idx), (ww, wh), phase, boost, status, idx, len(paths),
                                thumb, det.trace, det.sens)
            cv2.imshow(win, frame_img)
            phase += 0.02 + boost * 0.05
            boost *= 0.94

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
                    cap, thumb, status = None, None, "Camera off"
                else:
                    cap = open_camera(args.camera)
                    det.reset()
                    status = "Camera on"
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_control(args):
    try:
        import pyautogui
    except ImportError:
        sys.exit("--control needs pyautogui:  pip install pyautogui")
    pyautogui.FAILSAFE = True
    cap = open_camera(args.camera)
    det = WaveDetector(args.sens)
    win = "Wave control (click your slideshow to give it focus)"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    status = "Start your slideshow, then wave"
    print("Wave control running. Press q in the preview window to stop.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        move = det.update(frame)
        if move:
            pyautogui.press("right" if move > 0 else "left")
            status = "next" if move > 0 else "previous"
        view = cv2.flip(cv2.resize(frame, (320, 240)), 1)
        if len(det.trace) > 1:
            pts = [(int(i / 59 * 320), 240 - int(v * 240)) for i, v in enumerate(det.trace)]
            cv2.polylines(view, [np.array(pts, np.int32)], False, SAND, 1, cv2.LINE_AA)
        cv2.putText(view, f"{status}  sens {det.sens}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow(win, view)
        k = cv2.waitKeyEx(30)
        if k in (ord("q"), 27):
            break
        if k in (ord("+"), ord("=")):
            det.sens = min(10, det.sens + 1)
        elif k in (ord("-"), ord("_")):
            det.sens = max(1, det.sens - 1)
    cap.release()
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description="Change slides by waving your hand.")
    ap.add_argument("source", nargs="?", help=".pptx, .pdf, image, or folder of images")
    ap.add_argument("--control", action="store_true", help="send arrow keys to the focused presentation app")
    ap.add_argument("--sens", type=int, default=5, choices=range(1, 11), metavar="1-10", help="sensitivity (default 5)")
    ap.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--no-camera", action="store_true", help="viewer only, keyboard navigation")
    args = ap.parse_args()

    if args.control:
        run_control(args)
    elif args.source:
        run_viewer(args)
    else:
        ap.error("give a file to present, or use --control")


if __name__ == "__main__":
    main()

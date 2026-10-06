# Wave Slides

Control presentations by waving your hand. Built with OpenCV and Python.

Supports PowerPoint (.pptx), PDF, and image folders. Two modes: viewer (renders slides with animated backdrop) or control (sends arrow keys to PowerPoint/Keynote/Google Slides).

The "wave_slider_simple.py" is the simpler version without the webcam, waves, or any extra things. It is just the hand gestures and your file and nothing else.

## Requirements

- Python 3.7+
- Webcam
- LibreOffice (for .pptx support)


## Installation

```
git clone https://github.com/yourusername/wave-slides.git
cd wave-slides
pip install opencv-python numpy pymupdf pyyaml pyautogui
```


## Quick Start

Viewer mode:
```
python wave_slides.py presentations/talk.pptx
python wave_slides.py presentations/handout.pdf
python wave_slides.py presentations/
```

Control mode (sends arrow keys to PowerPoint/Keynote):
```
python wave_slides.py --control
```

Options:
```
--sens 1-10          Sensitivity (default 5)
--camera 0           Camera index (default 0)
--fullscreen         Start fullscreen
--no-camera          Keyboard only
```


## Configuration

config.yaml is created on first run. Edit to customize:

```
camera:
  index: 0
  width: 320
  height: 240

window:
  width: 1280
  height: 720
  fullscreen: false

wave_detection:
  sensitivity: 5
  frame_rate_ms: 45

wave_animation:
  phase_speed: 0.02
  boost_increase: 0.15
  boost_decay: 0.94

colors:
  deep: [58, 42, 11]
  ink: [31, 22, 6]
  sand: [166, 217, 242]
```


## Controls

Keyboard:
  Right, n, d, Space  - Next slide
  Left, p, a          - Previous slide
  f                   - Fullscreen
  c                   - Camera on/off
  +/-                 - Adjust sensitivity
  q, Esc              - Quit

Gesture:
  Wave right          - Next slide
  Wave left           - Previous slide


## Troubleshooting

Camera won't open:
  Try --camera 1 to use a different camera

LibreOffice not found:
  Convert .pptx to PDF first, or install LibreOffice

Gestures not triggering:
  - Check lighting (need good ambient light)
  - Adjust sensitivity with +/- keys
  - Press c to see the motion trace
  - Wave smoothly and deliberately

Control mode not working:
  Click on your presentation window to give it focus


## License

MIT

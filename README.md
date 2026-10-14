# Waveform Visualizer

A small Windows program with its own window that shows, in real time, whatever audio
your computer is currently playing: a mono waveform, a stereo (L/R) waveform and a
spectrum analyzer. Each view can be switched on or off from the toolbar. Audio is captured from the default
output device via WASAPI loopback, so no virtual audio cable is needed.

## Run

Double-click `Waveform Visualizer.bat`. The first run creates a `.venv` folder and
installs the two dependencies (PyAudioWPatch, NumPy); later runs start instantly.

Or from a terminal:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python waveform_visualizer.py
```

## Controls

| Key   | Action                       |
|-------|------------------------------|
| 1     | Toggle mono waveform view    |
| 2     | Toggle stereo L/R view       |
| 3     | Toggle spectrum analyzer     |
| Esc   | Quit                         |
| T     | Toggle always-on-top         |
| + / - | Increase / decrease gain     |

The spectrum shows 48 log-spaced bands from 30 Hz to 20 kHz over a 70 dB range, with
instant attack and a slow release. Visible views share the window height equally.

The window follows the default output device: if you switch to headphones it reconnects
within a couple of seconds.

## Tests

```
.venv\Scripts\python -m unittest discover tests
```

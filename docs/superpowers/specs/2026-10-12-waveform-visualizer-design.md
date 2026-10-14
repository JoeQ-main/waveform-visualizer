# Waveform Visualizer – design

## Goal
A small standalone Windows program with its own window that draws, in real time,
the waveform of whatever audio the computer is currently playing.

## Constraints and assumptions
- Windows 11, Python 3.14 present, no .NET SDK. Python is the implementation language.
- System audio is captured with WASAPI loopback via PyAudioWPatch (no virtual cable needed).
- The window is Tkinter (ships with Python) so no GUI dependency is required.
- "Whatever is playing" means the current default output device. If the default device
  changes (e.g. headphones plugged in) the capture follows it.

## Components
- `waveform/capture.py` – `RingBuffer` (fixed-size mono float32 buffer, thread safe) and
  `LoopbackCapture` (finds the loopback device for the default output, opens a callback
  stream, downmixes to mono into the ring buffer, can restart when the device changes).
- `waveform/app.py` – Tkinter window. Every ~16 ms it snapshots the latest N samples from
  the buffer and redraws a polyline. Shows the device name. Polls the default device every
  2 s and restarts capture if it changed or the stream died.
- `waveform_visualizer.py` – entry point.
- `Waveform Visualizer.bat` – double-click launcher that creates `.venv` and installs
  requirements on first run, then starts the app with `pythonw` (no console window).

## Controls
Esc quits. T toggles always-on-top. + / - change vertical gain.

## Testing
`RingBuffer` and the mono downmix are pure functions and get unit tests (`unittest`, no
extra dependency). Device capture and the window are verified by running the program.

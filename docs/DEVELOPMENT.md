# Developer guide

## Layout

```
src/audio_to_video/
    core.py       logic: input checks, building the ffmpeg command, running it, progress, cancel
    gui.py        Tkinter window; conversion runs in a background thread
    cli.py        command-line interface (argparse)
    __main__.py   python -m audio_to_video: window without arguments, CLI with arguments
tests/
    conftest.py           generates test files with ffmpeg (440 Hz tone, images)
    test_core.py          unit tests that do not run ffmpeg
    test_integration.py   real conversions through ffmpeg
    test_cli.py           command line
    test_gui.py           window: field logic and a full conversion through the GUI
run_app.py        entry point for PyInstaller
build_exe.py      builds a single .exe
```

## How a conversion works

`core.convert()`:

1. Checks that the files exist and their extensions are supported.
2. Finds the audio duration by parsing the `Duration:` line of `ffmpeg -i`.
3. Scales the image once into a temporary PNG (`prepare_image`):

   ```
   ffmpeg -i cover.jpg -frames:v 1
          -vf "scale='trunc(min(iw,1280)/2)*2':-2,setsar=1,format=rgb24" cover.png
   ```

   - `scale` rounds dimensions down to even numbers (required by yuv420p)
     and never upscales; `setsar=1` gives square pixels.
   - Converting to RGB removes JPEG full colour range (yuvj420p), CMYK and
     animation (the first frame is used).
   - Why a separate step: looping a small PNG is about 2× faster than
     decoding and scaling a large JPEG for every frame.

4. Builds the main command (`build_command`):

   ```
   ffmpeg -progress pipe:1 -n
          -loop 1 -framerate 1 -t <duration> -i cover.png
          -i song.flac
          -map 0:v:0 -map 1:a:0
          -c:v libx264 -preset ultrafast -tune stillimage -pix_fmt yuv420p -r 1
          -c:a aac -aac_coder fast -b:a 320k     # or -c:a copy
          -movflags +faststart out.mp4
   ```

   - `-t` is set on the **image input**, not on the output, so a copied
     audio stream (MP3/FLAC) is never cut short. The test
     `test_mp4_from_mp3_keeps_audio_bit_exact` checks this.
   - Audio: MKV and MP3 → `copy`; WAV/FLAC in MP4 → AAC (`audio_codec_args`).
     `-aac_coder fast` is twice as fast as the default at the same bitrate.
     On real music ffmpeg's built-in AAC encoder usually produces
     ~220–320 kbit/s, which is transparent quality.

5. Reads `-progress` from stdout (`out_time_us=...`) and calls
   `progress(0.0…1.0)`. stderr is read in a separate thread so the pipe
   never fills up.
6. On cancel (`cancel_event.set()`) or error, kills ffmpeg and deletes the
   partially written file.

### Where ffmpeg comes from

By default from the `imageio-ffmpeg` package (a ready-made binary for
Windows, macOS and Linux). To use your own, set the environment variable
`AUDIO_TO_VIDEO_FFMPEG=/path/to/ffmpeg`.

### Using it as a library

```python
from audio_to_video import ConversionOptions, convert

convert(
    "song.flac",
    "cover.jpg",
    "video.mkv",
    ConversionOptions(output_format="mkv", max_width=1920),
    progress=lambda f: print(f"{f:.0%}"),
)
```

## Tests

```bash
pip install -e ".[dev]"
python -m pytest -v
python -m pytest -m "not integration"   # fast tests only, no ffmpeg
```

The integration tests generate their own audio and images with ffmpeg and
check:

- MP4 from WAV, FLAC and MP3: H.264 + audio, duration matches the audio;
- MP3 → MP4 and WAV/FLAC → MKV: decoded audio is **bit-for-bit** identical to the source;
- odd image sizes, spaces and non-ASCII characters in paths;
- large images are downscaled, small ones are left as is;
- refusing to overwrite without the flag, overwriting with it;
- broken audio/image files, cancelling, output path equal to an input.

The GUI tests create a Tkinter window (on Linux CI through `xvfb-run`) and
run a full conversion with the dialogs stubbed out.

CI (`.github/workflows/ci.yml`) runs the tests on Windows, Linux and macOS
(Python 3.10 and 3.13) and builds `AudioToVideo.exe`. Pushing a `v*` tag
attaches the .exe to a GitHub Release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Building the .exe locally

```bash
pip install -r requirements-dev.txt
python build_exe.py
```

Result: `dist/AudioToVideo.exe`, a single file of about 50 MB with Python
and ffmpeg built in.

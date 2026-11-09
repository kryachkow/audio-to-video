# User guide

## What the program does

It takes an audio file and an image and builds a video from them:

- the video is as long as the audio;
- your image is on screen for the whole video;
- the audio plays in full with no noticeable loss of quality.

## Supported formats

**Audio:** `.mp3`, `.wav`, `.flac`

**Images:** `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`, `.gif`, `.tif`, `.tiff`.
Any resolution works, including odd sizes such as 333×211: dimensions are
adjusted automatically to what the video codec requires. PNG transparency is
not kept; transparent areas become black.

**Output video:**

| Format | Video | Audio | Plays in |
|---|---|---|---|
| MP4 | H.264 | MP3 copied; WAV/FLAC → AAC up to 320 kbit/s | Everywhere: Windows, phones, browsers, YouTube, Telegram, Instagram |
| MKV | H.264 | Always an exact copy of the original | VLC, mpv, YouTube; the built-in Windows 10/11 player |

## Step by step

1. Run `AudioToVideo.exe` (or `audio-to-video-gui`).
2. **Audio → Browse…**: choose a track. The *Save as* field fills itself in:
   the video goes next to the track under the same name.
3. **Image → Browse…**: choose the cover.
4. Optionally change **Format** and **Video width**.
5. Click **Create video**. Progress is shown at the bottom.
6. When it's done, the program offers to open the folder with the video.

## Why it's fast

The picture never changes, so the video is written at **1 frame per second**,
encoded with the `ultrafast` preset and `stillimage` tuning, and large images
are scaled down once to the chosen width before encoding. A 4-minute track
usually takes a few seconds. Most of the time goes into re-encoding the audio
to AAC (only for MP4 made from WAV/FLAC).

The default width is 1280 px (720p). For maximum speed choose 854 px; for the
sharpest picture choose *Original image size*.

## FAQ

**Will the audio get worse?**
MP3 audio is copied as is. For WAV/FLAC in MP4, AAC at up to 320 kbit/s is
used, which is indistinguishable from the original by ear. If you need a
mathematically exact copy, choose MKV.

**Can I upload MKV to YouTube?**
Yes, YouTube accepts MKV.

**A file with that name already exists.**
The program asks whether to overwrite it. On the command line use `-y`.

**Error "Could not determine the audio duration".**
The file is damaged or is not actually audio despite its extension. Check
that the track plays in a regular player.

**Windows SmartScreen warns about the .exe.**
The file is not digitally signed. Click *More info* → *Run anyway*, or build
the .exe yourself (see [DEVELOPMENT.md](DEVELOPMENT.md)).

**The video is slightly longer than the track.**
At 1 frame per second the last frame can stay on screen for up to a second
after the audio ends. The audio itself is never cut.

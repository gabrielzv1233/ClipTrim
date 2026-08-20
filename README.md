<div align="center">

# ClipTrim

</div>

  ClipTrim is a small, no-project video trimmer for Windows. Open a video, choose an In and Out frame, and export a broadly compatible `.mp4` without creating a project, media library, or sidecar session file.  
  The UI is built around a video preview and a precise, zoomable timeline. Common actions use single-key controls; modifier keys expose finer navigation, snapping, shuttle playback, and volume control.  

<div align="center">
  <a href="https://ko-fi.com/gabrielzv1233">
    <img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Donate on Ko-fi" width="350">
  </a>
</div>

---

### Basic controls

> See [advanced controls](#advanced-controls) for bind modifiers

| Control | Action |
| --- | --- |
| `Space` | Play/pause. |
| `K` | Play/pause when tapped; also used for slow shuttle playback. |
| `I` / `[` | Set and immediately save In. |
| `O` / `]` | Set and immediately save Out. |
| `R` | Confirm and reload the current clip from a clean session state. |
| `Left` / `J` | Back one frame. |
| `Right` / `L` | Forward one frame. |
| `1` - `9` | Jump evenly across the full source: `1` is the start, `5` the middle, and `9` the final frame. |
| `Shift+1` - `Shift+9` | Jump to the equivalent position inside the selected In/Out range. |
| `Up` / `Down` | Volume ±5%. |
| `M` | Toggle mute. |
| `Enter` / `E` | Export. |
| `Esc` | Return to launcher. |
| `H` | Toggle the editor HUD. |
| `0` | Reset preview zoom and pan. |
| `F11` / `Alt+Enter` | Toggle borderless fullscreen. |

## Requirements

### Packaged app

ClipTrim is intended for 64-bit Windows.

- Minimum editor area: **800 × 520 px**
- Launcher area: about **460 × 270 px**
- The ClipTrim folder must be writable.
- Keep the complete distributed folder together. `ClipTrim.exe` depends on files in its subfolders.
- Leave enough free space for `.tmp` working data and exports.

The packaged build already includes Python, PySide6/Qt, FFmpeg, FFprobe, the app resources, and Nuitka runtime files. You do **not** need to install any of those separately, and Premiere Pro is not required.

You only need Windows, a supported video, write access to the app/export folders, and enough free disk space. Persistent In/Out state additionally requires NTFS; editing and export still work without it.

Preview playback uses Windows Media Foundation through Qt. FFmpeg is used separately for probing, scrub previews, and export.

## Getting started

1. Run `ClipTrim.exe`.
2. Drop a video onto the launcher, or click the drop area to choose one.
3. Move the playback cursor and press `I` or `[` to set In.
4. Move it again and press `O` or `]` to set Out.
5. Press `Enter` or `E` to export.

You can also open a video directly and skip the launcher:

```bat
ClipTrim.exe "C:\Users\Default\Downloads\video.mp4"
```

Cancelling the initial file chooser or pressing `Esc` in the launcher exits ClipTrim. `Esc` in the editor returns to the launcher.

### Timeline and preview

On the timeline, click or drag to scrub, drag the In/Out handles to trim, scroll to pan, and use `Alt+wheel` or a precision-touchpad pinch to zoom around the pointer. The playback cursor can move anywhere in the full source, including before In or after Out. Starting playback from outside the selected range still begins at In and stops at Out. Drag the timeline's top edge to resize it. Zooming in reveals progressively finer ruler markers down to individual frames.

While dragging an In or Out handle, the preview temporarily shows that handle's frame. Releasing the handle saves the new trim point and returns the preview to the playback cursor, clamped inside the selected range if needed.

In the video preview, left-drag or two-finger scroll to pan. Use `Alt+wheel` or touchpad pinch to zoom. Double-click or press `0` to reset the view.

## Advanced controls

`J` mirrors `Left`; `L` mirrors `Right`. A **large** or **small** marker means the current major or minor timeline ruler division, so jump distances change with timeline zoom.

### Navigation

| Modifier | Backward | Forward |
| --- | --- | --- |
| None | One frame | One frame |
| `Shift` | Previous large marker | Next large marker |
| `Ctrl` | Previous small marker | Next small marker |

### Shuttle playback

Hold a direction key instead of tapping it:

| Chord | Speed |
| --- | --- |
| `K` + direction | 0.25× |
| `Shift+K` + direction | 0.10× |
| `Ctrl+K` + direction | 0.50× |
| `Alt` + direction | 1.50× |
| `Alt+Shift` + direction | 2.00× |
| `Alt+Ctrl` + direction | 1.25× |

Use `Left`/`J` for reverse and `Right`/`L` for forward. Releasing the direction key stops shuttle playback.

### Volume precision

| Control | Change |
| --- | --- |
| `Up` / `Down` | ±5% |
| `Shift+Up` / `Shift+Down` | ±1% |
| `Ctrl+Up` / `Ctrl+Down` | ±10% |

### Trim-handle snapping

| Modifier | Snap behavior |
| --- | --- |
| None | Nearest frame |
| `Shift` | Nearest large ruler marker |
| `Ctrl` | Nearest small ruler marker |

## How it works

### Saved trim state

ClipTrim does not create project/session files. When In or Out changes through `I`, `O`, or a released trim handle, ClipTrim immediately stores the relevant **frame numbers** in an NTFS alternate data stream attached to the source video:

```text
<video filename>:ClipTrim.TrimState
```

The source video/audio streams are not rewritten.

When that video is opened again, ClipTrim probes it first, validates the saved frame values, and restores them. Missing or invalid values fall back safely. If In is the first frame or Out is the final frame, that default value is omitted; if both are defaults, the metadata stream is removed.

Because this uses NTFS alternate data streams, saved trim state can be lost when a clip passes through ZIP archives, cloud services, non-NTFS drives, or tools that do not preserve them.

### What `R` does

`R` is a confirmed **fresh reload of the current clip for this session**. It:

- stops playback and reloads/probes the source;
- ignores saved trim metadata for this reload;
- resets In/Out to the full clip;
- discards and rebuilds the scrub cache;
- resets timeline zoom/pan;
- resets preview zoom/pan;
- preserves volume and mute state; and
- pauses at the new In point.

`R` does **not** erase the saved NTFS trim state by itself. If you reload and close the app without setting a new In or Out, the old saved trim can return on the next fresh launch. Changing In or Out after reloading immediately replaces the saved state. Reload is disabled during export.

### Scrubbing

When a video opens, FFmpeg builds lower-quality JPEG preview frames in the background. Scrubbing uses those cached previews instead of repeatedly decoding full-resolution frames. Recently used previews are also kept in a bounded RAM cache.

Normal playback and the final frame shown after scrubbing still use the original media source.

### Playback at Out

When playback reaches Out, ClipTrim stops on the last visible video frame. Pressing play again starts from In. The timeline follows the actual video-frame span rather than a longer audio/container tail, avoiding the black flash that can occur when audio outlasts video.

### Export

`Enter` opens a Save dialog in `Downloads` with a default name such as `clipped_example.mp4`. ClipTrim will not export over its source file.

Existing 8-bit 4:2:0 H.264 video and AAC audio are copied when safe, avoiding quality loss. Other sources are converted to a high-quality H.264 High-profile video stream at CRF 10 with AAC-LC audio at 320 kb/s. The MP4/H.264/AAC combination is designed for native Windows playback and broad editor compatibility, including Premiere Pro and DaVinci Resolve. Export intermediates live under `.tmp` and are only moved/copied to the chosen destination after FFmpeg succeeds.

### Temporary data

ClipTrim keeps its disposable data in `.tmp` beside the app or development script rather than the system `%TEMP%` directory. This includes scrub previews, temporary FFmpeg files, and export intermediates.

Stale data from a crashed run is cleaned on the next startup. Clean shutdown removes the current run's temporary directory.

Packaged layout:

```text
ClipTrim/
├─ ClipTrim.exe
├─ icon.ico
├─ runtime/
├─ bin/
├─ config/
├─ logs/
├─ assets/
└─ .tmp/
```

`runtime/` contains packaged dependencies, `bin/` contains FFmpeg/FFprobe, and `.tmp/` contains disposable app data.

### Configuration

Configuration is currently code-based and split into two groups:

- `CONFIG` for behavior, such as touchpad pinch sensitivity and timeline/player zoom multipliers.
- `THEME` for colors and visual dimensions such as handle width, marker styling, playhead styling, trim backgrounds, and the volume line.

The planned configuration system will move these user-facing values into real files under `config/`, allowing changes without recompiling. That migration is not implemented yet, so files placed there currently have no effect.

### Other behavior and limitations

- `Ctrl+C` in an attached console requests a clean shutdown.
- Operational/crash diagnostics currently print to the attached console. `logs/` is reserved for later persistent logging such as `latest.log`.
- Constant-frame-rate media is the most predictable for exact frame stepping; variable-frame-rate media can be less exact.
- Reverse shuttle is cache-backed stepping, while forward shuttle can use native playback-rate support.
- Windows or Qt may axis-lock some precision-touchpad movement before ClipTrim receives it.

--- 

## Developer guide

### Development requirements

ClipTrim was originally developed and tested with:

- Windows 11
- Python **3.14.7** (`.python-version` pins the tested patch release)
- `uv` (bootstrapped by `setup.bat` if it is missing)
- PySide6 **6.11.2**
- Nuitka **4.1.3**
- FFmpeg and FFprobe on `PATH` (`setup.bat` installs Gyan.FFmpeg through WinGet when needed)

The project declares Python `>=3.14`. Runtime and development dependencies are defined separately in `pyproject.toml` and locked in `uv.lock`:

```text
pyside6>=6.11.2

[development]
nuitka[all]>=4.1.3
```

FFmpeg and FFprobe are external executables, not pip packages.

### Run from source

Normal Windows setup:

```bat
setup.bat
run.bat
```

> `setup.bat` installs or locates `uv`, installs a uv-managed Python 3.14 runtime, creates `.venv`, synchronizes every locked dependency, verifies PySide6 and Nuitka from that environment, and installs FFmpeg/FFprobe through WinGet when they are missing. An internet connection is required for anything not already installed or cached. WinGet is required only when FFmpeg must be installed automatically.

Or with `uv` directly:

```bat
uv sync
uv run python cliptrim.py
```
> `setup.bat` and `build_exe.bat` use `uv` and do not fall back to unmanaged project-wide pip installs. Nuitka is still installed from its official PyPI package into `.venv` through `uv sync`, then invoked with `.venv\Scripts\python.exe -m nuitka`.

Development runtime folders live beside `cliptrim.py`:

```text
project/
├─ cliptrim.py
├─ config/
├─ logs/
├─ assets/
└─ .tmp/
```

### Build

From the project root:

```bat
buildtools\build_exe.bat
```

The build script prepares dependencies, generates `icon.ico` from `icon.svg`, builds the Nuitka standalone app, bundles the validated FFmpeg/FFprobe pair and required license material, and creates the final distributable at `build\ClipTrim`.

The packaged root includes `LICENSE` and `THIRD_PARTY_NOTICES.md`; copied license and attribution material plus the exact FFmpeg build inventory are under `licenses/`. The build stops if a pinned runtime/tool version, binary hash, plugin allowlist, or legal file no longer matches the notice inventory.

The bundled Gyan FFmpeg executables are static GPLv3 builds. Before publishing a binary release, follow the corresponding-source action documented in `THIRD_PARTY_NOTICES.md`; the vendor README and upstream links alone do not complete that distribution obligation.

The final folder keeps `ClipTrim.exe` in the root while dependencies stay in subfolders. With Nuitka 4.1.3, which does not expose `--put-runtime-files-in`, the build uses a small native root launcher and places the compiled application under `runtime/` instead.

### Project files

| Path | Purpose |
| --- | --- |
| `cliptrim.py` | Main app, UI, playback, trim state, caching, probing, and export logic. |
| `icon.af` | Editable Affinity Designer source for the app icon. |
| `icon.svg` | Canonical vector icon used by the build. |
| `pyproject.toml` | Project metadata plus runtime and development dependency groups. |
| `uv.lock` | Locked Python dependencies. |
| `.python-version` | Pinned development Python version. |
| `THIRD_PARTY_NOTICES.md` | Runtime/build dependency inventory, attribution, and source index. |
| `licenses/` | License texts committed for redistribution by the build. |
| `buildtools/update_qt_notices.ps1` | Regenerates the pinned offline Qt component-attribution bundle. |
| `buildtools/update_python_licenses.ps1` | Refreshes exact standalone-Python and platform runtime license files. |
| `setup.bat` | Creates/checks the development environment. |
| `run.bat` | Runs ClipTrim from source. |
| `buildtools/build_exe.bat` | Main packaging script. |
| `buildtools/build_icon.py` | Generates the multi-size Windows icon. |
| `buildtools/cliptrim_launcher.c` | Native root launcher used by the Nuitka fallback layout. |
| `buildtools/cliptrim_launcher.rc` | Windows resources for that launcher. |
| `config/` | Reserved for future external config files. |
| `logs/` | Reserved for future persistent logs. |
| `assets/` | External app resources. |
| `.tmp/` | Disposable runtime data. |
| `build/ClipTrim/` | Generated distributable. |

Build products, generated icons, virtual environments, and runtime working data are ignored by Git. Keep both `icon.af` and `icon.svg`: the first is the editable design source; the second is the reproducible build source.

---

ClipTrim is free and open-source software licensed under the  
**GNU General Public License v3.0 only**.

Copyright © 2026 **gabrielzv1233**

See [`LICENSE`](LICENSE) for the full license terms.

</div>

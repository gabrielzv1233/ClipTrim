# ClipTrim third-party notices

ClipTrim 0.6.0 is distributed under GNU GPL version 3. The complete license is
in `legal/LICENSE`, and the corresponding ClipTrim source is available at
<https://github.com/gabrielzv1233/ClipTrim>.

The Windows build also distributes the components below. Their applicable
license texts and attribution notices are in `legal/licenses/`.

| Component | Version | License | Source |
| --- | --- | --- | --- |
| CPython (Astral standalone build) | 3.14.7, build 20260807 | PSF-2.0 and incorporated-component terms | [CPython](https://github.com/python/cpython/tree/v3.14.7), [Astral release](https://github.com/astral-sh/python-build-standalone/releases/tag/20260807) |
| PySide6, Shiboken6, and Qt | 6.11.2 | GPL-3.0-only option and incorporated-component terms | [PySide6 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/), [Qt source](https://download.qt.io/official_releases/qt/6.11/6.11.2/) |
| OpenSSL | 3.5.7 | Apache-2.0 | [Source](https://github.com/openssl/openssl/tree/openssl-3.5.7) |
| libffi | ABI 8 | MIT | [Source](https://github.com/libffi/libffi) |
| libmpdec | 4.0.0 | BSD-2-Clause | [Source](https://www.bytereef.org/mpdecimal/) |
| Unicode Character Database | 16.0.0 | Unicode License v3 | [Source](https://www.unicode.org/versions/Unicode16.0.0/) |
| Nuitka runtime support | 4.1.3 | AGPL-3.0 with the Nuitka Runtime Library Exception 1.0 | [Source](https://github.com/Nuitka/Nuitka/tree/4.1.3) |
| mingw-w64 startup/runtime code | bundled with the Zig toolchain | Component-specific permissive terms | [Source](https://www.mingw-w64.org/) |
| FFmpeg and FFprobe (Gyan full build) | 9.0 | GPL-3.0 | [FFmpeg source commit](https://github.com/FFmpeg/FFmpeg/commit/d32b387f2b), [Gyan builds](https://www.gyan.dev/ffmpeg/builds/) |

Only the Qt modules and plugins present in the packaged application are covered
by `legal/licenses/Qt-6.11.2-THIRD-PARTY-NOTICES.txt`. The build excludes Qt PDF,
Qt SVG, Qt's FFmpeg backend, and unused plugins.

Nuitka itself is only a build tool. The executable contains its runtime support,
so the packaged notices include Nuitka's base license, runtime exception, and
copyright notice.

## FFmpeg source requirement

The packaged `ffmpeg.exe` and `ffprobe.exe` are unmodified copies of Gyan's
static GPLv3 full build. Its distributor-supplied GPL text is included in
`legal/licenses/FFmpeg-9.0-LICENSE.txt`.

Before publishing those binaries, the release must also provide GPL-compliant
access to the exact corresponding source for FFmpeg and its statically linked
libraries. The links above do not replace that requirement.
See <https://ffmpeg.org/legal.html>.

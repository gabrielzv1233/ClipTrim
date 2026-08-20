# ClipTrim third-party notices

This document describes third-party software used to build or distributed with
ClipTrim 0.6.0. It is an attribution and source index, not a replacement for the
applicable license terms. The corresponding license files are shipped beside
this document in `LICENSE` and `licenses/`.

The inventory is for the locked Windows x86-64 build produced by
`buildtools/build_exe.bat`. If a dependency or toolchain version changes, this
file and the copied license material must be reviewed before distribution.

## Distributed runtime components

| Component | Version | Distributed location | License used for this distribution | Project and source |
| --- | --- | --- | --- | --- |
| CPython, Astral standalone build | 3.14.7, build 20260807 | `runtime/python3.dll`, `runtime/python314.dll`, standard-library extension modules | Python Software Foundation License 2.0 and incorporated-component terms | [Python](https://www.python.org/), [CPython 3.14.7 source](https://github.com/python/cpython/tree/v3.14.7), [exact Astral release](https://github.com/astral-sh/python-build-standalone/releases/tag/20260807) |
| PySide6, PySide6 Essentials, PySide6 Addons, and Shiboken6 | 6.11.2 | `runtime/PySide6/`, `runtime/shiboken6/`, and related DLLs | GPL-3.0-only option from `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | [Qt for Python](https://doc.qt.io/qtforpython-6/), [6.11.2 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/) |
| Qt Core, GUI, Widgets, Network, Multimedia, and Multimedia Widgets | 6.11.2 | `runtime/qt6*.dll` and selected `runtime/PySide6/qt-plugins/` files | GPL-3.0-only option from Qt's open-source licensing alternatives | [Qt licensing](https://doc.qt.io/qt-6/licensing.html), [Qt 6.11 source](https://download.qt.io/official_releases/qt/6.11/6.11.2/) |
| OpenSSL | 3.5.7 | `runtime/libcrypto-3-x64.dll`, `runtime/libssl-3-x64.dll` | Apache-2.0 | [OpenSSL 3.5.7 source](https://github.com/openssl/openssl/tree/openssl-3.5.7) |
| libffi | ABI 8 | `runtime/libffi-8.dll` | MIT | [libffi](https://github.com/libffi/libffi) |
| libmpdec | 4.0.0 | Statically linked into `runtime/_decimal.pyd` | BSD-2-Clause | [mpdecimal](https://www.bytereef.org/mpdecimal/) |
| XZ Utils/liblzma | 5.8.3 | Statically linked into `runtime/_lzma.pyd` | 0BSD | [XZ Utils](https://tukaani.org/xz/) |
| Unicode Character Database | 16.0.0 | Data incorporated into `runtime/unicodedata.pyd` and CPython | Unicode License v3 | [Unicode 16.0.0](https://www.unicode.org/versions/Unicode16.0.0/) |
| Nuitka runtime support | 4.1.3 | Code linked into `runtime/ClipTrim.runtime.exe` | AGPL-3.0 with the Nuitka Runtime Library Exception 1.0 | [Nuitka 4.1.3](https://github.com/Nuitka/Nuitka/tree/4.1.3) |
| mingw-w64 startup/runtime code | Zig 0.16.0 toolchain copy | Code linked into root `ClipTrim.exe` and Nuitka's `runtime/ClipTrim.runtime.exe` | Zope Public License 2.1, public-domain declarations, and the component-specific terms in `mingw-w64-COPYING.txt` | [mingw-w64](https://www.mingw-w64.org/), [Zig 0.16.0](https://github.com/ziglang/zig/tree/0.16.0) |
| Microsoft Visual C++ Runtime | 14.44.35211 | `runtime/msvcp140*.dll`, `runtime/vcruntime140*.dll` | Microsoft Visual C++ Redistributable terms | [Microsoft redistributable documentation](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) |
| FFmpeg and FFprobe, Gyan full build | `9.0-full_build-www.gyan.dev` | `bin/ffmpeg.exe`, `bin/ffprobe.exe` | GPL-3.0 because the build enables GPL and version-3 components | [FFmpeg](https://ffmpeg.org/), [exact FFmpeg source commit `d32b387f2b`](https://github.com/FFmpeg/FFmpeg/commit/d32b387f2b), [Gyan builds](https://www.gyan.dev/ffmpeg/builds/) |

ClipTrim itself and the GPL-selected Qt/PySide components are distributed under
GNU GPL version 3. The complete GPLv3 text is the top-level `LICENSE` file. The
ClipTrim corresponding source, including its build scripts, is available from
<https://github.com/gabrielzv1233/ClipTrim>. A distributor must also satisfy the
GPLv3 source-distribution requirements for the exact Qt/PySide binaries it
ships; the table above identifies the matching 6.11.2 source release.

### CPython incorporated software

The runtime is the Astral `python-build-standalone` 20260807 Windows x86-64
build of CPython 3.14.7, release commit
[`00c8a06113f11220667c3bcf5fab1672ff9e78ef`](https://github.com/astral-sh/python-build-standalone/commit/00c8a06113f11220667c3bcf5fab1672ff9e78ef).
The build script rejects another `BUILD` identifier. CPython's binary and
extension modules contain separately licensed software: the copied CPython
license includes bzip2 and Zstandard terms; exact Astral 20260807 license files
for libffi, liblzma, libmpdec, and OpenSSL are also bundled. Unicode's official
license covers the Unicode 16.0.0 data used by `unicodedata`.

The standalone runtime also contains `libffi-8.dll`. libffi is copyright its
authors and contributors and is distributed under the MIT license. The binary
does not expose a sufficiently reliable source-version identifier; ABI 8 is
reported here rather than asserting an unverified release number. Astral's
unmodified build-system license is included for build provenance; its MPL-2.0
builder code is not copied into the application runtime.

### Qt incorporated software

The selected Qt modules contain third-party code under permissive and weak
copyleft terms. The applicable Qt attribution families include:

- Apache Tika MIME definitions, BLAKE2, Double Conversion, PCRE2, TinyCBOR,
  Unicode UCD/CLDR data, and zlib in Qt Core;
- Adobe glyph data, FreeType and its incorporated code, HarfBuzz,
  libjpeg-turbo, libpng, MD4C, graphics API headers/allocators, and several
  small rendering algorithms in Qt GUI and the JPEG image plugin;
- DR Libs, Signalsmith Stretch, and TLSF in Qt Multimedia; and
- Mozilla's Public Suffix List data and libpsl code in Qt Network.

Qt's authoritative 6.11.2 copyright statements and full component-specific
terms are reproduced offline in
`licenses/Qt-6.11.2-THIRD-PARTY-NOTICES.txt`; its source index is the
[Qt third-party attribution inventory](https://doc.qt.io/qt-6/licenses-used-in-qt.html).
The bundled file is a conservative module-level superset and may mention
platform-specific code absent from this Windows wheel. Only plugins required
by ClipTrim are packaged. In particular, the build
excludes Qt PDF/PDFium, Qt's FFmpeg multimedia backend, Qt SVG, and unused image
and platform plugins; those components are therefore not part of this runtime
inventory.

Qt and PySide remain dynamically replaceable DLLs in `runtime/`. ClipTrim does
not prohibit reverse engineering for the purpose of debugging modifications to
those libraries.

### OpenSSL

OpenSSL is copyright the OpenSSL Project Authors. It is licensed under the
Apache License 2.0; the exact license copied from Astral build 20260807 is in
`licenses/OpenSSL-3-LICENSE.txt`. No use of the OpenSSL names or trademarks to
endorse ClipTrim is implied.

### Nuitka runtime exception

Nuitka is used as a compiler. Its compiler is not redistributed. The generated
executable contains Nuitka runtime support governed by AGPL-3.0 with the Nuitka
Runtime Library Exception 1.0. The build copies Nuitka's unmodified
`LICENSE.txt`, `LICENSE-RUNTIME.txt`, and `NOTICE.txt` into `licenses/`.

### FFmpeg full build

The two command-line executables are unmodified copies from a Gyan static full
build. That build enables GPL and version-3 code and statically incorporates
many codec and utility libraries, including x264, x265, libvpx, libaom, dav1d,
libass, FreeType, HarfBuzz, libjpeg-xl, libwebp, libvorbis, libopus, and others.
The exact configuration, component versions, and source commit supplied by the
distributor are preserved verbatim in
`licenses/FFmpeg-9.0-README.txt`; its GPLv3 text is in
`licenses/FFmpeg-9.0-LICENSE.txt`.

The build accepts only these reviewed binaries:

- `ffmpeg.exe` SHA-256:
  `05F4251BCE9293C2AB492CB17CA7724A0FFD0D06C881BA2EE83B82A89C2FC740`
- `ffprobe.exe` SHA-256:
  `51E0780CD881F83749B029ED716CBB841C2EAC6289F418050F2F2961B158896B`

Distributors must make the exact corresponding FFmpeg source, including the
sources for statically linked libraries and any build changes, available as
required by their chosen GPLv3 distribution method. FFmpeg's own
[legal and compliance guidance](https://ffmpeg.org/legal.html) explains that a
source link or license notice alone is not a substitute for corresponding
source compliance. The Gyan sidecar files do not reproduce every statically
linked library's copyright/license notice. Do not publish the packaged FFmpeg
binaries until the chosen distribution method also supplies the exact complete
corresponding source and any additional component notices required by that
source bundle.

## Build-only tools and dependencies

The following packages are present in the locked development environment but
are not imported into or copied as Python packages in the distributable. They
are listed to document the reproducible build toolchain.

| Component | Locked/detected version | License | Project |
| --- | --- | --- | --- |
| Nuitka compiler | 4.1.3 | AGPL-3.0 | [Nuitka](https://github.com/Nuitka/Nuitka) |
| ImageIO | 2.37.4 | BSD-2-Clause | [ImageIO](https://github.com/imageio/imageio) |
| NumPy | 2.5.2 | BSD-3-Clause and bundled component licenses | [NumPy](https://github.com/numpy/numpy) |
| Pillow | 12.3.0 | MIT-CMU and bundled component licenses | [Pillow](https://github.com/python-pillow/Pillow) |
| setuptools | 84.0.0 | MIT and vendored component licenses | [setuptools](https://github.com/pypa/setuptools) |
| toml | 0.10.2 | MIT | [toml](https://github.com/uiri/toml) |
| uv | 0.12.3 | Apache-2.0 OR MIT | [uv](https://github.com/astral-sh/uv) |
| SCons, vendored by Nuitka | 4.10.1 | MIT | [SCons](https://github.com/SCons/scons) |
| Zig compiler | 0.16.0 | MIT; bundled toolchain components have additional terms | [Zig](https://github.com/ziglang/zig) |
| Astral python-build-standalone builder | 20260807 | MPL-2.0; its output has component-specific terms listed above | [release](https://github.com/astral-sh/python-build-standalone/releases/tag/20260807) |

## Project assets

`icon.af` and `icon.svg` are project assets, not third-party packages. The SVG
is self-contained and does not reference external fonts or raster resources.
The editable Affinity source should only be redistributed if all linked design
resources are owned by or licensed to the ClipTrim project.

## License-file index in the packaged app

| File | Contents |
| --- | --- |
| `LICENSE` | ClipTrim and selected Qt/PySide GPL-3.0 license text |
| `THIRD_PARTY_NOTICES.md` | This inventory and attribution index |
| `licenses/Apache-2.0.txt` | General Apache License 2.0 text |
| `licenses/Astral-python-build-standalone-LICENSE.txt` | Astral builder MPL-2.0 terms (build provenance) |
| `licenses/CPython-3.14.7-LICENSE.txt` | CPython and incorporated-software terms |
| `licenses/libffi-LICENSE.txt` | Exact Astral 20260807 libffi copyright and MIT terms |
| `licenses/liblzma-LICENSE.txt` | Exact Astral 20260807 XZ Utils/liblzma terms |
| `licenses/libmpdec-LICENSE.txt` | Exact Astral 20260807 libmpdec BSD-2-Clause terms |
| `licenses/Microsoft-Visual-C-Runtime-2015-2022-License.docx` | Microsoft Visual C++ Runtime license terms |
| `licenses/OpenSSL-3-LICENSE.txt` | Exact Astral 20260807 OpenSSL 3 license |
| `licenses/Qt-6.11.2-THIRD-PARTY-NOTICES.txt` | Offline Qt module/component copyrights and license statements |
| `licenses/Unicode-3.0-LICENSE.txt` | Unicode License v3 |
| `licenses/Nuitka-4.1.3-LICENSE.txt` | Nuitka compiler/runtime base license |
| `licenses/Nuitka-4.1.3-LICENSE-RUNTIME.txt` | Nuitka Runtime Library Exception 1.0 |
| `licenses/Nuitka-4.1.3-NOTICE.txt` | Nuitka copyright notice |
| `licenses/FFmpeg-9.0-LICENSE.txt` | Gyan full-build GPLv3 license text |
| `licenses/FFmpeg-9.0-README.txt` | Exact Gyan build configuration, dependencies, and source commit |
| `licenses/Zig-0.16.0-LICENSE.txt` | Zig compiler license (build provenance) |
| `licenses/mingw-w64-COPYING.txt` | License terms for launcher startup/runtime code |

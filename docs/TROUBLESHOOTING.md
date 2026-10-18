# Troubleshooting

## Windows says "Windows protected your PC"

- **Why:** the installer and EXE are not code-signed, so SmartScreen warns about them.
- **What to do:**
  1. Check the file's SHA-256 against `SHA256SUMS.txt` from the same release, using `Get-FileHash .\PrintScaleStudio_Setup_v1.0.6.exe`.
  2. If it matches, choose **More info › Run anyway**.

## The AI modes run on the CPU, or are slow

- **What runs where:**
  - The AI modes use DirectML on any DirectX 12 GPU.
  - The status bar and the export summary show the device that actually ran the job.
  - If the GPU is unavailable, or fails while running, the job is retried with smaller tiles and then on the CPU.
  - Preserve Artwork always uses the CPU and is fast.
- **Check the GPU setting:** open **Settings › Processing › Hardware** and confirm that **Use GPU (DirectML) when available** is on.
- **Check the graphics driver:** update it; DirectML needs a DirectX 12 driver.
- **Virtual machines and remote sessions** often have no usable DirectX 12 adapter. There, the CPU is expected.
- **CPU time:** on the CPU, an AI export at 4200 × 4800 px can take several minutes. Use **Preview Crop** to judge quality first.

## "Not enough memory" or the export is refused

Before processing starts, PrintScale Studio estimates the working memory a job needs. It refuses the job if that
is more than the free RAM, or if the canvas is larger than 30,000 px on either side.

**What to try:**
- close other large applications;
- choose a smaller canvas or a lower DPI;
- use Preserve Artwork, which needs less memory than the AI modes.

## The print size or DPI is not what I expected

DPI is only metadata: it says how large the pixels should print. It adds no detail.
- **Print size mode:** the pixel count follows from inches × DPI, so 14 × 16 in at 300 DPI is 4200 × 4800 px.
- **Pixel canvas mode:** the pixels are fixed, and the DPI changes the print size: 4200 × 4800 px at 500 DPI prints at 8.4 × 9.6 in.
- **Viewers disagree:** some programs read JFIF density and others read EXIF. PrintScale Studio writes both consistently, plus a PNG `pHYs` chunk.
- **Changing only the stored DPI** of an existing file: use **DPI metadata only**.

## Edges look dark or haloed after an AI export

- **Where the halo comes from:** semi-transparent edges may already contain fringe colours in the source, and AI models can make them more visible.
- **How to check:** compare the result on black and white viewer backgrounds.
- **For logos and lettering:** **Preserve Artwork** is the conservative choice.

## The Start menu or taskbar still shows an old icon after an upgrade

- **Why:** Windows caches icons. The installer refreshes its own shortcuts after installing.
- **If an old icon remains:**
  1. Unpin and re-pin the app.
  2. If needed, delete the **PrintScale Studio** shortcut and run the installer again to recreate it.
- **Leave the global cache alone:** you do not need to clear Windows' global icon cache.
- **Old taskbar pins:** the taskbar groups windows by an ID that includes the version number, so a pin made with an older version may group separately. Re-pin after upgrading.

## Settings or a damaged configuration

- **Where settings are stored:** `%APPDATA%\PrintScaleStudio\config.json`. Invalid values are reset to defaults one by one.
- **To start fresh:** close the app and rename that file.

## Known limitations

- **Windows 10:** expected to work, but not tested.
- **Display scaling:** tested on a physical display at 150% scaling. Other scaling levels were checked only with simulated scaling.
- **Drag and drop from File Explorer:** drop handling is implemented and covered by tests, but a manual drag from Explorer has not been verified for this release.
- **Format support:** the app is Windows-only; macOS and Linux builds are not provided. Animated and multi-frame images are not supported.

## Still stuck?

Open an issue using the bug report form: https://github.com/baki2222/printscale-studio/issues/new/choose

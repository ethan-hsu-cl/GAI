"""Shrink the videos embedded in a generated report .pptx so PowerPoint can open it.

Kling 3.0 clips come back at ~19 Mbps, so a 200-slide deck passes PowerPoint's
2 GB limit (and past 2 GB Python's zipfile writes ZIP64 records PowerPoint can't
read). This re-encodes every ppt/media/*.mp4 to H.264 CRF 22 in place, keeping
the part names so no slide relationship changes, and writes a new zip.

Usage: python shrink_report_videos.py "Report/[0924] Kling 3.0 ....pptx" [...]
Writes the result over the original after keeping a .bak copy next to it.
"""
import shutil
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _reencode(src: Path, dst: Path) -> Path:
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-i', str(src),
         '-c:v', 'libx264', '-crf', '22', '-preset', 'medium', '-pix_fmt', 'yuv420p',
         '-c:a', 'copy', '-movflags', '+faststart', str(dst)],
        check=True)
    # Never swap in a bigger file
    return dst if dst.stat().st_size < src.stat().st_size else src


def shrink(pptx: Path, workers: int = 3) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(pptx) as zin:
            infos = zin.infolist()
            videos = [i for i in infos if i.filename.startswith('ppt/media/') and i.filename.lower().endswith('.mp4')]
            for i in videos:
                zin.extract(i, tmp / 'in')

            done = 0
            def job(info):
                src = tmp / 'in' / info.filename
                dst = tmp / 'out' / info.filename
                dst.parent.mkdir(parents=True, exist_ok=True)
                return info.filename, _reencode(src, dst)

            replaced = {}
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for name, path in ex.map(job, videos):
                    replaced[name] = path
                    done += 1
                    print(f'\r  {done}/{len(videos)} videos', end='', flush=True)
            print()

            out = pptx.with_suffix('.shrunk.pptx')
            with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
                for info in infos:
                    if info.filename in replaced:
                        # Already compressed video: store, don't deflate
                        zout.write(replaced[info.filename], info.filename, compress_type=zipfile.ZIP_STORED)
                    else:
                        zout.writestr(info, zin.read(info.filename))

    size = out.stat().st_size
    if size >= 2 * 1024**3:
        print(f'  WARNING: still {size / 1e9:.2f} GB — over PowerPoint\'s 2 GB limit')
    bak = pptx.with_suffix('.pptx.bak')
    shutil.move(pptx, bak)
    shutil.move(out, pptx)
    print(f'  {bak.stat().st_size / 1e9:.2f} GB -> {size / 1e9:.2f} GB (original kept as {bak.name})')


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        print(Path(arg).name)
        shrink(Path(arg))

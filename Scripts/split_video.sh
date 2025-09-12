#!/bin/bash
# Usage: ./split_video.sh input.mp4 output_dir

input="$1"
outdir="$2"
basename=$(basename "$input" .mp4)

mkdir -p "$outdir"

ffmpeg -i "$input" -c copy -map 0 -segment_time 29 -f segment -reset_timestamps 1 "${outdir}/${basename}_temp_%03d.mp4"

i=1
for f in "${outdir}/${basename}_temp_"*.mp4; do
    mv "$f" "${outdir}/${basename} section ${i}.mp4"
    i=$((i + 1))
done

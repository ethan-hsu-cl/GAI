#!/usr/bin/env python3
"""
Image-to-Video Matching Tool - Optimized for More Videos Than Images
"""

import cv2
import json
import logging
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from skimage.metrics import structural_similarity as ssim
    _ssim_available = True
except ImportError:
    _ssim_available = False


class ImageToVideoMatcher:
    def __init__(self, config_file="batch_config.json"):
        with open(config_file, 'r') as f:
            self.config = json.load(f)

    def similarity(self, img1_path, img2_path):
        """Enhanced similarity calculation"""
        img1 = cv2.imread(str(img1_path), cv2.IMREAD_COLOR)
        img2 = cv2.imread(str(img2_path), cv2.IMREAD_COLOR)
        if img1 is None or img2 is None:
            return 0.0

        # Resize to match
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        if h1 * w1 > h2 * w2:
            img1 = cv2.resize(img1, (w2, h2))
        else:
            img2 = cv2.resize(img2, (w1, h1))

        scores = []

        # SSIM (best for structure)
        if _ssim_available:
            try:
                gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
                scores.append(ssim(gray1, gray2) * 0.5)
            except:
                pass

        # Template matching
        try:
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(gray1, gray2, cv2.TM_CCOEFF_NORMED)
            _, template_score, _, _ = cv2.minMaxLoc(result)
            scores.append(max(0.0, template_score) * 0.3)
        except:
            pass

        # Color histogram
        try:
            hist1 = cv2.calcHist([img1], [0, 1, 2], None, [32, 32, 32], [0, 256, 0, 256, 0, 256])
            hist2 = cv2.calcHist([img2], [0, 1, 2], None, [32, 32, 32], [0, 256, 0, 256, 0, 256])
            hist_score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            scores.append(max(0.0, hist_score) * 0.2)
        except:
            pass

        return sum(scores) if scores else 0.0

    def extract_frame(self, video_path):
        """Extract good frame from video"""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return None

        # Try 3 positions
        positions = [
            min(30, total_frames - 1),
            min(total_frames // 3, total_frames - 1),
            min(total_frames // 2, total_frames - 1)
        ]

        best_frame = None
        best_brightness = 0

        for pos in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if ret and frame is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness = cv2.mean(gray)[0]
                if 30 < brightness < 220 and brightness > best_brightness:
                    best_brightness = brightness
                    best_frame = frame.copy()

        cap.release()
        return best_frame

    def process_image(self, image_file, video_files, source_dir, video_dir, temp_dir):
        """Find the best video match for a single image"""
        image_path = source_dir / image_file.name
        best_score = 0.0
        best_video = None
        
        for video_file in video_files:
            # Check if this video already has a thumbnail
            temp_thumb = temp_dir / f"{video_file.stem}_thumb.jpg"
            
            if not temp_thumb.exists():
                # Extract frame and save thumbnail
                frame = self.extract_frame(video_dir / video_file.name)
                if frame is not None:
                    cv2.imwrite(str(temp_thumb), frame)
                else:
                    continue
            
            # Compare image with video thumbnail
            if temp_thumb.exists():
                score = self.similarity(image_path, temp_thumb)
                if score > best_score:
                    best_score = score
                    best_video = video_file

        return image_file, best_video, best_score

    def rename_videos(self, folder_path, threshold=0.3, workers=4):
        """Match images to their best videos (optimized for more videos than images)"""
        folder = Path(folder_path)
        source_dir = folder / "Source"
        video_dir = folder / "Generated_Video"
        temp_dir = video_dir / "temp_thumbs"

        if not source_dir.exists() or not video_dir.exists():
            logger.error("Missing Source or Generated_Video folder")
            return False

        images = [f for f in source_dir.iterdir() if f.suffix.lower() in {'.png', '.jpg', '.jpeg'}]
        videos = [f for f in video_dir.iterdir() if f.suffix.lower() in {'.mp4', '.avi', '.mov', '.mkv'}]

        if not images or not videos:
            logger.warning("No images or videos found")
            return False

        # Create temp directory for thumbnails
        temp_dir.mkdir(exist_ok=True)
        
        logger.info(f"Matching {len(images)} images to best of {len(videos)} videos")
        logger.info(f"Threshold: {threshold}, SSIM: {_ssim_available}")

        # Pre-extract all video thumbnails (more efficient)
        logger.info("Extracting video thumbnails...")
        for video_file in videos:
            temp_thumb = temp_dir / f"{video_file.stem}_thumb.jpg"
            if not temp_thumb.exists():
                frame = self.extract_frame(video_dir / video_file.name)
                if frame is not None:
                    cv2.imwrite(str(temp_thumb), frame)

        renamed = 0
        below_threshold = 0
        used_videos = set()

        # Process each image to find its best video match
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.process_image, img, videos, source_dir, video_dir, temp_dir): img 
                for img in images
            }
            
            for future in futures:
                image_file = futures[future]
                try:
                    img, best_video, score = future.result()
                    
                    if best_video and score >= threshold and best_video not in used_videos:
                        old_path = video_dir / best_video.name
                        new_path = video_dir / (img.stem + old_path.suffix)
                        
                        if not new_path.exists() or new_path == old_path:
                            old_path.rename(new_path)
                            used_videos.add(best_video)
                            renamed += 1
                            logger.info(f"✅ {img.name} → {best_video.name} ({score:.3f})")
                        else:
                            logger.warning(f"Target exists: {new_path.name}")
                    elif best_video:
                        below_threshold += 1
                        status = "used" if best_video in used_videos else f"below {threshold}"
                        logger.info(f"❌ {img.name} best: {best_video.name} ({score:.3f}) - {status}")
                    else:
                        logger.warning(f"❌ No match found for {img.name}")
                        
                except Exception as e:
                    logger.warning(f"Error processing {image_file.name}: {e}")

        # Cleanup thumbnails
        try:
            for thumb_file in temp_dir.iterdir():
                thumb_file.unlink()
            temp_dir.rmdir()
        except:
            pass

        success_rate = (renamed / len(images)) * 100 if images else 0
        unmatched_videos = len(videos) - len(used_videos)
        
        logger.info(f"Results: {renamed}/{len(images)} images matched ({success_rate:.1f}%)")
        logger.info(f"{unmatched_videos} videos remain unmatched")
        return renamed > 0

    def process_all_tasks(self, threshold=0.3, workers=4):
        """Process all config tasks"""
        for i, task in enumerate(self.config.get('tasks', []), 1):
            folder = Path(task.get('folder', ''))
            if folder.exists():
                logger.info(f"Task {i}: {folder}")
                self.rename_videos(folder, threshold, workers)
                logger.info("-" * 50)
            else:
                logger.warning(f"Task {i} folder not found: {folder}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Match images to their best videos")
    parser.add_argument('-c', '--config', default='batch_config.json')
    parser.add_argument('-f', '--folder', help='Single folder to process')
    parser.add_argument('-t', '--threshold', type=float, default=0.3)
    parser.add_argument('-w', '--workers', type=int, default=4)
    args = parser.parse_args()

    tool = ImageToVideoMatcher(args.config)
    
    if args.folder:
        tool.rename_videos(args.folder, args.threshold, args.workers)
    else:
        tool.process_all_tasks(args.threshold, args.workers)


if __name__ == '__main__':
    main()

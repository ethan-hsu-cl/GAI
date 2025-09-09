#!/usr/bin/env python3
"""
Video Comparison and Renaming Tool

This tool compares videos in the Generated_Video folder with images in the Source folder
and renames videos to match their corresponding source images based on visual similarity.

Uses the same batch_config.json configuration file as auto_report_optimized.py.
"""

import json
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import argparse
import sys

# Optional imports for image/video processing
try:
    import cv2
    import numpy as np
    _cv2_available = True
except ImportError:
    _cv2_available = False
    print("Warning: OpenCV not available. Install with: pip install opencv-python")

try:
    from skimage.metrics import structural_similarity as compare_ssim
    _ssim_available = True
except ImportError:
    _ssim_available = False
    print("Warning: scikit-image not available. Install with: pip install scikit-image")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('video_comparison.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)


class VideoComparisonTool:
    """Tool for comparing and renaming videos based on visual similarity to source images"""
    
    def __init__(self, config_file: str = "batch_config.json"):
        """Initialize with configuration file"""
        self.config_file = config_file
        self.load_config()
        
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"Loaded configuration from {self.config_file}")
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            sys.exit(1)
    
    def generate_diff_image(self, img_src: str, img_dest: str, img_diff: str) -> float:
        """
        Compare two images and return similarity score.
        Optimized with multiple comparison methods for better accuracy.
        """
        if not _cv2_available:
            logger.warning("OpenCV not available, cannot compare images")
            return 0.0
            
        try:
            # Load the two images
            img1 = cv2.imread(img_src)  # Source image (typically larger)
            img2 = cv2.imread(img_dest)  # Video thumbnail (typically smaller)
            
            if img1 is None or img2 is None:
                logger.warning(f"Failed to load images: {img_src}, {img_dest}")
                return 0.0

            # Get dimensions
            h1, w1 = img1.shape[:2]  # Source image dimensions
            h2, w2 = img2.shape[:2]  # Thumbnail dimensions
            
            # Always resize to the thumbnail dimensions (typically smaller)
            # This gives better comparison accuracy since video thumbnails are usually smaller
            if h1 != h2 or w1 != w2:
                # Resize source image to match thumbnail dimensions
                img1 = cv2.resize(img1, (w2, h2))
                logger.debug(f"Resized source image from ({w1}x{h1}) to thumbnail size ({w2}x{h2})")

            # Convert to grayscale for analysis
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

            # Method 1: Structural Similarity Index (SSIM)
            try:
                if _ssim_available:
                    ssim_score, _ = compare_ssim(gray1, gray2, full=True)
                else:
                    ssim_score = 0.0
            except Exception as e:
                logger.debug(f"SSIM comparison failed: {e}")
                ssim_score = 0.0
            
            # Method 2: Histogram Comparison (for color/brightness distribution)
            try:
                # Calculate histograms for each color channel
                hist1_b = cv2.calcHist([img1], [0], None, [256], [0, 256])
                hist1_g = cv2.calcHist([img1], [1], None, [256], [0, 256])
                hist1_r = cv2.calcHist([img1], [2], None, [256], [0, 256])
                
                hist2_b = cv2.calcHist([img2], [0], None, [256], [0, 256])
                hist2_g = cv2.calcHist([img2], [1], None, [256], [0, 256])
                hist2_r = cv2.calcHist([img2], [2], None, [256], [0, 256])
                
                # Compare histograms using correlation
                corr_b = cv2.compareHist(hist1_b, hist2_b, cv2.HISTCMP_CORREL)
                corr_g = cv2.compareHist(hist1_g, hist2_g, cv2.HISTCMP_CORREL)
                corr_r = cv2.compareHist(hist1_r, hist2_r, cv2.HISTCMP_CORREL)
                
                hist_score = (corr_b + corr_g + corr_r) / 3.0
            except Exception as e:
                logger.debug(f"Histogram comparison failed: {e}")
                hist_score = 0.0
            
            # Method 3: Template Matching (for position-independent comparison)
            try:
                # Use smaller image as template
                if gray1.size <= gray2.size:
                    template, image = gray1, gray2
                else:
                    template, image = gray2, gray1
                
                # Perform template matching
                result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
                _, template_score, _, _ = cv2.minMaxLoc(result)
                template_score = max(0.0, template_score)  # Ensure non-negative
            except Exception as e:
                logger.debug(f"Template matching failed: {e}")
                template_score = 0.0
            
            # Method 4: Feature-based comparison using ORB (if available)
            feature_score = 0.0
            try:
                orb = cv2.ORB_create(nfeatures=500)
                
                # Find keypoints and descriptors
                kp1, des1 = orb.detectAndCompute(gray1, None)
                kp2, des2 = orb.detectAndCompute(gray2, None)
                
                if des1 is not None and des2 is not None and len(des1) > 10 and len(des2) > 10:
                    # Use FLANN matcher for better performance
                    FLANN_INDEX_LSH = 6
                    index_params = dict(algorithm=FLANN_INDEX_LSH,
                                      table_number=6,
                                      key_size=12,
                                      multi_probe_level=1)
                    search_params = dict(checks=50)
                    
                    flann = cv2.FlannBasedMatcher(index_params, search_params)
                    matches = flann.knnMatch(des1, des2, k=2)
                    
                    # Apply Lowe's ratio test
                    good_matches = []
                    for match_pair in matches:
                        if len(match_pair) == 2:
                            m, n = match_pair
                            if m.distance < 0.7 * n.distance:
                                good_matches.append(m)
                    
                    # Calculate feature score based on good matches
                    if len(kp1) > 0 and len(kp2) > 0:
                        feature_score = len(good_matches) / max(len(kp1), len(kp2))
                    
            except Exception as e:
                logger.debug(f"Feature matching failed: {e}")
                feature_score = 0.0
            
            # Combine scores with weighted average
            # SSIM is most reliable for structural similarity
            # Histogram helps with color/brightness matching
            # Template matching helps with position-independent content
            # Feature matching helps with scale/rotation invariant content
            weights = [0.4, 0.25, 0.2, 0.15]  # SSIM, Histogram, Template, Features
            scores = [ssim_score, hist_score, template_score, feature_score]
            
            # Only include scores that are meaningful (> 0)
            valid_scores = [(score, weight) for score, weight in zip(scores, weights) if score > 0]
            
            if valid_scores:
                weighted_sum = sum(score * weight for score, weight in valid_scores)
                total_weight = sum(weight for _, weight in valid_scores)
                final_score = weighted_sum / total_weight
            else:
                final_score = 0.0
            
            logger.debug(f"Comparison scores - SSIM: {ssim_score:.3f}, Hist: {hist_score:.3f}, "
                        f"Template: {template_score:.3f}, Features: {feature_score:.3f}, "
                        f"Final: {final_score:.3f}")
            
            return final_score
            
        except Exception as e:
            logger.warning(f"Error comparing images {img_src} and {img_dest}: {e}")
            return 0.0

    def extract_multiple_frames(self, video_path: Path, num_frames: int = 3) -> List[np.ndarray]:
        """Extract multiple frames from video file for better comparison"""
        if not _cv2_available:
            return []
            
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                logger.warning(f"Could not open video {video_path}")
                return []
                
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                logger.warning(f"No frames found in video {video_path}")
                cap.release()
                return []
            
            frames = []
            # Extract frames from different positions: start, middle, and a bit later
            frame_positions = [0, min(30, total_frames // 3), min(60, total_frames // 2)]
            frame_positions = frame_positions[:num_frames]
            
            for frame_pos in frame_positions:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                if ret and frame is not None:
                    frames.append(frame)
                    
            cap.release()
            logger.debug(f"Extracted {len(frames)} frames from {video_path.name}")
            return frames
            
        except Exception as e:
            logger.warning(f"Error extracting frames from {video_path}: {e}")
            return []

    def extract_and_save_multiple_thumbnails(self, video_file: Path, video_folder: Path, thumbnails_folder: Path) -> tuple:
        """
        Extract and save multiple thumbnails for a single video file.
        Returns (video_file, thumbnail_paths) on success, (video_file, []) on failure.
        """
        video_path = video_folder / video_file.name
        frames = self.extract_multiple_frames(video_path, num_frames=3)
        
        if not frames:
            logger.warning(f"Could not extract frames from {video_file.name}")
            return (video_file, [])

        thumbnail_paths = []
        for i, frame in enumerate(frames):
            # Save thumbnail with video filename and frame index
            thumbnail_path = thumbnails_folder / f"{video_file.stem}_thumb_{i}.jpg"
            try:
                cv2.imwrite(str(thumbnail_path), frame)
                thumbnail_paths.append(thumbnail_path)
            except Exception as e:
                logger.warning(f"Could not save thumbnail {i} for {video_file.name}: {e}")
                
        return (video_file, thumbnail_paths)

    def compare_image_with_thumbnails(self, image_path: Path, thumbnail_paths: List[Path], thumbnails_folder: Path) -> float:
        """
        Compare a single image with multiple video thumbnails and return the best similarity score.
        """
        if not thumbnail_paths:
            return 0.0
            
        best_similarity = 0.0
        for thumbnail_path in thumbnail_paths:
            try:
                similarity = self.generate_diff_image(str(image_path), str(thumbnail_path), 
                                                    str(thumbnails_folder / "temp_diff.jpg"))
                if similarity > best_similarity:
                    best_similarity = similarity
            except Exception as e:
                logger.debug(f"Error comparing {image_path.name} with {thumbnail_path.name}: {e}")
                continue
                
        return best_similarity

    def find_best_match_for_video(self, video_info: tuple, image_files: List[Path], source_folder: Path, thumbnails_folder: Path) -> tuple:
        """
        Find the best matching image for a video (used in multithreading).
        Returns (video_file, matched_image, highest_similarity)
        """
        video_file, thumbnail_paths = video_info
        
        if not thumbnail_paths:
            return (video_file, None, 0.0)
            
        matched_image = None
        highest_similarity = 0.0
        
        for image_file in image_files:
            image_path = source_folder / image_file.name
            try:
                similarity = self.compare_image_with_thumbnails(image_path, thumbnail_paths, thumbnails_folder)
                logger.debug(f"Comparing {image_file.name} with {video_file.name}: similarity={similarity:.3f}")
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    matched_image = image_file
            except Exception as e:
                logger.warning(f"Error comparing {image_file.name} and {video_file.name}: {e}")
        
        return (video_file, matched_image, highest_similarity)

    def compare_and_rename_videos(self, folder_path: Path, threshold: float = 0.7, max_workers: int = 4) -> bool:
        """
        Compare videos in Generated_Video folder with images in Source folder and rename them to match.
        Enhanced version with multiple frame extraction, multi-method comparison, and multithreaded processing.
        """
        if not _cv2_available:
            logger.warning("OpenCV not available, cannot rename videos")
            return False
            
        logger.info(f"Comparing and renaming videos in {folder_path}")
        
        # Define folder paths
        source_folder = folder_path / "Source"
        video_folder = folder_path / "Generated_Video"
        
        if not source_folder.exists():
            logger.warning(f"Source folder not found: {source_folder}")
            return False
            
        if not video_folder.exists():
            logger.warning(f"Generated_Video folder not found: {video_folder}")
            return False
            
        # Get all image files in source_folder
        image_files = [f for f in source_folder.iterdir() if f.suffix.lower() in {'.png', '.jpg', '.jpeg'}]
        # Get all video files in video folder
        video_files = [f for f in video_folder.iterdir() if f.suffix.lower() in {'.mp4', '.avi', '.mov', '.mkv'}]
        
        if not image_files:
            logger.warning(f"No image files found in source folder: {source_folder}")
            return False
            
        if not video_files:
            logger.warning(f"No video files found in video folder: {video_folder}")
            return False

        # Step 1: Extract and save multiple video thumbnails using multithreading
        logger.info(f"Extracting multiple thumbnails from {len(video_files)} videos using multithreading...")
        thumbnails_folder = video_folder / "temp_thumbnails"
        thumbnails_folder.mkdir(exist_ok=True)
        
        video_thumbnails = {}  # video_file -> [thumbnail_paths]
        
        # Use ThreadPoolExecutor for parallel thumbnail extraction
        max_workers = min(len(video_files), max_workers)
        logger.info(f"Using {max_workers} worker threads for thumbnail extraction")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all extraction tasks
            future_to_video = {
                executor.submit(self.extract_and_save_multiple_thumbnails, video_file, video_folder, thumbnails_folder): video_file 
                for video_file in video_files
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_video):
                video_file, thumbnail_paths = future.result()
                if thumbnail_paths:
                    video_thumbnails[video_file] = thumbnail_paths
                    logger.debug(f"Extracted {len(thumbnail_paths)} thumbnails for {video_file.name}")
                else:
                    logger.warning(f"Failed to extract thumbnails for {video_file.name}")
            
        logger.info(f"Successfully extracted thumbnails for {len(video_thumbnails)} videos")
        
        if not video_thumbnails:
            logger.warning("No video thumbnails could be extracted")
            # Clean up empty thumbnails folder
            if thumbnails_folder.exists():
                thumbnails_folder.rmdir()
            return False

        # Step 2: Do all cross-comparisons using multithreading
        logger.info(f"Performing multithreaded cross-comparisons between {len(image_files)} images and {len(video_thumbnails)} videos...")
        
        # Prepare video info for multithreaded processing
        video_info_list = [(video_file, thumbnail_paths) for video_file, thumbnail_paths in video_thumbnails.items()]
        
        renamed_count = 0
        
        # Use multithreading for the comparison phase as well
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all comparison tasks
            future_to_comparison = {
                executor.submit(self.find_best_match_for_video, video_info, image_files, source_folder, thumbnails_folder): video_info[0]
                for video_info in video_info_list
            }
            
            # Process results as they complete
            for future in as_completed(future_to_comparison):
                video_file, matched_image, highest_similarity = future.result()
                video_path = video_folder / video_file.name
                
                # Rename video if match found
                if matched_image and highest_similarity >= threshold:
                    new_name = matched_image.stem + video_path.suffix
                    new_path = video_folder / new_name
                    
                    # Don't rename if target name already exists and is not the same file
                    if new_path.exists() and new_path != video_path:
                        logger.warning(f"Target filename {new_name} already exists, skipping rename")
                        continue
                        
                    try:
                        video_path.rename(new_path)
                        logger.info(f"Renamed {video_file.name} to {new_name} (similarity={highest_similarity:.3f})")
                        renamed_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to rename {video_file.name} to {new_name}: {e}")
                else:
                    logger.info(f"No match found for {video_file.name} (highest similarity={highest_similarity:.3f})")

        # Step 3: Clean up all temporary files
        logger.info("Cleaning up temporary files...")
        try:
            # Remove all thumbnail files
            for thumbnail_paths in video_thumbnails.values():
                for thumbnail_path in thumbnail_paths:
                    if thumbnail_path.exists():
                        thumbnail_path.unlink()
            
            # Remove temp diff file if it exists
            temp_diff_path = thumbnails_folder / "temp_diff.jpg"
            if temp_diff_path.exists():
                temp_diff_path.unlink()
                
            # Remove thumbnails folder
            if thumbnails_folder.exists():
                thumbnails_folder.rmdir()
                
        except Exception as e:
            logger.warning(f"Error cleaning up temporary files: {e}")

        logger.info(f"Renamed {renamed_count} videos")
        return renamed_count > 0

    def process_all_tasks(self, threshold: float = 0.7, max_workers: int = 4):
        """Process all tasks defined in the configuration file"""
        if 'tasks' not in self.config:
            logger.error("No tasks found in configuration file")
            return
            
        tasks = self.config['tasks']
        logger.info(f"Processing {len(tasks)} tasks from configuration")
        
        for i, task in enumerate(tasks, 1):
            logger.info(f"Processing task {i}/{len(tasks)}")
            
            folder_path = Path(task.get('folder', ''))
            if not folder_path.exists():
                logger.warning(f"Task folder not found: {folder_path}")
                continue
                
            # Process the main folder
            success = self.compare_and_rename_videos(folder_path, threshold, max_workers)
            
            # Also process reference folder if it exists
            reference_folder = task.get('reference_folder')
            if reference_folder:
                ref_path = Path(reference_folder)
                if ref_path.exists():
                    logger.info(f"Processing reference folder: {ref_path}")
                    self.compare_and_rename_videos(ref_path, threshold, max_workers)
                else:
                    logger.warning(f"Reference folder not found: {ref_path}")
                    
            logger.info(f"Task {i} completed {'successfully' if success else 'with issues'}")

    def process_single_folder(self, folder_path: str, threshold: float = 0.7, max_workers: int = 4):
        """Process a single folder (not from config file)"""
        path = Path(folder_path)
        if not path.exists():
            logger.error(f"Folder not found: {folder_path}")
            return False
            
        return self.compare_and_rename_videos(path, threshold, max_workers)


def main():
    """Main function for command line usage"""
    parser = argparse.ArgumentParser(
        description="Compare videos with source images and rename them based on visual similarity"
    )
    parser.add_argument(
        '--config', '-c',
        default='batch_config.json',
        help='Configuration file path (default: batch_config.json)'
    )
    parser.add_argument(
        '--folder', '-f',
        help='Process a single folder instead of using config file tasks'
    )
    parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.7,
        help='Similarity threshold for matching (0.0-1.0, default: 0.7)'
    )
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=4,
        help='Number of worker threads (default: 4)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check dependencies
    if not _cv2_available:
        logger.error("OpenCV is required but not installed. Please install with: pip install opencv-python")
        sys.exit(1)
    
    # Create tool instance
    tool = VideoComparisonTool(args.config)
    
    # Process folder or tasks
    if args.folder:
        logger.info(f"Processing single folder: {args.folder}")
        success = tool.process_single_folder(args.folder, args.threshold, args.workers)
        sys.exit(0 if success else 1)
    else:
        logger.info("Processing all tasks from configuration file")
        tool.process_all_tasks(args.threshold, args.workers)


if __name__ == '__main__':
    main()

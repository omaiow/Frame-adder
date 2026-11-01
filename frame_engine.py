"""
PNG Frame Studio - Core Frame Engine
Handles transparent PNG aperture detection, image fitting/compositing, and batch rendering.
"""

import os
import concurrent.futures
from typing import Tuple, Optional, Callable
from PIL import Image, ImageOps

class FrameEngine:
    FIT_TO_APERTURE = "Fit Photo to Aperture (Keep Aspect)"
    FILL_APERTURE = "Fill Aperture (Crop Photo)"
    STRETCH_TO_APERTURE = "Stretch Photo to Aperture"
    STRETCH_FRAME_TO_PHOTO = "Stretch Frame to Photo"
    STRETCH_PHOTO_TO_FRAME = "Stretch Photo to Full Frame Size"

    LAYER_FRAME_OVER = "Frame Over Photo (Transparent Opening)"
    LAYER_PHOTO_OVER = "Photo Over Frame (Mat / Card Border)"

    @staticmethod
    def detect_aperture(frame_img: Image.Image) -> Tuple[int, int, int, int]:
        """
        Scans the alpha channel of a PNG frame to find the bounding box of the transparent window/hole.
        Returns (x, y, width, height).
        """
        if frame_img.mode != 'RGBA':
            frame_img = frame_img.convert('RGBA')
        
        alpha = frame_img.getchannel('A')
        w, h = frame_img.size

        # Binary threshold for transparency (alpha < 128 considered transparent aperture)
        threshold = 128
        # Get bounding box of transparent pixels
        # Invert alpha so transparent areas become non-zero (opaque for getbbox)
        inverted_alpha = alpha.point(lambda p: 255 if p < threshold else 0)
        bbox = inverted_alpha.getbbox()

        if bbox is None:
            # Fully opaque image or no transparency found -> fallback to full image bounds
            return (0, 0, w, h)

        x1, y1, x2, y2 = bbox
        return (x1, y1, x2 - x1, y2 - y1)

    @staticmethod
    def composite_image(
        photo_img: Image.Image,
        frame_img: Image.Image,
        aperture: Tuple[int, int, int, int],
        fit_mode: str = FIT_TO_APERTURE,
        layer_order: str = LAYER_FRAME_OVER,
        bg_color: Tuple[int, int, int, int] = (0, 0, 0, 0)
    ) -> Image.Image:
        """
        Composites photo_img with frame_img according to aperture rect and fit_mode.
        Returns composite RGBA Image.
        """
        # Ensure RGBA modes
        if photo_img.mode != 'RGBA':
            photo_img = photo_img.convert('RGBA')
        if frame_img.mode != 'RGBA':
            frame_img = frame_img.convert('RGBA')

        ax, ay, aw, ah = aperture
        fw, fh = frame_img.size
        pw, ph = photo_img.size

        if fit_mode == FrameEngine.STRETCH_FRAME_TO_PHOTO:
            # Scale frame and its aperture proportionally to photo dimensions
            scale_x = pw / max(1, fw)
            scale_y = ph / max(1, fh)
            new_fw, new_fh = pw, ph
            resized_frame = frame_img.resize((new_fw, new_fh), Image.Resampling.LANCZOS)
            
            scaled_ax = int(ax * scale_x)
            scaled_ay = int(ay * scale_y)
            scaled_aw = int(aw * scale_x)
            scaled_ah = int(ah * scale_y)

            # Composite photo & resized frame
            canvas = Image.new('RGBA', (new_fw, new_fh), bg_color)
            if layer_order == FrameEngine.LAYER_FRAME_OVER:
                # Place photo under
                # Fit/Cover photo to scaled aperture or match
                photo_resized = photo_img.resize((new_fw, new_fh), Image.Resampling.LANCZOS)
                canvas.alpha_composite(photo_resized, (0, 0))
                canvas.alpha_composite(resized_frame, (0, 0))
            else:
                canvas.alpha_composite(resized_frame, (0, 0))
                photo_resized = ImageOps.fit(photo_img, (max(1, scaled_aw), max(1, scaled_ah)), method=Image.Resampling.LANCZOS)
                canvas.alpha_composite(photo_resized, (scaled_ax, scaled_ay))
            return canvas

        elif fit_mode == FrameEngine.STRETCH_PHOTO_TO_FRAME:
            # Stretch photo to entire frame dimensions
            canvas = Image.new('RGBA', (fw, fh), bg_color)
            photo_resized = photo_img.resize((fw, fh), Image.Resampling.LANCZOS)
            if layer_order == FrameEngine.LAYER_FRAME_OVER:
                canvas.alpha_composite(photo_resized, (0, 0))
                canvas.alpha_composite(frame_img, (0, 0))
            else:
                canvas.alpha_composite(frame_img, (0, 0))
                canvas.alpha_composite(photo_resized, (0, 0))
            return canvas

        elif fit_mode == FrameEngine.STRETCH_TO_APERTURE:
            # Stretch photo to fill exact aperture box
            canvas = Image.new('RGBA', (fw, fh), bg_color)
            photo_resized = photo_img.resize((max(1, aw), max(1, ah)), Image.Resampling.LANCZOS)
            if layer_order == FrameEngine.LAYER_FRAME_OVER:
                canvas.alpha_composite(photo_resized, (ax, ay))
                canvas.alpha_composite(frame_img, (0, 0))
            else:
                canvas.alpha_composite(frame_img, (0, 0))
                canvas.alpha_composite(photo_resized, (ax, ay))
            return canvas

        elif fit_mode == FrameEngine.FILL_APERTURE:
            # Cover / crop photo to fill aperture completely
            canvas = Image.new('RGBA', (fw, fh), bg_color)
            photo_cropped = ImageOps.fit(photo_img, (max(1, aw), max(1, ah)), method=Image.Resampling.LANCZOS)
            if layer_order == FrameEngine.LAYER_FRAME_OVER:
                canvas.alpha_composite(photo_cropped, (ax, ay))
                canvas.alpha_composite(frame_img, (0, 0))
            else:
                canvas.alpha_composite(frame_img, (0, 0))
                canvas.alpha_composite(photo_cropped, (ax, ay))
            return canvas

        else:  # FIT_TO_APERTURE (Default: keep aspect ratio, fit inside aperture)
            canvas = Image.new('RGBA', (fw, fh), bg_color)
            
            # Calculate aspect fit dimensions
            ratio = min(aw / max(1, pw), ah / max(1, ph))
            new_w = max(1, int(pw * ratio))
            new_h = max(1, int(ph * ratio))
            photo_fitted = photo_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Center photo within aperture box
            offset_x = ax + (aw - new_w) // 2
            offset_y = ay + (ah - new_h) // 2

            if layer_order == FrameEngine.LAYER_FRAME_OVER:
                canvas.alpha_composite(photo_fitted, (offset_x, offset_y))
                canvas.alpha_composite(frame_img, (0, 0))
            else:
                canvas.alpha_composite(frame_img, (0, 0))
                canvas.alpha_composite(photo_fitted, (offset_x, offset_y))
            return canvas

    @staticmethod
    def process_single_file(
        photo_path: str,
        frame_img: Image.Image,
        aperture: Tuple[int, int, int, int],
        fit_mode: str,
        layer_order: str,
        output_dir: str,
        output_format: str,
        jpeg_quality: int,
        naming_pattern: str,
        bg_color: Tuple[int, int, int, int] = (0, 0, 0, 0)
    ) -> Tuple[bool, str, str]:
        """
        Process a single image file and save to output_dir.
        Returns (success: bool, photo_path: str, message_or_dest_path: str).
        """
        try:
            filename = os.path.basename(photo_path)
            basename, ext = os.path.splitext(filename)

            with Image.open(photo_path) as photo_img:
                photo_img = ImageOps.exif_transpose(photo_img) # Fix EXIF rotation if present
                result = FrameEngine.composite_image(
                    photo_img=photo_img,
                    frame_img=frame_img,
                    aperture=aperture,
                    fit_mode=fit_mode,
                    layer_order=layer_order,
                    bg_color=bg_color
                )

                # Format destination filename
                out_name = naming_pattern.replace("{filename}", basename)
                
                # Determine output format and extension
                if output_format.upper() == "ORIGINAL":
                    save_fmt = ext.lstrip('.').upper()
                    if save_fmt not in ['PNG', 'JPG', 'JPEG', 'WEBP']:
                        save_fmt = 'PNG'
                else:
                    save_fmt = output_format.upper()

                out_ext = f".{save_fmt.lower()}"
                if out_ext == '.jpeg':
                    out_ext = '.jpg'

                if not out_name.endswith(out_ext):
                    dest_file = f"{out_name}{out_ext}"
                else:
                    dest_file = out_name

                dest_path = os.path.join(output_dir, dest_file)

                # Convert to RGB if saving as JPEG (no alpha in JPEG)
                if save_fmt in ['JPG', 'JPEG']:
                    if result.mode in ('RGBA', 'LA') or (result.mode == 'P' and 'transparency' in result.info):
                        # Fill alpha with white or chosen bg_color
                        bg = Image.new("RGB", result.size, (255, 255, 255) if bg_color[3] == 0 else bg_color[:3])
                        bg.paste(result, mask=result.split()[3])
                        result = bg
                    else:
                        result = result.convert("RGB")
                    result.save(dest_path, "JPEG", quality=jpeg_quality, optimize=True)
                elif save_fmt == 'WEBP':
                    result.save(dest_path, "WEBP", quality=jpeg_quality, lossless=(jpeg_quality == 100))
                else:
                    # Default PNG (Lossless)
                    result.save(dest_path, "PNG", optimize=True)

                return True, photo_path, dest_path
        except Exception as e:
            return False, photo_path, str(e)

    @staticmethod
    def process_batch(
        photo_paths: list[str],
        frame_path: str,
        aperture: Tuple[int, int, int, int],
        fit_mode: str,
        layer_order: str,
        output_dir: str,
        output_format: str = "PNG",
        jpeg_quality: int = 95,
        naming_pattern: str = "framed_{filename}",
        bg_color: Tuple[int, int, int, int] = (0, 0, 0, 0),
        progress_callback: Optional[Callable[[int, int, str, bool], None]] = None,
        max_workers: int = 4
    ) -> list[Tuple[bool, str, str]]:
        """
        Batch process multiple photos in parallel using thread pool.
        Calls progress_callback(completed_count, total_count, current_file_path, success).
        """
        os.makedirs(output_dir, exist_ok=True)
        results = []
        total = len(photo_paths)

        # Pre-load frame image
        with Image.open(frame_path) as f_img:
            frame_img = f_img.convert('RGBA')

        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_photo = {
                executor.submit(
                    FrameEngine.process_single_file,
                    p,
                    frame_img,
                    aperture,
                    fit_mode,
                    layer_order,
                    output_dir,
                    output_format,
                    jpeg_quality,
                    naming_pattern,
                    bg_color
                ): p for p in photo_paths
            }

            for future in concurrent.futures.as_completed(future_to_photo):
                photo_p = future_to_photo[future]
                try:
                    success, path, res_msg = future.result()
                    results.append((success, path, res_msg))
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total, path, success)
                except Exception as exc:
                    results.append((False, photo_p, str(exc)))
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total, photo_p, False)

        return results

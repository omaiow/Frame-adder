"""
Test Script for PNG Frame Studio Engine
Generates sample assets and verifies batch framing compositing logic.
"""

import os
from PIL import Image, ImageDraw
from frame_engine import FrameEngine

def create_sample_assets(test_dir):
    os.makedirs(test_dir, exist_ok=True)
    
    # 1. Create a 400x400 PNG Frame with a 200x200 transparent window in center (x=100, y=100)
    frame = Image.new('RGBA', (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    # Draw thick gold border (opaque)
    draw.rectangle([0, 0, 399, 399], fill=(212, 175, 55, 255), outline=(139, 115, 36, 255), width=10)
    # Draw inner dark frame mat (opaque)
    draw.rectangle([20, 20, 379, 379], fill=(30, 30, 40, 255))
    # Cut out transparent center aperture (alpha = 0)
    # Drawing with RGBA (0,0,0,0) requires using composite/clear or direct pixel manipulation
    alpha = frame.getchannel('A')
    alpha_draw = ImageDraw.Draw(alpha)
    alpha_draw.rectangle([100, 100, 299, 299], fill=0)
    frame.putalpha(alpha)
    
    frame_path = os.path.join(test_dir, "sample_frame.png")
    frame.save(frame_path, "PNG")

    # 2. Create 3 test photos (various resolutions and colors)
    photo_paths = []
    colors = [(220, 60, 60), (60, 180, 60), (60, 100, 220)]
    sizes = [(600, 400), (400, 600), (800, 800)]
    
    for i, (col, sz) in enumerate(zip(colors, sizes), 1):
        p_img = Image.new('RGB', sz, col)
        p_draw = ImageDraw.Draw(p_img)
        p_draw.line([(0, 0), sz], fill=(255, 255, 255), width=5)
        p_draw.text((30, 30), f"Sample Photo #{i}", fill=(255, 255, 255))
        p_path = os.path.join(test_dir, f"photo_{i}.jpg")
        p_img.save(p_path, "JPEG")
        photo_paths.append(p_path)

    return frame_path, photo_paths

def run_tests():
    test_dir = os.path.join(os.getcwd(), "test_data")
    out_dir = os.path.join(test_dir, "framed_output")
    
    print("Generating sample assets...")
    frame_path, photo_paths = create_sample_assets(test_dir)
    
    with Image.open(frame_path) as f_img:
        aperture = FrameEngine.detect_aperture(f_img)
        print(f"Detected Aperture: {aperture}")
        assert aperture == (100, 100, 200, 200), f"Expected (100, 100, 200, 200), got {aperture}"

    # Test Fit Modes
    for mode in [FrameEngine.FIT_TO_APERTURE, FrameEngine.FILL_APERTURE, FrameEngine.STRETCH_FRAME_TO_PHOTO]:
        print(f"Testing batch process with fit mode: {mode}")
        results = FrameEngine.process_batch(
            photo_paths=photo_paths,
            frame_path=frame_path,
            aperture=aperture,
            fit_mode=mode,
            layer_order=FrameEngine.LAYER_FRAME_OVER,
            output_dir=out_dir,
            output_format="PNG",
            naming_pattern=f"framed_{mode[:5].lower()}_{{filename}}"
        )
        
        for success, src, dst in results:
            assert success, f"Failed for {src}: {dst}"
            assert os.path.exists(dst), f"Output file missing: {dst}"
            print(f"  [SUCCESS] {os.path.basename(src)} -> {os.path.basename(dst)}")

    print("\nALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()

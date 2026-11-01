"""
PNG Frame Studio - Main GUI Application
A modern, native Windows application built with CustomTkinter for mass framing images using custom PNG overlays.
"""

import os
import sys
import threading
import subprocess
from typing import Optional, List, Tuple
from PIL import Image, ImageTk

import customtkinter as ctk
from tkinter import filedialog, messagebox

from frame_engine import FrameEngine

# Set CustomTkinter dark theme and color palette
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class PNGFrameStudio(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Config
        self.title("PNG Frame Studio — Mass Image Framing")
        self.geometry("1240x820")
        self.minsize(980, 680)

        # State Variables
        self.frame_path: Optional[str] = None
        self.frame_img: Optional[Image.Image] = None
        self.aperture: Tuple[int, int, int, int] = (0, 0, 0, 0)
        self.photo_paths: List[str] = []
        self.current_preview_index: int = 0
        self.output_dir: str = os.path.join(os.getcwd(), "output")
        self.is_processing: bool = False

        # Create Layout
        self._init_ui()

    def _init_ui(self):
        # Grid layout (1 row, 2 columns: Sidebar & Main Area)
        self.grid_columnconfigure(0, weight=0, minsize=380)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # LEFT SIDEBAR - CONTROLS & CONFIGURATION
        # ==========================================
        self.sidebar = ctk.CTkScrollableFrame(self, width=380, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)

        # App Title Header
        title_label = ctk.CTkLabel(
            self.sidebar,
            text="🖼️ PNG Frame Studio",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(anchor="w", pady=(0, 5))

        subtitle_label = ctk.CTkLabel(
            self.sidebar,
            text="Mass apply custom PNG frame overlays",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        subtitle_label.pack(anchor="w", pady=(0, 15))

        # --- SECTION 1: CUSTOM FRAME SELECTION ---
        frame_section_label = ctk.CTkLabel(
            self.sidebar, text="1. Custom PNG Frame", font=ctk.CTkFont(size=14, weight="bold")
        )
        frame_section_label.pack(anchor="w", pady=(10, 5))

        self.btn_select_frame = ctk.CTkButton(
            self.sidebar,
            text="📂 Select PNG Frame...",
            command=self._on_select_frame,
            fg_color="#1f538d",
            hover_color="#14375e"
        )
        self.btn_select_frame.pack(fill="x", pady=5)

        self.frame_info_lbl = ctk.CTkLabel(
            self.sidebar,
            text="No PNG frame loaded.",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            anchor="w",
            justify="left"
        )
        self.frame_info_lbl.pack(fill="x", pady=(0, 10))

        # Aperture Info & Manual Override Toggle
        self.aperture_info_lbl = ctk.CTkLabel(
            self.sidebar,
            text="Aperture: N/A",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
            anchor="w"
        )
        self.aperture_info_lbl.pack(fill="x", pady=(0, 5))

        self.manual_aperture_switch = ctk.CTkSwitch(
            self.sidebar,
            text="Manual Aperture Override",
            command=self._on_toggle_manual_aperture
        )
        self.manual_aperture_switch.pack(anchor="w", pady=(0, 5))

        # Manual Aperture Inputs Container
        self.aperture_frame = ctk.CTkFrame(self.sidebar)
        # Hidden by default

        self.entry_ap_x = self._create_number_input(self.aperture_frame, "X Offset (px):", 0)
        self.entry_ap_y = self._create_number_input(self.aperture_frame, "Y Offset (px):", 0)
        self.entry_ap_w = self._create_number_input(self.aperture_frame, "Width (px):", 100)
        self.entry_ap_h = self._create_number_input(self.aperture_frame, "Height (px):", 100)

        # Separator Line
        self._add_separator()

        # --- SECTION 2: FITTING & LAYERING OPTIONS ---
        options_section_label = ctk.CTkLabel(
            self.sidebar, text="2. Framing Options", font=ctk.CTkFont(size=14, weight="bold")
        )
        options_section_label.pack(anchor="w", pady=(10, 5))

        layer_label = ctk.CTkLabel(self.sidebar, text="Layering Mode:", font=ctk.CTkFont(size=12))
        layer_label.pack(anchor="w", pady=(5, 0))

        self.layer_order_combo = ctk.CTkOptionMenu(
            self.sidebar,
            values=[FrameEngine.LAYER_FRAME_OVER, FrameEngine.LAYER_PHOTO_OVER],
            command=lambda _: self._update_preview()
        )
        self.layer_order_combo.pack(fill="x", pady=(0, 10))

        fit_label = ctk.CTkLabel(self.sidebar, text="Photo Fitting Mode:", font=ctk.CTkFont(size=12))
        fit_label.pack(anchor="w", pady=(5, 0))

        self.fit_mode_combo = ctk.CTkOptionMenu(
            self.sidebar,
            values=[
                FrameEngine.FIT_TO_APERTURE,
                FrameEngine.FILL_APERTURE,
                FrameEngine.STRETCH_TO_APERTURE,
                FrameEngine.STRETCH_FRAME_TO_PHOTO,
                FrameEngine.STRETCH_PHOTO_TO_FRAME,
            ],
            command=lambda _: self._update_preview()
        )
        self.fit_mode_combo.pack(fill="x", pady=(0, 10))

        # Separator Line
        self._add_separator()

        # --- SECTION 3: EXPORT SETTINGS ---
        export_section_label = ctk.CTkLabel(
            self.sidebar, text="3. Export Settings", font=ctk.CTkFont(size=14, weight="bold")
        )
        export_section_label.pack(anchor="w", pady=(10, 5))

        format_label = ctk.CTkLabel(self.sidebar, text="Output Format:", font=ctk.CTkFont(size=12))
        format_label.pack(anchor="w", pady=(5, 0))

        self.format_combo = ctk.CTkOptionMenu(
            self.sidebar,
            values=["PNG", "JPEG", "WEBP", "Original"],
            command=self._on_format_change
        )
        self.format_combo.pack(fill="x", pady=(0, 10))

        self.quality_label = ctk.CTkLabel(self.sidebar, text="JPEG/WEBP Quality: 95%", font=ctk.CTkFont(size=12))
        self.quality_label.pack(anchor="w", pady=(5, 0))

        self.quality_slider = ctk.CTkSlider(
            self.sidebar,
            from_=10,
            to=100,
            number_of_steps=90,
            command=self._on_quality_change
        )
        self.quality_slider.set(95)
        self.quality_slider.pack(fill="x", pady=(0, 10))

        naming_label = ctk.CTkLabel(self.sidebar, text="Filename Pattern:", font=ctk.CTkFont(size=12))
        naming_label.pack(anchor="w", pady=(5, 0))

        self.entry_naming = ctk.CTkEntry(self.sidebar, placeholder_text="framed_{filename}")
        self.entry_naming.insert(0, "framed_{filename}")
        self.entry_naming.pack(fill="x", pady=(0, 10))

        out_dir_label = ctk.CTkLabel(self.sidebar, text="Output Folder:", font=ctk.CTkFont(size=12))
        out_dir_label.pack(anchor="w", pady=(5, 0))

        self.btn_select_out_dir = ctk.CTkButton(
            self.sidebar,
            text=f"📁 {os.path.basename(self.output_dir)}",
            command=self._on_select_out_dir,
            fg_color="gray30",
            hover_color="gray40"
        )
        self.btn_select_out_dir.pack(fill="x", pady=(0, 15))

        # Separator Line
        self._add_separator()

        # --- SECTION 4: ACTION BUTTONS ---
        self.btn_start_batch = ctk.CTkButton(
            self.sidebar,
            text="🚀 START BATCH PROCESS (0)",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=45,
            fg_color="#2fa572",
            hover_color="#1c754f",
            command=self._start_batch_process
        )
        self.btn_start_batch.pack(fill="x", pady=(10, 5))

        self.btn_open_out_dir = ctk.CTkButton(
            self.sidebar,
            text="📂 Open Output Folder",
            height=35,
            fg_color="gray30",
            hover_color="gray40",
            command=self._open_output_folder
        )
        self.btn_open_out_dir.pack(fill="x", pady=(0, 10))

        # ==========================================
        # RIGHT MAIN PANEL - PREVIEW & PHOTO LIST
        # ==========================================
        self.main_panel = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_panel.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.main_panel.grid_rowconfigure(1, weight=1)
        self.main_panel.grid_columnconfigure(0, weight=1)

        # Top Action Bar
        top_bar = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.btn_add_files = ctk.CTkButton(
            top_bar, text="➕ Add Photos...", command=self._on_add_photos, width=130
        )
        self.btn_add_files.pack(side="left", padx=(0, 10))

        self.btn_add_folder = ctk.CTkButton(
            top_bar, text="📁 Add Folder...", command=self._on_add_folder, width=130, fg_color="gray30", hover_color="gray40"
        )
        self.btn_add_folder.pack(side="left", padx=(0, 10))

        self.btn_clear_photos = ctk.CTkButton(
            top_bar, text="🗑️ Clear List", command=self._on_clear_photos, width=100, fg_color="#a83232", hover_color="#732222"
        )
        self.btn_clear_photos.pack(side="left", padx=(0, 10))

        self.nav_prev_btn = ctk.CTkButton(
            top_bar, text="◀ Prev", width=60, command=self._prev_preview
        )
        self.nav_prev_btn.pack(side="right", padx=(5, 0))

        self.nav_next_btn = ctk.CTkButton(
            top_bar, text="Next ▶", width=60, command=self._next_preview
        )
        self.nav_next_btn.pack(side="right", padx=(0, 5))

        self.preview_counter_lbl = ctk.CTkLabel(
            top_bar, text="Photo 0 / 0", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.preview_counter_lbl.pack(side="right", padx=10)

        # Center Preview Canvas / Label Container
        self.preview_container = ctk.CTkFrame(self.main_panel, fg_color="gray15")
        self.preview_container.grid(row=1, column=0, sticky="nsew", pady=5)
        self.preview_container.grid_rowconfigure(0, weight=1)
        self.preview_container.grid_columnconfigure(0, weight=1)

        self.preview_label = ctk.CTkLabel(
            self.preview_container,
            text="🖼️ Live Preview Box\n\n1. Load a Custom PNG Frame\n2. Add Photo(s)\n3. See live composite result here!",
            font=ctk.CTkFont(size=14),
            text_color="gray60"
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        # Bottom Progress & Photo List Frame
        bottom_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        bottom_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(bottom_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(0, 5))

        self.status_label = ctk.CTkLabel(
            bottom_frame, text="Ready. Add photos and frame to start.", font=ctk.CTkFont(size=11), text_color="gray70", anchor="w"
        )
        self.status_label.pack(fill="x")

    # ==========================================
    # HELPER & EVENT HANDLERS
    # ==========================================
    def _create_number_input(self, parent, label_text, default_val):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=2)
        lbl = ctk.CTkLabel(frame, text=label_text, font=ctk.CTkFont(size=11), width=100, anchor="w")
        lbl.pack(side="left")
        entry = ctk.CTkEntry(frame, width=80, font=ctk.CTkFont(size=11))
        entry.insert(0, str(default_val))
        entry.pack(side="right")
        entry.bind("<KeyRelease>", lambda _: self._on_manual_aperture_change())
        return entry

    def _add_separator(self):
        sep = ctk.CTkFrame(self.sidebar, height=2, fg_color="gray30")
        sep.pack(fill="x", pady=12)

    def _on_toggle_manual_aperture(self):
        if self.manual_aperture_switch.get() == 1:
            self.aperture_frame.pack(fill="x", pady=5)
        else:
            self.aperture_frame.pack_forget()
            if self.frame_img:
                self.aperture = FrameEngine.detect_aperture(self.frame_img)
                self._update_aperture_entries()
        self._update_preview()

    def _update_aperture_entries(self):
        x, y, w, h = self.aperture
        self.entry_ap_x.delete(0, 'end')
        self.entry_ap_x.insert(0, str(x))
        self.entry_ap_y.delete(0, 'end')
        self.entry_ap_y.insert(0, str(y))
        self.entry_ap_w.delete(0, 'end')
        self.entry_ap_w.insert(0, str(w))
        self.entry_ap_h.delete(0, 'end')
        self.entry_ap_h.insert(0, str(h))

    def _on_manual_aperture_change(self):
        try:
            x = int(self.entry_ap_x.get())
            y = int(self.entry_ap_y.get())
            w = int(self.entry_ap_w.get())
            h = int(self.entry_ap_h.get())
            self.aperture = (x, y, max(1, w), max(1, h))
            self.aperture_info_lbl.configure(text=f"Aperture: {x}, {y} ({w}x{h})")
            self._update_preview()
        except ValueError:
            pass

    def _on_select_frame(self):
        file_path = filedialog.askopenfilename(
            title="Select Custom PNG Frame Overlay",
            filetypes=[("PNG Files", "*.png"), ("All Supported", "*.png;*.webp;*.tga")]
        )
        if file_path:
            try:
                img = Image.open(file_path)
                self.frame_path = file_path
                self.frame_img = img.convert('RGBA')
                w, h = self.frame_img.size

                # Auto detect aperture
                self.aperture = FrameEngine.detect_aperture(self.frame_img)
                ax, ay, aw, ah = self.aperture

                self.btn_select_frame.configure(text=f"🖼️ {os.path.basename(file_path)}")
                self.frame_info_lbl.configure(
                    text=f"Frame Size: {w} x {h} px\nPath: ...{file_path[-30:]}",
                    text_color="gray85"
                )
                self.aperture_info_lbl.configure(text=f"Aperture Window: {ax}, {ay} ({aw}x{ah})")
                self._update_aperture_entries()

                self._update_preview()
            except Exception as e:
                messagebox.showerror("Frame Error", f"Failed to load PNG frame:\n{str(e)}")

    def _on_add_photos(self):
        files = filedialog.askopenfilenames(
            title="Select Photos to Frame",
            filetypes=[("Image Files", "*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.tiff")]
        )
        if files:
            for f in files:
                if f not in self.photo_paths:
                    self.photo_paths.append(f)
            self._update_photo_counter()
            self._update_preview()

    def _on_add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder containing Photos")
        if folder:
            valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
            added = 0
            for root, _, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith(valid_exts):
                        full_p = os.path.join(root, file)
                        if full_p not in self.photo_paths:
                            self.photo_paths.append(full_p)
                            added += 1
            self._update_photo_counter()
            self._update_preview()

    def _on_clear_photos(self):
        self.photo_paths.clear()
        self.current_preview_index = 0
        self._update_photo_counter()
        self.preview_label.configure(
            image=None,
            text="🖼️ Live Preview Box\n\n1. Load a Custom PNG Frame\n2. Add Photo(s)\n3. See live composite result here!"
        )

    def _update_photo_counter(self):
        count = len(self.photo_paths)
        self.btn_start_batch.configure(text=f"🚀 START BATCH PROCESS ({count})")
        if count == 0:
            self.preview_counter_lbl.configure(text="Photo 0 / 0")
        else:
            self.preview_counter_lbl.configure(text=f"Photo {self.current_preview_index + 1} / {count}")

    def _prev_preview(self):
        if self.photo_paths:
            self.current_preview_index = (self.current_preview_index - 1) % len(self.photo_paths)
            self._update_photo_counter()
            self._update_preview()

    def _next_preview(self):
        if self.photo_paths:
            self.current_preview_index = (self.current_preview_index + 1) % len(self.photo_paths)
            self._update_photo_counter()
            self._update_preview()

    def _on_format_change(self, choice):
        if choice in ["JPEG", "WEBP"]:
            self.quality_slider.configure(state="normal")
            self.quality_label.configure(text_color="gray90")
        else:
            self.quality_slider.configure(state="disabled")
            self.quality_label.configure(text_color="gray50")

    def _on_quality_change(self, val):
        self.quality_label.configure(text=f"JPEG/WEBP Quality: {int(val)}%")

    def _on_select_out_dir(self):
        dir_selected = filedialog.askdirectory(title="Select Output Folder")
        if dir_selected:
            self.output_dir = dir_selected
            self.btn_select_out_dir.configure(text=f"📁 {os.path.basename(self.output_dir)}")

    def _update_preview(self):
        if not self.frame_img:
            return

        if not self.photo_paths:
            # Render frame preview only
            try:
                preview_frame = self.frame_img.copy()
                preview_frame.thumbnail((550, 550), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=preview_frame, dark_image=preview_frame, size=preview_frame.size)
                self.preview_label.configure(image=ctk_img, text="")
            except Exception:
                pass
            return

        photo_path = self.photo_paths[self.current_preview_index]
        fit_mode = self.fit_mode_combo.get()
        layer_order = self.layer_order_combo.get()

        try:
            with Image.open(photo_path) as photo_img:
                composite = FrameEngine.composite_image(
                    photo_img=photo_img,
                    frame_img=self.frame_img,
                    aperture=self.aperture,
                    fit_mode=fit_mode,
                    layer_order=layer_order
                )

                # Thumbnail resize for smooth high-DPI preview display
                disp_w = max(1, self.preview_container.winfo_width() - 40)
                disp_h = max(1, self.preview_container.winfo_height() - 40)
                if disp_w < 100 or disp_h < 100:
                    disp_w, disp_h = 550, 550

                composite.thumbnail((disp_w, disp_h), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=composite, dark_image=composite, size=composite.size)
                self.preview_label.configure(image=ctk_img, text="")
        except Exception as e:
            self.preview_label.configure(image=None, text=f"Preview Error:\n{str(e)}")

    # ==========================================
    # BATCH PROCESS EXECUTION
    # ==========================================
    def _start_batch_process(self):
        if not self.frame_path or not self.frame_img:
            messagebox.showwarning("Missing Frame", "Please select a PNG frame overlay first.")
            return

        if not self.photo_paths:
            messagebox.showwarning("No Photos", "Please add at least one photo to process.")
            return

        if self.is_processing:
            return

        self.is_processing = True
        self.btn_start_batch.configure(state="disabled", text="⏳ Processing Batch...")
        self.progress_bar.set(0)

        # Read config values
        photo_paths = list(self.photo_paths)
        frame_path = self.frame_path
        aperture = self.aperture
        fit_mode = self.fit_mode_combo.get()
        layer_order = self.layer_order_combo.get()
        out_dir = self.output_dir
        out_fmt = self.format_combo.get()
        jpeg_qual = int(self.quality_slider.get())
        naming_pattern = self.entry_naming.get().strip() or "framed_{filename}"

        # Run background thread
        threading.Thread(
            target=self._run_batch_worker,
            args=(photo_paths, frame_path, aperture, fit_mode, layer_order, out_dir, out_fmt, jpeg_qual, naming_pattern),
            daemon=True
        ).start()

    def _run_batch_worker(
        self, photo_paths, frame_path, aperture, fit_mode, layer_order, out_dir, out_fmt, jpeg_qual, naming_pattern
    ):
        def progress_cb(completed, total, file_path, success):
            frac = completed / max(1, total)
            fname = os.path.basename(file_path)
            status_text = f"[{completed}/{total}] {'✅' if success else '❌'} {fname}"
            self.after(0, self._update_batch_progress, frac, status_text)

        results = FrameEngine.process_batch(
            photo_paths=photo_paths,
            frame_path=frame_path,
            aperture=aperture,
            fit_mode=fit_mode,
            layer_order=layer_order,
            output_dir=out_dir,
            output_format=out_fmt,
            jpeg_quality=jpeg_qual,
            naming_pattern=naming_pattern,
            progress_callback=progress_cb
        )

        success_count = sum(1 for r in results if r[0])
        self.after(0, self._on_batch_complete, success_count, len(results))

    def _update_batch_progress(self, frac, status_text):
        self.progress_bar.set(frac)
        self.status_label.configure(text=status_text)

    def _on_batch_complete(self, success_count, total):
        self.is_processing = False
        self.btn_start_batch.configure(state="normal", text=f"🚀 START BATCH PROCESS ({len(self.photo_paths)})")
        self.status_label.configure(text=f"🎉 Batch Complete! {success_count} / {total} photos successfully framed.")

        answer = messagebox.askyesno(
            "Batch Completed!",
            f"Successfully processed {success_count} of {total} images!\n\nWould you like to open the output folder now?"
        )
        if answer:
            self._open_output_folder()

    def _open_output_folder(self):
        os.makedirs(self.output_dir, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(self.output_dir)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', self.output_dir])
        else:
            subprocess.Popen(['xdg-open', self.output_dir])


if __name__ == "__main__":
    app = PNGFrameStudio()
    app.mainloop()

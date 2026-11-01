use std::{
    fs,
    io::{BufReader, Cursor},
    path::{Path, PathBuf},
};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use image::{
    imageops::{self, FilterType},
    DynamicImage, ImageBuffer, ImageEncoder, ImageFormat, Rgba, RgbaImage,
};
use serde::{Deserialize, Serialize};
use tauri::Emitter;

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum FitMode {
    Fit,
    Fill,
    StretchAperture,
    StretchFrameToPhoto,
    StretchPhotoToFrame,
}

#[derive(Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum LayerOrder {
    FrameOver,
    PhotoOver,
}

#[derive(Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum ExportFormat {
    Png,
    Jpeg,
    Webp,
    Original,
}

#[derive(Clone, Copy, Serialize, Deserialize)]
struct Aperture {
    x: u32,
    y: u32,
    width: u32,
    height: u32,
}

#[derive(Serialize)]
struct FrameInfo {
    path: String,
    width: u32,
    height: u32,
    aperture: Aperture,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct PreviewRequest {
    frame_path: String,
    photo_path: Option<String>,
    aperture: Aperture,
    fit: FitMode,
    layer: LayerOrder,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExportRequest {
    photos: Vec<String>,
    frame_path: String,
    aperture: Aperture,
    fit: FitMode,
    layer: LayerOrder,
    output_dir: String,
    format: ExportFormat,
    quality: u8,
    naming: String,
}

#[derive(Serialize, Clone)]
struct ExportProgress {
    completed: usize,
    total: usize,
    name: String,
    success: bool,
    detail: String,
}

#[derive(Serialize)]
struct ExportSummary {
    succeeded: usize,
    total: usize,
}

#[tauri::command]
fn pick_frame() -> Option<String> {
    rfd::FileDialog::new()
        .add_filter("Transparent frame", &["png", "webp", "bmp", "jpg", "jpeg"])
        .pick_file()
        .map(|path| path.to_string_lossy().into_owned())
}

#[tauri::command]
fn pick_photos() -> Vec<String> {
    rfd::FileDialog::new()
        .add_filter(
            "Photos",
            &["jpg", "jpeg", "png", "webp", "bmp", "tiff", "tif"],
        )
        .pick_files()
        .unwrap_or_default()
        .into_iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect()
}

#[tauri::command]
fn pick_folder() -> Option<String> {
    rfd::FileDialog::new()
        .pick_folder()
        .map(|path| path.to_string_lossy().into_owned())
}

#[tauri::command]
fn pick_output_folder(current: String) -> Option<String> {
    rfd::FileDialog::new()
        .set_directory(current)
        .pick_folder()
        .map(|path| path.to_string_lossy().into_owned())
}

#[tauri::command]
fn default_output_folder() -> String {
    std::env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("output")
        .to_string_lossy()
        .into_owned()
}

#[tauri::command]
fn load_frame(path: String) -> Result<FrameInfo, String> {
    let image = image::open(&path).map_err(|error| error.to_string())?;
    let frame = image.into_rgba8();
    let (width, height) = frame.dimensions();
    Ok(FrameInfo {
        path,
        width,
        height,
        aperture: detect_aperture(&frame),
    })
}

#[tauri::command]
fn scan_folder(path: String) -> Result<Vec<String>, String> {
    collect_images(Path::new(&path)).map(|paths| {
        paths
            .into_iter()
            .map(|path| path.to_string_lossy().into_owned())
            .collect()
    })
}

#[tauri::command]
fn preview(request: PreviewRequest) -> Result<String, String> {
    let frame = image::open(&request.frame_path)
        .map_err(|error| error.to_string())?
        .into_rgba8();
    let frame_dimensions = frame.dimensions();
    let mut image = if let Some(photo_path) = request.photo_path {
        let photo = load_photo(Path::new(&photo_path))?;
        composite(&photo, &frame, request.aperture, request.fit, request.layer)
    } else {
        frame
    };
    image = preview_canvas(&image, frame_dimensions);
    let image = thumbnail(&image, 1800, 1200);
    let mut png = Cursor::new(Vec::new());
    image::codecs::png::PngEncoder::new(&mut png)
        .write_image(
            image.as_raw(),
            image.width(),
            image.height(),
            image::ColorType::Rgba8.into(),
        )
        .map_err(|error| error.to_string())?;
    Ok(format!(
        "data:image/png;base64,{}",
        BASE64.encode(png.into_inner())
    ))
}

#[tauri::command]
fn add_paths(paths: Vec<String>) -> Result<Vec<String>, String> {
    let mut images = Vec::new();
    for path in paths {
        let path = PathBuf::from(path);
        if path.is_dir() {
            images.extend(collect_images(&path)?);
        } else if is_supported_image(&path) {
            images.push(path);
        }
    }
    images.sort();
    images.dedup();
    Ok(images
        .into_iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect())
}

#[tauri::command]
async fn export_batch(
    app: tauri::AppHandle,
    request: ExportRequest,
) -> Result<ExportSummary, String> {
    tauri::async_runtime::spawn_blocking(move || run_export(app, request))
        .await
        .map_err(|error| error.to_string())?
}

#[tauri::command]
fn open_output_folder(path: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    fs::create_dir_all(&path).map_err(|error| error.to_string())?;
    #[cfg(target_os = "windows")]
    let result = std::process::Command::new("explorer").arg(&path).spawn();
    #[cfg(target_os = "macos")]
    let result = std::process::Command::new("open").arg(&path).spawn();
    #[cfg(all(unix, not(target_os = "macos")))]
    let result = std::process::Command::new("xdg-open").arg(&path).spawn();
    result.map(|_| ()).map_err(|error| error.to_string())
}

fn run_export(app: tauri::AppHandle, request: ExportRequest) -> Result<ExportSummary, String> {
    let frame = image::open(&request.frame_path)
        .map_err(|error| format!("Could not load frame: {error}"))?
        .into_rgba8();
    let output_dir = PathBuf::from(&request.output_dir);
    fs::create_dir_all(&output_dir).map_err(|error| error.to_string())?;

    let total = request.photos.len();
    let mut succeeded = 0;
    for (index, photo_path) in request.photos.iter().enumerate() {
        let path = Path::new(photo_path);
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("image")
            .to_owned();
        let result = export_one(path, &frame, &request, &output_dir);
        let (success, detail, name) = match result {
            Ok(output) => {
                succeeded += 1;
                (
                    true,
                    String::new(),
                    output
                        .file_name()
                        .and_then(|v| v.to_str())
                        .unwrap_or("image")
                        .to_owned(),
                )
            }
            Err(error) => (false, error, name),
        };
        let _ = app.emit(
            "export-progress",
            ExportProgress {
                completed: index + 1,
                total,
                name,
                success,
                detail,
            },
        );
    }
    Ok(ExportSummary { succeeded, total })
}

fn export_one(
    path: &Path,
    frame: &RgbaImage,
    request: &ExportRequest,
    output_dir: &Path,
) -> Result<PathBuf, String> {
    let photo = load_photo(path)?;
    let result = composite(&photo, frame, request.aperture, request.fit, request.layer);
    let stem = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("image");
    let pattern = if request.naming.trim().is_empty() {
        "framed_{filename}"
    } else {
        request.naming.trim()
    };
    let expanded = pattern.replace("{filename}", stem);
    let output_stem = Path::new(&expanded)
        .file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| "Filename pattern must produce a valid file name.".to_owned())?;

    let format = match request.format {
        ExportFormat::Original => match path
            .extension()
            .and_then(|extension| extension.to_str())
            .unwrap_or("")
            .to_ascii_lowercase()
            .as_str()
        {
            "jpg" | "jpeg" => ExportFormat::Jpeg,
            "webp" => ExportFormat::Webp,
            _ => ExportFormat::Png,
        },
        format => format,
    };
    let extension = match format {
        ExportFormat::Png => "png",
        ExportFormat::Jpeg => "jpg",
        ExportFormat::Webp => "webp",
        ExportFormat::Original => unreachable!(),
    };
    let output_name = if output_stem
        .to_ascii_lowercase()
        .ends_with(&format!(".{extension}"))
    {
        output_stem.to_owned()
    } else {
        format!("{output_stem}.{extension}")
    };
    let destination = output_dir.join(output_name);
    match format {
        ExportFormat::Png => DynamicImage::ImageRgba8(result)
            .save_with_format(&destination, ImageFormat::Png)
            .map_err(|error| error.to_string())?,
        ExportFormat::Jpeg => {
            let mut rgb = ImageBuffer::from_pixel(
                result.width(),
                result.height(),
                image::Rgb([255, 255, 255]),
            );
            for (x, y, pixel) in result.enumerate_pixels() {
                let alpha = pixel[3] as u16;
                let inverse_alpha = 255 - alpha;
                rgb.put_pixel(
                    x,
                    y,
                    image::Rgb([
                        ((pixel[0] as u16 * alpha + 255 * inverse_alpha + 127) / 255) as u8,
                        ((pixel[1] as u16 * alpha + 255 * inverse_alpha + 127) / 255) as u8,
                        ((pixel[2] as u16 * alpha + 255 * inverse_alpha + 127) / 255) as u8,
                    ]),
                );
            }
            let file = fs::File::create(&destination).map_err(|error| error.to_string())?;
            image::codecs::jpeg::JpegEncoder::new_with_quality(file, request.quality)
                .encode_image(&DynamicImage::ImageRgb8(rgb))
                .map_err(|error| error.to_string())?;
        }
        ExportFormat::Webp => {
            let encoder = webp::Encoder::from_rgba(&result, result.width(), result.height());
            let encoded = if request.quality == 100 {
                encoder.encode_lossless()
            } else {
                encoder.encode(request.quality as f32)
            };
            fs::write(&destination, &*encoded).map_err(|error| error.to_string())?;
        }
        ExportFormat::Original => unreachable!(),
    }
    Ok(destination)
}

fn is_supported_image(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|extension| extension.to_str())
            .unwrap_or("")
            .to_ascii_lowercase()
            .as_str(),
        "jpg" | "jpeg" | "png" | "webp" | "bmp" | "tif" | "tiff"
    )
}

fn collect_images(folder: &Path) -> Result<Vec<PathBuf>, String> {
    let mut images = Vec::new();
    for entry in walkdir::WalkDir::new(folder) {
        let entry = entry.map_err(|error| error.to_string())?;
        if entry.file_type().is_file() && is_supported_image(entry.path()) {
            images.push(entry.path().to_path_buf());
        }
    }
    Ok(images)
}

fn detect_aperture(frame: &RgbaImage) -> Aperture {
    let mut bounds: Option<(u32, u32, u32, u32)> = None;
    for (x, y, pixel) in frame.enumerate_pixels() {
        if pixel[3] < 128 {
            bounds = Some(match bounds {
                Some((left, top, right, bottom)) => {
                    (left.min(x), top.min(y), right.max(x), bottom.max(y))
                }
                None => (x, y, x, y),
            });
        }
    }
    match bounds {
        Some((left, top, right, bottom)) => Aperture {
            x: left,
            y: top,
            width: right - left + 1,
            height: bottom - top + 1,
        },
        None => Aperture {
            x: 0,
            y: 0,
            width: frame.width(),
            height: frame.height(),
        },
    }
}

fn load_photo(path: &Path) -> Result<RgbaImage, String> {
    let image = image::open(path).map_err(|error| error.to_string())?;
    let orientation = fs::File::open(path)
        .ok()
        .and_then(|file| {
            exif::Reader::new()
                .read_from_container(&mut BufReader::new(file))
                .ok()
        })
        .and_then(|data| {
            data.get_field(exif::Tag::Orientation, exif::In::PRIMARY)
                .and_then(|field| field.value.get_uint(0))
        })
        .unwrap_or(1);
    let rgba = image.into_rgba8();
    Ok(match orientation {
        2 => imageops::flip_horizontal(&rgba),
        3 => imageops::rotate180(&rgba),
        4 => imageops::flip_vertical(&rgba),
        5 => imageops::rotate90(&imageops::flip_horizontal(&rgba)),
        6 => imageops::rotate90(&rgba),
        7 => imageops::rotate270(&imageops::flip_horizontal(&rgba)),
        8 => imageops::rotate270(&rgba),
        _ => rgba,
    })
}

fn composite(
    photo: &RgbaImage,
    frame: &RgbaImage,
    aperture: Aperture,
    fit: FitMode,
    layer: LayerOrder,
) -> RgbaImage {
    let (frame_width, frame_height) = frame.dimensions();
    let (photo_width, photo_height) = photo.dimensions();
    let area_width = aperture.width.max(1);
    let area_height = aperture.height.max(1);

    if matches!(fit, FitMode::StretchFrameToPhoto) {
        let mut resized_frame =
            imageops::resize(frame, photo_width, photo_height, FilterType::Lanczos3);
        let scaled_aperture = Aperture {
            x: scale(aperture.x, photo_width, frame_width),
            y: scale(aperture.y, photo_height, frame_height),
            width: scale(area_width, photo_width, frame_width).max(1),
            height: scale(area_height, photo_height, frame_height).max(1),
        };
        if matches!(layer, LayerOrder::FrameOver) {
            let mut canvas = photo.clone();
            imageops::overlay(&mut canvas, &resized_frame, 0, 0);
            return canvas;
        }
        let fitted = resize_to_fill(
            photo,
            scaled_aperture.width,
            scaled_aperture.height,
            FilterType::Lanczos3,
        );
        imageops::overlay(
            &mut resized_frame,
            &fitted,
            scaled_aperture.x as i64,
            scaled_aperture.y as i64,
        );
        return resized_frame;
    }

    let mut canvas = ImageBuffer::from_pixel(frame_width, frame_height, Rgba([0, 0, 0, 0]));
    let full_photo = matches!(fit, FitMode::StretchPhotoToFrame);
    let (target_x, target_y, target_width, target_height) = if full_photo {
        (0, 0, frame_width, frame_height)
    } else {
        (aperture.x, aperture.y, area_width, area_height)
    };
    let fitted = match fit {
        FitMode::Fill => resize_to_fill(photo, target_width, target_height, FilterType::Lanczos3),
        FitMode::Fit => resize_to_fit(photo, target_width, target_height),
        FitMode::StretchAperture | FitMode::StretchPhotoToFrame => imageops::resize(
            photo,
            target_width.max(1),
            target_height.max(1),
            FilterType::Lanczos3,
        ),
        FitMode::StretchFrameToPhoto => unreachable!(),
    };
    let (photo_x, photo_y) = if matches!(fit, FitMode::Fit) {
        (
            target_x + target_width.saturating_sub(fitted.width()) / 2,
            target_y + target_height.saturating_sub(fitted.height()) / 2,
        )
    } else {
        (target_x, target_y)
    };
    if matches!(layer, LayerOrder::FrameOver) {
        imageops::overlay(&mut canvas, &fitted, photo_x as i64, photo_y as i64);
        imageops::overlay(&mut canvas, frame, 0, 0);
    } else {
        imageops::overlay(&mut canvas, frame, 0, 0);
        imageops::overlay(&mut canvas, &fitted, photo_x as i64, photo_y as i64);
    }
    canvas
}

fn scale(value: u32, new_size: u32, old_size: u32) -> u32 {
    ((value as u64 * new_size as u64) / old_size.max(1) as u64) as u32
}

fn resize_to_fit(photo: &RgbaImage, width: u32, height: u32) -> RgbaImage {
    let factor = (width as f64 / photo.width().max(1) as f64)
        .min(height as f64 / photo.height().max(1) as f64);
    let new_width = ((photo.width() as f64 * factor).floor() as u32).max(1);
    let new_height = ((photo.height() as f64 * factor).floor() as u32).max(1);
    imageops::resize(photo, new_width, new_height, FilterType::Lanczos3)
}

fn resize_to_fill(photo: &RgbaImage, width: u32, height: u32, filter: FilterType) -> RgbaImage {
    let factor = (width as f64 / photo.width().max(1) as f64)
        .max(height as f64 / photo.height().max(1) as f64);
    let scaled_width = ((photo.width() as f64 * factor).ceil() as u32).max(width);
    let scaled_height = ((photo.height() as f64 * factor).ceil() as u32).max(height);
    let scaled = imageops::resize(photo, scaled_width, scaled_height, filter);
    imageops::crop_imm(
        &scaled,
        (scaled_width - width) / 2,
        (scaled_height - height) / 2,
        width,
        height,
    )
    .to_image()
}

fn thumbnail(image: &RgbaImage, max_width: u32, max_height: u32) -> RgbaImage {
    let factor = (max_width as f64 / image.width().max(1) as f64)
        .min(max_height as f64 / image.height().max(1) as f64)
        .min(1.0);
    imageops::resize(
        image,
        ((image.width() as f64 * factor).round() as u32).max(1),
        ((image.height() as f64 * factor).round() as u32).max(1),
        FilterType::Lanczos3,
    )
}

fn preview_canvas(image: &RgbaImage, frame_size: (u32, u32)) -> RgbaImage {
    if image.dimensions() == frame_size {
        image.clone()
    } else {
        imageops::resize(image, frame_size.0, frame_size.1, FilterType::Lanczos3)
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            pick_frame,
            pick_photos,
            pick_folder,
            pick_output_folder,
            default_output_folder,
            load_frame,
            scan_folder,
            add_paths,
            preview,
            export_batch,
            open_output_folder
        ])
        .run(tauri::generate_context!())
        .expect("error while running Frame Studio");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_transparent_aperture_bounds() {
        let mut frame = RgbaImage::from_pixel(40, 30, Rgba([20, 20, 20, 255]));
        for y in 7..19 {
            for x in 9..25 {
                frame.put_pixel(x, y, Rgba([0, 0, 0, 0]));
            }
        }
        let aperture = detect_aperture(&frame);
        assert_eq!(
            (aperture.x, aperture.y, aperture.width, aperture.height),
            (9, 7, 16, 12)
        );
    }

    #[test]
    fn preview_thumbnail_preserves_portrait_and_landscape_aspect_ratios() {
        let landscape = RgbaImage::from_pixel(1920, 1080, Rgba([255, 0, 0, 255]));
        let landscape_preview = thumbnail(&landscape, 1400, 1000);
        assert_eq!(landscape_preview.dimensions(), (1400, 788));
        let portrait = RgbaImage::from_pixel(1080, 1920, Rgba([255, 0, 0, 255]));
        let portrait_preview = thumbnail(&portrait, 1400, 1000);
        assert_eq!(portrait_preview.dimensions(), (563, 1000));
    }

    #[test]
    fn aperture_previews_keep_the_selected_frame_dimensions() {
        let photo = RgbaImage::from_pixel(120, 80, Rgba([40, 130, 180, 255]));
        let frame = RgbaImage::from_pixel(96, 64, Rgba([0, 0, 0, 0]));
        let aperture = Aperture {
            x: 8,
            y: 8,
            width: 80,
            height: 48,
        };
        for fit in [
            FitMode::Fit,
            FitMode::Fill,
            FitMode::StretchAperture,
            FitMode::StretchPhotoToFrame,
            FitMode::StretchFrameToPhoto,
        ] {
            let result = composite(&photo, &frame, aperture, fit, LayerOrder::FrameOver);
            let preview = preview_canvas(&result, frame.dimensions());
            assert_eq!(
                preview.dimensions(),
                frame.dimensions(),
                "fit mode: {fit:?}"
            );
        }
    }

    #[test]
    fn opaque_frame_uses_full_bounds() {
        let frame = RgbaImage::from_pixel(8, 6, Rgba([255, 0, 0, 255]));
        let aperture = detect_aperture(&frame);
        assert_eq!(
            (aperture.x, aperture.y, aperture.width, aperture.height),
            (0, 0, 8, 6)
        );
    }
}

/**
 * Hasarİ desktop — Rust backend.
 *
 * Tauri 2 commands exposed to the React frontend:
 *  - app_info         : runtime / version / platform info
 *  - pick_files       : native multi-file image picker (returns absolute paths)
 *  - pick_folder      : native folder picker
 *  - read_image       : raw bytes for a given path (used by frontend to build Blobs/Files)
 *  - save_report      : writes a UTF-8 string (CSV) or base64 (PDF) to a user-chosen path
 *  - open_in_explorer : reveal a file/folder in the host file manager
 *  - show_notification: native OS toast
 *
 * Plugins enabled: dialog, fs, shell (open), notification, os, store, window-state, single-instance.
 */
use std::path::PathBuf;

use serde::Serialize;
use tauri::{Emitter, Manager};

#[derive(Serialize)]
struct AppInfo {
    name: String,
    version: String,
    platform: String,
}

#[tauri::command]
fn app_info() -> AppInfo {
    AppInfo {
        name: "Hasarİ".into(),
        version: env!("CARGO_PKG_VERSION").into(),
        platform: std::env::consts::OS.into(),
    }
}

#[tauri::command]
async fn pick_files(app: tauri::AppHandle) -> Result<Vec<PathBuf>, String> {
    use tauri_plugin_dialog::DialogExt;
    // `blocking_pick_files` runs the dialog on the main thread and returns when the
    // user closes it. Using the blocking variant from an async command keeps the
    // surface tiny — Tauri runs commands on its async runtime, not the UI thread.
    let files = app
        .dialog()
        .file()
        .add_filter("Görüntü", &["jpg", "jpeg", "png", "webp"])
        .blocking_pick_files();
    Ok(files
        .unwrap_or_default()
        .into_iter()
        .filter_map(|p| p.into_path().ok())
        .collect())
}

#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Result<Option<PathBuf>, String> {
    use tauri_plugin_dialog::DialogExt;
    let folder = app.dialog().file().blocking_pick_folder();
    Ok(folder.and_then(|p| p.into_path().ok()))
}

#[tauri::command]
fn read_image(path: String) -> Result<Vec<u8>, String> {
    std::fs::read(&path).map_err(|e| format!("Dosya okunamadı: {} ({})", path, e))
}

/// Writes a report to disk. `content` is either UTF-8 text (CSV) or base64 (PDF).
/// `format` ∈ {"csv","pdf","json","txt"}. Returns the path it was saved to.
#[tauri::command]
async fn save_report(
    app: tauri::AppHandle,
    inspection_id: String,
    format: String,
    content: String,
) -> Result<String, String> {
    use tauri_plugin_dialog::DialogExt;
    let fmt = format.to_lowercase();
    let ext = match fmt.as_str() {
        "csv" => "csv",
        "pdf" => "pdf",
        "json" => "json",
        _ => "txt",
    };
    let default_name = format!("inspection_{}.{}", inspection_id, ext);
    let chosen = app
        .dialog()
        .file()
        .set_file_name(&default_name)
        .add_filter(ext, &[ext])
        .blocking_save_file();
    let path = chosen
        .and_then(|p| p.into_path().ok())
        .ok_or_else(|| "İptal edildi".to_string())?;
    if fmt == "pdf" {
        // Decode base64 → bytes
        let bytes = decode_b64(&content).map_err(|e| format!("base64 hatası: {}", e))?;
        std::fs::write(&path, bytes).map_err(|e| e.to_string())?;
    } else {
        std::fs::write(&path, content.as_bytes()).map_err(|e| e.to_string())?;
    }
    Ok(path.to_string_lossy().to_string())
}

#[tauri::command]
fn open_in_explorer(_app: tauri::AppHandle, path: String) -> Result<(), String> {
    // Cross-platform reveal: `explorer /select,` (Win), `open -R` (Mac), `xdg-open` (Linux).
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg("/select,")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
        return Ok(());
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg("-R")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
        return Ok(());
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        std::process::Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
        Ok(())
    }
}

#[tauri::command]
async fn show_notification(
    app: tauri::AppHandle,
    title: String,
    body: String,
) -> Result<(), String> {
    use tauri_plugin_notification::NotificationExt;
    app.notification()
        .builder()
        .title(title)
        .body(body)
        .show()
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Minimal base64 decoder (avoid extra dependency).
fn decode_b64(input: &str) -> Result<Vec<u8>, &'static str> {
    const CHARSET: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut buf = Vec::with_capacity(input.len() * 3 / 4);
    let mut acc: u32 = 0;
    let mut bits: u32 = 0;
    for b in input.bytes().filter(|c| !c.is_ascii_whitespace()) {
        if b == b'=' {
            break;
        }
        let v = CHARSET.iter().position(|&c| c == b).ok_or("invalid char")? as u32;
        acc = (acc << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            buf.push(((acc >> bits) & 0xFF) as u8);
        }
    }
    Ok(buf)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default();

    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // Re-focus existing window when a second instance is launched.
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
                let _ = w.unminimize();
                let _ = app.emit("single-instance", ());
            }
        }));
    }

    builder
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![
            app_info,
            pick_files,
            pick_folder,
            read_image,
            save_report,
            open_in_explorer,
            show_notification
        ])
        .setup(|_app| {
            // Auto-update placeholder — wire a real updater plugin here later.
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Tauri uygulaması başlatılamadı");
}

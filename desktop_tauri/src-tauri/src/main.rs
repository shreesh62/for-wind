// FRIDAY Desktop — Tauri backend entry point.
//
// Responsibilities:
// - Launch the Python FRIDAY API server as a sidecar process
// - System tray integration
// - Window management
//
// Prevents an extra console window on Windows in release.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, State,
};

/// Holds the Python backend process handle so we can clean it up.
struct BackendProcess(Mutex<Option<Child>>);

/// Start the Python FRIDAY API server as a child process.
fn start_backend() -> Option<Child> {
    // In production, the Python backend is bundled; in dev it runs from repo.
    let result = Command::new("python")
        .args(["-m", "friday.api.server"])
        .current_dir("..")
        .spawn();

    match result {
        Ok(child) => {
            println!("[FRIDAY] Backend started (pid {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[FRIDAY] Failed to start backend: {}", e);
            None
        }
    }
}

#[tauri::command]
fn backend_status(state: State<BackendProcess>) -> String {
    let guard = state.0.lock().unwrap();
    if guard.is_some() {
        "running".to_string()
    } else {
        "stopped".to_string()
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(start_backend())))
        .setup(|app| {
            // System tray
            let show = MenuItem::with_id(app, "show", "Show FRIDAY", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("FRIDAY")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.show();
                            let _ = win.set_focus();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_status])
        .on_window_event(|window, event| {
            // Hide to tray instead of closing
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building FRIDAY")
        .run(|app_handle, event| {
            // Clean up backend on exit
            if let tauri::RunEvent::ExitRequested { .. } = event {
                let state: State<BackendProcess> = app_handle.state();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                    println!("[FRIDAY] Backend stopped");
                }
            }
        });
}

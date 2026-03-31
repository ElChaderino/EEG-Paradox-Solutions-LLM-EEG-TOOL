// Copyright (C) 2026  EEG Paradox Solutions LLM contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// This file is part of Paradox Solutions LLM. See LICENSE in the repository root.

use serde::Serialize;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{
    AppHandle, Emitter, Manager, State,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::TrayIconBuilder,
};
use tokio::process::Command as TokioCommand;

// ── Shared state ───────────────────────────────────────────────────────

struct ApiProcess(Mutex<Option<u32>>);

// ── Data types for frontend communication ──────────────────────────────

#[derive(Clone, Serialize)]
struct SetupProgress {
    stage: String,
    detail: String,
    done: bool,
}

// ── Path helpers ───────────────────────────────────────────────────────

fn ollama_exe_path() -> Option<PathBuf> {
    let candidates = [
        dirs::data_local_dir().map(|d| d.join("Programs").join("Ollama").join("ollama.exe")),
        Some(PathBuf::from(r"C:\Program Files\Ollama\ollama.exe")),
        Some(PathBuf::from(r"C:\Program Files (x86)\Ollama\ollama.exe")),
    ];
    for c in candidates.into_iter().flatten() {
        if c.exists() {
            return Some(c);
        }
    }
    which_in_path("ollama")
}

fn which_in_path(name: &str) -> Option<PathBuf> {
    std::env::var_os("PATH").and_then(|paths| {
        std::env::split_paths(&paths).find_map(|dir| {
            let full = dir.join(format!("{name}.exe"));
            full.exists().then_some(full)
        })
    })
}

fn appdata_dir() -> PathBuf {
    dirs::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("ParadoxSolutionsLLM")
}

// ── Tauri commands ─────────────────────────────────────────────────────

#[tauri::command]
async fn check_ollama() -> Result<bool, String> {
    Ok(ollama_exe_path().is_some())
}

#[tauri::command]
async fn get_ollama_models() -> Result<Vec<String>, String> {
    let ollama = ollama_exe_path().ok_or("Ollama not found")?;
    let output = TokioCommand::new(&ollama)
        .arg("list")
        .output()
        .await
        .map_err(|e| e.to_string())?;
    let text = String::from_utf8_lossy(&output.stdout);
    let models: Vec<String> = text
        .lines()
        .skip(1)
        .filter_map(|line| line.split_whitespace().next().map(String::from))
        .collect();
    Ok(models)
}

#[tauri::command]
async fn pull_model(app: AppHandle, model: String) -> Result<(), String> {
    app.emit(
        "setup-progress",
        SetupProgress {
            stage: "model".into(),
            detail: format!("Pulling {model}..."),
            done: false,
        },
    )
    .ok();

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(7200))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    let mut resp = client
        .post("http://127.0.0.1:11434/api/pull")
        .json(&serde_json::json!({ "name": model }))
        .send()
        .await
        .map_err(|e| format!("Failed to connect to Ollama API: {e}"))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("Ollama pull request failed (HTTP {status}): {body}"));
    }

    let mut buffer = String::new();
    let mut last_emit = std::time::Instant::now();

    loop {
        let chunk = resp
            .chunk()
            .await
            .map_err(|e| format!("Stream error while pulling {model}: {e}"))?;

        match chunk {
            Some(bytes) => {
                buffer.push_str(&String::from_utf8_lossy(&bytes));

                while let Some(pos) = buffer.find('\n') {
                    let line: String = buffer.drain(..=pos).collect();
                    let line = line.trim();
                    if line.is_empty() {
                        continue;
                    }

                    if let Ok(json) = serde_json::from_str::<serde_json::Value>(line) {
                        if let Some(error) = json.get("error").and_then(|e| e.as_str()) {
                            return Err(format!("Failed to pull {model}: {error}"));
                        }

                        let status_str =
                            json.get("status").and_then(|s| s.as_str()).unwrap_or("");

                        let detail = match (
                            json.get("completed").and_then(|c| c.as_u64()),
                            json.get("total").and_then(|t| t.as_u64()),
                        ) {
                            (Some(completed), Some(total)) if total > 0 => {
                                let pct = (completed as f64 / total as f64 * 100.0) as u32;
                                let done_mb = completed / 1_048_576;
                                let total_mb = total / 1_048_576;
                                format!(
                                    "{model}: {status_str} — {done_mb} MB / {total_mb} MB ({pct}%)"
                                )
                            }
                            _ => format!("{model}: {status_str}"),
                        };

                        if last_emit.elapsed() >= std::time::Duration::from_millis(500)
                            || status_str == "success"
                        {
                            app.emit(
                                "setup-progress",
                                SetupProgress {
                                    stage: "model".into(),
                                    detail,
                                    done: false,
                                },
                            )
                            .ok();
                            last_emit = std::time::Instant::now();
                        }
                    }
                }
            }
            None => break,
        }
    }

    app.emit(
        "setup-progress",
        SetupProgress {
            stage: "model".into(),
            detail: format!("{model} ready"),
            done: true,
        },
    )
    .ok();
    Ok(())
}

#[tauri::command]
async fn ensure_ollama_serving() -> Result<(), String> {
    let client = reqwest::Client::new();
    if client
        .get("http://127.0.0.1:11434/api/tags")
        .send()
        .await
        .is_ok()
    {
        log::info!("Ollama already serving");
        return Ok(());
    }

    let ollama = ollama_exe_path().ok_or("Ollama not found")?;
    TokioCommand::new(&ollama)
        .arg("serve")
        .env("OLLAMA_FLASH_ATTENTION", "1")
        .env("OLLAMA_KV_CACHE_TYPE", "q8_0")
        .spawn()
        .map_err(|e| format!("Failed to start Ollama: {e}"))?;

    log::info!("Ollama spawned with FLASH_ATTENTION=1 KV_CACHE_TYPE=q8_0");

    for _ in 0..30 {
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        if client
            .get("http://127.0.0.1:11434/api/tags")
            .send()
            .await
            .is_ok()
        {
            return Ok(());
        }
    }
    Err("Ollama did not start within 30 seconds".into())
}

#[tauri::command]
async fn get_optimization_status() -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({
        "flash_attention": true,
        "kv_cache_type": "q8_0",
        "kv_cache_savings": "~50% VRAM reduction",
        "embed_quantize": "int8",
    }))
}

#[tauri::command]
async fn start_api_sidecar(app: AppHandle, state: State<'_, ApiProcess>) -> Result<(), String> {
    {
        let lock = state.0.lock().map_err(|e| e.to_string())?;
        if lock.is_some() {
            return Ok(());
        }
    }

    let resource_dir = app
        .path()
        .resource_dir()
        .unwrap_or_else(|_| PathBuf::from("."));

    let sidecar_name = if cfg!(windows) {
        "paradox-api.exe"
    } else {
        "paradox-api"
    };

    let exe_dir = app
        .path()
        .resource_dir()
        .ok()
        .and_then(|p| p.parent().map(|pp| pp.to_path_buf()))
        .unwrap_or_else(|| resource_dir.clone());

    let candidates = [
        resource_dir.join("dist").join("paradox-api"),
        resource_dir.join("_up_").join("dist").join("paradox-api"),
        exe_dir.join("_up_").join("dist").join("paradox-api"),
        exe_dir.join("dist").join("paradox-api"),
    ];

    let sidecar_dir = candidates
        .iter()
        .find(|d| d.join(sidecar_name).exists())
        .cloned()
        .ok_or_else(|| {
            let tried: Vec<String> = candidates.iter().map(|c| format!("  {}", c.display())).collect();
            format!(
                "API sidecar not found. Searched:\n{}\nresource_dir = {}",
                tried.join("\n"),
                resource_dir.display()
            )
        })?;

    let sidecar_path = sidecar_dir.join(sidecar_name);
    log::info!("Starting API sidecar from: {}", sidecar_path.display());

    let child = TokioCommand::new(&sidecar_path)
        .current_dir(&sidecar_dir)
        .spawn()
        .map_err(|e| format!("Failed to start API sidecar at {}: {e}", sidecar_path.display()))?;

    let pid = child.id();
    {
        let mut lock = state.0.lock().map_err(|e| e.to_string())?;
        *lock = pid;
    }

    let client = reqwest::Client::new();
    for _ in 0..60 {
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        if client
            .get("http://127.0.0.1:8765/health")
            .send()
            .await
            .is_ok()
        {
            return Ok(());
        }
    }
    Err("API sidecar did not become healthy within 60 seconds".into())
}

#[tauri::command]
async fn download_ollama(app: AppHandle) -> Result<(), String> {
    app.emit(
        "setup-progress",
        SetupProgress {
            stage: "ollama".into(),
            detail: "Downloading Ollama installer...".into(),
            done: false,
        },
    )
    .ok();

    let url = "https://ollama.com/download/OllamaSetup.exe";
    let download_dir = appdata_dir().join("downloads");
    std::fs::create_dir_all(&download_dir).map_err(|e| e.to_string())?;
    let installer_path = download_dir.join("OllamaSetup.exe");

    let client = reqwest::Client::new();
    let resp = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("Download failed: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!("Download returned status {}", resp.status()));
    }

    let bytes = resp.bytes().await.map_err(|e| e.to_string())?;
    tokio::fs::write(&installer_path, &bytes)
        .await
        .map_err(|e| e.to_string())?;

    app.emit(
        "setup-progress",
        SetupProgress {
            stage: "ollama".into(),
            detail: "Installing Ollama...".into(),
            done: false,
        },
    )
    .ok();

    let status = TokioCommand::new(&installer_path)
        .args(["/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"])
        .status()
        .await
        .map_err(|e| format!("Installer failed: {e}"))?;

    if !status.success() {
        return Err("Ollama installer returned non-zero exit code".into());
    }

    app.emit(
        "setup-progress",
        SetupProgress {
            stage: "ollama".into(),
            detail: "Ollama installed".into(),
            done: true,
        },
    )
    .ok();
    Ok(())
}

#[tauri::command]
fn get_appdata_path() -> String {
    appdata_dir().to_string_lossy().into_owned()
}

// ── App setup ──────────────────────────────────────────────────────────

fn kill_api_process(state: &ApiProcess) {
    if let Ok(mut lock) = state.0.lock() {
        if let Some(pid) = lock.take() {
            #[cfg(windows)]
            {
                let _ = std::process::Command::new("taskkill")
                    .args(["/F", "/PID", &pid.to_string()])
                    .output();
            }
            #[cfg(not(windows))]
            {
                unsafe {
                    libc::kill(pid as i32, libc::SIGTERM);
                }
            }
        }
    }
}

pub fn run() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .manage(ApiProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            check_ollama,
            get_ollama_models,
            pull_model,
            ensure_ollama_serving,
            start_api_sidecar,
            download_ollama,
            get_appdata_path,
            get_optimization_status,
        ])
        .setup(|app| {
            let quit = MenuItemBuilder::with_id("quit", "Quit Paradox")
                .build(app)?;
            let show = MenuItemBuilder::with_id("show", "Show Window")
                .build(app)?;
            let menu = MenuBuilder::new(app)
                .item(&show)
                .separator()
                .item(&quit)
                .build()?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("Paradox Solutions LLM")
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "quit" => {
                        let state: State<ApiProcess> = app.state();
                        kill_api_process(state.inner());
                        std::process::exit(0);
                    }
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Paradox Solutions LLM");
}

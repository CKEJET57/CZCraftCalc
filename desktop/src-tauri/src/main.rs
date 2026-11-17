#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::{
    env,
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};

fn call_python_bridge(request: Value) -> Result<Value, String> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir
        .join("../..")
        .canonicalize()
        .map_err(|error| format!("Не удалось определить корень CZCraftCalc: {error}"))?;
    let bridge_path = repo_root.join("desktop/python/bridge.py");

    if !bridge_path.is_file() {
        return Err(format!("Python bridge не найден: {}", bridge_path.display()));
    }

    let python = env::var_os("CZCRAFTCALC_PYTHON")
        .unwrap_or_else(|| "python".into());

    let mut child = Command::new(python)
        .arg(&bridge_path)
        .current_dir(&repo_root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| {
            format!(
                "Не удалось запустить Python. Установите Python или задайте CZCRAFTCALC_PYTHON: {error}"
            )
        })?;

    {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or_else(|| "Не удалось открыть stdin Python bridge.".to_string())?;
        serde_json::to_writer(&mut *stdin, &request)
            .map_err(|error| format!("Не удалось сериализовать команду: {error}"))?;
        stdin
            .write_all(b"\n")
            .map_err(|error| format!("Не удалось передать команду Python: {error}"))?;
    }

    let output = child
        .wait_with_output()
        .map_err(|error| format!("Ошибка ожидания Python bridge: {error}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python bridge завершился с ошибкой: {}", stderr.trim()));
    }

    let response: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        let stderr = String::from_utf8_lossy(&output.stderr);
        format!(
            "Python bridge вернул некорректный JSON: {error}. stderr: {}",
            stderr.trim()
        )
    })?;

    if response.get("ok").and_then(Value::as_bool) != Some(true) {
        let message = response
            .get("error")
            .and_then(|error| error.get("message"))
            .and_then(Value::as_str)
            .unwrap_or("Неизвестная ошибка Python bridge.");
        return Err(message.to_string());
    }

    response
        .get("data")
        .cloned()
        .ok_or_else(|| "В ответе Python bridge отсутствует поле data.".to_string())
}

#[tauri::command]
async fn search_character(name: String, region: Option<String>) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        call_python_bridge(json!({
            "action": "search_character",
            "name": name,
            "region": region.unwrap_or_else(|| "RU".to_string())
        }))
    })
    .await
    .map_err(|error| format!("Ошибка фоновой задачи: {error}"))?
}

#[tauri::command]
async fn get_stats_metadata() -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(|| {
        call_python_bridge(json!({ "action": "stats_metadata" }))
    })
    .await
    .map_err(|error| format!("Ошибка фоновой задачи: {error}"))?
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            search_character,
            get_stats_metadata
        ])
        .run(tauri::generate_context!())
        .expect("Не удалось запустить CZCraftCalc Desktop");
}

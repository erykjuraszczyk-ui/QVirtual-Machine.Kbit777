from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

try:
    from qiskit import QuantumCircuit, transpile
    from qiskit.quantum_info import Statevector
    from qiskit_aer import AerSimulator
    QISKIT_AVAILABLE = True
except Exception:
    QISKIT_AVAILABLE = False
    QuantumCircuit = None
    transpile = None
    AerSimulator = None
    Statevector = None

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("QWANTUM_DATA_DIR", str(APP_DIR.parent / "data")))
PROJECTS_DIR = Path(os.environ.get("QWANTUM_PROJECTS_DIR", str(DATA_DIR / "circuit_files")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("QWANTUM_DB_PATH", str(DATA_DIR / "qwantum_vm.sqlite3")))
MAX_QUBITS = 8
WORKER_COUNT = max(1, min(int(os.environ.get("QWANTUM_WORKERS", "2")), 4))

app = FastAPI(title="Qwantum VM 2.9", version="2.9.0")
executor = ThreadPoolExecutor(max_workers=WORKER_COUNT, thread_name_prefix="qwantum-worker")
job_futures: dict[str, Future] = {}
future_lock = threading.Lock()
shutdown_event = threading.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db() -> None:
    with connect_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, qubits INTEGER NOT NULL,
            shots INTEGER NOT NULL, counts_json TEXT NOT NULL, created_at TEXT NOT NULL,
            circuit_json TEXT NOT NULL DEFAULT '{}', noise REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, circuit_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
            payload_json TEXT NOT NULL, result_json TEXT, error TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
        """)
        # Safe migration for databases created by earlier VM versions.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(experiments)")}
        if "circuit_json" not in columns:
            conn.execute("ALTER TABLE experiments ADD COLUMN circuit_json TEXT NOT NULL DEFAULT '{}'")
        if "noise" not in columns:
            conn.execute("ALTER TABLE experiments ADD COLUMN noise REAL NOT NULL DEFAULT 0")
        job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        if "cancel_requested" not in job_columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")


class Gate(BaseModel):
    gate: str
    qubit: int
    target: int | None = None
    angle: float | None = None


class CircuitPayload(BaseModel):
    name: str = Field(default="Eksperyment", min_length=1, max_length=100)
    qubits: int = Field(default=2, ge=1, le=MAX_QUBITS)
    shots: int = Field(default=1024, ge=1, le=100000)
    gates: list[Gate] = Field(default_factory=list, max_length=500)
    noise: float = Field(default=0.0, ge=0.0, le=0.2)


class ProjectPayload(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=100)
    circuit: dict[str, Any]


def validate_circuit(payload: CircuitPayload) -> None:
    allowed = {"h", "x", "y", "z", "s", "t", "rx", "ry", "rz", "cx", "cz", "swap"}
    for item in payload.gates:
        if item.gate.lower() not in allowed:
            raise HTTPException(400, f"Nieobsługiwana bramka: {item.gate}")
        if not 0 <= item.qubit < payload.qubits:
            raise HTTPException(400, f"Kubit {item.qubit} poza zakresem")
        if item.gate.lower() in {"cx", "cz", "swap"}:
            if item.target is None or not 0 <= item.target < payload.qubits:
                raise HTTPException(400, f"Bramka {item.gate} wymaga poprawnego kubitu docelowego")
            if item.target == item.qubit:
                raise HTTPException(400, "Kubit kontrolny i docelowy muszą być różne")


def execute_circuit(payload: CircuitPayload) -> dict[str, Any]:
    if not QISKIT_AVAILABLE:
        raise RuntimeError("Brak Qiskit Aer. Uruchom install_windows.bat.")
    validate_circuit(payload)
    circuit = QuantumCircuit(payload.qubits, payload.qubits)
    for item in payload.gates:
        gate = item.gate.lower()
        q = item.qubit
        if gate in {"h", "x", "y", "z", "s", "t"}:
            getattr(circuit, gate)(q)
        elif gate in {"rx", "ry", "rz"}:
            # Rotation angles are fixed to pi/2 in this MVP schema.
            getattr(circuit, gate)(item.angle if item.angle is not None else math.pi / 2, q)
        elif gate == "cx":
            circuit.cx(q, item.target)
        elif gate == "cz":
            circuit.cz(q, item.target)
        elif gate == "swap":
            circuit.swap(q, item.target)
    circuit.measure(range(payload.qubits), range(payload.qubits))
    simulator = AerSimulator()
    if payload.noise > 0:
        from qiskit_aer.noise import NoiseModel, depolarizing_error
        noise_model = NoiseModel()
        one_qubit_error = depolarizing_error(payload.noise, 1)
        two_qubit_error = depolarizing_error(min(payload.noise * 2, 0.5), 2)
        for gate_name in ["h", "x", "y", "z", "s", "t", "rx", "ry", "rz"]:
            noise_model.add_all_qubit_quantum_error(one_qubit_error, gate_name)
        for gate_name in ["cx", "cz", "swap"]:
            noise_model.add_all_qubit_quantum_error(two_qubit_error, gate_name)
        simulator = AerSimulator(noise_model=noise_model)
    compiled = transpile(circuit, simulator)
    counts = simulator.run(compiled, shots=payload.shots).result().get_counts()
    result = {
        "counts": counts,
        "qubits": payload.qubits,
        "shots": payload.shots,
        "noise": payload.noise,
        "circuit_qasm": None,
        "circuit_text": str(circuit),
    }
    try:
        result["circuit_qasm"] = circuit.qasm()
    except Exception:
        try:
            from qiskit.qasm2 import dumps
            result["circuit_qasm"] = dumps(circuit)
        except Exception:
            result["circuit_qasm"] = None
    return result


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return row_to_dict(row) if row else None


def worker(job_id: str, payload_data: dict[str, Any]) -> None:
    with connect_db() as conn:
        row = conn.execute("SELECT status, cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["cancel_requested"] or row["status"] == "CANCELLED":
            conn.execute("UPDATE jobs SET status='CANCELLED', finished_at=? WHERE id=? AND status='QUEUED'",
                         (now_iso(), job_id))
            return
        conn.execute("UPDATE jobs SET status='RUNNING', started_at=? WHERE id=? AND status='QUEUED'",
                     (now_iso(), job_id))
    try:
        payload = CircuitPayload.model_validate(payload_data)
        result = execute_circuit(payload)
        with connect_db() as conn:
            row = conn.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row and row["cancel_requested"]:
                conn.execute("UPDATE jobs SET status='CANCELLED', finished_at=? WHERE id=?",
                             (now_iso(), job_id))
            else:
                conn.execute("UPDATE jobs SET status='COMPLETED', result_json=?, finished_at=? WHERE id=?",
                             (json.dumps(result), now_iso(), job_id))
                conn.execute(
                    "INSERT INTO experiments(id,name,qubits,shots,counts_json,created_at,circuit_json,noise) VALUES(?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), payload.name, payload.qubits, payload.shots,
                     json.dumps(result["counts"]), now_iso(), json.dumps(payload_data), payload.noise)
                )
    except Exception as exc:
        with connect_db() as conn:
            conn.execute("UPDATE jobs SET status='FAILED', error=?, finished_at=? WHERE id=?",
                         (str(exc)[:1000], now_iso(), job_id))
    finally:
        with future_lock:
            job_futures.pop(job_id, None)


@app.on_event("startup")
def startup() -> None:
    init_db()
    # Jobs that were active when the process stopped cannot resume safely.
    with connect_db() as conn:
        conn.execute("UPDATE jobs SET status='INTERRUPTED', finished_at=?, error=COALESCE(error,'Proces zakończył się przed zapisaniem wyniku') WHERE status IN ('QUEUED','RUNNING')",
                     (now_iso(),))
        rows = conn.execute("SELECT id FROM jobs WHERE status='INTERRUPTED' AND cancel_requested=0").fetchall()
        for row in rows:
            conn.execute("UPDATE jobs SET status='QUEUED', started_at=NULL, finished_at=NULL, error=NULL WHERE id=?", (row['id'],))
    with connect_db() as conn:
        rows = conn.execute("SELECT id,payload_json FROM jobs WHERE status='QUEUED'").fetchall()
    for row in rows:
        try:
            future = executor.submit(worker, row['id'], json.loads(row['payload_json']))
            with future_lock:
                job_futures[row['id']] = future
        except Exception as exc:
            with connect_db() as conn:
                conn.execute("UPDATE jobs SET status='FAILED', error=?, finished_at=? WHERE id=?", (str(exc)[:1000], now_iso(), row['id']))


@app.on_event("shutdown")
def shutdown() -> None:
    shutdown_event.set()
    executor.shutdown(wait=False, cancel_futures=True)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (APP_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": "2.9.0", "qiskit_available": QISKIT_AVAILABLE,
            "workers": WORKER_COUNT, "max_qubits": MAX_QUBITS}


@app.get("/api/version")
def version() -> dict[str, str]:
    return {"name": "Qwantum VM", "version": "2.9.0", "backend": "Qiskit Aer simulator"}


@app.post("/api/jobs", status_code=202)
def create_job(payload: CircuitPayload) -> dict[str, Any]:
    validate_circuit(payload)
    job_id = str(uuid.uuid4())
    now = now_iso()
    with connect_db() as conn:
        conn.execute(
            "INSERT INTO jobs(id,name,status,created_at,payload_json) VALUES(?,?,?,?,?)",
            (job_id, payload.name, "QUEUED", now, payload.model_dump_json())
        )
    try:
        future = executor.submit(worker, job_id, payload.model_dump())
    except Exception as exc:
        with connect_db() as conn:
            conn.execute("UPDATE jobs SET status='FAILED', error=?, finished_at=? WHERE id=?",
                         (str(exc)[:1000], now_iso(), job_id))
        raise HTTPException(503, "Nie udało się dodać zadania do kolejki")
    with future_lock:
        job_futures[job_id] = future
    return {"id": job_id, "name": payload.name, "status": "QUEUED", "created_at": now}


@app.get("/api/jobs")
def list_jobs(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT id,name,status,created_at,started_at,finished_at,error FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return {"jobs": [row_to_dict(row) for row in rows]}


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Nie znaleziono zadania")
    job["payload"] = json.loads(job.pop("payload_json"))
    job["result"] = json.loads(job.pop("result_json")) if job.get("result_json") else None
    job.pop("cancel_requested", None)
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    with connect_db() as conn:
        row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Nie znaleziono zadania")
        status = row["status"]
        if status == "QUEUED":
            conn.execute("UPDATE jobs SET status='CANCELLED', cancel_requested=1, finished_at=? WHERE id=?",
                         (now_iso(), job_id))
            with future_lock:
                future = job_futures.get(job_id)
                if future:
                    future.cancel()
            return {"id": job_id, "status": "CANCELLED"}
        if status == "RUNNING":
            conn.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))
            return {"id": job_id, "status": "CANCEL_REQUESTED",
                    "message": "Obliczenie nie zostanie przerwane w połowie; wynik zostanie odrzucony po zakończeniu."}
        return {"id": job_id, "status": status, "message": "Zadanie nie jest już aktywne."}


@app.get("/api/experiments")
def list_experiments(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT id,name,qubits,shots,counts_json,created_at,circuit_json,noise FROM experiments ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    experiments = []
    for row in rows:
        item = row_to_dict(row)
        item["counts"] = json.loads(item.pop("counts_json"))
        item["circuit"] = json.loads(item.pop("circuit_json") or "{}")
        experiments.append(item)
    return {"experiments": experiments}


@app.get("/api/experiments/compare")
def compare_experiments(a: str, b: str) -> dict[str, Any]:
    with connect_db() as conn:
        rows = conn.execute("SELECT id,name,counts_json,shots,qubits,noise FROM experiments WHERE id IN (?,?)", (a,b)).fetchall()
    by_id = {row["id"]: row for row in rows}
    if a not in by_id or b not in by_id:
        raise HTTPException(404, "Nie znaleziono jednego lub obu eksperymentów")
    ra, rb = by_id[a], by_id[b]
    ca, cb = json.loads(ra["counts_json"]), json.loads(rb["counts_json"])
    keys = sorted(set(ca) | set(cb))
    pa = {key: ca.get(key,0)/max(1,ra["shots"]) for key in keys}
    pb = {key: cb.get(key,0)/max(1,rb["shots"]) for key in keys}
    return {
        "a": {"id": a, "name": ra["name"], "shots": ra["shots"], "qubits": ra["qubits"], "noise": ra["noise"]},
        "b": {"id": b, "name": rb["name"], "shots": rb["shots"], "qubits": rb["qubits"], "noise": rb["noise"]},
        "distribution": [{"state": key, "a_count": ca.get(key,0), "b_count": cb.get(key,0),
                          "a_probability": round(pa[key],6), "b_probability": round(pb[key],6),
                          "absolute_difference": round(abs(pa[key]-pb[key]),6)} for key in keys]
    }



class ExportPayload(BaseModel):
    name: str = Field(default="circuit", min_length=1, max_length=100)
    circuit: CircuitPayload


def safe_filename(name: str) -> str:
    stem = Path(name).stem
    cleaned = "".join(ch for ch in stem if ch.isalnum() or ch in ("-", "_", " ")).strip()
    cleaned = "_".join(cleaned.split())[:80]
    return cleaned or "circuit"


@app.post("/api/circuits/export")
def export_circuit(payload: ExportPayload) -> dict[str, Any]:
    validate_circuit(payload.circuit)
    filename = safe_filename(payload.name) + ".json"
    target = PROJECTS_DIR / filename
    content = {"format": "qwantum-circuit-v1", "name": payload.name,
               "circuit": payload.circuit.model_dump(), "exported_at": now_iso()}
    target.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"filename": filename, "format": content["format"]}


@app.get("/api/circuits/files")
def list_circuit_files() -> dict[str, Any]:
    result = []
    for path in sorted(PROJECTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result.append({"filename": path.name, "name": data.get("name", path.stem)})
        except (OSError, json.JSONDecodeError):
            continue
    return {"files": result}


@app.get("/api/circuits/files/{filename}")
def load_circuit_file(filename: str) -> dict[str, Any]:
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise HTTPException(400, "Niepoprawna nazwa pliku")
    target = PROJECTS_DIR / filename
    if not target.is_file():
        raise HTTPException(404, "Nie znaleziono pliku obwodu")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(400, "Niepoprawny plik JSON")


@app.post("/api/circuits/import")
def import_circuit(payload: dict[str, Any]) -> dict[str, Any]:
    circuit_data = payload.get("circuit", payload)
    try:
        circuit = CircuitPayload.model_validate(circuit_data)
    except Exception as exc:
        raise HTTPException(400, f"Niepoprawny obwód: {exc}")
    validate_circuit(circuit)
    return {"name": payload.get("name", circuit.name), "circuit": circuit.model_dump()}

@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    with connect_db() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return {"projects": [row_to_dict(row) | {"circuit": json.loads(row["circuit_json"])} for row in rows]}


@app.post("/api/projects")
def save_project(payload: ProjectPayload) -> dict[str, Any]:
    project_id = payload.id or str(uuid.uuid4())
    now = now_iso()
    with connect_db() as conn:
        conn.execute(
            "INSERT INTO projects(id,name,circuit_json,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name,circuit_json=excluded.circuit_json,updated_at=excluded.updated_at",
            (project_id, payload.name, json.dumps(payload.circuit), now)
        )
    return {"id": project_id, "name": payload.name, "updated_at": now}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    with connect_db() as conn:
        cursor = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        if cursor.rowcount == 0:
            raise HTTPException(404, "Nie znaleziono projektu")
    return {"deleted": True, "id": project_id}


@app.post("/api/circuit/validate")
def validate_circuit_endpoint(payload: CircuitPayload) -> dict[str, Any]:
    """Validate a circuit without submitting it to the simulation queue."""
    validate_circuit(payload)
    warnings = []
    if payload.qubits > 6:
        warnings.append("Obwody powyżej 6 kubitów mogą wymagać więcej pamięci.")
    if payload.shots > 50000:
        warnings.append("Duża liczba pomiarów może wydłużyć obliczenia.")
    if not payload.gates:
        warnings.append("Obwód nie zawiera bramek; wynik pozostanie w stanie |0…0⟩.")
    return {
        "valid": True,
        "name": payload.name,
        "qubits": payload.qubits,
        "gate_count": len(payload.gates),
        "shots": payload.shots,
        "noise": payload.noise,
        "warnings": warnings,
        "message": "Obwód przeszedł walidację."
    }


@app.post("/api/experiments/import")
def import_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    """Import a portable experiment JSON previously exported by Qwantum VM."""
    if payload.get("format") != "qwantum-experiment":
        raise HTTPException(400, "Nieobsługiwany format pliku eksperymentu.")
    try:
        circuit_data = payload.get("circuit")
        if not isinstance(circuit_data, dict):
            raise ValueError("Brak definicji obwodu.")
        circuit = CircuitPayload.model_validate(circuit_data)
        validate_circuit(circuit)
        counts = payload.get("counts", {})
        if not isinstance(counts, dict) or any(
            not isinstance(k, str) or not isinstance(v, int) or v < 0 for k, v in counts.items()
        ):
            raise ValueError("Niepoprawny rozkład wyników.")
        new_id = str(uuid.uuid4())
        imported_name = str(payload.get("name") or circuit.name)[:100]
        with connect_db() as conn:
            conn.execute(
                "INSERT INTO experiments(id,name,qubits,shots,counts_json,created_at,circuit_json,noise) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (new_id, imported_name + " (import)", circuit.qubits, circuit.shots,
                 json.dumps(counts), now_iso(), json.dumps(circuit.model_dump()), circuit.noise)
            )
        return {"id": new_id, "name": imported_name + " (import)", "imported": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Niepoprawny plik eksperymentu: {str(exc)[:300]}")


@app.post("/api/experiments/{experiment_id}/rerun", status_code=202)
def rerun_experiment(experiment_id: str) -> dict[str, Any]:
    """Submit a fresh simulation using the saved circuit configuration."""
    with connect_db() as conn:
        row = conn.execute(
            "SELECT id,name,circuit_json FROM experiments WHERE id=?", (experiment_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Nie znaleziono eksperymentu")
    try:
        circuit_data = json.loads(row["circuit_json"] or "{}")
        payload = CircuitPayload.model_validate(circuit_data)
        validate_circuit(payload)
    except Exception as exc:
        raise HTTPException(400, f"Zapisany obwód nie może być ponownie uruchomiony: {str(exc)[:300]}")
    payload.name = (payload.name or row["name"])[:90] + " (ponownie)"
    return create_job(payload)


@app.get("/api/experiments/compare/multi")
def compare_multiple_experiments(ids: str) -> dict[str, Any]:
    """Compare up to 20 saved experiment distributions in one report."""
    requested = list(dict.fromkeys(part.strip() for part in ids.split(",") if part.strip()))
    if len(requested) < 2 or len(requested) > 20:
        raise HTTPException(400, "Podaj od 2 do 20 różnych identyfikatorów eksperymentów.")
    placeholders = ",".join("?" for _ in requested)
    with connect_db() as conn:
        rows = conn.execute(
            f"SELECT id,name,counts_json,shots,qubits,noise,created_at FROM experiments WHERE id IN ({placeholders})",
            tuple(requested)
        ).fetchall()
    by_id = {row["id"]: row for row in rows}
    missing = [experiment_id for experiment_id in requested if experiment_id not in by_id]
    if missing:
        raise HTTPException(404, "Nie znaleziono eksperymentu: " + ", ".join(missing))
    experiments = []
    all_states = set()
    for experiment_id in requested:
        row = by_id[experiment_id]
        counts = json.loads(row["counts_json"])
        all_states.update(counts.keys())
        experiments.append({
            "id": row["id"], "name": row["name"], "shots": row["shots"],
            "qubits": row["qubits"], "noise": row["noise"], "created_at": row["created_at"],
            "counts": counts,
        })
    states = sorted(all_states)
    for item in experiments:
        item["distribution"] = {
            state: round(item["counts"].get(state, 0) / max(1, item["shots"]), 8)
            for state in states
        }
    return {"count": len(experiments), "states": states, "experiments": experiments}


@app.get("/api/experiments/compare/export.csv")
def export_comparison_csv(a: str, b: str) -> Response:
    """Download a pairwise comparison as UTF-8 CSV."""
    from io import StringIO
    import csv
    comparison = compare_experiments(a, b)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["state", "a_count", "b_count", "a_probability", "b_probability", "absolute_difference"])
    for item in comparison["distribution"]:
        writer.writerow([
            item["state"], item["a_count"], item["b_count"],
            item["a_probability"], item["b_probability"], item["absolute_difference"]
        ])
    return Response(
        content="\\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="qwantum-comparison.csv"'}
    )


@app.get("/api/experiments/{experiment_id}/export")
def export_experiment(experiment_id: str) -> JSONResponse:
    """Export a saved experiment and its result as portable JSON."""
    with connect_db() as conn:
        row = conn.execute(
            "SELECT id,name,qubits,shots,counts_json,created_at,circuit_json,noise "
            "FROM experiments WHERE id=?", (experiment_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Nie znaleziono eksperymentu")
    item = row_to_dict(row)
    try:
        item["counts"] = json.loads(item.pop("counts_json"))
    except (TypeError, json.JSONDecodeError):
        item["counts"] = {}
    try:
        item["circuit"] = json.loads(item.pop("circuit_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["circuit"] = {}
    item["format"] = "qwantum-experiment"
    item["format_version"] = 1
    filename = f"qwantum-experiment-{experiment_id[:8]}.json"
    return JSONResponse(
        content=item,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/diagnostics/export")
def export_diagnostics() -> JSONResponse:
    """Run diagnostics and return a timestamped, portable JSON report."""
    report = diagnostics_endpoint()
    report["format"] = "qwantum-diagnostics"
    report["format_version"] = 1
    report["generated_at"] = now_iso()
    filename = "qwantum-diagnostics.json"
    return JSONResponse(
        content=report,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/diagnostics")
def diagnostics_endpoint() -> dict[str, Any]:
    """Run small known-answer checks against the installed statevector backend."""
    if not QISKIT_AVAILABLE or Statevector is None:
        raise HTTPException(503, "Brak Qiskit Aer/Qiskit. Uruchom install_windows.bat.")
    checks: list[dict[str, Any]] = []

    def probability_map(qubits: int, gates: list[tuple[str, int, int | None]]) -> dict[str, float]:
        circuit = QuantumCircuit(qubits)
        for gate, q, target in gates:
            if gate in {"h", "x", "y", "z", "s", "t"}:
                getattr(circuit, gate)(q)
            elif gate == "cx":
                circuit.cx(q, target)
            elif gate == "cz":
                circuit.cz(q, target)
            elif gate == "swap":
                circuit.swap(q, target)
        state = Statevector.from_instruction(circuit)
        return {format(i, f"0{qubits}b"): float(abs(amp) ** 2)
                for i, amp in enumerate(state.data)}

    def check(name: str, actual: dict[str, float], expected: dict[str, float], tol: float = 1e-7) -> None:
        keys = set(actual) | set(expected)
        max_error = max((abs(actual.get(k, 0.0) - expected.get(k, 0.0)) for k in keys), default=0.0)
        checks.append({"name": name, "passed": max_error <= tol, "max_error": round(max_error, 12),
                       "expected": expected, "actual": {k: round(v, 10) for k, v in actual.items() if v > tol}})

    check("Stan początkowy |0⟩", probability_map(1, []), {"0": 1.0, "1": 0.0})
    check("Bramka X: |0⟩ → |1⟩", probability_map(1, [("x", 0, None)]), {"0": 0.0, "1": 1.0})
    check("Superpozycja H", probability_map(1, [("h", 0, None)]), {"0": 0.5, "1": 0.5})
    check("Stan Bella", probability_map(2, [("h", 0, None), ("cx", 0, 1)]),
          {"00": 0.5, "01": 0.0, "10": 0.0, "11": 0.5})
    passed = sum(1 for item in checks if item["passed"])
    return {"version": "2.9.0", "backend": "Qiskit Statevector", "passed": passed,
            "total": len(checks), "ok": passed == len(checks), "checks": checks,
            "note": "Testy sprawdzają znane rozkłady idealnego wektora stanu; nie testują fizycznego sprzętu."}


@app.post("/api/statevector/noise-evolution")
def noisy_state_evolution_endpoint(payload: CircuitPayload) -> dict[str, Any]:
    """Compare ideal probabilities with noisy sampled distributions after each gate."""
    validate_circuit(payload)
    if not QISKIT_AVAILABLE or Statevector is None or AerSimulator is None:
        raise HTTPException(503, "Brak Qiskit Aer. Uruchom install_windows.bat.")
    if len(payload.gates) > 80:
        raise HTTPException(400, "Porównanie szumu obsługuje maksymalnie 80 bramek na jeden raport.")
    shots = max(128, min(payload.shots, 4096))
    noise_model = None
    if payload.noise > 0:
        try:
            from qiskit_aer.noise import NoiseModel, depolarizing_error
            noise_model = NoiseModel()
            one_qubit_error = depolarizing_error(payload.noise, 1)
            two_qubit_error = depolarizing_error(min(payload.noise * 2, 0.5), 2)
            for gate_name in ["h", "x", "y", "z", "s", "t", "rx", "ry", "rz"]:
                noise_model.add_all_qubit_quantum_error(one_qubit_error, gate_name)
            for gate_name in ["cx", "cz", "swap"]:
                noise_model.add_all_qubit_quantum_error(two_qubit_error, gate_name)
        except Exception as exc:
            raise HTTPException(503, f"Nie udało się skonfigurować modelu szumu: {str(exc)[:200]}")
    simulator = AerSimulator(noise_model=noise_model) if noise_model else AerSimulator()
    circuit = QuantumCircuit(payload.qubits)
    steps: list[dict[str, Any]] = []

    def add_gate(item: Gate) -> str:
        gate, q = item.gate.lower(), item.qubit
        if gate in {"h", "x", "y", "z", "s", "t"}:
            getattr(circuit, gate)(q)
        elif gate in {"rx", "ry", "rz"}:
            getattr(circuit, gate)(item.angle if item.angle is not None else math.pi / 2, q)
        elif gate == "cx":
            circuit.cx(q, item.target)
        elif gate == "cz":
            circuit.cz(q, item.target)
        elif gate == "swap":
            circuit.swap(q, item.target)
        return f"{gate.upper()} q{q}" + (f" → q{item.target}" if item.target is not None else "")

    for index in range(len(payload.gates) + 1):
        if index > 0:
            add_gate(payload.gates[index - 1])
        ideal_state = Statevector.from_instruction(circuit)
        ideal_probs = {
            format(i, f"0{payload.qubits}b"): round(float(abs(amplitude) ** 2), 8)
            for i, amplitude in enumerate(ideal_state.data)
        }
        measured = circuit.copy()
        measured.measure_all()
        try:
            compiled = transpile(measured, simulator)
            counts = simulator.run(compiled, shots=shots).result().get_counts()
        except Exception as exc:
            raise HTTPException(500, f"Błąd symulacji etapu {index}: {str(exc)[:250]}")
        noisy_probs = {state: round(count / shots, 8) for state, count in counts.items()}
        all_states = sorted(set(ideal_probs) | set(noisy_probs))
        steps.append({
            "index": index,
            "label": "Stan początkowy" if index == 0 else f"{index}. " + (
                f"{payload.gates[index-1].gate.upper()} q{payload.gates[index-1].qubit}" +
                (f" → q{payload.gates[index-1].target}" if payload.gates[index-1].target is not None else "")
            ),
            "ideal": [{"state": state, "probability": ideal_probs.get(state, 0.0)} for state in all_states],
            "noisy": [{"state": state, "probability": noisy_probs.get(state, 0.0)} for state in all_states],
            "total_variation_distance": round(0.5 * sum(abs(ideal_probs.get(s, 0.0) - noisy_probs.get(s, 0.0)) for s in all_states), 8),
        })
    return {
        "name": payload.name, "qubits": payload.qubits, "noise": payload.noise,
        "shots_used_per_step": shots, "step_count": len(steps), "steps": steps,
        "note": "Rozkład idealny pochodzi z wektora stanu; rozkład zaszumiony z pomiarów symulatora. Przy skończonej liczbie shots występują fluktuacje statystyczne.",
    }



@app.post("/api/analysis/shots-stability")
def shots_stability_endpoint(payload: CircuitPayload) -> dict[str, Any]:
    """Estimate finite-shot stability against ideal probabilities using repeated samples."""
    validate_circuit(payload)
    if len(payload.gates) > 40:
        raise HTTPException(400, "Analiza stabilności obsługuje maksymalnie 40 bramek.")
    if not QISKIT_AVAILABLE or Statevector is None or AerSimulator is None:
        raise HTTPException(503, "Brak Qiskit Aer. Uruchom install_windows.bat.")
    # Keep runtime bounded even if a client sends a very high shot count.
    max_shots = max(128, min(payload.shots, 4096))
    shot_levels = sorted(set([128, 256, 512, 1024, max_shots]))
    repetitions = 3
    circuit = QuantumCircuit(payload.qubits)
    for item in payload.gates:
        gate, q = item.gate.lower(), item.qubit
        if gate in {"h", "x", "y", "z", "s", "t"}:
            getattr(circuit, gate)(q)
        elif gate in {"rx", "ry", "rz"}:
            getattr(circuit, gate)(item.angle if item.angle is not None else math.pi / 2, q)
        elif gate == "cx":
            circuit.cx(q, item.target)
        elif gate == "cz":
            circuit.cz(q, item.target)
        elif gate == "swap":
            circuit.swap(q, item.target)
    state = Statevector.from_instruction(circuit)
    ideal = {format(i, f"0{payload.qubits}b"): float(abs(amp) ** 2)
             for i, amp in enumerate(state.data)}
    measured = circuit.copy()
    measured.measure_all()
    simulator = AerSimulator()
    rows: list[dict[str, Any]] = []
    for shots in shot_levels:
        tvds = []
        for _ in range(repetitions):
            try:
                compiled = transpile(measured, simulator)
                counts = simulator.run(compiled, shots=shots).result().get_counts()
            except Exception as exc:
                raise HTTPException(500, f"Błąd analizy stabilności: {str(exc)[:220]}")
            states = set(ideal) | set(counts)
            sampled = {state_name: counts.get(state_name, 0) / shots for state_name in states}
            tvd = 0.5 * sum(abs(ideal.get(state_name, 0.0) - sampled.get(state_name, 0.0))
                            for state_name in states)
            tvds.append(tvd)
        mean_tvd = sum(tvds) / len(tvds)
        variance = sum((value - mean_tvd) ** 2 for value in tvds) / len(tvds)
        rows.append({
            "shots": shots, "repetitions": repetitions,
            "tvd_values": [round(value, 8) for value in tvds],
            "mean_tvd": round(mean_tvd, 8),
            "stddev_tvd": round(math.sqrt(variance), 8),
        })
    return {
        "format": "qwantum-shots-stability", "format_version": "1.0",
        "name": payload.name, "qubits": payload.qubits, "gate_count": len(payload.gates),
        "ideal_probabilities": [{"state": state_name, "probability": round(prob, 10)}
                                for state_name, prob in ideal.items()],
        "results": rows,
        "note": "TVD porównuje rozkład z próby z idealnym rozkładem. To eksperymentalna miara fluktuacji przy skończonej liczbie pomiarów; nie jest gwarancją dokładności sprzętu.",
    }


@app.post("/api/statevector/evolution")
def statevector_evolution_endpoint(payload: CircuitPayload) -> dict[str, Any]:
    """Return the ideal statevector after each gate, including the initial state."""
    validate_circuit(payload)
    if not QISKIT_AVAILABLE or Statevector is None:
        raise HTTPException(503, "Brak Qiskit. Uruchom install_windows.bat.")
    circuit = QuantumCircuit(payload.qubits)
    steps: list[dict[str, Any]] = []

    def snapshot(label: str, index: int) -> None:
        state = Statevector.from_instruction(circuit)
        probabilities = []
        amplitudes = []
        for idx, amp in enumerate(state.data):
            bits = format(idx, f"0{payload.qubits}b")
            probability = float(abs(amp) ** 2)
            probabilities.append({"state": bits, "probability": round(probability, 10)})
            if probability > 1e-12:
                amplitudes.append({
                    "state": bits,
                    "real": round(float(amp.real), 10),
                    "imag": round(float(amp.imag), 10),
                    "magnitude": round(float(abs(amp)), 10),
                    "phase": round(float(math.atan2(amp.imag, amp.real)), 10),
                })
        steps.append({
            "index": index, "label": label, "gate_count": index,
            "amplitudes": amplitudes, "probabilities": probabilities,
        })

    snapshot("Stan początkowy", 0)
    for index, item in enumerate(payload.gates, start=1):
        gate, q = item.gate.lower(), item.qubit
        if gate in {"h", "x", "y", "z", "s", "t"}:
            getattr(circuit, gate)(q)
        elif gate in {"rx", "ry", "rz"}:
            getattr(circuit, gate)(item.angle if item.angle is not None else math.pi / 2, q)
        elif gate == "cx":
            circuit.cx(q, item.target)
        elif gate == "cz":
            circuit.cz(q, item.target)
        elif gate == "swap":
            circuit.swap(q, item.target)
        snapshot(f"{index}. {gate.upper()} q{q}" + (f" → q{item.target}" if item.target is not None else ""),
                 index)
    return {
        "name": payload.name, "qubits": payload.qubits, "step_count": len(steps),
        "steps": steps,
        "note": "Idealna ewolucja wektora stanu po każdej bramce. Nie uwzględnia szumu ani pomiaru.",
    }


@app.post("/api/statevector")
def statevector_endpoint(payload: CircuitPayload) -> dict[str, Any]:
    validate_circuit(payload)
    if not QISKIT_AVAILABLE or Statevector is None:
        raise HTTPException(503, "Brak Qiskit. Uruchom install_windows.bat.")
    circuit = QuantumCircuit(payload.qubits)
    for item in payload.gates:
        gate, q = item.gate.lower(), item.qubit
        if gate in {"h", "x", "y", "z", "s", "t"}:
            getattr(circuit, gate)(q)
        elif gate in {"rx", "ry", "rz"}:
            getattr(circuit, gate)(item.angle if item.angle is not None else math.pi / 2, q)
        elif gate == "cx":
            circuit.cx(q, item.target)
        elif gate == "cz":
            circuit.cz(q, item.target)
        elif gate == "swap":
            circuit.swap(q, item.target)
    state = Statevector.from_instruction(circuit)
    amps, probs = [], []
    for idx, amp in enumerate(state.data):
        bits = format(idx, f"0{payload.qubits}b")
        amps.append({"state": bits, "real": round(float(amp.real), 10),
                     "imag": round(float(amp.imag), 10), "magnitude": round(float(abs(amp)), 10),
                     "phase": round(float(math.atan2(amp.imag, amp.real)), 10)})
        probs.append({"state": bits, "probability": round(float(abs(amp)**2), 10)})
    return {"name": payload.name, "qubits": payload.qubits, "basis_order": "big-endian display",
            "amplitudes": amps, "probabilities": probs,
            "note": "Idealny stan przed pomiarem; nie uwzględnia szumu ani losowości pomiarów."}


@app.get("/api/circuit/gates")
def gate_catalog() -> dict[str, Any]:
    return {"single_qubit": ["h", "x", "y", "z", "s", "t", "rx", "ry", "rz"],
            "two_qubit": ["cx", "cz", "swap"], "rotation_default_angle": "pi/2", "rotation_angle_unit": "radians"}

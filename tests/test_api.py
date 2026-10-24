import os, tempfile, unittest
from pathlib import Path
_tmp = tempfile.TemporaryDirectory()
os.environ["QWANTUM_DATA_DIR"] = _tmp.name
os.environ["QWANTUM_DB_PATH"] = str(Path(_tmp.name) / "test.sqlite3")
os.environ["QWANTUM_PROJECTS_DIR"] = str(Path(_tmp.name) / "circuits")
from fastapi.testclient import TestClient
from app.server import app, init_db, QISKIT_AVAILABLE
class QwantumVM29Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
    def test_health(self):
        r=self.client.get("/api/health")
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()["version"],"2.9.0")
    def test_invalid_qubit(self):
        r=self.client.post("/api/jobs",json={"name":"bad","qubits":1,"shots":8,"gates":[{"gate":"h","qubit":1}]})
        self.assertEqual(r.status_code,400)
    def test_circuit_file_roundtrip(self):
        p={"name":"rot","circuit":{"name":"rot","qubits":1,"shots":8,"gates":[{"gate":"rz","qubit":0,"angle":0.75}]}}
        saved=self.client.post("/api/circuits/export",json=p)
        self.assertEqual(saved.status_code,200)
        loaded=self.client.get("/api/circuits/files/"+saved.json()["filename"])
        self.assertEqual(loaded.status_code,200)
        imported=self.client.post("/api/circuits/import",json=loaded.json())
        self.assertEqual(imported.status_code,200)
    def test_circuit_validation(self):
        r = self.client.post("/api/circuit/validate", json={
            "name":"valid", "qubits":2, "shots":32,
            "gates":[{"gate":"h","qubit":0},{"gate":"cx","qubit":0,"target":1}]
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["valid"])
        self.assertEqual(r.json()["gate_count"], 2)

    def test_diagnostics_endpoint(self):
        if not QISKIT_AVAILABLE:
            self.skipTest("Qiskit unavailable")
        r = self.client.get("/api/diagnostics")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 4)
        self.assertTrue(r.json()["ok"])






    def test_noise_evolution_validation(self):
        r = self.client.post("/api/statevector/noise-evolution", json={
            "name": "too-many-gates", "qubits": 1, "shots": 16, "noise": 0,
            "gates": [{"gate": "x", "qubit": 0}] * 81
        })
        self.assertEqual(r.status_code, 400)

    def test_statevector_evolution_requires_qiskit_or_returns_steps(self):
        r = self.client.post("/api/statevector/evolution", json={
            "name": "test", "qubits": 1, "shots": 16, "noise": 0,
            "gates": [{"gate": "x", "qubit": 0}]
        })
        self.assertIn(r.status_code, (200, 503))
        if r.status_code == 200:
            data = r.json()
            self.assertEqual(data["step_count"], 2)
            self.assertEqual(data["steps"][0]["index"], 0)
            self.assertEqual(data["steps"][1]["label"], "1. X q0")

    def test_multi_compare_rejects_one_id(self):
        r = self.client.get("/api/experiments/compare/multi", params={"ids": "one"})
        self.assertEqual(r.status_code, 400)

    def test_csv_compare_missing_ids(self):
        r = self.client.get("/api/experiments/compare/export.csv", params={"a": "missing-a", "b": "missing-b"})
        self.assertEqual(r.status_code, 404)

    def test_experiment_import_rejects_wrong_format(self):
        r = self.client.post("/api/experiments/import", json={"format": "wrong"})
        self.assertEqual(r.status_code, 400)

    def test_rerun_missing_experiment(self):
        r = self.client.post("/api/experiments/missing/rerun")
        self.assertEqual(r.status_code, 404)

    def test_diagnostics_export(self):
        r = self.client.get("/api/diagnostics/export")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["format"], "qwantum-diagnostics")
        self.assertIn("generated_at", r.json())

    def test_experiment_export_not_found(self):
        r = self.client.get("/api/experiments/does-not-exist/export")
        self.assertEqual(r.status_code, 404)

    def test_statevector(self):
        if not QISKIT_AVAILABLE: self.skipTest("Qiskit unavailable")
        r=self.client.post("/api/statevector",json={"name":"zero","qubits":1,"shots":8,"gates":[]})
        self.assertEqual(r.status_code,200)
        self.assertAlmostEqual(r.json()["probabilities"][0]["probability"],1.0)

    def test_shots_stability_rejects_too_many_gates(self):
        r = self.client.post("/api/analysis/shots-stability", json={
            "name": "too-many", "qubits": 1, "shots": 128, "noise": 0,
            "gates": [{"gate": "x", "qubit": 0}] * 41
        })
        self.assertEqual(r.status_code, 400)

    def test_shots_stability_endpoint_shape(self):
        if not QISKIT_AVAILABLE:
            self.skipTest("Qiskit unavailable")
        r = self.client.post("/api/analysis/shots-stability", json={
            "name": "stable", "qubits": 1, "shots": 128, "noise": 0,
            "gates": [{"gate": "h", "qubit": 0}]
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["format"], "qwantum-shots-stability")
        self.assertTrue(len(data["results"]) >= 1)
        self.assertIn("mean_tvd", data["results"][0])

if __name__=="__main__": unittest.main()


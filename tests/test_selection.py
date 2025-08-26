from __future__ import annotations

import csv
from pathlib import Path

from src.selection import Candidate, PRIORITY, compute_quota, partition_by_category, run_lottery


def load_sample(path: Path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return [Candidate(row=r, categoria=r["categoria"]) for r in rows]


def test_quota_distribution():
    quotas = compute_quota(10, {"Aluno": 0.6, "Servidor": 0.2, "Comunidade Externa": 0.2})
    assert quotas["Aluno"] + quotas["Servidor"] + quotas["Comunidade Externa"] == 10


def test_run_lottery_determinism(tmp_path: Path):
    sample = Path(__file__).parent.parent / "data" / "candidatos_exemplo.csv"
    candidates = load_sample(sample)
    aprovados1, espera1 = run_lottery(candidates, vagas=7, pct_aluno=0.5, pct_servidor=0.3, pct_comunidade=0.2, seed=42)
    aprovados2, espera2 = run_lottery(candidates, vagas=7, pct_aluno=0.5, pct_servidor=0.3, pct_comunidade=0.2, seed=42)
    assert aprovados1 == aprovados2
    assert espera1 == espera2


def test_priority_and_redistribution():
    # Construir um caso com poucas vagas e falta em uma categoria
    rows = [
        {"id": "1", "nome": "A1", "categoria": "Aluno"},
        {"id": "2", "nome": "A2", "categoria": "Aluno"},
        {"id": "3", "nome": "S1", "categoria": "Servidor"},
    ]
    candidates = [Candidate(row=r, categoria=r["categoria"]) for r in rows]
    aprovados, espera = run_lottery(candidates, vagas=3, pct_aluno=0.6, pct_servidor=0.2, pct_comunidade=0.2, seed=1)
    # Deve aprovar todos os disponíveis, com prioridade para alunos, e redistribuir sobras
    assert len(aprovados) == 3
    assert set(r["id"] for r in aprovados) == {"1", "2", "3"}

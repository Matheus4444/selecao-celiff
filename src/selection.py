from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path
import re
import hashlib
from typing import Dict, Iterable, List, Tuple, Optional, Callable

PRIORITY = ["Aluno", "Servidor", "Comunidade Externa"]


@dataclass
class Candidate:
    row: Dict[str, str]
    categoria: str
    turma: Optional[str] = None


def _trueish(val: str) -> bool:
    v = (val or "").strip().lower()
    return v in {"true", "1", "sim", "yes", "y"}


def _detect_real_csv(fieldnames: List[str]) -> bool:
    needed = {"Turma [Vaga]", "Nome [Candidato]"}
    return needed.issubset(set(fieldnames or []))


def _categoria_from_real_row(row: Dict[str, str]) -> str:
    # Decide categoria pela maior prioridade dentre flags true
    if _trueish(row.get("Aluno [Candidato]", "")):
        return "Aluno"
    if _trueish(row.get("Servidor [Candidato]", "")):
        return "Servidor"
    if _trueish(row.get("Externo [Candidato]", "")):
        return "Comunidade Externa"
    # fallback: tratar como Comunidade Externa
    return "Comunidade Externa"


def read_candidates(csv_path: Path) -> List[Candidate]:
    """Lê candidatos de dois formatos:
    - Simples (colunas: id, nome, categoria)
    - CSV real (colunas: Turma [Vaga], Nome [Candidato], Aluno/Servidor/Externo [Candidato])
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        out: List[Candidate] = []
        if _detect_real_csv(fieldnames):
            for row in reader:
                cat = _categoria_from_real_row(row)
                turma = (row.get("Turma [Vaga]", "") or "").strip()
                # acrescente a categoria no row para exportar depois
                row = dict(row)
                row["categoria"] = cat
                out.append(Candidate(row=row, categoria=cat, turma=turma))
        else:
            required = {"id", "nome", "categoria"}
            missing = required - set(fieldnames)
            if missing:
                raise ValueError(f"CSV faltando colunas obrigatórias: {missing}")
            for row in reader:
                categoria = row.get("categoria", "").strip()
                if categoria not in PRIORITY:
                    raise ValueError(
                        f"Categoria inválida '{categoria}'. Esperado um de {PRIORITY}"
                    )
                out.append(Candidate(row=row, categoria=categoria, turma=row.get("turma")))
    return out


def partition_by_category(candidates: Iterable[Candidate]) -> Dict[str, List[Candidate]]:
    groups: Dict[str, List[Candidate]] = {k: [] for k in PRIORITY}
    for c in candidates:
        groups[c.categoria].append(c)
    return groups


def compute_quota(vagas: int, pct_by_cat: Dict[str, float]) -> Dict[str, int]:
    # Arredonda para baixo; sobras serão redistribuídas depois
    base = {cat: int(math.floor(vagas * max(0.0, pct_by_cat.get(cat, 0.0)))) for cat in PRIORITY}
    allocated = sum(base.values())
    remainder = vagas - allocated
    # Distribui sobras pela ordem de prioridade
    i = 0
    while remainder > 0:
        cat = PRIORITY[i % len(PRIORITY)]
        base[cat] += 1
        remainder -= 1
        i += 1
    return base


def draw_for_category(rng: random.Random, group: List[Candidate], k: int) -> Tuple[List[Candidate], List[Candidate]]:
    if k <= 0 or not group:
        return [], group.copy()
    if k >= len(group):
        # embaralha para produzir ordem determinística também na lista de espera
        shuffled = group.copy()
        rng.shuffle(shuffled)
        return shuffled, []
    # escolha sem reposição
    selected = rng.sample(group, k)
    # lista de espera = os demais na ordem aleatória
    remaining = [c for c in group if c not in selected]
    rng.shuffle(remaining)
    return selected, remaining


def redistribute_shortfalls(
    rng: random.Random,
    per_cat_selected: Dict[str, List[Candidate]],
    per_cat_waiting: Dict[str, List[Candidate]],
    per_cat_quota: Dict[str, int],
) -> None:
    # Se alguma categoria não alcançou sua cota por falta de candidatos,
    # redistribui suas vagas restantes para as categorias de maior prioridade com candidatos na espera.
    deficit_by_cat = {
        cat: max(0, per_cat_quota[cat] - len(per_cat_selected.get(cat, []))) for cat in PRIORITY
    }
    total_deficit = sum(deficit_by_cat.values())
    if total_deficit == 0:
        return

    # Preenche vagas extras começando da maior prioridade
    for cat in PRIORITY:
        if total_deficit == 0:
            break
        waitlist = per_cat_waiting.get(cat, [])
        while waitlist and total_deficit > 0:
            cand = waitlist.pop(0)  # já está numa ordem aleatória
            per_cat_selected[cat].append(cand)
            total_deficit -= 1

    # Se ainda sobrar déficit (não havia candidatos suficientes em nenhuma categoria), não há o que fazer


def run_lottery(
    candidates: List[Candidate],
    vagas: int,
    pct_aluno: float,
    pct_servidor: float,
    pct_comunidade: float,
    seed: int,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    if vagas <= 0:
        return [], []

    # Normaliza percentuais caso não somem 1.0 (opcional): mantém proporção
    total_pct = pct_aluno + pct_servidor + pct_comunidade
    if total_pct <= 0:
        raise ValueError("A soma dos percentuais deve ser > 0")
    pct_aluno, pct_servidor, pct_comunidade = (
        pct_aluno / total_pct,
        pct_servidor / total_pct,
        pct_comunidade / total_pct,
    )

    rng = random.Random(seed)

    groups = partition_by_category(candidates)

    quotas = compute_quota(
        vagas,
        {
            "Aluno": pct_aluno,
            "Servidor": pct_servidor,
            "Comunidade Externa": pct_comunidade,
        },
    )

    per_cat_selected: Dict[str, List[Candidate]] = {k: [] for k in PRIORITY}
    per_cat_waiting: Dict[str, List[Candidate]] = {k: [] for k in PRIORITY}

    # Sorteio por categoria
    for cat in PRIORITY:
        selected, waiting = draw_for_category(rng, groups.get(cat, []), quotas[cat])
        per_cat_selected[cat] = selected
        per_cat_waiting[cat] = waiting

    # Redistribui sobras por prioridade
    redistribute_shortfalls(rng, per_cat_selected, per_cat_waiting, quotas)

    # Consolida aprovados (na ordem de prioridade: Aluno, Servidor, Comunidade)
    aprovados: List[Candidate] = []
    for cat in PRIORITY:
        aprovados.extend(per_cat_selected[cat])

    # Se, por redistribuição, ainda faltarem vagas (por falta total de candidatos), truncar pelo total de vagas
    aprovados = aprovados[:vagas]

    # Lista de espera: todos os restantes, por prioridade e ordem aleatória já definida
    espera: List[Candidate] = []
    for cat in PRIORITY:
        espera.extend(per_cat_waiting[cat])
    # também incluir os candidatos não selecionados inicialmente porque não couberam após truncar (caso extremo)
    # porém aqui aprovados já é no máximo vagas, então não há excedentes em selected

    return [c.row for c in aprovados], [c.row for c in espera]


# -------------------- Sorteio por turma (real CSV) --------------------

def _parse_int_maybe(val: str) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s == "-":
        return None
    m = re.search(r"\d+", s)
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


def _allowed_cats_for_turma(sample_row: Dict[str, str]) -> List[str]:
    allowed = []
    if _trueish(sample_row.get("Aluno [Vaga]", "true")):
        allowed.append("Aluno")
    if _trueish(sample_row.get("Servidor [Vaga]", "true")):
        allowed.append("Servidor")
    if _trueish(sample_row.get("Externo [Vaga]", "true")):
        allowed.append("Comunidade Externa")
    # Se nenhuma marcada, considerar todas permitidas
    return allowed or PRIORITY.copy()


def _normalize_pcts(pcts: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, p) for p in pcts.values())
    if total <= 0:
        raise ValueError("A soma dos percentuais deve ser > 0")
    return {k: max(0.0, v) / total for k, v in pcts.items()}


def run_lottery_per_turma(
    candidates: List[Candidate],
    vagas_por_turma: Dict[str, int],
    pct_aluno: float,
    pct_servidor: float,
    pct_comunidade: float,
    seed: int,
) -> Dict[str, Tuple[List[Dict[str, str]], List[Dict[str, str]]]]:
    """Executa o sorteio independentemente por turma.
    - Respeita categorias permitidas por turma (se presentes no CSV real)
    - Aplica as mesmas porcentagens de reserva para cada turma
    - Usa seed derivada por turma para reprodutibilidade isolada
    Retorna: {turma: (aprovados_rows, espera_rows)}
    """
    # Agrupar por turma
    turmas: Dict[str, List[Candidate]] = {}
    for c in candidates:
        t = c.turma or ""
        turmas.setdefault(t, []).append(c)

    # Normaliza percentuais globais
    pcts = _normalize_pcts({
        "Aluno": pct_aluno,
        "Servidor": pct_servidor,
        "Comunidade Externa": pct_comunidade,
    })

    results: Dict[str, Tuple[List[Dict[str, str]], List[Dict[str, str]]]] = {}

    # Determinar categorias permitidas por turma com base em uma linha de amostra
    sample_by_turma: Dict[str, Dict[str, str]] = {}
    for c in candidates:
        if c.turma not in sample_by_turma and c.turma is not None:
            sample_by_turma[c.turma] = c.row

    for turma, cands in turmas.items():
        vagas = vagas_por_turma.get(turma, 0)
        if vagas <= 0:
            results[turma] = ([], [])
            continue
        allowed = _allowed_cats_for_turma(sample_by_turma.get(turma, {}))

        # Filtrar candidatos apenas para categorias permitidas
        cands_allowed = [c for c in cands if c.categoria in allowed]

        # Ajustar percentuais: zera para categorias não permitidas e normaliza
        pcts_turma = {cat: (pcts[cat] if cat in allowed else 0.0) for cat in PRIORITY}
        pcts_turma = _normalize_pcts(pcts_turma)

        # RNG derivada por turma (determinística e estável entre execuções)
        h = hashlib.sha256(f"{seed}|{turma}".encode("utf-8")).hexdigest()
        rng_seed = int(h[:16], 16)
        rng = random.Random(rng_seed)

        # Preparar grupos e quotas por turma
        groups = partition_by_category(cands_allowed)
        quotas = compute_quota(vagas, pcts_turma)

        per_cat_selected: Dict[str, List[Candidate]] = {k: [] for k in PRIORITY}
        per_cat_waiting: Dict[str, List[Candidate]] = {k: [] for k in PRIORITY}

        for cat in PRIORITY:
            selected, waiting = draw_for_category(rng, groups.get(cat, []), quotas[cat])
            per_cat_selected[cat] = selected
            per_cat_waiting[cat] = waiting

        redistribute_shortfalls(rng, per_cat_selected, per_cat_waiting, quotas)

        aprovados: List[Candidate] = []
        for cat in PRIORITY:
            aprovados.extend(per_cat_selected[cat])
        aprovados = aprovados[:vagas]

        espera: List[Candidate] = []
        for cat in PRIORITY:
            espera.extend(per_cat_waiting[cat])

        results[turma] = ([c.row for c in aprovados], [c.row for c in espera])

    return results


def write_csv(rows: List[Dict[str, str]], header: List[str], out_path: Path) -> None:
    """Escreve CSV com as colunas solicitadas:
    - Id do candidato
    - Número de sorteio do candidato (coluna 'Numero' do CSV real)
    - Nome
    - Turma
    - Categoria (Aluno, Servidor ou Comunidade Externa)

    Aceita tanto CSV real quanto o formato simples (faz mapeamento de chaves quando possível).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    target_fields = [
        "Id [Candidato]",
        "Número de sorteio",
        "Nome [Candidato]",
        "Turma [Vaga]",
        "Categoria",
    ]

    def project(r: Dict[str, str]) -> Dict[str, str]:
        # Categoria já é incorporada em read_candidates (campo 'categoria')
        categoria = r.get("categoria") or (
            "Aluno" if r.get("Aluno [Candidato]") in ("true", "True", True) else (
                "Servidor" if r.get("Servidor [Candidato]") in ("true", "True", True) else (
                    "Comunidade Externa" if r.get("Externo [Candidato]") in ("true", "True", True) else ""
                )
            )
        )
        return {
            "Id [Candidato]": r.get("Id [Candidato]") or r.get("id") or "",
            "Número de sorteio": r.get("Numero") or "",
            "Nome [Candidato]": r.get("Nome [Candidato]") or r.get("nome") or "",
            "Turma [Vaga]": r.get("Turma [Vaga]") or r.get("turma") or "",
            "Categoria": categoria,
        }

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=target_fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(project(r))

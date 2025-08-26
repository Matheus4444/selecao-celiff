from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .selection import (
    PRIORITY,
    read_candidates,
    run_lottery,
    run_lottery_per_turma,
    write_csv,
)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sorteio de candidatos com cotas e prioridade",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", required=True, help="CSV de entrada com candidatos")
    p.add_argument("--vagas", type=int, required=False, help="Número total de vagas (obrigatório no modo simples; opcional no modo por turma)")
    p.add_argument("--pct-aluno", type=float, required=True, help="Percentual de vagas para Aluno (0-1)")
    p.add_argument("--pct-servidor", type=float, required=True, help="Percentual de vagas para Servidor (0-1)")
    p.add_argument(
        "--pct-comunidade",
        type=float,
        required=True,
        help="Percentual de vagas para Comunidade Externa (0-1)",
    )
    p.add_argument("--seed", type=int, required=True, help="Seed do sorteio para reprodutibilidade")
    p.add_argument("--por-turma", action="store_true", help="Executa sorteio por turma (usa coluna 'Turma [Vaga]')")
    p.add_argument(
        "--vagas-por-turma",
        help="Especificar vagas por turma, formato TURMA=NUM;TURMA2=NUM2 (se omitido, tenta ler do CSV real 'Quantidade vagas [Vaga]')",
    )
    p.add_argument("--out-aprovados", help="Arquivo CSV de saída para aprovados (ou prefixo quando por turma)")
    p.add_argument("--out-espera", help="Arquivo CSV de saída para lista de espera (ou prefixo quando por turma)")
    p.add_argument(
        "--out-consolidado-aprovados",
        help="Caminho para CSV único com todos os aprovados de todas as turmas (somente com --por-turma)",
    )
    p.add_argument(
        "--out-consolidado-espera",
        help="Caminho para CSV único com toda a lista de espera de todas as turmas (somente com --por-turma)",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    candidates = read_candidates(input_path)

    if args.por_turma:
        # Monta vagas por turma: via argumento ou via CSV real
        vagas_por_turma = {}
        if args.vagas_por_turma:
            for part in args.vagas_por_turma.split(";"):
                if not part.strip():
                    continue
                turma, num = part.split("=", 1)
                vagas_por_turma[turma.strip()] = int(num.strip())
        else:
            # tentar inferir a partir do CSV real: "Quantidade vagas [Vaga]" por turma
            for c in candidates:
                turma = (c.turma or "").strip()
                if turma and turma not in vagas_por_turma:
                    raw = c.row.get("Quantidade vagas [Vaga]")
                    # pode ser '-' ou vazio; nesse caso requer --vagas-por-turma ou --vagas
                    try:
                        from .selection import _parse_int_maybe  # type: ignore
                    except Exception:
                        _parse_int_maybe = lambda x: None  # noqa: E731
                    v = _parse_int_maybe(raw or "")
                    if v is not None:
                        vagas_por_turma[turma] = v
        # fallback: usa --vagas como valor padrão para qualquer turma sem definição
        if args.vagas is not None:
            for c in candidates:
                t = c.turma or ""
                vagas_por_turma.setdefault(t, args.vagas)

        results = run_lottery_per_turma(
            candidates=candidates,
            vagas_por_turma=vagas_por_turma,
            pct_aluno=args.__dict__["pct_aluno"],
            pct_servidor=args.__dict__["pct_servidor"],
            pct_comunidade=args.__dict__["pct_comunidade"],
            seed=args.seed,
        )

        # O writer projeta colunas fixas; o header aqui é ignorado, mas passamos as mesmas chaves
        header = [
            "Id [Candidato]",
            "Número de sorteio",
            "Nome [Candidato]",
            "Turma [Vaga]",
            "Categoria",
        ]

        def out_path(base: Optional[str], turma: str, suffix: str) -> Optional[Path]:
            if not base:
                return None
            base = base.rstrip("/")
            safe_turma = turma.replace("/", "-").replace(" ", "_")
            return Path(f"{base}_{safe_turma}_{suffix}.csv")

        # imprimir e opcionalmente salvar por turma
        for turma, (aprovados, espera) in results.items():
            print(f"\n=== Turma: {turma} ===")
            def fmt(rows):
                # tenta usar colunas amigáveis; cai para id/nome/categoria se existirem
                lines = []
                for r in rows:
                    nome = r.get("Nome [Candidato]") or r.get("nome")
                    ident = r.get("Id [Candidato]") or r.get("id")
                    cat = r.get("categoria")
                    lines.append(f"{ident} - {nome} ({cat})")
                return lines

            print("Aprovados:")
            for s in fmt(aprovados):
                print(" - ", s)
            print("Lista de espera:")
            for s in fmt(espera):
                print(" - ", s)

            ap = out_path(args.out_aprovados, turma, "aprovados")
            es = out_path(args.out_espera, turma, "espera")
            if ap:
                write_csv(aprovados, header, ap)
            if es:
                write_csv(espera, header, es)

        # Saídas consolidadas
        def ensure_turma(rows: list[dict], turma: str) -> list[dict]:
            out = []
            for r in rows:
                rr = dict(r)
                rr.setdefault("Turma [Vaga]", turma)
                out.append(rr)
            return out

    # Cabeçalho fixo também para os consolidados
        if args.out_consolidado_aprovados:
            all_aprovados: list[dict] = []
            for turma in sorted(results.keys()):
                apr, _ = results[turma]
                all_aprovados.extend(ensure_turma(apr, turma))
            write_csv(all_aprovados, header, Path(args.out_consolidado_aprovados))
        if args.out_consolidado_espera:
            all_espera: list[dict] = []
            for turma in sorted(results.keys()):
                _, esp = results[turma]
                all_espera.extend(ensure_turma(esp, turma))
            write_csv(all_espera, header, Path(args.out_consolidado_espera))
    else:
        aprovados, espera = run_lottery(
            candidates=candidates,
            vagas=args.vagas,
            pct_aluno=args.__dict__["pct_aluno"],
            pct_servidor=args.__dict__["pct_servidor"],
            pct_comunidade=args.__dict__["pct_comunidade"],
            seed=args.seed,
        )

        header = [
            "Id [Candidato]",
            "Número de sorteio",
            "Nome [Candidato]",
            "Turma [Vaga]",
            "Categoria",
        ]

        if args.out_aprovados:
            write_csv(aprovados, header, Path(args.out_aprovados))
        if args.out_espera:
            write_csv(espera, header, Path(args.out_espera))

        # Saída legível no terminal
        def fmt(rows):
            return [f"{r.get('id')} - {r.get('nome')} ({r.get('categoria')})" for r in rows]

        print("Aprovados:")
        for s in fmt(aprovados):
            print(" - ", s)

        print("\nLista de espera:")
        for s in fmt(espera):
            print(" - ", s)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

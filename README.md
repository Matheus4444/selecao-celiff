# Seleção CELIFF - Sorteio com prioridade baseada em categorias

Este projeto implementa um sorteio de candidatos com três categorias e ordem de prioridade:

1. Aluno
2. Servidor
3. Comunidade Externa

Cada categoria possui uma porcentagem de vagas reservadas. Sobras são redistribuídas respeitando a ordem de prioridade.

- Entrada: CSV simples (colunas mínimas: `id`, `nome`, `categoria`) ou CSV real exportado do sistema (campos como `Turma [Vaga]`, `Nome [Candidato]`, flags `Aluno/Servidor/Externo [Candidato]`).
- Parâmetros: número total de vagas, percentuais por categoria, e seed para reprodutibilidade.
- Saída: CSVs com aprovados e lista de espera.

## Uso rápido

Opcionalmente crie e ative um virtualenv. Depois, instale dependências (somente stdlib; não há requirements) e rode:

```bash
python -m src.cli \
  --input data/candidatos_exemplo.csv \
  --vagas 10 \
  --pct-aluno 0.6 \
  --pct-servidor 0.2 \
  --pct-comunidade 0.2 \
  --seed 12345 \
  --out-aprovados out/aprovados.csv \
  --out-espera out/espera.csv
```

### Modo por turma (CSV real)

O CSV real possui colunas como `Turma [Vaga]`, `Quantidade vagas [Vaga]`, `Nome [Candidato]`, e flags `Aluno/Servidor/Externo [Candidato]`.

- Rodar por turma com vagas lidas do próprio CSV (quando preenchidas):

```bash
python -m src.cli \
  --input data/inscricao_2025-03-24_15h43m57.csv \
  --pct-aluno 0.6 --pct-servidor 0.2 --pct-comunidade 0.2 \
  --seed 42 \
  --por-turma
```

- Forçar vagas por turma via argumento:

```bash
python -m src.cli \
  --input data/inscricao_2025-03-24_15h43m57.csv \
  --pct-aluno 0.6 --pct-servidor 0.2 --pct-comunidade 0.2 \
  --seed 42 \
  --por-turma \
  --vagas-por-turma "CCGI - 101=20;CCGE - 101=15"
```

- Salvar um CSV por turma usando um prefixo de saída:

```bash
python -m src.cli \
  --input data/inscricao_2025-03-24_15h43m57.csv \
  --pct-aluno 0.6 --pct-servidor 0.2 --pct-comunidade 0.2 \
  --seed 42 \
  --por-turma \
  --out-aprovados out/resultados \
  --out-espera out/resultados
```

Veja `--help` para todas as opções.

## Formato do CSV de entrada

Colunas válidas:

- CSV simples: `id`, `nome`, `categoria` (um de `Aluno`, `Servidor`, `Comunidade Externa`).
- CSV real: `Turma [Vaga]`, `Nome [Candidato]`, flags `Aluno/Servidor/Externo [Candidato]`; a categoria é inferida pela maior prioridade entre as flags marcadas.
  Todas as colunas lidas são preservadas nas saídas, com um campo adicional `categoria` calculado no caso do CSV real.

## Regras

- Prioridade: Aluno > Servidor > Comunidade Externa.
- Reserva de vagas por percentual arredondada para baixo, com redistribuição de sobras por prioridade.
- Sorteio dentro de cada categoria usando seed determinística.
- Se faltarem candidatos em uma categoria, as vagas remanescentes são redistribuídas por prioridade.
- Resultado reprodutível para a mesma seed e entrada.

## Teste rápido

```bash
python -m src.cli --input data/candidatos_exemplo.csv --vagas 7 \
  --pct-aluno 0.5 --pct-servidor 0.3 --pct-comunidade 0.2 --seed 42
```

Os aprovados e a lista de espera serão impressos no terminal.

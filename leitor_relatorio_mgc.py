import csv
import re
from pathlib import Path

def numeros(v):
    return re.sub(r'\D', '', str(v or ''))


def ler_csv(path):
    content = Path(path).read_bytes()
    result = None
    for encoding in ('utf-8-sig', 'cp1252', 'latin1'):
        try:
            text = content.decode(encoding)
            lines = text.splitlines()
            idx = next(i for i, line in enumerate(lines) if 'CPF/CNS' in line and 'Nome equipe' in line)
            rows = list(csv.DictReader(lines[idx:], delimiter=';'))
            if not rows:
                raise ValueError('Nenhum registro no relatório')
            result = rows
            break
        except (UnicodeDecodeError, StopIteration):
            continue
    if result is None:
        raise ValueError('Cabeçalho do relatório do PEC não encontrado')
    seen, people = set(), []
    for n, row in enumerate(result, 1):
        ident = numeros(row.get('CPF/CNS', ''))
        nome = (row.get('Nome') or '').strip()
        nascimento = (row.get('Data de nascimento') or '').strip()
        key = ident or f'SEM_ID_{n}_{nome}_{nascimento}'
        if not nome or key in seen:
            continue
        seen.add(key)
        people.append({'id': key, 'cpf_cns': ident, 'nome': nome,
                       'nascimento': nascimento, 'telefone': numeros(row.get('Telefone celular', '')),
                       'manual': not bool(ident)})
    return people



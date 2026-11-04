"""PEC v0.3.6 — lote com verificação automática de persistência no próprio PEC.
Em resultados ambíguos, interrompe e solicita conferência do operador.
"""
import csv
import hashlib
import json
import queue
import re
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent
DATA = Path.home() / 'Documents' / 'Automatizador_PEC'
DATA.mkdir(parents=True, exist_ok=True)


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


# Regra opcional da coordenação: número de contato substituto informado pelo operador.
# IMPORTANTE: este número deve ter autorização formal para uso como contato administrativo.
TELEFONE_COORDENACAO = '22997979797'
DDDS_VALIDOS = {11,12,13,14,15,16,17,18,19,21,22,24,27,28,31,32,33,34,35,37,38,41,42,43,44,45,46,47,48,49,51,53,54,55,61,62,63,64,65,66,67,68,69,71,73,74,75,77,79,81,82,83,84,85,86,87,88,89,91,92,93,94,95,96,97,98,99}


def telefone_celular_invalido(valor):
    """Somente invalidez estrutural; não tenta deduzir se um número plausível é fictício."""
    tel = numeros(valor)
    if not tel:
        return True
    if len(tel) != 11 or int(tel[:2]) not in DDDS_VALIDOS or tel[2] != '9':
        return True
    if len(set(tel)) == 1 or len(set(tel[2:])) == 1:
        return True
    return False


def validar_servidor(txt):
    u = urlsplit(txt.strip())
    if u.scheme not in ('http', 'https') or not u.netloc or u.username or u.password:
        raise ValueError('Informe um servidor válido, como http://servidor:8080')
    return f'{u.scheme}://{u.netloc}'


class BrowserWorker(threading.Thread):
    def __init__(self, commands, responses, base_url, autorizar_indocumentada=False, autorizar_telefone=False, autorizar_fora_area=False):
        super().__init__(daemon=True)
        self.commands, self.responses, self.base_url = commands, responses, base_url
        self.autorizar_indocumentada = autorizar_indocumentada
        self.autorizar_telefone = autorizar_telefone
        self.autorizar_fora_area = autorizar_fora_area
        self.fora_area_requer_verificacao = False
        self.validated_person = None
        self.validated_edit_url = None
        self.territory_marked = False
        self.manual_verified = False
        self.cns_missing_cpf = False

    def emit(self, operation, success, detail):
        self.responses.put((operation, success, detail))

    def run(self):
        from playwright.sync_api import sync_playwright
        profile = DATA / 'perfil_chrome'
        with sync_playwright() as pw:
            try:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile), channel='chrome', headless=False,
                    no_viewport=True, args=['--start-maximized'], accept_downloads=False)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(self.base_url + '/gestaoCadastros/cadastro-individual', wait_until='domcontentloaded', timeout=30000)
                self.emit('abrir', True, 'Chrome aberto. Faça login normalmente, se necessário.')
            except Exception as e:
                self.emit('abrir', False, f'Não foi possível abrir o Chrome: {str(e)[:220]}')
                return
            while True:
                op, person = self.commands.get()
                if op == 'fechar':
                    break
                try:
                    if op == 'pesquisar':
                        self.validated_person = None
                        self.validated_edit_url = None
                        self.territory_marked = False
                        self.fora_area_requer_verificacao = False
                        self.manual_verified = False
                        self.cns_missing_cpf = False
                        page.goto(self.base_url + '/gestaoCadastros/cadastro-individual', wait_until='domcontentloaded', timeout=30000)
                        search = page.locator('input[name="nomeCpfCns"]')
                        search.wait_for(state='visible', timeout=20000)
                        if search.count() != 1:
                            raise ValueError('Campo Nome/CNS/CPF ambíguo. Pesquisa interrompida.')
                        search.fill(person['cpf_cns'])
                        buscar = page.locator('[data-cy="BuscarCidadaoButton"]')
                        if buscar.count() != 1:
                            raise ValueError('Botão Buscar cadastro não identificado de forma única.')
                        buscar.click()
                        # O resultado precisa corresponder a UM cidadão antes de abrir o menu.
                        dropdown = page.locator('[data-testid="Button.Dropdown"]')
                        dropdown.first.wait_for(state='visible', timeout=20000)
                        if dropdown.count() != 1:
                            raise ValueError('Pesquisa retornou múltiplas ações ou resultados; confira manualmente.')
                        # Checagem conservadora: CPF/CNS do resultado renderizado, sem usar a URL.
                        content = page.locator('main').inner_text(timeout=10000)
                        if person['cpf_cns'] not in numeros(content):
                            raise ValueError('Identificador não confirmado no resultado. Nada foi aberto.')
                        dropdown.click()
                        item = page.get_by_role('menuitem', name='Atualizar cadastro', exact=True)
                        if item.count() != 1 or not item.is_visible():
                            raise ValueError('Opção Atualizar cadastro não localizada no menu.')
                        item.click()
                        page.wait_for_url(re.compile(r'/gestaoCadastros/cadastro-individual/\d+/edit'), timeout=20000)
                        found = []
                        for selector in ('input[name="dadosPessoais.cpf"]', 'input[name="dadosPessoais.cns"]'):
                            field = page.locator(selector)
                            if field.count() == 1:
                                found.append(numeros(field.input_value()))
                        if person['cpf_cns'] not in found:
                            # PEC pode renderizar campos de identidade assincronamente.
                            for _ in range(10):
                                page.wait_for_timeout(500)
                                found = []
                                for selector in ('input[name="dadosPessoais.cpf"]', 'input[name="dadosPessoais.cns"]'):
                                    el = page.locator(selector)
                                    if el.count() == 1:
                                        found.append(numeros(el.input_value()))
                                if person['cpf_cns'] in found:
                                    break
                        self.validated_edit_url = page.url
                        if person['cpf_cns'] not in found:
                            self.emit(op, False, 'Edição aberta, mas identificação automática inconclusiva. CONFIRA NOME, NASCIMENTO E CPF/CNS NA TELA e clique em Confirmar cadastro visualmente. Nenhum campo foi alterado.')
                        else:
                            self.validated_person = person['id']
                            cpf_field = page.locator('input[name="dadosPessoais.cpf"]')
                            self.cns_missing_cpf = (len(person['cpf_cns']) == 15 and cpf_field.count() == 1 and not numeros(cpf_field.input_value()))
                            detail = 'Cadastro conferido e edição aberta.'
                            if self.cns_missing_cpf:
                                detail += ' SOMENTE_CNS_SEM_CPF: confirme no PEC a declaração de ausência de CPF e a justificativa apropriada antes de continuar.'
                            self.emit(op, True, detail)
                    elif op == 'inspecionar_cpf':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('Identificação não confirmada para inspeção de CPF.')
                        cpf_field = page.locator('input[name="dadosPessoais.cpf"]')
                        cns_field = page.locator('input[name="dadosPessoais.cns"]')
                        has_cpf = cpf_field.count() == 1 and bool(numeros(cpf_field.input_value()))
                        has_cns = cns_field.count() == 1 and bool(numeros(cns_field.input_value()))
                        if not has_cpf and has_cns:
                            self.emit(op, True, 'SOMENTE_CNS_SEM_CPF: confirme ausência real de CPF e justificativa no PEC antes de continuar.')
                        elif has_cpf:
                            self.emit(op, True, 'CPF existente no cadastro. Continuando.')
                        else:
                            raise ValueError('CPF/CNS não disponível na edição. Revisão necessária.')
                    elif op == 'regularizar_cpf':
                        # Aplicar somente a cadastro previamente identificado pelo CNS e com CPF realmente vazio no PEC.
                        if not self.autorizar_indocumentada:
                            raise ValueError('Regra Pessoa indocumentada não autorizada para este lote.')
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('CPF ausente: edição não corresponde ao cidadão validado.')
                        if len(person['cpf_cns']) != 15:
                            raise ValueError('CPF ausente: o identificador da busca não é um CNS.')
                        cpf_el=page.locator('input[name="dadosPessoais.cpf"]')
                        cns_el=page.locator('input[name="dadosPessoais.cns"]')
                        if cpf_el.count()!=1 or cns_el.count()!=1 or numeros(cpf_el.input_value()) or numeros(cns_el.input_value()) != person['cpf_cns']:
                            raise ValueError('CPF/CNS na tela não atende à regra. Revisão manual necessária.')
                        flag=page.locator('input[name="dadosPessoais.stNaoPossuiCpf"]')
                        if flag.count()!=1:
                            raise ValueError('Checkbox Cidadão não possui CPF não identificado.')
                        if not flag.is_checked():
                            label=page.locator('label').filter(has=flag)
                            if label.count()!=1: raise ValueError('Rótulo Cidadão não possui CPF ambíguo.')
                            label.click(timeout=5000)
                        if not flag.is_checked(): raise ValueError('Checkbox de ausência de CPF não foi marcado.')
                        # Campo real identificado no HTML salvo do PEC (Downshift).
                        campo = page.locator('input[name="dadosPessoais.justificativaNaoPossuiCpf"]')
                        if campo.count() != 1:
                            raise ValueError('Campo de justificativa não localizado de forma única; não foi salvo.')
                        def valor_justificativa():
                            return campo.input_value(timeout=3000).strip()
                        atual = valor_justificativa()
                        if atual and atual.casefold() != 'pessoa indocumentada':
                            raise ValueError('Já existe justificativa diferente. Preservada para revisão.')
                        if atual.casefold() != 'pessoa indocumentada':
                            campo.click(timeout=5000)
                            opc = page.get_by_role('option', name='Pessoa indocumentada', exact=True)
                            if opc.count() != 1 or not opc.is_visible():
                                raise ValueError('Opção Pessoa indocumentada indisponível; não foi salvo.')
                            opc.click(timeout=5000)
                        # Conferir o valor persistido no input real após a seleção React.
                        confirmado = False
                        for _ in range(16):
                            page.wait_for_timeout(250)
                            if flag.is_checked() and valor_justificativa().casefold() == 'pessoa indocumentada':
                                confirmado = True
                                break
                        if not confirmado:
                            raise ValueError('Justificativa não registrada no input após seleção. Pausando sem salvar.')
                        self.emit(op,True,'Somente CNS: checkbox de ausência de CPF e justificativa Pessoa indocumentada selecionados; ainda NÃO salvos.')
                    elif op == 'confirmar_manual':
                        if not re.search(r'/gestaoCadastros/cadastro-individual/\d+/edit', page.url):
                            raise ValueError('Abra uma página de edição do cidadão antes da confirmação.')
                        if self.validated_edit_url != page.url:
                            raise ValueError('A tela de edição mudou desde a pesquisa. Pesquise novamente.')
                        self.validated_person = person['id']
                        self.manual_verified = True
                        cpf_field = page.locator('input[name="dadosPessoais.cpf"]')
                        self.cns_missing_cpf = (len(person['cpf_cns']) == 15 and cpf_field.count() == 1 and not numeros(cpf_field.input_value()))
                        self.emit(op, True, 'Conferência manual aceita para este cidadão e esta URL de edição. Ainda NÃO houve alteração.')
                    elif op == 'marcar':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('BLOQUEADO: pesquisa deste cidadão não foi confirmada nesta sessão. Pesquise novamente antes de marcar.')
                        if not re.search(r'/gestaoCadastros/cadastro-individual/\d+/edit', page.url):
                            raise ValueError('O Chrome não está na tela de edição do cadastro individual.')
                        found = []
                        for selector in ('input[name="dadosPessoais.cpf"]', 'input[name="dadosPessoais.cns"]'):
                            el = page.locator(selector)
                            if el.count() == 1:
                                found.append(numeros(el.input_value()))
                        if person['cpf_cns'] not in found and not self.manual_verified:
                            raise ValueError('CPF/CNS da tela não corresponde ao CSV. Confirme visualmente antes de marcar.')
                        flag = page.locator('input[name="responsabilidadeAcompanhamento.statusCidadaoSaiuTerritorio"]')
                        if flag.count() != 1:
                            raise ValueError('Campo Mudou-se não encontrado de forma inequívoca.')
                        # O PEC usa um checkbox personalizado: o input pode ficar visualmente oculto.
                        # Clicar no input com check() produz tentativas repetidas de rolagem.
                        # Acione somente o LABEL real desse input, sem rolagem automática.
                        if not flag.is_checked():
                            label = page.locator('label').filter(has=flag)
                            if label.count() != 1:
                                raise ValueError('Rótulo Mudou-se não encontrado de forma inequívoca.')
                            label.click(timeout=5000, no_wait_after=True)
                            page.wait_for_timeout(250)
                        if not flag.is_checked():
                            raise ValueError('A opção Mudou-se não ficou marcada. Nenhuma confirmação foi registrada; confira manualmente.')
                        self.territory_marked = True
                        if self.autorizar_fora_area:
                            fora = page.locator('input[name="responsabilidadeAcompanhamento.statusForaArea"]')
                            if fora.count() != 1:
                                raise ValueError('Regra Fora de área ativada, mas checkbox não é único. PAUSAR sem salvar.')
                            if fora.is_checked():
                                rotulo_fora = page.locator('label').filter(has=fora)
                                if rotulo_fora.count() != 1:
                                    raise ValueError('Rótulo Fora de área não identificado de forma inequívoca. PAUSAR sem salvar.')
                                rotulo_fora.click(timeout=5000, no_wait_after=True)
                                page.wait_for_timeout(250)
                                if fora.is_checked():
                                    raise ValueError('Fora de área permaneceu marcado após clique. PAUSAR sem salvar.')
                                self.emit('aviso_etapa', True, 'Regra opcional: Fora de área DESMARCADO nesta edição, AINDA NÃO SALVO.')
                            else:
                                self.emit('aviso_etapa', True, 'Regra opcional: Fora de área já estava desmarcado; preservado.')
                            self.fora_area_requer_verificacao = True
                        self.emit(op, True, 'Opção Mudou-se CONFIRMADA, AINDA NÃO SALVA. Agora use Preencher NÃO somente nos campos vazios.')
                    elif op == 'preencher_vazios':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('BLOQUEADO: é necessário pesquisar e confirmar este cidadão antes de alterar respostas.')
                        if not self.territory_marked:
                            raise ValueError('BLOQUEADO: marque primeiro a saída do território.')
                        if not re.search(r'/gestaoCadastros/cadastro-individual/\d+/edit', page.url):
                            raise ValueError('O Chrome não está na edição deste cadastro.')
                        encontrados = []
                        for selector in ('input[name="dadosPessoais.cpf"]', 'input[name="dadosPessoais.cns"]'):
                            el = page.locator(selector)
                            if el.count() == 1:
                                encontrados.append(numeros(el.input_value()))
                        if person['cpf_cns'] not in encontrados and not self.manual_verified:
                            raise ValueError('BLOQUEADO: confirme visualmente a identidade do cidadão antes de preencher.')
                        campos = [
                            ('Identidade de gênero', 'dadosPessoais.desejaInformarIdentidadeGenero'),
                            ('Orientação sexual', 'dadosPessoais.desejaInformarOrientacaoSexual'),
                            ('Situação de rua', 'statusSituacaoRua'),
                        ]
                        resultados = []
                        for titulo, nome in campos:
                            radios = page.locator(f'input[type="radio"][name="{nome}"]')
                            if radios.count() != 2:
                                raise ValueError(f'{titulo}: estrutura inesperada ({radios.count()} alternativas). Interrompido.')
                            marcados = radios.evaluate_all('(els) => els.filter(e => e.checked).map(e => e.value)')
                            if len(marcados) > 1:
                                raise ValueError(f'{titulo}: múltiplas respostas marcadas. Interrompido.')
                            if marcados:
                                resultados.append(f'{titulo}: mantido {marcados[0]}')
                                continue
                            nao = page.locator(f'input[type="radio"][name="{nome}"][value="NAO"]')
                            if nao.count() != 1:
                                raise ValueError(f'{titulo}: opção NÃO ambígua ou ausente.')
                            rotulo = page.locator('label').filter(has=nao)
                            if rotulo.count() != 1:
                                raise ValueError(f'{titulo}: rótulo visível não encontrado.')
                            rotulo.click(timeout=5000)
                            page.wait_for_timeout(150)
                            if not nao.is_checked():
                                raise ValueError(f'{titulo}: clique não confirmou NÃO. Interrompido.')
                            resultados.append(f'{titulo}: vazio → NÃO')
                        self.emit(op, True, ' | '.join(resultados) + ' | Alterações AINDA NÃO SALVAS. Confira no PEC.')
                    elif op == 'revisar_campos':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('BLOQUEADO: confira primeiro a pesquisa do cidadão atual.')
                        if not re.search(r'/gestaoCadastros/cadastro-individual/\d+/edit', page.url):
                            raise ValueError('Abra a edição do cadastro antes de revisar respostas.')
                        found = []
                        for selector in ('input[name="dadosPessoais.cpf"]', 'input[name="dadosPessoais.cns"]'):
                            el = page.locator(selector)
                            if el.count() == 1:
                                found.append(numeros(el.input_value()))
                        if person['cpf_cns'] not in found and not self.manual_verified:
                            raise ValueError('CPF/CNS diferente do CSV. Confirme visualmente primeiro.')
                        campos = [
                            ('Deseja informar identidade de gênero?', 'dadosPessoais.desejaInformarIdentidadeGenero'),
                            ('Deseja informar orientação sexual?', 'dadosPessoais.desejaInformarOrientacaoSexual'),
                            ('Cidadão em situação de rua?', 'statusSituacaoRua'),
                        ]
                        linhas=[]
                        for titulo,nome in campos:
                            radios=page.locator(f'input[type="radio"][name="{nome}"]')
                            if radios.count() != 2:
                                linhas.append(f'{titulo}: estrutura inesperada ({radios.count()} opções)')
                                continue
                            values=radios.evaluate_all('(els) => els.filter(e => e.checked).map(e => e.value)')
                            val=values[0] if len(values)==1 else 'SEM RESPOSTA'
                            linhas.append(f'{titulo}: {val}')
                        self.emit(op,True,' | '.join(linhas)+' | Confira as opções manualmente no PEC. Nenhuma declaração foi preenchida automaticamente.')
                    elif op == 'verificar_campos':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('BLOQUEADO: confira primeiro a pesquisa do cidadão atual.')
                        if not re.search(r'/gestaoCadastros/cadastro-individual/\d+/edit', page.url):
                            raise ValueError('Abra a edição do cadastro antes da verificação.')
                        campos = [
                            ('Identidade de gênero', 'dadosPessoais.desejaInformarIdentidadeGenero'),
                            ('Orientação sexual', 'dadosPessoais.desejaInformarOrientacaoSexual'),
                            ('Situação de rua', 'statusSituacaoRua'),
                        ]
                        linhas = []
                        for titulo, nome in campos:
                            radios = page.locator(f'input[type="radio"][name="{nome}"]')
                            if radios.count() != 2:
                                linhas.append(f'{titulo}: estrutura inesperada ({radios.count()} opções)')
                                continue
                            selecionados = radios.evaluate_all('(els) => els.filter(e => e.checked).map(e => e.value)')
                            valor = selecionados[0] if len(selecionados) == 1 else 'SEM RESPOSTA'
                            linhas.append(f'{titulo}: {valor}')
                        self.emit(op, True, ' | '.join(linhas) + '. Respostas não foram alteradas.')
                    elif op == 'regularizar_telefone':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('BLOQUEADO: identificação do cidadão não confirmada para telefone.')
                        if not self.territory_marked:
                            raise ValueError('BLOQUEADO: marque primeiro a saída do território.')
                        if not self.autorizar_telefone:
                            self.emit(op, True, 'Regra do telefone desativada; campo preservado.')
                            continue
                        campo = page.locator('input[name="contatos.telefoneCelular"]')
                        if campo.count() != 1:
                            raise ValueError('Telefone celular obrigatório não localizado de maneira única. Pausando.')
                        atual = numeros(campo.input_value())
                        if not telefone_celular_invalido(atual):
                            self.emit(op, True, 'Telefone celular plausível existente preservado; nenhum ajuste.')
                            continue
                        # Números plausíveis nunca são sobrescritos; o valor da coordenação é explícito.
                        campo.fill(TELEFONE_COORDENACAO)
                        campo.press('Tab')
                        page.wait_for_timeout(300)
                        if numeros(campo.input_value()) != TELEFONE_COORDENACAO:
                            raise ValueError('Telefone da coordenação não permaneceu no campo; NÃO salvar automaticamente.')
                        self.emit(op, True, 'Regra da coordenação: telefone vazio/inválido substituído pelo contato administrativo configurado; alteração AINDA NÃO SALVA.')
                    elif op == 'salvar_assistido':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('BLOQUEADO: edição não corresponde ao cidadão validado nesta sessão.')
                        if not self.territory_marked:
                            raise ValueError('BLOQUEADO: confirme primeiro a marcação de saída do território.')
                        if not re.search(r'/gestaoCadastros/cadastro-individual/\d+/edit', page.url):
                            raise ValueError('O PEC não está na edição do cadastro esperado.')
                        botao = page.locator('[data-cy="FormFooter.salvar"]')
                        if botao.count() != 1 or not botao.is_enabled():
                            raise ValueError('Botão Salvar não localizado ou desabilitado. Confira os campos obrigatórios.')
                        botao.click(timeout=8000, no_wait_after=True)
                        # Um único clique em Salvar. A cada segundo, verificar se a URL já
                        # saiu da edição; não exigir 10 s de espera se o PEC respondeu antes.
                        # O total de 3 x 10 s permanece como limite de segurança.
                        edicao = re.compile(r'/gestaoCadastros/cadastro-individual/\d+/edit')
                        terminou = False
                        # A linha de status e exclusiva deste salvamento. Nos primeiros
                        # dois segundos nao exibimos barra; o PEC costuma responder rapido.
                        self.emit('espera_salvar', True, '0|-1')
                        for tentativa in range(1, 4):
                            if tentativa > 1:
                                self.emit('espera_salvar', True, f'{tentativa}|0')
                            for segundo in range(1, 11):
                                page.wait_for_timeout(1000)
                                saiu_da_edicao = not edicao.search(page.url)
                                if tentativa == 1:
                                    if segundo == 1:
                                        self.emit('espera_salvar', True, '1|-1')
                                    elif segundo == 2 and not saiu_da_edicao:
                                        self.emit('espera_salvar', True, '1|0')
                                    elif segundo > 2 and not saiu_da_edicao:
                                        self.emit('espera_salvar', True, f'1|{segundo - 2}')
                                elif not saiu_da_edicao:
                                    self.emit('espera_salvar', True, f'{tentativa}|{segundo}')
                                if saiu_da_edicao:
                                    self.emit(op, True, f'Salvar acionado uma única vez; PEC saiu da edição na tentativa {tentativa}, após {segundo} s desta janela. Conferindo persistência...')
                                    terminou = True
                                    break
                            if terminou:
                                break
                            # Inspecionar avisos apenas ao final da janela, evitando
                            # confundir carregamento transitório com erro do formulário.
                            texto = page.locator('body').inner_text(timeout=8000)
                            avisos = [linha.strip() for linha in texto.splitlines()
                                      if re.search(r'campo obrigat[oó]rio|preencha|inv[aá]lido|n[aã]o foi poss[ií]vel|erro ao salvar', linha, re.I)]
                            if avisos:
                                self.emit(op, False, 'Salvar acionado, mas há validações/avisos no PEC: ' + ' | '.join(avisos[:3])[:220] + '. Não marque como concluído.')
                                terminou = True
                                break
                            if tentativa == 3:
                                self.emit(op, False, 'Após até três janelas de 10 segundos, a edição ainda permanece aberta. Salvamento NÃO confirmado; confira no PEC antes de prosseguir.')

                    elif op == 'verificar_persistencia':
                        # Após o salvamento, recarregar a MESMA edição do cidadão identificado.
                        # Sair da tela de edição sozinho não é evidência de persistência.
                        if self.validated_person != person['id'] or not self.validated_edit_url:
                            raise ValueError('BLOQUEADO: não há identidade e URL de edição previamente validadas.')
                        old_url = self.validated_edit_url
                        if not old_url.startswith(self.base_url + '/gestaoCadastros/cadastro-individual/'):
                            raise ValueError('URL de edição fora do servidor configurado.')
                        page.goto(old_url, wait_until='domcontentloaded', timeout=30000)
                        page.wait_for_url(re.compile(r'/gestaoCadastros/cadastro-individual/\d+/edit'), timeout=15000)
                        if page.url.split('?')[0] != old_url.split('?')[0]:
                            raise ValueError('O PEC redirecionou para outro cadastro. Conferência manual necessária.')
                        flag = page.locator('input[name="responsabilidadeAcompanhamento.statusCidadaoSaiuTerritorio"]')
                        flag.wait_for(state='attached',timeout=15000)
                        cpf = page.locator('input[name="dadosPessoais.cpf"]')
                        cns = page.locator('input[name="dadosPessoais.cns"]')
                        found = []
                        for _ in range(12):
                            found = [numeros(x.input_value()) for x in (cpf,cns) if x.count() == 1]
                            if person['cpf_cns'] in found: break
                            page.wait_for_timeout(400)
                        if person['cpf_cns'] not in found:
                            raise ValueError('Após recarregar, CPF/CNS não confere com a lista. Não concluir automaticamente.')
                        # aguardar marcação de formulário carregado; nunca forçar checkbox.
                        if not flag.is_checked():
                            raise ValueError('Após recarregar, Mudou-se NÃO permaneceu marcado. Conferência manual obrigatória.')
                        if self.fora_area_requer_verificacao:
                            fora = page.locator('input[name="responsabilidadeAcompanhamento.statusForaArea"]')
                            if fora.count() != 1 or fora.is_checked():
                                raise ValueError('Após recarregar, Fora de área segue marcado ou não foi identificado. Conferência manual obrigatória.')
                            self.emit('aviso_etapa', True, 'VERIFICADO NO PEC: Fora de área continua DESMARCADO após recarregar.')
                        self.emit(op, True, 'VERIFICADO NO PEC: cadastro e CPF/CNS conferem; após recarregar a edição, Mudou-se continua marcado.')
                    elif op == 'localizar_salvar':
                        if self.validated_person != person['id'] or self.validated_edit_url != page.url:
                            raise ValueError('BLOQUEADO: confira primeiro a pesquisa do cidadão atual.')
                        if not re.search(r'/gestaoCadastros/cadastro-individual/\d+/edit', page.url):
                            raise ValueError('Abra a edição do cadastro antes de localizar Salvar.')
                        botao = page.locator('[data-cy="FormFooter.salvar"]')
                        if botao.count() != 1:
                            raise ValueError('Botão Salvar não identificado de forma única.')
                        botao.scroll_into_view_if_needed(timeout=5000)
                        visivel = botao.is_visible()
                        habilitado = botao.is_enabled()
                        self.emit(op, visivel, 'Botão Salvar localizado no rodapé (habilitado: %s). Revise e clique manualmente no PEC; o robô NÃO salvou.' % ('sim' if habilitado else 'não'))
                except Exception as e:
                    self.emit(op, False, str(e)[:350])
            try:
                context.close()
            except Exception:
                pass


class App:
    def __init__(self, root):
        self.root = root
        root.title('Higienizador — MGC1.0.6.4 | Gestão territorial')
        root.geometry('1140x790')
        root.minsize(860, 600)
        self.csv_path = tk.StringVar()
        self.url = tk.StringVar(value='')
        self.unidade = tk.StringVar(value='')
        self.limite = tk.StringVar(value='')
        self.modo_lote = tk.StringVar(value='automatico')
        self.autorizar_indocumentada = tk.BooleanVar(value=True)
        self.autorizar_telefone = tk.BooleanVar(value=False)
        self.autorizar_fora_area = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Selecione a UBS, o limite do lote e o CSV para começar.')
        self.progress = tk.StringVar(value='Nenhum relatório carregado')
        self.people, self.index, self.key = [], -1, ''
        self.records = {}
        self.worker = None
        self.commands, self.responses = queue.Queue(), queue.Queue()
        self.in_action = False
        self.auto_running = False
        self.auto_paused = False
        self.auto_stage = None
        self.auto_waiting_cns = False
        self.auto_waiting_identity = False
        self.auto_waiting_confirmation = False
        self.batch_running = False
        self.batch_waiting_next = False
        self.profiles_path = DATA / 'unidades.json'
        self.profiles = self._load_profiles()
        self.selected_ubs = tk.StringVar(value='')
        self.metric_confirmed = tk.StringVar(value='0')
        self.metric_pending = tk.StringVar(value='0')
        self.metric_remaining = tk.StringVar(value='0')
        self.make_ui()
        root.after(150, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.exit)

    def _load_profiles(self):
        # Catálogo inicial das 26 unidades. Configurações locais existentes têm prioridade:
        # atualizar o programa NÃO altera URLs personalizadas nem apaga unidades próprias.
        catalogo = {
            'Aeroporto': 'http://serv-aeroporto:8080',
            'Are': 'http://serv-ubsare:8080',
            'Boa Fortuna': 'http://serv-bfortuna:8080',
            'Boa Ventura': 'http://servidor-ubsboaventura:8080',
            'Boa Vista': 'http://atend1-boavista:8080',
            'Carulas': 'http://serv-carulas:8080',
            'Cehab': 'http://serv-cehab:8080',
            'Córrego da Chica': 'http://serv-cchica:8080',
            'Córrego Seco': 'http://servidor-ubscorregoseco:8080',
            'Costa e Silva': 'http://serv-csilva:8080',
            'Fiteiro': 'http://serv-fiteiro:8080',
            'Frigorífico': 'http://serv-frigorifico:8080',
            'Guarita': 'http://serv-guarita:8080',
            'Horto': 'http://serv-horto:8080',
            'Itajara': 'http://servidor-ubsitajara:8080',
            'Lions': 'http://serv-lions:8080',
            'Penha': 'http://servidor-penha:8080',
            'Prisional': 'http://serv-prisional:8080',
            'Raposo': 'http://serv-raposo:8080',
            'Retiro': 'http://servidor-retiro:8080',
            'São Francisco': 'http://saofranc-servidor:8080',
            'São Manoel': 'http://serv-smanoel:8080',
            'São Mateus': 'http://serv-smateus:8080',
            'Surubi': 'http://serv-surubi:8080',
            'Venâncio': 'http://serv-venancio:8080',
            'Vinhosa Centro': 'http://serv-vcentro:8080',
        }
        try:
            raw = json.loads(self.profiles_path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                for name, address in raw.items():
                    if isinstance(name, str) and isinstance(address, str) and name.strip():
                        try:
                            catalogo[name.strip()] = validar_servidor(address)
                        except ValueError:
                            pass  # Uma configuração local inválida não impede abrir o programa.
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return catalogo

    def _save_profiles(self):
        temp = self.profiles_path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.profiles_path)

    def on_profile(self, event=None):
        name = self.selected_ubs.get()
        if name in self.profiles and not self.worker:
            self.unidade.set(name)
            self.url.set(self.profiles[name])

    def add_profile(self):
        if self.worker:
            messagebox.showwarning('Sessão em andamento', 'Para trocar a UBS, encerre e reabra o programa.'); return
        name = self.unidade.get().strip() or self.selected_ubs.get().strip()
        if not name:
            messagebox.showwarning('Nome da UBS', 'Informe o nome da unidade.'); return
        try:
            address = validar_servidor(self.url.get())
        except ValueError as exc:
            messagebox.showerror('Servidor PEC', str(exc)); return
        if name in self.profiles and not messagebox.askyesno('Atualizar UBS', f'Sobrescrever o endereço da unidade {name}?'):
            return
        self.profiles[name] = address
        self._save_profiles()
        self.ubs_combo.configure(values=sorted(self.profiles))
        self.selected_ubs.set(name)
        self.log(f'UBS cadastrada/atualizada: {name}.')

    def remove_profile(self):
        if self.worker:
            messagebox.showwarning('Sessão em andamento', 'Não altere UBS durante a sessão.'); return
        name = self.selected_ubs.get()
        if name not in self.profiles: return
        if not messagebox.askyesno('Excluir configuração', f'Excluir apenas o atalho da unidade {name}? O histórico não será apagado.'):
            return
        del self.profiles[name]
        self._save_profiles()
        self.ubs_combo.configure(values=sorted(self.profiles))
        self.selected_ubs.set(next(iter(sorted(self.profiles)), ''))
        self.on_profile()
        self.log('Atalho da unidade excluído. Históricos preservados.')

    def _refresh_metrics(self):
        saved = sum(1 for p in self.people if self.records.get(p['id']) in ('SALVO_CONFERIDO','SALVO_VERIFICADO'))
        pending = sum(1 for p in self.people if p['manual'] or self.records.get(p['id']) in ('PENDENTE','PULADO'))
        remaining = sum(1 for p in self.people if not p['manual'] and self.records.get(p['id']) not in ('SALVO_CONFERIDO','SALVO_VERIFICADO','PENDENTE','PULADO'))
        self.metric_confirmed.set(str(saved))
        self.metric_pending.set(str(pending))
        self.metric_remaining.set(str(remaining))

    def make_ui(self):
        style = ttk.Style(self.root)
        if 'classic' in style.theme_names():
            style.theme_use('classic')
        elif 'vista' in style.theme_names():
            style.theme_use('vista')
        BG = '#c0c0c0'; PANEL='#d4d0c8'; NAVY='#0a246a'; FG='#000000'
        self.root.configure(bg=BG)
        style.configure('App.TFrame', background=BG)
        style.configure('Panel.TFrame', background=PANEL, relief='raised', borderwidth=1)
        style.configure('App.TLabel', background=BG, foreground=FG, font=('Tahoma', 9))
        style.configure('Panel.TLabel', background=PANEL, foreground=FG, font=('Tahoma', 9))
        style.configure('Muted.TLabel', background=PANEL, foreground='#404040', font=('Tahoma', 8))
        style.configure('Metric.TLabel', background=PANEL, foreground=FG, font=('Tahoma', 18, 'bold'))
        style.configure('Main.TButton', font=('Tahoma', 9, 'bold'), padding=(10,6))
        style.configure('Action.TButton', font=('Tahoma', 8), padding=(8,5))
        style.configure('TEntry', padding=3)
        style.configure('TCombobox', padding=3)
        style.configure('TCheckbutton', background=PANEL, foreground=FG)
        style.configure('Horizontal.TProgressbar', troughcolor='#808080', background='#0a246a', thickness=10)

        # Cabeçalho retrô. PNG usa PhotoImage nativo: não exige Pillow instalado.
        banner=tk.Frame(self.root, bg='#000080', height=98, relief='raised', bd=2)
        banner.pack(fill='x'); banner.pack_propagate(False)
        logo_path = BASE / 'logo_higienizador_transparente.png'
        self.logo_img = None
        try:
            self.logo_img = tk.PhotoImage(file=str(logo_path))
            tk.Label(banner, image=self.logo_img, bg='#000080', bd=0, highlightthickness=0).pack(side='right', padx=20, pady=8)
        except tk.TclError:
            # Se o arquivo de imagem faltar, não impedir a abertura do programa.
            pass
        text_banner = tk.Frame(banner, bg='#000080')
        text_banner.pack(side='left', fill='y', padx=(24,10))
        tk.Label(text_banner, text='HIGIENIZADOR', font=('Fixedsys', 28, 'bold'),
                 bg='#000080', fg='white').pack(anchor='w', pady=(24,2))

        body=ttk.Frame(self.root,style='App.TFrame',padding=14)
        body.pack(fill='both',expand=True)
        cfg=ttk.Frame(body,style='Panel.TFrame',padding=13)
        cfg.pack(fill='x')
        # Formulário à esquerda; botões em uma coluna alinhada à direita.
        cfg.columnconfigure(0,weight=2)
        cfg.columnconfigure(1,weight=3)
        cfg.columnconfigure(2,weight=2)
        cfg.columnconfigure(3,weight=0,minsize=204)
        ttk.Label(cfg,text='Unidade de saúde',style='Muted.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(cfg,text='Servidor PEC',style='Muted.TLabel').grid(row=0,column=1,sticky='w',padx=(10,0))
        ttk.Label(cfg,text='Limite do lote',style='Muted.TLabel').grid(row=0,column=2,sticky='w',padx=(10,0))
        self.ubs_combo=ttk.Combobox(cfg,textvariable=self.selected_ubs,values=sorted(self.profiles),state='readonly')
        self.ubs_combo.grid(row=1,column=0,sticky='ew',pady=(4,8))
        self.ubs_combo.bind('<<ComboboxSelected>>',self.on_profile)
        ttk.Entry(cfg,textvariable=self.url).grid(row=1,column=1,sticky='ew',padx=(10,0),pady=(4,8))
        ttk.Combobox(cfg,textvariable=self.limite,values=('','1','5','10','25','50','Todos'),state='readonly',width=12).grid(row=1,column=2,sticky='ew',padx=(10,0),pady=(4,8))
        ttk.Label(cfg,text='Arquivo do relatório (CSV)',style='Muted.TLabel').grid(row=2,column=0,columnspan=3,sticky='w',pady=(7,0))
        ttk.Entry(cfg,textvariable=self.csv_path).grid(row=3,column=0,columnspan=3,sticky='ew',pady=(5,4))
        # Botões com a mesma largura, alinhados um abaixo do outro.
        right=ttk.Frame(cfg,style='Panel.TFrame')
        right.grid(row=1,column=3,rowspan=3,sticky='nsew',padx=(16,0),pady=(4,4))
        right.columnconfigure(0,weight=1)
        ttk.Button(right,text='Selecionar CSV',command=self.choose,style='Action.TButton').grid(row=0,column=0,sticky='ew',ipady=2)
        self.loadbutton=ttk.Button(right,text='Carregar relatório',command=self.load,style='Main.TButton')
        self.loadbutton.grid(row=1,column=0,sticky='ew',pady=(6,0),ipady=2)
        self.buttons={}
        self.buttons['abrir']=ttk.Button(right,text='Abrir Chrome',command=self.start,style='Action.TButton')
        self.buttons['abrir'].grid(row=2,column=0,sticky='ew',pady=(6,0),ipady=2)

        # Métricas: compactas, para manter o log acessível em monitores menores.
        metrics=ttk.Frame(body,style='App.TFrame')
        metrics.pack(fill='x',pady=(10,8))
        for i,(label,var) in enumerate((('Concluídos',self.metric_confirmed),('Pendências e revisão',self.metric_pending),('Na fila',self.metric_remaining))):
            metrics.columnconfigure(i,weight=1,uniform='metric')
            panel=ttk.Frame(metrics,style='Panel.TFrame',padding=(15,8))
            panel.grid(row=0,column=i,sticky='ew',padx=(0 if i==0 else 4,0))
            ttk.Label(panel,text=label,style='Muted.TLabel').pack(anchor='w')
            ttk.Label(panel,textvariable=var,style='Metric.TLabel').pack(anchor='w')

        work=ttk.Frame(body,style='Panel.TFrame',padding=12)
        work.pack(fill='x')
        ttk.Label(work,textvariable=self.progress,style='Panel.TLabel',font=('Segoe UI',11,'bold')).pack(anchor='w')
        self.person=ttk.Label(work,text='Nenhum cidadão selecionado',style='Panel.TLabel')
        self.person.pack(anchor='w',pady=(3,6))
        self.bar=ttk.Progressbar(work,maximum=100,style='Horizontal.TProgressbar')
        self.bar.pack(fill='x',pady=(0,10))
        actions=ttk.Frame(work,style='Panel.TFrame')
        actions.pack(fill='x')
        self.btn_batch=ttk.Button(actions,text='▶  Iniciar lote',command=self.start_batch,style='Main.TButton')
        self.btn_batch.pack(side='left',padx=(0,8))
        self.btn_pause=ttk.Button(actions,text='Pausar',command=self.pause_auto,style='Action.TButton')
        self.btn_pause.pack(side='left',padx=(0,8))
        self.btn_resume=ttk.Button(actions,text='Continuar',command=self.resume_auto,style='Action.TButton')
        self.btn_resume.pack(side='left',padx=(0,8))
        self.btn_stop=ttk.Button(actions,text='Parar',command=self.stop_auto,style='Action.TButton')
        self.btn_stop.pack(side='left')

        log_panel=ttk.Frame(body,style='Panel.TFrame',padding=10)
        log_panel.pack(fill='both',expand=True,pady=(9,0))
        top=ttk.Frame(log_panel,style='Panel.TFrame');top.pack(fill='x')
        ttk.Label(top,text='Registro de atividades',style='Panel.TLabel',font=('Segoe UI',11,'bold')).pack(side='left')
        ttk.Label(top,text='Log local • CPF/CNS completos não aparecem nesta área',style='Muted.TLabel').pack(side='right')
        log_body=ttk.Frame(log_panel,style='Panel.TFrame')
        log_body.pack(fill='both',expand=True,pady=(6,0))
        self.logbox=tk.Text(log_body,wrap='word',state='disabled',font=('Consolas',10),
                            bg='#FAFBFD',fg='#25364B',relief='flat',padx=9,pady=7,height=8)
        self.logbox.pack(side='left',fill='both',expand=True)
        logscroll=ttk.Scrollbar(log_body,orient='vertical',command=self.logbox.yview)
        logscroll.pack(side='right',fill='y')
        self.logbox.configure(yscrollcommand=logscroll.set)
        ttk.Label(body,textvariable=self.status,style='App.TLabel',wraplength=1050).pack(fill='x',pady=(6,0))

        mainmenu=tk.Menu(self.root)
        unitmenu=tk.Menu(mainmenu,tearoff=False)
        unitmenu.add_command(label='Salvar / atualizar UBS selecionada',command=self.add_profile)
        unitmenu.add_command(label='Excluir atalho da UBS selecionada',command=self.remove_profile)
        mainmenu.add_cascade(label='Unidades',menu=unitmenu)
        exceptionmenu=tk.Menu(mainmenu,tearoff=False)
        modo_menu=tk.Menu(exceptionmenu, tearoff=False)
        modo_menu.add_radiobutton(label='Conferência automática após salvar', variable=self.modo_lote, value='automatico')
        modo_menu.add_radiobutton(label='Conferência assistida após salvar', variable=self.modo_lote, value='assistido')
        exceptionmenu.add_cascade(label='Conferência após salvar', menu=modo_menu)
        exceptionmenu.add_checkbutton(label='Regra da coordenação: CNS sem CPF → Pessoa indocumentada', variable=self.autorizar_indocumentada)
        exceptionmenu.add_checkbutton(label='Regra da coordenação: telefone vazio/inválido → contato administrativo', variable=self.autorizar_telefone)
        exceptionmenu.add_checkbutton(label='Regra opcional: desmarcar Fora de área (mantendo Mudou-se)', variable=self.autorizar_fora_area)
        exceptionmenu.add_separator()
        exceptionmenu.add_command(label='Confirmar cadastro visualmente',command=self.confirm_manual)
        exceptionmenu.add_command(label='Registrar pendência',command=lambda:self.resolve('PENDENTE'))
        exceptionmenu.add_command(label='Pular cidadão',command=lambda:self.resolve('PULADO'))
        exceptionmenu.add_separator()
        exceptionmenu.add_command(label='Confirmar salvamento manual',command=lambda:self.resolve('SALVO_CONFERIDO'))
        mainmenu.add_cascade(label='Exceções',menu=exceptionmenu)
        mainmenu.add_command(label='Abrir pasta de relatórios',command=self.open_reports)
        self.root.configure(menu=mainmenu)
        self.refresh_buttons()

    def open_reports(self):
        # Abre a pasta local no Windows sem enviar seus dados para terceiros.
        import os
        try:
            os.startfile(str(DATA))
        except (AttributeError, OSError):
            messagebox.showinfo('Relatórios',f'Pasta de relatórios: {DATA}')

    def log(self, msg):
        self.status.set(msg)
        self.logbox.configure(state='normal')
        self.logbox.insert('end', f'[{datetime.now().strftime("%H:%M:%S")}] {msg}\n')
        self.logbox.see('end')
        self.logbox.configure(state='disabled')

    def atualizar_contagem_salvar(self, tentativa, segundo):
        # Apenas a linha da tentativa atual pode ser atualizada. Nao apagar a
        # ultima linha do log: ela pode conter a verificacao do telefone.
        # Evento 0|-1 inaugura um salvamento; evento 1|-1 registra o primeiro
        # segundo; 1|0 abre a barra depois de 2 s, se o PEC ainda aguardar.
        if tentativa == 0:
            self._tentativa_log = 0
            self._tentativa_linha = None
            mensagem = 'TENTATIVA 0 — salvamento enviado; verificando resposta do PEC...'
        elif segundo == -1:
            mensagem = f'TENTATIVA {tentativa} — verificando resposta do PEC...'
        else:
            progresso = min(10, max(0, segundo))
            barra = ' '.join(['•'] * progresso + ['X'] * (10 - progresso))
            mensagem = f'TENTATIVA {tentativa}: [ {barra} ]'

        horario = datetime.now().strftime('%H:%M:%S')
        linha = f'[{horario}] {mensagem}'
        self.status.set(mensagem)
        self.logbox.configure(state='normal')
        try:
            marca = getattr(self, '_tentativa_linha', None)
            # A marca do Tk ancora a linha mesmo quando novos logs sao inseridos.
            if marca and marca in self.logbox.mark_names():
                inicio = self.logbox.index(marca)
                self.logbox.delete(inicio, f'{inicio} lineend')
                self.logbox.insert(inicio, linha)
            else:
                inicio = self.logbox.index('end-1c')
                self.logbox.insert('end', linha + '\n')
                self.logbox.mark_set('tentativa_salvar_ativa', inicio)
                self.logbox.mark_gravity('tentativa_salvar_ativa', 'left')
                self._tentativa_linha = 'tentativa_salvar_ativa'
            self.logbox.see('end')
        finally:
            self.logbox.configure(state='disabled')

    def choose(self):
        f=filedialog.askopenfilename(title='Relatório de cidadãos vinculados',filetypes=[('CSV','*.csv')])
        if f:self.csv_path.set(f)

    def load(self):
        if self.worker:
            messagebox.showwarning('Sessão aberta','Feche e reabra o programa para trocar de UBS/servidor.');return
        if not self.selected_ubs.get().strip() and not self.url.get().strip():
            messagebox.showwarning('UBS não selecionada', 'Selecione a UBS ou informe o servidor PEC antes de carregar o relatório.')
            return
        if not self.limite.get().strip():
            messagebox.showwarning('Limite do lote', 'Selecione a quantidade do lote antes de carregar o relatório.')
            return
        raw_path = self.csv_path.get().strip().strip('"')
        if not raw_path:
            messagebox.showwarning('CSV não selecionado',
                'Selecione o arquivo CSV do relatório antes de clicar em Carregar relatório.')
            return
        path = Path(raw_path)
        if not path.is_file():
            messagebox.showerror('Arquivo não encontrado',
                'O caminho informado não é um arquivo válido. Selecione um CSV existente.')
            return
        if path.suffix.lower() != '.csv':
            messagebox.showwarning('Formato incorreto',
                'Selecione um relatório no formato .csv.')
            return
        try:
            self.people=ler_csv(path)
            server=validar_servidor(self.url.get())
            self.key=hashlib.sha256((server+'|'+str(path.resolve())+'|'+hashlib.sha256(path.read_bytes()).hexdigest()).encode()).hexdigest()[:20]
            state=DATA/f'{self.key}.json'
            self.records=json.loads(state.read_text(encoding='utf-8')) if state.exists() else {}
            manual=sum(1 for p in self.people if p['manual'])
            self.log(f'{len(self.people)} cidadãos únicos | {manual} sem CPF/CNS (revisão manual).')
            self.index=-1
            self.next_person()
        except Exception as e:
            messagebox.showerror('Falha ao ler relatório',str(e))
        self._refresh_metrics()
        self.refresh_buttons()

    def next_person(self):
        candidates=[i for i,p in enumerate(self.people) if not p['manual'] and self.records.get(p['id']) not in ('SALVO_CONFERIDO','SALVO_VERIFICADO','PULADO','PENDENTE')]
        max_count=len(candidates)
        total_done=sum(v in ('SALVO_CONFERIDO','SALVO_VERIFICADO') for v in self.records.values())
        self.bar['value']=100*total_done/max(1,len(self.people))
        self.progress.set(f'{total_done} confirmados / {len(self.people)} registros | {max_count} ainda sem decisão')
        if not candidates or (self.session_count() >= self.max_limit()):
            self.index=-1
            self.person.configure(text='Sessão concluída ou limite atingido.')
        else:
            self.index=candidates[0]
            p=self.people[self.index]
            self.person.configure(text=f'{p["nome"]} | CPF/CNS final {p["cpf_cns"][-4:]}')
        self._refresh_metrics()
        self.refresh_buttons()

    def max_limit(self):
        if not self.limite.get():
            return 0
        return 10**9 if self.limite.get()=='Todos' else int(self.limite.get())

    def session_count(self):
        return getattr(self,'processed_this_session',0)

    def current(self):
        return self.people[self.index] if self.index>=0 else None

    def start(self):
        if self.worker:return
        try: base_url=validar_servidor(self.url.get())
        except ValueError as e:messagebox.showerror('Servidor',str(e));return
        self.worker=BrowserWorker(self.commands,self.responses,base_url,self.autorizar_indocumentada.get(), self.autorizar_telefone.get(), self.autorizar_fora_area.get())
        self.worker.start();self.in_action=True
        self.log('Abrindo Chrome com sessão local do higienizador...')
        self.refresh_buttons()

    def send(self, op):
        if self.in_action or not self.current() or not self.worker:return
        self.in_action=True
        self.commands.put((op,self.current().copy()))
        self.log('Executando: '+op)
        self.refresh_buttons()

    def run_auto(self):
        if not self.worker or self.in_action or not self.current() or self.auto_running or self.batch_running:
            return
        if self.session_count() >= self.max_limit():
            messagebox.showinfo('Limite', 'O limite da sessão foi atingido.')
            return
        if not messagebox.askyesno('Iniciar fluxo',
            'Executar pesquisa, marcação de mudança, preenchimento de respostas vazias e clicar em Salvar para UM cidadão?\n\n'
            'As respostas existentes serão preservadas. Se faltar CPF no PEC, a sequência aguardará revisão da justificativa.\n\n'
            'Confirme o resultado no PEC antes de registrar conclusão.'):
            return
        if self.worker:
            self.worker.autorizar_telefone = self.autorizar_telefone.get()
            self.worker.autorizar_fora_area = self.autorizar_fora_area.get()
        if self.autorizar_telefone.get() and not messagebox.askyesno('Telefone administrativo',
            'Aplicar o contato administrativo configurado caso o celular esteja vazio ou inválido?\n\n'
            'Use apenas com autorização formal da coordenação.'):
            return
        self.auto_running = True
        self.auto_paused = False
        self.auto_waiting_confirmation = False
        self.auto_waiting_cns = False
        self.auto_waiting_identity = False
        self.auto_stage = 'pesquisar'
        self.send('pesquisar')

    def start_batch(self):
        if not self.worker or self.in_action or not self.current() or self.auto_running or self.batch_running:
            return
        limite_desc = self.limite.get()
        if not limite_desc:
            messagebox.showwarning('Limite do lote', 'Selecione a quantidade do lote antes de iniciar.')
            return
        if not messagebox.askyesno('Lote de atualização territorial',
            f'Iniciar um lote de {limite_desc} cidadãos?\n\n'
            f'Modo: {self.modo_lote.get()}. No modo automático o robô RELÊ a edição no PEC após salvar e só então avança. '
            'Se não conseguir confirmar a persistência, PAUSA para conferência.\n\n' +
            ('Cadastros CNS sem CPF serão tratados automaticamente conforme a regra da coordenação.\n' if self.autorizar_indocumentada.get() else 'Cadastros CNS sem CPF exigirão conferência manual.\n') + ('Telefone vazio/inválido será substituído pelo contato administrativo configurado.\n' if self.autorizar_telefone.get() else 'Regra do telefone DESLIGADA.\n') + ('Fora de área marcado será desmarcado e relido após salvar.\n' if self.autorizar_fora_area.get() else 'Regra Fora de área DESLIGADA.\n') + '\nContinuar?'):
            return
        if self.autorizar_telefone.get():
            if not messagebox.askyesno('ATENÇÃO — Telefone administrativo',
                'A regra de telefone da coordenação está ATIVADA.\n\n'
                'Cadastros com celular vazio ou estruturalmente inválido receberão o número '
                + TELEFONE_COORDENACAO + '.\n\n'
                'Esse número só deve ser usado se for um contato institucional autorizado; '
                'não representa o telefone pessoal do cidadão.\n\n'
                'Confirma a autorização e deseja continuar?'):
                return
        if self.worker:
            self.worker.autorizar_telefone = self.autorizar_telefone.get()
            self.worker.autorizar_fora_area = self.autorizar_fora_area.get()
        if self.autorizar_fora_area.get() and not messagebox.askyesno('ATENÇÃO — Fora de área',
            'A regra Fora de área está ATIVA. Esta opção modifica o indicador territorial de cada cidadão do lote.\n\n'
            'Tem autorização para desmarcar Fora de área nos registros selecionados?'):
            return
        self.batch_running = True
        self.log(f'LOTE INICIADO: limite {self.limite.get()} | modo {self.modo_lote.get()} | regra CNS sem CPF: {self.autorizar_indocumentada.get()} | regra telefone: {self.autorizar_telefone.get()} | desmarcar Fora de área: {self.autorizar_fora_area.get()} | exceções pausam a fila.')
        self._begin_batch_person()

    def _begin_batch_person(self):
        self.batch_waiting_next = False
        if not self.batch_running or self.auto_paused:
            return
        if self.in_action or self.auto_running:
            return
        if self.session_count() >= self.max_limit() or not self.current():
            self.batch_running = False
            self.log('LOTE CONCLUÍDO: limite atingido ou não há mais cidadãos.')
            self.refresh_buttons()
            return
        self.auto_running = True
        self.auto_paused = False
        self.auto_waiting_confirmation = False
        self.auto_waiting_cns = False
        self.auto_waiting_identity = False
        self.auto_stage = 'pesquisar'
        self.log('LOTE: iniciando cidadão e executando o fluxo de atualização.')
        self.send('pesquisar')

    def pause_auto(self):
        if self.batch_running or self.auto_running:
            self.auto_paused = True
            self.log('Pausa solicitada: aguardará antes da próxima etapa.')

    def resume_auto(self):
        if self.batch_running and not self.auto_running and not self.in_action and self.current() and not self.auto_waiting_confirmation:
            self.auto_paused = False
            self._begin_batch_person()
            return
        if not self.auto_running or self.in_action:
            return
        self.auto_paused = False
        if self.auto_waiting_identity:
            self.log('Confira a identidade do cidadão e use Confirmar cadastro visualmente.')
            return
        if self.auto_waiting_cns:
            if not messagebox.askyesno('Cadastro somente CNS',
                'Você conferiu que o cidadão realmente não possui CPF, marcou essa opção e registrou a justificativa adequada no PEC?\n\n'
                'Use Pessoa indocumentada somente quando essa condição estiver confirmada.\n\n'
                'Continuar a atualização?'):
                return
            self.auto_waiting_cns = False
            self.auto_stage = 'marcar'
            self.send('marcar')
            return
        if self.auto_stage and not self.auto_waiting_confirmation:
            self.send(self.auto_stage)

    def stop_auto(self):
        self.batch_running = False
        self.batch_waiting_next = False
        self.auto_running = False
        self.auto_paused = False
        self.auto_stage = None
        self.log('Sequência interrompida; nenhuma conclusão foi registrada automaticamente.')

    def search(self):self.send('pesquisar')
    def locate_save(self):
        if not self.worker:
            messagebox.showwarning('Chrome', 'Abra o Chrome primeiro.')
            return
        if self.index < 0 or self.index >= len(self.people):
            return
        self.commands.put(('localizar_salvar', self.people[self.index]))

    def save_assisted(self):
        if not self.worker or not self.current() or self.in_action:
            return
        if not messagebox.askyesno('Salvar cadastro no PEC',
            'Você conferiu o nome, CPF/CNS e a opção Mudou-se no cadastro atualmente aberto?\n\n'
            'O programa clicará em SALVAR no PEC. Se houver erro ou confirmação adicional, você precisará conferir na tela.\n\n'
            'Deseja tentar salvar ESTE cadastro?'):
            return
        self.send('salvar_assistido')

    def fill_no(self):
        if not self.worker:
            messagebox.showwarning('Chrome', 'Abra o Chrome primeiro.')
            return
        if not messagebox.askyesno('Confirmar preenchimento dos vazios',
            'Para o cidadão atualmente identificado, preencher NÃO somente nas três perguntas que ainda estiverem sem resposta?\n\n'
            'Os valores SIM e NÃO já existentes serão preservados.\n\n'
            'As duas primeiras perguntas indicam não informar identidade de gênero/orientação sexual; '
            'a terceira registra que o cidadão não está em situação de rua.\n\n'
            'A alteração ficará pendente até você conferir e salvar manualmente no PEC.'):
            return
        self.send('preencher_vazios')

    def check_fields(self):self.send('verificar_campos')

    def confirm_manual(self):
        p = self.current()
        if not p or self.in_action or not self.worker:
            return
        aviso = (f'CONFIRA NO PEC, NA TELA DE EDIÇÃO:\n\n'
                 f'Nome: {p["nome"]}\n'
                 f'Nascimento (CSV): {p["nascimento"]}\n'
                 f'CPF/CNS termina em: {p["cpf_cns"][-4:]}\n\n'
                 'Confirma que estes dados correspondem à pessoa exibida no PEC? '
                 'NÃO confirme em caso de divergência ou dúvida.')
        if messagebox.askyesno('Conferência de identidade', aviso):
            self.send('confirmar_manual')

    def mark(self):self.send('marcar')

    def resolve(self, status):
        p=self.current()
        if not p or self.in_action:return
        if status=='SALVO_CONFERIDO' and self.batch_running and self.modo_lote.get() == 'automatico' and self.auto_stage == 'verificar_persistencia':
            messagebox.showwarning('Verificação em andamento','Aguarde o robô reler o cadastro ou interrompa o lote.')
            return
        if status=='SALVO_CONFERIDO' and self.batch_running and not self.auto_waiting_confirmation and not self.auto_paused:
            messagebox.showwarning('Sem confirmação de salvamento', 'O PEC ainda não concluiu a etapa de salvar nesta sequência. Confira a situação manualmente e registre uma pendência se necessário.')
            return
        if status=='SALVO_CONFERIDO' and self.auto_running and not self.auto_waiting_confirmation:
            messagebox.showwarning('Aguarde', 'A sequência ainda não terminou. Confira o PEC após clicar em Salvar.')
            return
        if status=='SALVO_CONFERIDO':
            if not messagebox.askyesno('Confirmação obrigatória',
                'Você revisou os campos obrigatórios, salvou no PEC e conferiu a confirmação de sucesso?\n\n'
                'Mesmo que o botão Salvar tenha sido acionado pelo programa, a verificação final depende de você.'):
                return
        elif status=='PENDENTE':
            if not messagebox.askyesno('Pendência','Confirme no PEC que a alteração NÃO foi concluída antes de marcar como pendente.\n\nRegistrar a pendência para revisão manual?'):
                return
        if status=='PULADO' and not messagebox.askyesno('Pular cidadão', 'Este registro permanecerá sem alteração e será excluído da fila desta importação. Continuar?'):
            return
        self._registrar_resultado(status)

    def _concluir_verificado(self):
        """Conclui automaticamente somente depois de uma nova leitura independente do formulário."""
        if not (self.batch_running and self.modo_lote.get() == 'automatico' and self.auto_waiting_confirmation):
            return
        p = self.current()
        if not p or self.in_action:
            return
        self._registrar_resultado('SALVO_VERIFICADO')

    def _registrar_resultado(self,status):
        p = self.current()
        if not p: return
        continue_batch = self.batch_running and status in ('SALVO_CONFERIDO','SALVO_VERIFICADO','PENDENTE','PULADO')
        if not continue_batch:
            self.batch_running = False
        self.auto_running = False
        self.auto_waiting_confirmation = False
        self.auto_waiting_cns = False
        self.auto_waiting_identity = False
        self.auto_stage = None
        self.records[p['id']] = status
        self.persist()
        self.processed_this_session = self.session_count() + 1
        self.log(f'{status}: {p["nome"]} (final {p["cpf_cns"][-4:]})')
        self.next_person()
        if continue_batch:
            self.batch_waiting_next = True
            if self.auto_paused:
                self.log('LOTE PAUSADO: clique em Continuar para iniciar o próximo cidadão.')
            else:
                self.root.after(400,self._begin_batch_person)

    def persist(self):
        dst=DATA/f'{self.key}.json'
        tmp=dst.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.records,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(dst)
        report=DATA/f'{self.key}_resultados.csv'
        with report.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f,delimiter=';')
            w.writerow(['CPF_CNS','nome','status'])
            for p in self.people:
                w.writerow([p['cpf_cns'],p['nome'],self.records.get(p['id'],'MANUAL_SEM_IDENTIFICADOR' if p['manual'] else 'NA_FILA')])

    def poll(self):
        try:
            while True:
                op,ok,msg=self.responses.get_nowait()
                if op == 'espera_salvar':
                    tentativa, segundo = map(int, msg.split('|'))
                    self.atualizar_contagem_salvar(tentativa, segundo)
                    continue
                if op == 'aviso_etapa':
                    # Mensagem informativa: não concluir uma operação nem avançar a fila.
                    self.log(('OK: ' if ok else 'ATENÇÃO: ') + msg)
                    continue
                self.in_action=False
                self.log(('OK: ' if ok else 'ATENÇÃO: ')+msg)
                if self.auto_running:
                    if not ok:
                        if op == 'pesquisar' and 'identificação automática inconclusiva' in msg:
                            self.auto_waiting_identity = True
                            self.log('FLUXO PAUSADO: use Confirmar cadastro visualmente para o cidadão atual.')
                        else:
                            self.auto_running = False
                            self.auto_stage = None
                            if self.batch_running:
                                self.auto_paused = True
                                self.log('LOTE PAUSADO POR EXCEÇÃO: se houve tentativa de salvar, CONFERIR no PEC antes de marcar pendência, pular ou confirmar manualmente.')
                            else:
                                self.log('FLUXO INTERROMPIDO: corrija a pendência antes de iniciar novamente.')
                    elif op == 'confirmar_manual' and self.auto_waiting_identity:
                        self.auto_waiting_identity = False
                        # Exigir revisão manual de CPF ausente se o registro foi encontrado por CNS.
                        self.auto_stage = 'inspecionar_cpf'
                    elif op == 'pesquisar':
                        self.auto_stage = 'inspecionar_cpf'
                    elif op == 'inspecionar_cpf':
                        self.auto_stage = 'marcar'
                        if 'SOMENTE_CNS_SEM_CPF' in msg:
                            if self.worker and self.worker.autorizar_indocumentada:
                                self.auto_stage = 'regularizar_cpf'
                                self.log('CNS SEM CPF: aplicando regra da coordenação e verificando justificativa antes de salvar.')
                            else:
                                self.auto_waiting_cns = True
                                self.log('FLUXO PAUSADO: revise a ausência de CPF e justificativa; clique em Continuar.')
                    elif op == 'regularizar_cpf':
                        self.auto_stage = 'marcar'
                    elif op == 'marcar':
                        self.auto_stage = 'preencher_vazios'
                    elif op == 'preencher_vazios':
                        self.auto_stage = 'regularizar_telefone'
                    elif op == 'regularizar_telefone':
                        self.auto_stage = 'salvar_assistido'
                    elif op == 'salvar_assistido':
                        if self.batch_running and self.modo_lote.get() == 'automatico':
                            self.auto_stage = 'verificar_persistencia'
                            self.log('SALVO: relendo cadastro no PEC para verificar a persistência...')
                        else:
                            self.auto_waiting_confirmation = True
                            self.auto_stage = None
                            self.log('FLUXO AGUARDANDO: confira a persistência da saída territorial no PEC e clique em Salvei e conferi.')
                    elif op == 'verificar_persistencia':
                        self.auto_waiting_confirmation = True
                        self.auto_stage = None
                        self.log('PERSISTÊNCIA CONFIRMADA: registrando atualização e avançando no lote.')
                        self.root.after(100, self._concluir_verificado)
                    if self.auto_running and not self.auto_paused and not self.auto_waiting_identity and not self.auto_waiting_confirmation:
                        if self.auto_stage and not self.auto_waiting_cns:
                            self.commands.put((self.auto_stage, self.current().copy()))
                            self.in_action = True
                if not ok and op=='abrir':self.worker=None
                self.refresh_buttons()
        except queue.Empty:pass
        self.root.after(150,self.poll)

    def refresh_buttons(self):
        has = self.current() is not None
        self.buttons['abrir'].configure(state='disabled' if self.worker else 'normal' if has else 'disabled')
        self.btn_batch.configure(state='normal' if has and self.worker and not self.in_action and not self.auto_running and not self.batch_running else 'disabled')
        self.btn_pause.configure(state='normal' if self.auto_running or self.batch_running else 'disabled')
        self.btn_resume.configure(state='normal' if (self.auto_running or self.batch_running) and not self.in_action else 'disabled')
        self.btn_stop.configure(state='normal' if self.auto_running or self.batch_running else 'disabled')

    def exit(self):
        self.batch_running = False
        if self.worker:
            self.commands.put(('fechar',None))
        self.root.destroy()


if __name__=='__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()

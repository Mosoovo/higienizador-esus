"""Higienizador 2.0 — Etapa 3: interface visual sem automação.
Revisão 11 — QWebEngineView persistente, com camada de logo sobreposta.
"""
from __future__ import annotations
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime
from leitor_relatorio_mgc import ler_csv

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit, QFileDialog,
    QBoxLayout, QProgressBar, QTextEdit, QSplitter, QMessageBox,
    QScrollArea, QStackedWidget, QStackedLayout, QMenuBar, QInputDialog,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

BASE = Path(__file__).resolve().parent
UBS = {
    'Aeroporto':'http://serv-aeroporto:8080', 'Are':'http://serv-ubsare:8080',
    'Boa Fortuna':'http://serv-bfortuna:8080', 'Boa Ventura':'http://servidor-ubsboaventura:8080',
    'Boa Vista':'http://atend1-boavista:8080', 'Carulas':'http://serv-carulas:8080',
    'Cehab':'http://serv-cehab:8080', 'Córrego da Chica':'http://serv-cchica:8080',
    'Córrego Seco':'http://servidor-ubscorregoseco:8080', 'Costa e Silva':'http://serv-csilva:8080',
    'Fiteiro':'http://serv-fiteiro:8080', 'Frigorífico':'http://serv-frigorifico:8080',
    'Guarita':'http://serv-guarita:8080', 'Horto':'http://serv-horto:8080',
    'Itajara':'http://servidor-ubsitajara:8080', 'Lions':'http://serv-lions:8080',
    'Penha':'http://servidor-penha:8080', 'Prisional':'http://serv-prisional:8080',
    'Raposo':'http://serv-raposo:8080', 'Retiro':'http://servidor-retiro:8080',
    'São Francisco':'http://saofranc-servidor:8080', 'São Manoel':'http://serv-smanoel:8080',
    'São Mateus':'http://serv-smateus:8080', 'Surubi':'http://serv-surubi:8080',
    'Venâncio':'http://serv-venancio:8080', 'Vinhosa Centro':'http://serv-vcentro:8080'
}

CSS = """
QMainWindow, QWidget { background:#c0c0c0; color:#161616; font-family:'Tahoma'; font-size:11px; }
QFrame#panel { background:#d4d0c8; border:2px solid; border-color:#ffffff #787878 #787878 #ffffff; }
QFrame#sunken { border:2px solid; border-color:#777777 #ffffff #ffffff #777777; background:#c0c0c0; }
QFrame#banner {
    background:qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #000080, stop:1 #071d41);
    border:0;
}
QLabel#bannerTitle { background:transparent; color:#ffffff; font-family:'Courier New'; font-size:21px; font-weight:bold; letter-spacing:1px; }
QLabel#subtle { color:#525252; }
QLabel#metric { font-size:14px; font-weight:bold; color:#101010; }
QFrame#metricCell { background:#d4d0c8; border-left:1px solid #a3a099; }
QLabel#metricCaption { color:#222222; font-size:10px; }
QPushButton { background:#d4d0c8; border:2px solid; border-color:#ffffff #777777 #777777 #ffffff; padding:2px 5px; min-height:20px; }
QPushButton:pressed { border-color:#777777 #ffffff #ffffff #777777; }
QPushButton:disabled { color:#888888; }
QComboBox, QLineEdit { background:#ffffff; border:2px solid; border-color:#777777 #ffffff #ffffff #777777; padding:2px 4px; min-height:19px; }
QComboBox QAbstractItemView { background:white; }
QProgressBar { border:2px solid; border-color:#777777 #ffffff #ffffff #777777; background:#aaa; min-height:7px; max-height:7px; }
QProgressBar::chunk { background:#000080; }
QTextEdit { background:#fafafa; border:0; font-family:Consolas; font-size:10px; selection-background-color:#000080; }
QSplitter::handle { background:#c0c0c0; }
"""


def panel(layout='v', spacing=7, margins=(12, 9, 12, 9)):
    frame = QFrame()
    frame.setObjectName('panel')
    lay = QVBoxLayout(frame) if layout == 'v' else QHBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return frame, lay


class Preview(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Higienizador 1.9.14.6.7 | TESTE 6 — ALTERACAO NAO SALVA')
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if available:
            width = min(1530, max(900, int(available.width() * 0.94)))
            height = min(920, max(600, int(available.height() * 0.94)))
            self.resize(width, height)
        else:
            self.resize(1200, 740)
        self.setMinimumSize(900, 600)
        self._compact_state = None
        self.preview_active = False
        self.current_target = ''
        self.relatorio_pessoas = []
        self.motor_process = None
        self.readonly_test = None
        self.readonly_poll = 0
        self.territory_test_running = False
        self.web_pending = False
        self.build()
        self.note('HIGIENIZADOR 1.9.14.6.7 — TESTE 6: Mudou-se na edição, SEM salvar; motor preservado.')

    def build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.root_layout = layout
        layout.setContentsMargins(7, 4, 7, 6)
        layout.setSpacing(4)

        # Menus suspensos verdadeiros (ainda sem integração do motor).
        self.top_menu = QMenuBar(root)
        self.top_menu.setNativeMenuBar(False)
        self.top_menu.setFixedHeight(21)
        self.top_menu.setStyleSheet("""
            QMenuBar { background:#c0c0c0; border:0; padding:0; }
            QMenuBar::item { background:transparent; padding:2px 9px; }
            QMenuBar::item:selected { background:#000080; color:white; }
            QMenu { background:#d4d0c8; border:2px solid; border-color:white #777 #777 white;
                    color:#111; padding:3px; }
            QMenu::item { padding:5px 26px 5px 20px; }
            QMenu::item:selected { background:#000080; color:white; }
            QMenu::item:disabled { color:#777; }
            QMenu::separator { height:1px; background:#888; margin:4px 6px; }
        """)
        self._build_top_menus()
        layout.addWidget(self.top_menu)

        self.banner = QFrame(); self.banner.setObjectName('banner')
        self.banner.setFixedHeight(42)
        header = QHBoxLayout(self.banner)
        header.setContentsMargins(12, 0, 12, 0)
        # Artes PNG originais, recortadas somente nas bordas transparentes.
        # Os dois lados usam a mesma margem; a cruz mantém proporção e altura.
        self.banner_title = QLabel()
        self.banner_title.setObjectName('bannerTitle')
        self.banner_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.banner_cross = QLabel()
        self.banner_cross.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.banner_title.setStyleSheet('background:transparent; border:0;')
        self.banner_cross.setStyleSheet('background:transparent; border:0;')
        self.letter_art = QPixmap(str(BASE / 'assets' / 'logo_letreiro.png'))
        self.cross_art = QPixmap(str(BASE / 'assets' / 'cruz_letreiro.png'))
        self._size_banner_art(42)
        header.addWidget(self.banner_title, 0, Qt.AlignLeft | Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(self.banner_cross, 0, Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.banner)

        cfg, cl = panel('h', spacing=7, margins=(8, 6, 8, 6))
        self.config_layout = cl
        config_grid = QGridLayout()
        config_grid.setHorizontalSpacing(6)
        config_grid.setVerticalSpacing(2)
        for col, title in ((0, 'Unidade de saúde'), (1, 'Servidor PEC'), (3, 'Arquivo do relatório (CSV)')):
            config_grid.addWidget(QLabel(title), 0, col)
        self.ubs = QComboBox(); self.ubs.addItem(''); self.ubs.addItems(sorted(UBS))
        self.ubs.setCurrentIndex(0)
        self.ubs.currentTextChanged.connect(self.changed_ubs)
        config_grid.addWidget(self.ubs, 1, 0)
        self.server = QLineEdit(); self.server.setReadOnly(True)
        self.server.setPlaceholderText('Preenchido ao selecionar a UBS')
        config_grid.addWidget(self.server, 1, 1)
        pick = QPushButton('Selecionar CSV'); pick.clicked.connect(self.choose_file)
        pick.setFixedWidth(112)
        config_grid.addWidget(pick, 1, 2)
        self.csv = QLineEdit(); self.csv.setPlaceholderText('Selecione um relatório para visualizar o caminho')
        config_grid.addWidget(self.csv, 1, 3)
        for col, weight in ((0, 17), (1, 27), (2, 16), (3, 40)):
            config_grid.setColumnStretch(col, weight)
        cl.addLayout(config_grid, 1)
        self.start_button = QPushButton('Iniciar ambiente')
        self.start_button.clicked.connect(self.open_web_environment)
        self.start_button.setFixedWidth(112)
        self.close_button = QPushButton('Fechar ambiente')
        self.close_button.setFixedWidth(112)
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.close_web_environment)
        cl.addWidget(self.start_button)
        cl.addWidget(self.close_button)
        layout.addWidget(cfg)

        op, ol = panel(spacing=1, margins=(8, 4, 8, 4))
        self.operation_layout = ol
        self.progress_text = QLabel('Nenhum relatório carregado')
        self.progress_text.setStyleSheet('font-weight:bold;')
        ol.addWidget(self.progress_text)
        self.person = QLabel('Nenhum cidadão selecionado')
        ol.addWidget(self.person)
        self.progress = QProgressBar(); self.progress.setValue(0)
        self.progress.setTextVisible(False)
        ol.addWidget(self.progress)
        lower = QBoxLayout(QBoxLayout.LeftToRight)
        lower.setSpacing(3)
        self.operation_row = lower

        self.lot_group = QWidget()
        lot_l = QVBoxLayout(self.lot_group)
        lot_l.setContentsMargins(0, 0, 5, 0)
        lot_l.setSpacing(1)
        lot_l.addWidget(QLabel('Limite do lote'))
        self.limit = QComboBox()
        self.limit.addItems(['', '1', '5', '10', '25', '50', 'Todos'])
        self.limit.setCurrentIndex(0)
        self.limit.setEnabled(False)
        lot_l.addWidget(self.limit)
        self.lot_group.setFixedWidth(132)
        self.lot_group.setFixedHeight(45)
        lower.addWidget(self.lot_group, 0, Qt.AlignBottom)

        self.operation_buttons = []
        for caption in ('▶ Iniciar lote', 'Pausar', 'Continuar', 'Parar'):
            b = QPushButton(caption)
            b.setEnabled(False)
            lower.addWidget(b, 0, Qt.AlignBottom)
            self.operation_buttons.append(b)
        lower.addSpacing(8)

        self.metrics = {}
        self.metric_cells = []
        for title, value in [
            ('Total', '0'), ('Na fila', '0'), ('Concluídos', '0'), ('Pendências e revisão', '0'),
            ('Tempo estimado', '00:00'), ('Tempo', '00:00'), ('Progresso', '0%')
        ]:
            frame = QFrame(); frame.setObjectName('metricCell')
            cell = QVBoxLayout(frame); cell.setContentsMargins(5, 1, 3, 1); cell.setSpacing(0)
            cap = QLabel(title); cap.setObjectName('metricCaption')
            val = QLabel(value); val.setObjectName('metric')
            cell.addWidget(cap); cell.addWidget(val)
            frame.setFixedHeight(38)
            lower.addWidget(frame, 1, Qt.AlignBottom)
            self.metric_cells.append(frame)
            self.metrics[title] = val
        ol.addLayout(lower)
        layout.addWidget(op)

        split = QSplitter(Qt.Vertical); split.setChildrenCollapsible(False)
        viewer_panel, viewer_l = panel(margins=(6, 5, 6, 5))
        # O navegador é o componente permanente da área central, criado
        # enquanto a janela é montada. Uma camada opaca com a logo fica por
        # cima dele; nenhuma troca de QWebEngineView é feita ao iniciar PEC.
        self.viewer_host = QWidget()
        self.viewer_host.setObjectName('viewerHost')
        stack = QStackedLayout(self.viewer_host)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setStackingMode(QStackedLayout.StackAll)
        self.viewer_stack = stack
        self.webview = QWebEngineView()
        self.webview.setObjectName('pecWebview')
        self.webview.loadStarted.connect(self.web_load_started)
        self.webview.loadProgress.connect(self.web_load_progress)
        self.webview.loadFinished.connect(self.web_load_finished)
        self.webview.urlChanged.connect(self.web_url_changed)
        stack.addWidget(self.webview)
        self.home_overlay = QWidget()
        self.home_overlay.setObjectName('homeOverlay')
        self.home_overlay.setAutoFillBackground(True)
        self.home_overlay.setStyleSheet('QWidget#homeOverlay { background-color:#c0c0c0; }')
        home_layout = QVBoxLayout(self.home_overlay)
        home_layout.setContentsMargins(4, 4, 4, 4)
        home_layout.setAlignment(Qt.AlignCenter)
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet('background:transparent; border:none;')
        pix = QPixmap(str(BASE / 'assets' / 'logo.png'))
        if not pix.isNull():
            self.logo_label.setPixmap(pix.scaled(380, 330, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        home_layout.addWidget(self.logo_label)
        stack.addWidget(self.home_overlay)
        stack.setCurrentWidget(self.home_overlay)
        viewer_l.addWidget(self.viewer_host)
        split.addWidget(viewer_panel)
        self.viewer_panel = viewer_panel

        log_panel, log_l = panel(spacing=1, margins=(7, 2, 7, 3))
        log_head = QHBoxLayout(); log_head.setSpacing(4)
        title = QLabel('Registro de atividades'); title.setStyleSheet('font-weight:bold;')
        log_head.addWidget(title); log_head.addStretch()
        copy = QPushButton('Copiar log'); copy.clicked.connect(self.copy_log)
        export = QPushButton('Exportar TXT'); export.clicked.connect(self.export_log)
        for b in (copy, export):
            b.setStyleSheet('padding:1px 5px; min-height:15px; font-size:10px;')
            log_head.addWidget(b)
        log_l.addLayout(log_head)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setMinimumHeight(40)
        self.log.setMaximumHeight(82)
        log_l.addWidget(self.log)
        split.addWidget(log_panel)
        split.setStretchFactor(0, 5); split.setStretchFactor(1, 0)
        split.setHandleWidth(4)
        self.splitter = split
        layout.addWidget(split, 1)

        self.inspect_button = QPushButton('Diagnóstico de leitura')
        self.inspect_button.clicked.connect(self.inspect_page)
        self.inspect_button.setEnabled(False)
        self.inspect_button.hide()
        QTimer.singleShot(0, self._initialize_splitter)
        QTimer.singleShot(0, self._apply_responsive_layout)
        self.set_home()
        self.changed_ubs(self.ubs.currentText())
        # Inicializa a superfície do QtWebEngine sem navegar no PEC.
        QTimer.singleShot(0, self._prime_webview)

    def _prime_webview(self):
        self.webview.load(QUrl('about:blank'))


    def _build_top_menus(self):
        # As opções estão visíveis para avaliação. O MGC não está conectado.
        def entry(menu, text, *, enabled=False, checkable=False, checked=False, callback=None):
            action=menu.addAction(text)
            action.setCheckable(checkable)
            if checkable:
                action.setChecked(checked)
            action.setEnabled(enabled)
            if callback is not None:
                action.triggered.connect(callback)
            return action

        # Adaptador de comunicação: TESTE SOMENTE LEITURA.
        bridge=self.top_menu.addMenu("Teste MGC")
        entry(bridge,"1. Identificar página PEC",enabled=True,callback=self.readonly_identify_page)
        entry(bridge,"2. Pesquisar e abrir cidadão (sem editar)",enabled=True,callback=self.readonly_select_person)
        entry(bridge,"3. Conferir identidade na edição",enabled=True,callback=self.readonly_verify_identity)
        entry(bridge,"4. Inspecionar Mudou-se (sem alterar)",enabled=True,callback=self.readonly_inspect_territory)
        entry(bridge,"5. TESTE 6 — Marcar Mudou-se (NÃO SALVAR)",enabled=True,callback=self.test6_mark_territory)
        bridge.addSeparator()
        entry(bridge,"Interromper teste",enabled=True,callback=self.readonly_cancel)
        entry(bridge,"Sobre o teste",enabled=True,callback=self.explain_readonly)

        units=self.top_menu.addMenu("Unidades")
        for title in ("Novo", "Atualizar", "Excluir"):
            entry(units,title)

        conference=self.top_menu.addMenu("Conferência")
        entry(conference, "Conferência automática",checkable=True,checked=True)
        entry(conference, "Conferência assistida",checkable=True)

        settings=self.top_menu.addMenu("Configurações")
        for title in ("Sem CPF", "Sem telefone", "Desmarcar Fora de área",
                      "Pendências de responsável", "Marcar Mudou-se"):
            entry(settings,title,checkable=True,checked=(title=="Marcar Mudou-se"))

        exceptions=self.top_menu.addMenu("Exceções")
        for title in ("Confirmar cadastro visualmente", "Confirmar salvamento manual",
                      "Registrar pendência", "Pular cidadão"):
            entry(exceptions,title)

        help_menu=self.top_menu.addMenu("Ajuda")
        entry(help_menu,"Sobre o Higienizador",enabled=True,callback=self.show_about)
        entry(help_menu,"Leia-me",enabled=True,callback=self.show_readme)
        help_menu.addSeparator()
        for title in ("FAQ","Manual de utilização","Diagnóstico do ambiente",
                      "Informar problema","Atualizações"):
            entry(help_menu,title)

    def show_about(self):
        QMessageBox.information(self,"Sobre o Higienizador",
            "Higienizador 2.0 — Interface 0.13a\\n"
            "Prévia da interface Win Old.\\n"
            "Teste de comunicação baseado em seletores do MGC1.0.6.7.\n"
            "Somente pesquisa, navegação e conferência de identidade — sem salvar.")

    def explain_integration(self):
        QMessageBox.information(self,"Ponte MGC — Etapa 4",
            "O navegador incorporado continua independente do motor MGC.\n\n"
            "Para preservar a versão estável, o comando Abrir MGC inicia o programa "
            "original em outra janela, que por sua vez abre seu próprio Chrome.\n\n"
            "A Interface 2.0 consegue ler o CSV e mostrar totais, mas ainda não acompanha "
            "a fila ou os resultados executados pelo MGC.\n\n"
            "Não execute o mesmo lote simultaneamente nos dois navegadores.")

    def open_legacy_motor(self):
        if self.motor_process is not None and self.motor_process.poll() is None:
            QMessageBox.information(self,"MGC já aberto","O motor está em execução em outra janela.")
            return
        answer=QMessageBox.question(self,"Abrir motor preservado",
            "Abrir MGC1.0.6.5 em uma janela separada?\n\n"
            "Ele utilizará o Chrome próprio do Playwright; não atuará no PEC integrado.\n"
            "O relatório e a UBS devem ser selecionados novamente no motor.\n"
            "Não inicie lotes simultâneos nos dois ambientes.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:
            return
        path=BASE/'motor_preservado'/'higienizador_v1065.py'
        if not path.exists():
            QMessageBox.warning(self,'Motor indisponível','Arquivo do MGC não localizado.')
            return
        try:
            self.motor_process=subprocess.Popen([sys.executable,str(path)],cwd=str(path.parent))
            self.note('MGC1.0.6.5 iniciado em janela separada; esta interface não controla o lote.')
        except Exception as exc:
            QMessageBox.warning(self,'Não foi possível abrir MGC',str(exc))
            self.note('Falha ao iniciar motor separado: '+str(exc)[:180])

    def show_readme(self):
        file=BASE/"LEIA-ME.txt"
        if file.exists():
            QMessageBox.information(self,"Leia-me",file.read_text(encoding="utf-8-sig")[:3500])
        else:
            QMessageBox.information(self,"Leia-me","Documentação indisponível.")

    def _initialize_splitter(self):
        if hasattr(self, 'splitter'):
            total = max(250, self.splitter.height())
            log_size = 73 if self.height() >= 850 else 66
            self.splitter.setSizes([max(180, total - log_size), log_size])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'banner'):
            self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        compact = self.height() < 810 or self.width() < 1250
        narrow = self.width() < 1020
        state = (compact, narrow)
        if state == self._compact_state:
            return
        self._compact_state = state
        self.root_layout.setContentsMargins(*( (5, 3, 5, 4) if compact else (7, 4, 7, 6) ))
        self.root_layout.setSpacing(3 if compact else 4)
        self.banner.setFixedHeight(38 if compact else 42)
        self._size_banner_art(38 if compact else 42)
        self.config_layout.setContentsMargins(*( (6, 4, 6, 4) if compact else (8, 6, 8, 6) ))
        self.operation_layout.setContentsMargins(*( (6, 3, 6, 3) if compact else (8, 4, 8, 4) ))
        self.log.setMinimumHeight(38 if compact else 45)
        self.log.setMaximumHeight(57 if compact else 72)
        self.viewer_panel.setMinimumHeight(140 if compact else 210)
        for button in self.operation_buttons:
            button.setStyleSheet('padding:1px 4px; min-height:17px; font-size:10px;' if compact else 'padding:2px 5px; min-height:20px;')
        for label in self.metrics.values():
            label.setStyleSheet('font-size:13px; font-weight:bold;' if compact else '')
        self.operation_row.setDirection(QBoxLayout.LeftToRight)

    def _size_banner_art(self, banner_height):
        # Manter qualidade do pixel art e dimensionar sem distorcer a proporção.
        letter_height = 25 if banner_height <= 38 else 28
        cross_height = 32 if banner_height <= 38 else 36
        if not self.letter_art.isNull():
            self.banner_title.setPixmap(self.letter_art.scaledToHeight(letter_height, Qt.SmoothTransformation))
        if not self.cross_art.isNull():
            self.banner_cross.setPixmap(self.cross_art.scaledToHeight(cross_height, Qt.SmoothTransformation))

    def changed_ubs(self, name):
        self.server.setText(UBS.get(name, ''))
        if name:
            self.note('Destino selecionado: ' + name + '. Agora selecione o CSV e clique em Iniciar ambiente para abrir.')

    def set_home(self):
        """Revela a cobertura cinza sem destruir ou esconder o WebEngine."""
        self.preview_active = False
        self.home_overlay.show()
        self.viewer_stack.setCurrentWidget(self.home_overlay)
        self.home_overlay.raise_()

    def open_web_environment(self):
        destination = self.server.text().strip()
        if not destination:
            QMessageBox.information(self, 'Selecione uma UBS', 'Escolha uma UBS antes de iniciar o ambiente.')
            return
        parsed = QUrl(destination)
        if parsed.scheme() not in ('http', 'https') or not parsed.host():
            QMessageBox.warning(self, 'Endereço inválido', 'O endereço selecionado não é um URL HTTP/HTTPS válido.')
            return
        if self.preview_active:
            self.note('O ambiente já está aberto. Clique em Fechar ambiente antes de iniciar outro.')
            return
        self.note('Tentando abrir servidor PEC da UBS (requer rede interna).')
        self.current_target = destination
        self.start_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.ubs.setEnabled(False)
        self.web_pending = True
        self.preview_active = True
        # WebEngine já está criado e ocupa a área central desde o início.
        # A camada da logo continua por cima até a primeira carga terminar.
        self.progress_text.setText('Navegador integrado: preparando ambiente...')
        self.note('Carregando PEC sem trocar a tela inicial até a página responder: ' + self.ubs.currentText())
        self.inspect_button.setEnabled(False)
        self.webview.load(parsed)

    def close_web_environment(self):
        """Fecha a visualização, sem fechar a aplicação nem modificar cadastros."""
        if not self.preview_active:
            return
        self.preview_active = False
        self.web_pending = False
        self.inspect_button.setEnabled(False)
        # Reexibe a cobertura antes de limpar a página atual.
        self.home_overlay.show()
        self.viewer_stack.setCurrentWidget(self.home_overlay)
        self.home_overlay.raise_()
        self.readonly_cancel()
        self.webview.stop()
        self.webview.setUrl(QUrl('about:blank'))
        self.current_target = ''
        self.start_button.setEnabled(True)
        self.close_button.setEnabled(False)
        self.ubs.setEnabled(True)
        self.progress_text.setText(
            'Relatório selecionado — prévia sem processamento' if self.csv.text().strip()
            else 'Nenhum relatório carregado')
        self.person.setText('Nenhum cidadão selecionado')
        self.note('Ambiente PEC fechado. Você pode selecionar outra UBS e iniciar novamente.')

    def web_load_started(self):
        if self.preview_active:
            self.progress_text.setText('Navegador integrado: carregando página...')

    def web_load_progress(self, value):
        if self.preview_active:
            self.progress_text.setText(f'Navegador integrado: carregando... {value}%')

    def web_load_finished(self, ok):
        if not self.preview_active:
            return
        self.web_pending = False
        if ok:
            self.progress_text.setText('Navegador integrado: página carregada')
            # Troca somente depois de carregar, deixando o Qt terminar a
            # atualização de layout sem recriar a janela principal.
            QTimer.singleShot(80, self._show_loaded_webview)
            self.inspect_button.setEnabled(True)
        else:
            self.progress_text.setText('Navegador integrado: falha de carregamento')
            self.note('Não foi possível carregar o endereço. A camada inicial foi mantida.')
            self.inspect_button.setEnabled(False)
            self.preview_active = False
            self.web_pending = False
            self.start_button.setEnabled(True)
            self.close_button.setEnabled(False)
            self.ubs.setEnabled(True)

    def _show_loaded_webview(self):
        if not self.preview_active or self.web_pending:
            return
        if self.viewer_stack.currentWidget() is self.home_overlay:
            self.viewer_stack.setCurrentWidget(self.webview)
            self.home_overlay.hide()
            self.webview.setFocus(Qt.OtherFocusReason)
            self.note('OK: camada inicial retirada; PEC exibido no navegador previamente criado.')

    def inspect_page(self):
        if not self.preview_active:
            return
        self.inspect_button.setEnabled(False)
        js = """(() => ({title: document.title, url: location.href, ready: document.readyState}))()"""
        def got(result):
            self.inspect_button.setEnabled(True)
            if isinstance(result, dict):
                title = str(result.get('title', ''))[:120]
                url = str(result.get('url', ''))[:180]
                ready = str(result.get('ready', ''))
                self.note('LEITURA WEBENGINE OK: título=' + repr(title) + ' | estado=' + ready)
                self.note('URL visível: ' + url)
            else:
                self.note('LEITURA WEBENGINE INCONCLUSIVA: script não retornou dados.')
        self.webview.page().runJavaScript(js, got)

    def web_url_changed(self, url):
        if self.preview_active:
            self.note('Navegação interna do navegador atualizada.')

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Selecionar relatório CSV', '', 'CSV (*.csv)')
        if not path:
            return
        try:
            people=ler_csv(path)
        except Exception as exc:
            QMessageBox.warning(self,'Erro ao ler relatório',str(exc))
            self.note('CSV recusado: '+str(exc)[:180])
            return
        self.relatorio_pessoas=people
        self.csv.setText(path)
        total=len(people)
        without=sum(p['manual'] for p in people)
        self.limit.setEnabled(total>0)
        self.progress_text.setText(f'Relatório lido: {total} cidadãos únicos | {without} sem CPF/CNS (revisão manual)')
        self.metrics['Total'].setText(str(total))
        self.metrics['Na fila'].setText(str(total))
        self.note(f'CSV carregado: {total} cidadãos únicos, {without} sem CPF/CNS. Nenhum registro foi alterado.')
        self.note('Teste de comunicação disponível em Teste MGC (somente leitura; limite do lote não executa automação).')

    # ================================================================
    # ADAPTADOR SOMENTE LEITURA — motor MGC1.0.6.7 preservado em cópia.
    # Somente o QWebEngineView é utilizado; não existe clique em salvar.
    # ================================================================
    def explain_readonly(self):
        QMessageBox.information(self,"Teste MGC — somente leitura",
            "1. Abra o PEC e faça login normalmente.\n"
            "2. Carregue o CSV.\n"
            "3. Identifique a página; escolha um cidadão para pesquisa.\n"
            "4. O adaptador pode abrir Atualizar cadastro somente para leitura; "
            "nenhum campo será alterado ou salvo.\n\n"
            "Não execute lotes nesta versão. Nenhum motor estável foi modificado.")

    def readonly_cancel(self):
        self.territory_test_running = False
        self.readonly_test = None
        self.readonly_poll = 0
        self.person.setText('Nenhum cidadão em teste')

    def _readonly_ready(self):
        if not self.preview_active or self.web_pending or not self.webview.url().scheme().startswith('http'):
            QMessageBox.warning(self,"Ambiente indisponível",
                "Inicie o ambiente PEC e aguarde a página carregar; faça login antes do teste.")
            return False
        return True

    def readonly_identify_page(self):
        if not self._readonly_ready():
            return

        self.note('DEBUG JSON 1: iniciando leitura da página PEC')

        script = """(() => {
            try {
                return JSON.stringify({
                    url: location.href,
                    title: document.title,
                    ready: document.readyState,
                    pesquisa: document.querySelectorAll('input[name="nomeCpfCns"]').length,
                    cpf: document.querySelectorAll('input[name="dadosPessoais.cpf"]').length,
                    cns: document.querySelectorAll('input[name="dadosPessoais.cns"]').length
                });
            } catch (e) {
                return JSON.stringify({erro: String(e)});
            }
        })()"""

        def retorno(resultado):
            self.note('DEBUG JSON 2: callback | tipo=' + type(resultado).__name__)
            if not isinstance(resultado, str):
                self.note('DEBUG JSON: retorno não textual: ' + repr(resultado)[:180])
                return
            try:
                dados = json.loads(resultado)
            except (ValueError, TypeError) as exc:
                self.note('DEBUG JSON: falha ao interpretar retorno: ' + str(exc)[:140])
                return
            if 'erro' in dados:
                self.note('DEBUG JSON: erro JavaScript: ' + str(dados['erro'])[:160])
                return
            self.note('DIAGNÓSTICO PEC: título=' + str(dados.get('title', ''))[:60]
                      + ' | estado=' + str(dados.get('ready', ''))
                      + ' | pesquisa=' + str(dados.get('pesquisa', 0))
                      + ' | campos CPF/CNS=' + str(dados.get('cpf', 0))
                      + '/' + str(dados.get('cns', 0)))
            self.note('URL atual: ' + str(dados.get('url', ''))[:180])
            self.note('DEBUG JSON 3: leitura concluída com sucesso')

        self.webview.page().runJavaScript(script, retorno)

    def readonly_select_person(self):
        if not self._readonly_ready(): return
        if self.readonly_test:
            QMessageBox.information(self,"Teste em andamento","Finalize ou interrompa o teste anterior."); return
        selectable=[p for p in self.relatorio_pessoas if p.get('cpf_cns')]
        if not selectable:
            QMessageBox.information(self,"CSV necessário","Carregue um CSV com CPF/CNS antes de testar."); return
        choices=[f"{p['nome']}  | final {p['cpf_cns'][-4:]}" for p in selectable]
        choice,ok=QInputDialog.getItem(self,"Teste de comunicação — cidadão",
            "Escolha UM cidadão para localizar (somente leitura):",choices,0,False)
        if not ok or not choice:return
        person=selectable[choices.index(choice)]
        if QMessageBox.question(self,"Confirmação de teste",
            f"Pesquisar {person['nome']} (final {person['cpf_cns'][-4:]})?\n"
            "Somente navegar e ler; não preencher nem salvar.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.readonly_test={'person':person,'step':'navigate','token':object()}
        self.person.setText(f"TESTE: {person['nome']} | final {person['cpf_cns'][-4:]}")
        # Mesma rota padrão do MGC; São Francisco usa /cidadao.
        route='/cidadao' if self.ubs.currentText()=='São Francisco' else '/gestaoCadastros/cadastro-individual'
        url=QUrl(self.server.text().rstrip('/')+route)
        self.note('TESTE: abrindo listagem '+route+' (sem editar ou salvar).')
        self.webview.load(url)
        QTimer.singleShot(1300,lambda:self._readonly_poll('search',0))

    def _readonly_poll(self, step, tries):
        # TESTE 4: pesquisa, confere identidade e abre edição sem alterar/salvar.
        if not self.readonly_test:
            return
        if tries >= 20:
            self.note('TESTE INTERROMPIDO: tempo esgotado em ' + step + '.')
            self.readonly_cancel()
            return
        if self.web_pending:
            QTimer.singleShot(700, lambda: self._readonly_poll(step, tries + 1))
            return

        if step == 'search':
            js = """(() => {
                try {
                    const all = [...document.querySelectorAll('input[name="nomeCpfCns"]')];
                    const visible = all.filter(x => x.getClientRects().length);
                    const buttons = [...document.querySelectorAll('[data-cy="BuscarCidadaoButton"]')];
                    return JSON.stringify({count:all.length,visible:visible.length,
                                           button:buttons.length,url:location.pathname});
                } catch(e) {return JSON.stringify({erro:String(e)});}
            })()"""

            def got(raw):
                if not self.readonly_test:
                    return
                try:
                    dados = json.loads(raw) if isinstance(raw, str) else {}
                except (ValueError, TypeError):
                    dados = {}
                if tries == 0 or tries % 5 == 0:
                    self.note('DEBUG BUSCA: retorno=' + type(raw).__name__
                              + ' | campos=' + str(dados.get('count', '?'))
                              + ' | visíveis=' + str(dados.get('visible', '?'))
                              + ' | botões=' + str(dados.get('button', '?'))
                              + ' | rota=' + str(dados.get('url', '?'))[:100])
                if 'erro' in dados:
                    self.note('DEBUG BUSCA: erro JS: ' + str(dados['erro'])[:160])
                    self.readonly_cancel()
                elif (dados.get('count') == 1 and dados.get('visible') == 1
                      and dados.get('button') == 1):
                    self._readonly_fill_search()
                else:
                    QTimer.singleShot(700, lambda: self._readonly_poll('search', tries + 1))

            self.webview.page().runJavaScript(js, got)

        elif step == 'results':
            # O CPF/CNS é conferido a partir do TEXTO do resultado, não do input de busca.
            # Não abrir menu se existirem resultados ambíguos ou não correspondentes.
            js = r"""(() => {
                try {
                    const text = document.body.innerText || '';
                    const matches = [...text.matchAll(/\bCPF\s*:?\s*([0-9.\-]{11,18})/gi)]
                        .map(m => m[1].replace(/\D/g,''));
                    const actions = [...document.querySelectorAll(
                        '[data-testid="Button.Dropdown"],button[aria-haspopup="true"][aria-controls^="dropdown-"]')]
                        .filter(x => x.getClientRects().length);
                    const local = text.match(/Cadastros na base local\s+(\d+)\s+cadastro(?:s)? encontrado(?:s)?/i);
                    return JSON.stringify({cpfMatches:matches, actions:actions.length,
                        localCount:local ? Number(local[1]) : null, path:location.pathname});
                } catch(e) {return JSON.stringify({erro:String(e)});}
            })()"""

            def got(raw):
                if not self.readonly_test:
                    return
                try:
                    dados = json.loads(raw) if isinstance(raw, str) else {}
                except (ValueError, TypeError):
                    dados = {}
                if 'erro' in dados:
                    self.note('TESTE 3: erro na leitura: ' + str(dados['erro'])[:150])
                    self.readonly_cancel()
                    return
                ident = self.readonly_test['person']['cpf_cns']
                cpfs = dados.get('cpfMatches', [])
                if tries == 0 or tries % 5 == 0:
                    self.note('DEBUG RESULTADO: CPF exibidos=' + str(len(cpfs))
                              + ' | menus=' + str(dados.get('actions', '?'))
                              + ' | base local=' + str(dados.get('localCount', '?')))
                # Conferência estrita: resultado local único, um CPF exibido e um menu.
                if (dados.get('localCount') == 1 and len(cpfs) == 1
                        and cpfs[0] == ident and dados.get('actions') == 1):
                    self.note('TESTE 3: resultado local único; CPF exibido confere (final '
                              + ident[-4:] + ').')
                    self._readonly_open_menu()
                elif dados.get('localCount') is not None and (
                        dados.get('localCount') > 1 or
                        (cpfs and (len(cpfs) != 1 or cpfs[0] != ident)) or
                        dados.get('actions', 0) > 1):
                    self.note('TESTE 3 BLOQUEADO: resultado ambíguo ou CPF divergente.')
                    self.readonly_cancel()
                else:
                    QTimer.singleShot(700, lambda: self._readonly_poll('results', tries + 1))

            self.webview.page().runJavaScript(js, got)

        elif step == 'menu':
            self._readonly_poll_menu(tries)
        elif step == 'edit':
            self._readonly_poll_edit(tries)
        else:
            self.note('TESTE 4: etapa não autorizada: ' + str(step))
            self.readonly_cancel()

    def _readonly_fill_search(self):
        if not self.readonly_test:
            return
        identifier = self.readonly_test['person']['cpf_cns']
        js = """(() => {
            try {
                const field = document.querySelector('input[name="nomeCpfCns"]');
                const btn = document.querySelector('[data-cy="BuscarCidadaoButton"]');
                if (!field || !btn) {
                    return JSON.stringify({ok:false, why:'Campo ou botão ausente'});
                }
                if (!field.getClientRects().length || !btn.getClientRects().length) {
                    return JSON.stringify({ok:false, why:'Campo ou botão não visível'});
                }
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                setter.call(field, IDENT);
                field.dispatchEvent(new Event('input', {bubbles:true}));
                field.dispatchEvent(new Event('change', {bubbles:true}));
                btn.click();
                return JSON.stringify({ok:true});
            } catch (e) {
                return JSON.stringify({ok:false, why:String(e)});
            }
        })()""".replace('IDENT', json.dumps(identifier))

        def done(raw):
            if not self.readonly_test:
                return
            try:
                dados = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                dados = {}
            if not dados.get('ok'):
                self.note('PESQUISA NÃO INICIADA: ' + str(dados.get('why', 'retorno inválido'))[:160])
                self.readonly_cancel()
                return
            self.note('TESTE 2: clique em Buscar executado para CPF/CNS final '
                      + identifier[-4:] + '. Confira o resultado exibido no PEC.')
            self.note('TESTE 4: aguardando resultado para conferir CPF e abrir cadastro sem alterações.')
            QTimer.singleShot(1000, lambda: self._readonly_poll('results', 0))

        self.webview.page().runJavaScript(js, done)

    def _readonly_open_menu(self):
        # Abrir somente o menu do resultado único já validado.
        if not self.readonly_test:
            return
        js = """(() => {
            try {
                const actions = [...document.querySelectorAll(
                    '[data-testid="Button.Dropdown"],button[aria-haspopup="true"][aria-controls^="dropdown-"]')]
                    .filter(x => x.getClientRects().length);
                if (actions.length !== 1) {
                    return JSON.stringify({ok:false, why:'Quantidade de menus: '+actions.length});
                }
                actions[0].click();
                return JSON.stringify({ok:true});
            } catch(e) { return JSON.stringify({ok:false,why:String(e)}); }
        })()"""

        def got(raw):
            if not self.readonly_test:
                return
            try:
                dados = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                dados = {}
            if not dados.get('ok'):
                self.note('TESTE 4 INTERROMPIDO: menu: ' + str(dados.get('why', 'retorno inválido'))[:150])
                self.readonly_cancel()
                return
            self.note('TESTE 4: menu de três pontos acionado; procurando Atualizar cadastro.')
            QTimer.singleShot(450, lambda: self._readonly_poll('menu', 0))

        self.webview.page().runJavaScript(js, got)

    def _readonly_poll_menu(self, tries):
        if not self.readonly_test:
            return
        # Apenas identificar a ação; clicar ficará em função separada.
        js = """(() => {
            try {
                const nodes = [...document.querySelectorAll('[role="menuitem"],button,a')]
                    .filter(x => x.getClientRects().length &&
                        (x.innerText||'').trim() === 'Atualizar cadastro');
                return JSON.stringify({count:nodes.length, path:location.pathname});
            } catch(e) { return JSON.stringify({erro:String(e)}); }
        })()"""

        def got(raw):
            if not self.readonly_test:
                return
            try:
                dados = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                dados = {}
            if 'erro' in dados:
                self.note('TESTE 4: erro ao verificar menu: ' + str(dados['erro'])[:150])
                self.readonly_cancel()
            elif dados.get('count') == 1:
                self._readonly_choose_edit()
            elif dados.get('count', 0) > 1:
                self.note('TESTE 4 BLOQUEADO: múltiplas opções Atualizar cadastro.')
                self.readonly_cancel()
            else:
                if tries == 0 or tries % 5 == 0:
                    self.note('DEBUG MENU: ação Atualizar cadastro ainda não visível.')
                QTimer.singleShot(700, lambda: self._readonly_poll('menu', tries + 1))

        self.webview.page().runJavaScript(js, got)

    def _readonly_choose_edit(self):
        if not self.readonly_test:
            return
        js = """(() => {
            try {
                const nodes = [...document.querySelectorAll('[role="menuitem"],button,a')]
                    .filter(x => x.getClientRects().length &&
                        (x.innerText||'').trim() === 'Atualizar cadastro');
                if (nodes.length !== 1) {
                    return JSON.stringify({ok:false, why:'Opções encontradas: '+nodes.length});
                }
                nodes[0].click();
                return JSON.stringify({ok:true});
            } catch(e) { return JSON.stringify({ok:false, why:String(e)}); }
        })()"""

        def got(raw):
            if not self.readonly_test:
                return
            try:
                dados = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                dados = {}
            if not dados.get('ok'):
                self.note('TESTE 4 INTERROMPIDO: opção Atualizar cadastro: '
                          + str(dados.get('why', 'retorno inválido'))[:150])
                self.readonly_cancel()
                return
            self.note('TESTE 4: Atualizar cadastro acionado. Somente leitura, aguardando CPF/CNS.')
            QTimer.singleShot(800, lambda: self._readonly_poll('edit', 0))

        self.webview.page().runJavaScript(js, got)

    def _readonly_poll_edit(self, tries):
        if not self.readonly_test:
            return
        js = """(() => {
            try {
                const cpf = [...document.querySelectorAll('input[name="dadosPessoais.cpf"]')];
                const cns = [...document.querySelectorAll('input[name="dadosPessoais.cns"]')];
                return JSON.stringify({url:location.pathname,cpfCount:cpf.length,
                    cnsCount:cns.length,cpf:cpf.length===1?cpf[0].value:'',
                    cns:cns.length===1?cns[0].value:''});
            } catch(e) { return JSON.stringify({erro:String(e)}); }
        })()"""

        def got(raw):
            if not self.readonly_test:
                return
            try:
                dados = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                dados = {}
            if 'erro' in dados:
                self.note('TESTE 4: erro ao ler a edição: ' + str(dados['erro'])[:150])
                self.readonly_cancel()
                return
            import re
            path = str(dados.get('url', ''))
            route_ok = bool(re.fullmatch(
                r'/(?:cidadao|gestaoCadastros/cadastro-individual)/\d+/edit/?', path))
            identifiers = [re.sub(r'\D', '', str(dados.get(k, ''))) for k in ('cpf', 'cns')]
            ident = self.readonly_test['person']['cpf_cns']
            if tries == 0 or tries % 5 == 0:
                self.note('DEBUG EDIÇÃO: rota=' + path[:100]
                          + ' | campos CPF/CNS=' + str(dados.get('cpfCount', 0))
                          + '/' + str(dados.get('cnsCount', 0)))
            if route_ok and ident in identifiers:
                self.readonly_test['step'] = 'verified'
                self.readonly_test['verified_path'] = path
                self.note('TESTE 4 CONCLUÍDO: identidade conferida (final ' + ident[-4:] + ').')
                self.note('Cadastro aberto somente para leitura. Nenhum campo alterado ou salvo.')
                self.progress_text.setText('Comunicação MGC/QtWebEngine validada — SOMENTE LEITURA')
                return
            if route_ok and any(identifiers) and ident not in identifiers:
                self.note('TESTE 4 BLOQUEADO: CPF/CNS diverge do cidadão selecionado.')
                self.readonly_cancel()
                return
            QTimer.singleShot(700, lambda: self._readonly_poll('edit', tries + 1))

        self.webview.page().runJavaScript(js, got)

    def readonly_verify_identity(self):
        if not self._readonly_ready():return
        if not self.readonly_test or self.readonly_test.get('step')!='verified':
            QMessageBox.information(self,'Identidade','Execute primeiro a pesquisa e abertura de um cidadão do CSV.');return
        self._readonly_poll_edit(0)

    def readonly_inspect_territory(self):
        """Leitura do seletor territorial do MGC, sem eventos nem mudanças no DOM."""
        if not self._readonly_ready():
            return
        if not self.readonly_test or self.readonly_test.get('step') != 'verified':
            QMessageBox.information(self, 'Inspeção Mudou-se',
                'Primeiro execute o Teste 2 e aguarde a mensagem de identidade conferida.')
            return
        person = self.readonly_test['person']
        identifier = person['cpf_cns']
        token = self.readonly_test['token']
        script = r"""(() => {
            try {
                const path = location.pathname;
                const cpf = [...document.querySelectorAll('input[name="dadosPessoais.cpf"]')];
                const cns = [...document.querySelectorAll('input[name="dadosPessoais.cns"]')];
                const digits = v => String(v || '').replace(/\D/g, '');
                const identities = [];
                if (cpf.length === 1) identities.push(digits(cpf[0].value));
                if (cns.length === 1) identities.push(digits(cns[0].value));
                const flags = [...document.querySelectorAll(
                    'input[name="responsabilidadeAcompanhamento.statusCidadaoSaiuTerritorio"]')];
                const labels = flags.length === 1 ? [...document.querySelectorAll('label')]
                    .filter(label => label.contains(flags[0])) : [];
                const fora = [...document.querySelectorAll(
                    'input[name="responsabilidadeAcompanhamento.statusForaArea"]')];
                return JSON.stringify({
                    path, identities, cpfCount:cpf.length, cnsCount:cns.length,
                    flagCount: flags.length, marked:flags.length === 1 ? flags[0].checked : null,
                    flagType:flags.length === 1 ? flags[0].type : null,
                    labelCount:labels.length,
                    labelText:labels.length === 1 ? (labels[0].innerText || '').trim().slice(0,90) : '',
                    foraCount:fora.length,
                    foraMarked:fora.length === 1 ? fora[0].checked : null
                });
            } catch(e) {return JSON.stringify({erro:String(e)});}
        })()"""

        def done(raw):
            if not self.readonly_test or self.readonly_test.get('token') is not token:
                return
            try:
                data = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                data = {}
            if not isinstance(data, dict) or 'erro' in data:
                self.note('TESTE 5 INTERROMPIDO: leitura territorial falhou: '
                          + str(data.get('erro', 'retorno inválido'))[:120])
                return
            import re
            path = str(data.get('path', ''))
            route_ok = bool(re.fullmatch(
                r'/(?:cidadao|gestaoCadastros/cadastro-individual)/\d+/edit/?', path))
            found = [re.sub(r'\D', '', str(v)) for v in data.get('identities', [])]
            if not route_ok or identifier not in found:
                self.note('TESTE 5 BLOQUEADO: URL ou CPF/CNS não corresponde ao cidadão validado.')
                self.readonly_cancel()
                return
            self.note('TESTE 5: identidade reconferida (final ' + identifier[-4:] + ').')
            if data.get('flagCount') != 1:
                self.note('TESTE 5 INCONCLUSIVO: campo Mudou-se encontrado '
                          + str(data.get('flagCount')) + ' vez(es); esperado 1.')
                return
            estado = 'MARCADO' if data.get('marked') is True else 'DESMARCADO'
            self.note('TESTE 5: Mudou-se localizado | tipo='
                      + str(data.get('flagType')) + ' | estado=' + estado
                      + ' | rótulos associados=' + str(data.get('labelCount')))
            self.note('TESTE 5: Fora de área | campos=' + str(data.get('foraCount'))
                      + ' | marcado=' + str(data.get('foraMarked')))
            self.note('TESTE 5 CONCLUÍDO: somente leitura, sem clique, alteração ou salvamento.')

        self.note('TESTE 5: inspecionando Mudou-se no cadastro já validado (sem alterações).')
        self.webview.page().runJavaScript(script, done)

    def test6_mark_territory(self):
        """Teste 6: altera APENAS o estado local de Mudou-se; nunca salva."""
        if not self._readonly_ready():
            return
        test = self.readonly_test
        if not test or test.get('step') != 'verified' or not test.get('verified_path'):
            QMessageBox.information(self, 'Teste 6',
                'Primeiro execute o Teste 2 e aguarde a identidade conferida.')
            return
        if self.territory_test_running:
            QMessageBox.information(self, 'Teste 6', 'Aguarde o teste atual terminar.')
            return
        person = test['person']
        response = QMessageBox.question(
            self, 'Teste 6 — alteração NÃO SALVA',
            'Confirmar marcação temporária de Mudou-se para:\n\n'
            + person['nome'] + ' (CPF/CNS final ' + person['cpf_cns'][-4:] + ')?\n\n'
            'O checkbox será alterado na tela do PEC, mas o Higienizador NÃO clicará em Salvar.\n'
            'NÃO clique em Salvar manualmente durante este teste.\n'
            'Após conferir, descarte a alteração usando a navegação do PEC.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if response != QMessageBox.Yes:
            self.note('TESTE 6 cancelado pelo operador; nenhuma alteração executada.')
            return
        self.territory_test_running = True
        token = test['token']
        expected_path = test['verified_path']
        identifier = person['cpf_cns']
        # A operação inteira checa novamente a identidade no MESMO JavaScript do clique.
        js = r"""(() => {
            try {
                const expectedPath = EXPECTED_PATH;
                const expectedID = EXPECTED_ID;
                if (location.pathname !== expectedPath ||
                    !/^\/(?:cidadao|gestaoCadastros\/cadastro-individual)\/\d+\/edit\/?$/.test(location.pathname))
                    return JSON.stringify({ok:false,why:'Rota de edição mudou'});
                const digits = v => String(v || '').replace(/\D/g, '');
                const cpf = [...document.querySelectorAll('input[name="dadosPessoais.cpf"]')];
                const cns = [...document.querySelectorAll('input[name="dadosPessoais.cns"]')];
                const ids = [];
                if (cpf.length === 1) ids.push(digits(cpf[0].value));
                if (cns.length === 1) ids.push(digits(cns[0].value));
                if (!ids.includes(expectedID))
                    return JSON.stringify({ok:false,why:'CPF/CNS não coincide'});
                const flags = [...document.querySelectorAll(
                    'input[name="responsabilidadeAcompanhamento.statusCidadaoSaiuTerritorio"]')];
                if (flags.length !== 1 || flags[0].type !== 'checkbox')
                    return JSON.stringify({ok:false,why:'Checkbox Mudou-se ambíguo'});
                const labels = [...document.querySelectorAll('label')]
                    .filter(label => label.contains(flags[0]));
                if (labels.length !== 1)
                    return JSON.stringify({ok:false,why:'Rótulo Mudou-se ambíguo'});
                const fora = [...document.querySelectorAll(
                    'input[name="responsabilidadeAcompanhamento.statusForaArea"]')];
                if (fora.length !== 1)
                    return JSON.stringify({ok:false,why:'Campo Fora de área ambíguo'});
                const beforeFora = fora[0].checked;
                if (flags[0].checked)
                    return JSON.stringify({ok:true,already:true,marked:true,beforeFora,afterFora:fora[0].checked});
                labels[0].click();
                return JSON.stringify({ok:true,clicked:true,marked:flags[0].checked,
                    beforeFora,afterFora:fora[0].checked});
            } catch(e) {return JSON.stringify({ok:false,why:String(e)});}
        })()""".replace('EXPECTED_PATH', json.dumps(expected_path)).replace('EXPECTED_ID', json.dumps(identifier))

        def first_done(raw):
            if not self.readonly_test or self.readonly_test.get('token') is not token:
                self.territory_test_running = False
                return
            try:
                data = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                data = {}
            if not data.get('ok'):
                self.note('TESTE 6 BLOQUEADO: ' + str(data.get('why', 'resposta inválida'))[:140])
                self.territory_test_running = False
                return
            if data.get('already'):
                self.note('TESTE 6: Mudou-se já estava MARCADO; nenhuma alteração executada.')
            else:
                self.note('TESTE 6: clique único no rótulo Mudou-se efetuado; aguardando atualização do formulário.')
            if data.get('beforeFora') != data.get('afterFora'):
                self.note('ATENÇÃO: Fora de área mudou após clique; confira o formulário. NÃO SALVE.')
            QTimer.singleShot(450, lambda: self._test6_verify(token, expected_path, identifier, data))

        self.note('TESTE 6: reconferindo CPF/CNS e marcando somente Mudou-se (SEM SALVAR).')
        self.webview.page().runJavaScript(js, first_done)

    def _test6_verify(self, token, expected_path, identifier, initial):
        if not self.readonly_test or self.readonly_test.get('token') is not token:
            self.territory_test_running = False
            return
        js = r"""(() => {
            try {
                const digits = v => String(v || '').replace(/\D/g, '');
                const cpf = [...document.querySelectorAll('input[name="dadosPessoais.cpf"]')];
                const cns = [...document.querySelectorAll('input[name="dadosPessoais.cns"]')];
                const ids = [];
                if (cpf.length === 1) ids.push(digits(cpf[0].value));
                if (cns.length === 1) ids.push(digits(cns[0].value));
                const flag = [...document.querySelectorAll(
                    'input[name="responsabilidadeAcompanhamento.statusCidadaoSaiuTerritorio"]')];
                const fora = [...document.querySelectorAll(
                    'input[name="responsabilidadeAcompanhamento.statusForaArea"]')];
                return JSON.stringify({path:location.pathname,ids,
                    count:flag.length,marked:flag.length === 1 ? flag[0].checked : null,
                    foraCount:fora.length,fora:fora.length === 1 ? fora[0].checked : null});
            } catch(e) {return JSON.stringify({erro:String(e)});}
        })()"""

        def done(raw):
            self.territory_test_running = False
            if not self.readonly_test or self.readonly_test.get('token') is not token:
                return
            try:
                data = json.loads(raw) if isinstance(raw, str) else {}
            except (ValueError, TypeError):
                data = {}
            if (data.get('erro') or data.get('path') != expected_path
                    or identifier not in data.get('ids', []) or data.get('count') != 1):
                self.note('TESTE 6 INCONCLUSIVO: não foi possível reconferir a tela após o clique. NÃO SALVE.')
                return
            if data.get('marked') is not True:
                self.note('TESTE 6 FALHOU: Mudou-se não permaneceu marcado. NÃO SALVE.')
                return
            self.note('TESTE 6 CONCLUÍDO: Mudou-se MARCADO na edição (CPF/CNS final '
                      + identifier[-4:] + '). ALTERAÇÃO AINDA NÃO SALVA.')
            if data.get('foraCount') != 1 or data.get('fora') != initial.get('beforeFora'):
                self.note('ATENÇÃO: Fora de área mudou ou não foi localizado. Confira manualmente.')
            else:
                self.note('TESTE 6: Fora de área permaneceu inalterado.')
            self.note('NÃO CLIQUE EM SALVAR. Descarte as alterações ao sair da edição para encerrar o teste.')

        self.webview.page().runJavaScript(js, done)

    def note(self, value):
        self.log.append(f'[{datetime.now():%H:%M:%S}] {value}')

    def copy_log(self):
        QApplication.clipboard().setText(self.log.toPlainText())
        self.note('Log copiado para a área de transferência.')

    def export_log(self):
        file, _ = QFileDialog.getSaveFileName(self, 'Exportar registro', 'higienizador_previa_log.txt', 'Texto (*.txt)')
        if file:
            Path(file).write_text(self.log.toPlainText() + '\n', encoding='utf-8')
            self.note('Log de demonstração exportado.')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(CSS)
    window = Preview(); window.show()
    sys.exit(app.exec())

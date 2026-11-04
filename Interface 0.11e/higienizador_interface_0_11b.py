"""Higienizador 2.0 — Etapa 3: interface visual sem automação.
Revisão 11 — QWebEngineView persistente, com camada de logo sobreposta.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit, QFileDialog,
    QBoxLayout, QProgressBar, QTextEdit, QSplitter, QMessageBox,
    QScrollArea, QStackedWidget, QStackedLayout,
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
        self.setWindowTitle('Higienizador 2.0 | INTERFACE 0.11b (ALPHA)')
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
        self.web_pending = False
        self.build()
        self.note('ETAPA 3 - REVISAO 11: selecione uma UBS, carregue o CSV e inicie o ambiente. Nenhum cadastro será alterado.')

    def build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.root_layout = layout
        layout.setContentsMargins(7, 4, 7, 6)
        layout.setSpacing(4)

        menu = QHBoxLayout(); menu.setSpacing(13)
        for name in ('Unidades', 'Exceções', 'Abrir pasta de relatórios'):
            l = QLabel(name); l.setStyleSheet('font-size:11px;')
            menu.addWidget(l)
        menu.addStretch()
        layout.addLayout(menu)

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
        self.lot_group.setMinimumWidth(120)
        lower.addWidget(self.lot_group, 0)

        self.operation_buttons = []
        for caption in ('▶ Iniciar lote', 'Pausar', 'Continuar', 'Parar'):
            b = QPushButton(caption)
            b.setEnabled(False)
            lower.addWidget(b, 0)
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
            lower.addWidget(frame, 1)
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
        self.operation_row.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)

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
        if path:
            self.csv.setText(path)
            self.limit.setEnabled(True)
            self.progress_text.setText('Relatório carregado — quantidade será exibida após integração do motor')
            self.note('Arquivo selecionado para teste da interface: ' + Path(path).name)
            self.note('Fluxo revisado: agora escolha o limite do lote após visualizar o relatório carregado.')

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

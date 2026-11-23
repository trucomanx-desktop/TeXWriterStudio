#!/usr/bin/env python3
"""PyQt5 LaTeX editor with SyncTeX source/PDF navigation."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import (
    Qt,
    QProcess,
    QSettings,
    QTimer,
    QRect,
    QSize,
    QFileSystemWatcher,
    QProcessEnvironment,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QSyntaxHighlighter,
    QIcon,
    QDesktopServices,
)
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QAction,
    QStatusBar,
    QSizePolicy,
    QMenu,
)

import tex_writer_studio.about as about
import tex_writer_studio.modules.configure as configure
from tex_writer_studio.modules.resources import resource_path

from tex_writer_studio.modules.wabout import show_about_window
from tex_writer_studio.desktop import (
    create_desktop_file,
    create_desktop_directory,
    create_desktop_menu,
)

# ---------- Path to config file ----------
CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".config", about.__package__, "config.json"
)

DEFAULT_CONTENT = {
    "toolbar_configure": "Configure",
    "toolbar_configure_tooltip": "Open the configure Json file of program GUI",
    "toolbar_about": "About",
    "toolbar_about_tooltip": "About the program",
    "toolbar_coffee": "Coffee",
    "toolbar_coffee_tooltip": "Buy me a coffee (TrucomanX)",
    "window_width": 1024,
    "window_height": 800,
}

configure.verify_default_config(CONFIG_PATH, default_content=DEFAULT_CONTENT)

CONFIG = configure.load_config(CONFIG_PATH)

# ---------------------------------------


DEFAULTS = {
    "font_family": "DejaVu Sans Mono",
    "font_size": 12,
    "editor_bg": "#1e1e1e",
    "editor_fg": "#d4d4d4",
    "gutter_bg": "#252526",
    "gutter_fg": "#858585",
    "selection_bg": "#264f78",
    "current_line": "#282828",
    "command": "pdflatex -synctex=1 -interaction=nonstopmode -file-line-error %filename%",
    "passes": 1,
    "auto_save": True,
    "theme": "Dark",
    "pdf_zoom": 1.0,
}
THEMES = {
    "Dark": {
        "command": "#569cd6",
        "keyword": "#c586c0",
        "brace": "#d4d4d4",
        "comment": "#6a9955",
        "math": "#dcdcaa",
        "environment": "#4ec9b0",
        "option": "#ce9178",
    },
    "Light": {
        "command": "#0000cc",
        "keyword": "#800080",
        "brace": "#202020",
        "comment": "#008000",
        "math": "#a05000",
        "environment": "#007070",
        "option": "#a31515",
    },
    "Solarized": {
        "command": "#268bd2",
        "keyword": "#d33682",
        "brace": "#586e75",
        "comment": "#859900",
        "math": "#b58900",
        "environment": "#2aa198",
        "option": "#cb4b16",
    },
}


class LatexHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme="Dark"):
        super().__init__(document)
        self.set_theme(theme)

    def set_theme(self, theme):
        theme = {"Escuro": "Dark", "Claro": "Light", "Solarizado": "Solarized"}.get(
            theme, theme
        )
        colors = THEMES.get(theme, THEMES["Dark"])
        self.rules = []
        for key, patterns in {
            "comment": [r"%.*$"],
            "command": [r"\\[A-Za-z@]+", r"\\."],
            "environment": [r"\\(?:begin|end)\s*\{[^}]*\}"],
            "keyword": [
                r"\\(?:section|subsection|subsubsection|chapter|title|author|date|maketitle|label|ref|pageref|cite|include|input|documentclass|usepackage|newcommand|renewcommand|item|textbf|textit|emph|underline|url|href)\b"
            ],
            "math": [r"\$[^$]*\$", r"\\\[.*?\\\]", r"\\\(.*?\\\)"],
            "option": [r"\[[^\]]*\]"],
            "brace": [r"[{}]"],
        }.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colors[key]))
            if key in ("command", "keyword"):
                fmt.setFontWeight(QFont.Bold)
            self.rules.extend((re.compile(p), fmt) for p in patterns)

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class CodeEditor(QPlainTextEdit):
    sourceChanged = pyqtSignal(int, int)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.highlighter = LatexHighlighter(
            self.document(), settings.value("theme", DEFAULTS["theme"])
        )
        self.setToolTip(
            "LaTeX source editor. Right-click for editing and SyncTeX actions."
        )
        self.setTabStopDistance(QFontMetrics(self.font()).horizontalAdvance(" ") * 4)
        self.cursorPositionChanged.connect(self.report_cursor)
        self.apply_appearance()

    def apply_appearance(self):
        family = self.settings.value("font_family", DEFAULTS["font_family"])
        size = int(self.settings.value("font_size", DEFAULTS["font_size"]))
        self.setFont(QFont(family, size))
        bg = self.settings.value("editor_bg", DEFAULTS["editor_bg"])
        fg = self.settings.value("editor_fg", DEFAULTS["editor_fg"])
        sel = self.settings.value("selection_bg", DEFAULTS["selection_bg"])
        self.setStyleSheet(
            f"QPlainTextEdit {{background:{bg}; color:{fg}; selection-background-color:{sel}; border:0;}}"
        )
        self.highlighter.set_theme(self.settings.value("theme", DEFAULTS["theme"]))
        self.highlighter.rehighlight()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            delta = 1 if e.angleDelta().y() > 0 else -1
            n = max(6, min(48, self.font().pointSize() + delta))
            self.settings.setValue("font_size", n)
            self.apply_appearance()
            e.accept()
        else:
            super().wheelEvent(e)

    def report_cursor(self):
        c = self.textCursor()
        self.sourceChanged.emit(c.blockNumber() + 1, c.positionInBlock() + 1)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class EditorWithGutter(CodeEditor):
    rightClicked = pyqtSignal(int, int)

    def __init__(self, settings):
        super().__init__(settings)
        self.gutter = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_gutter_width)
        self.updateRequest.connect(self.update_gutter)
        self.update_gutter_width(0)

    def line_number_width(self):
        return 12 + QFontMetrics(self.font()).horizontalAdvance("9") * len(
            str(max(1, self.blockCount()))
        )

    def update_gutter_width(self, _):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_gutter_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.gutter.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_width(), cr.height())
        )

    def paint_line_numbers(self, event):
        p = QPainter(self.gutter)
        p.fillRect(
            event.rect(),
            QColor(self.settings.value("gutter_bg", DEFAULTS["gutter_bg"])),
        )
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())
        p.setPen(QColor(self.settings.value("gutter_fg", DEFAULTS["gutter_fg"])))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                p.drawText(
                    0,
                    top,
                    self.gutter.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignRight,
                    str(n + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            n += 1

    def go_to(self, line, col=1):
        block = self.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            c = self.textCursor()
            c.setPosition(block.position() + max(0, col - 1))
            self.setTextCursor(c)
            self.centerCursor()
            self.setFocus()

    def cursor_at_view_position(self, point):
        return self.cursorForPosition(point)

    def build_context_menu(self):
        """Build the editor context menu in small sections for easy extension."""
        menu = QMenu(self)
        self.add_clipboard_actions(menu)
        menu.addSeparator()
        jump = menu.addAction("Go to this position in PDF")
        jump.triggered.connect(self.emit_right_click_position)
        return menu

    def add_clipboard_actions(self, menu):
        selected = self.textCursor().hasSelection()
        cut = menu.addAction("Cut")
        cut.setEnabled(selected)
        cut.triggered.connect(self.cut)
        copy = menu.addAction("Copy")
        copy.setEnabled(selected)
        copy.triggered.connect(self.copy)
        paste = menu.addAction("Paste")
        paste.setEnabled(bool(QApplication.clipboard().text()))
        paste.triggered.connect(self.paste)

    def emit_right_click_position(self):
        c = self.textCursor()
        self.rightClicked.emit(c.blockNumber() + 1, c.positionInBlock() + 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            cursor = self.cursorForPosition(event.pos())
            current = self.textCursor()
            if not (
                current.hasSelection()
                and current.selectionStart()
                <= cursor.position()
                < current.selectionEnd()
            ):
                self.setTextCursor(cursor)
            self.emit_right_click_position()
            self.build_context_menu().exec_(self.viewport().mapToGlobal(event.pos()))
            event.accept()
            return
        super().mousePressEvent(event)


class PdfCanvas(QWidget):
    clicked = pyqtSignal(int, float, float)
    zoomChanged = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.pages = []
        self.page_sizes = []
        self.zoom = 1.0
        self.marker = None
        self.setStyleSheet("background:#555;")
        self.setToolTip("PDF preview. Use Ctrl + mouse wheel to change zoom.")

    def set_pages(self, pages, page_sizes):
        self.pages = pages
        self.page_sizes = page_sizes
        self.update()

    def set_content_size(self, width):
        if not self.pages:
            return
        content_width = max(width, max(page.width() for page in self.pages) + 40)
        content_height = 24 + sum(page.height() + 24 for page in self.pages)
        self.resize(content_width, content_height)
        self.update()

    def sizeHint(self):
        return self.size()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#555555"))
        y = 12
        for index, page in enumerate(self.pages, 1):
            w = page.width()
            h = page.height()
            x = max(12, (self.width() - w) // 2)
            p.fillRect(x + 3, y + 3, w, h, QColor("#333"))
            p.drawImage(x, y, page)
            if self.marker and self.marker[0] == index:
                _, mx, my = self.marker
                ps = self.page_sizes[index - 1]
                mx *= w / ps[0]
                my *= h / ps[1]
                p.setPen(QColor("#ff3b30"))
                p.setBrush(QColor(255, 59, 48, 100))
                p.drawEllipse(int(x + mx) - 7, int(y + my) - 7, 14, 14)
            y += h + 24

    def mousePressEvent(self, e):
        y = e.pos().y() - 12
        for i, page in enumerate(self.pages):
            h = page.height()
            w = page.width()
            x = max(12, (self.width() - w) // 2)
            if y >= 0 and y < h and x <= e.pos().x() <= x + w:
                # SyncTeX coordinates use PDF points from page top-left.
                ps = self.page_sizes[i]
                self.clicked.emit(i + 1, (e.pos().x() - x) * ps[0] / w, y * ps[1] / h)
                return
            y -= h + 24

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.zoom = max(
                0.35, min(4, self.zoom * (1.1 if e.angleDelta().y() > 0 else 0.9))
            )
            self.zoomChanged.emit(self.zoom)
            e.accept()
        else:
            super().wheelEvent(e)


class PdfWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.document = None
        self.pdf_path = None
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render_pages)
        self.setWindowTitle("PDF Preview — SyncTeX")
        self.canvas = PdfCanvas()
        self.canvas.zoomChanged.connect(self.zoom_changed)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.setCentralWidget(self.scroll)
        self.setMinimumSize(600, 700)
        self.canvas.zoom = float(settings.value("pdf_zoom", 1.0))
        self.statusBar().showMessage("Ctrl + mouse wheel: zoom")

    def load_pdf(self, path):
        try:
            import fitz

            if self.document:
                self.document.close()
            self.document = fitz.open(path)
            self.pdf_path = str(Path(path).resolve())
            self.statusBar().showMessage(
                f"{len(self.document)} page(s) — Ctrl + mouse wheel to zoom"
            )
            self.render_pages()
        except Exception as ex:
            QMessageBox.warning(
                self,
                "PDF unavailable",
                f"Could not open the PDF. Install PyMuPDF.\n\n{ex}",
            )

    def render_pages(self):
        if not self.document:
            return
        width = max(200, self.scroll.viewport().width() - 40)
        pages = []
        sizes = []
        for page in self.document:
            rect = page.rect
            factor = width / rect.width * self.canvas.zoom
            pix = page.get_pixmap(
                matrix=__import__("fitz").Matrix(factor, factor), alpha=False
            )
            pages.append(
                QImage(
                    pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
                ).copy()
            )
            sizes.append((rect.width, rect.height))
        self.canvas.set_pages(pages, sizes)
        self.canvas.set_content_size(self.scroll.viewport().width())

    def zoom_changed(self, zoom):
        self.settings.setValue("pdf_zoom", zoom)
        self.render_pages()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.document:
            self.render_timer.start(180)

    def go_page(self, page):
        if self.canvas.pages:
            self.scroll.verticalScrollBar().setValue(
                sum(p.height() + 24 for p in self.canvas.pages[: max(0, page - 1)])
            )

    def go_position(self, page, x, y):
        if not self.canvas.pages or page < 1 or page > len(self.canvas.pages):
            return
        self.canvas.marker = (page, x, y)
        self.canvas.update()
        ps = self.canvas.page_sizes[page - 1]
        ypix = y * self.canvas.pages[page - 1].height() / ps[1]
        top = 12 + sum(p.height() + 24 for p in self.canvas.pages[: page - 1])
        self.scroll.verticalScrollBar().setValue(
            max(0, int(top + ypix - self.scroll.viewport().height() / 2))
        )

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.canvas.zoom = max(
                0.35,
                min(4, self.canvas.zoom * (1.1 if e.angleDelta().y() > 0 else 0.9)),
            )
            self.settings.setValue("pdf_zoom", self.canvas.zoom)
            self.canvas.updateGeometry()
            self.canvas.update()
            e.accept()
        else:
            super().wheelEvent(e)


class TerminalWidget(QWidget):
    """Persistent Bash command prompt with modular right-click actions."""

    ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
    CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    ANSI_COLORS = {
        30: "#000000",
        31: "#cd3131",
        32: "#0dbc79",
        33: "#e5e510",
        34: "#2472c8",
        35: "#bc3fbc",
        36: "#11a8cd",
        37: "#e5e5e5",
        90: "#666666",
        91: "#f14c4c",
        92: "#23d18b",
        93: "#f5f543",
        94: "#3b8eea",
        95: "#d670d6",
        96: "#29b8db",
        97: "#ffffff",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.cwd = str(Path.cwd())
        self._fmt = QTextCharFormat()
        self._ansi_tail = ""
        self.setMinimumHeight(110)
        self.setToolTip("Run shell commands in a persistent Bash session.")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(4)
        header = QHBoxLayout()
        title = QLabel("Terminal")
        title.setStyleSheet("font-weight:bold")
        header.addWidget(title)
        header.addStretch()
        clear = QPushButton("Clear")
        clear.setToolTip("Clear terminal output")
        clear.clicked.connect(lambda: self.output.clear())
        header.addWidget(clear)
        restart = QPushButton("Restart shell")
        restart.setToolTip("Restart the Bash session")
        restart.clicked.connect(self.start_shell)
        header.addWidget(restart)
        layout.addLayout(header)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)
        self.output.setFont(QFont("DejaVu Sans Mono", 10))
        self.output.setStyleSheet(
            "QPlainTextEdit {background:#111315;color:#d4d4d4;border:1px solid #444;}"
        )
        self.output.setContextMenuPolicy(Qt.CustomContextMenu)
        self.output.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(self.output, pos)
        )
        layout.addWidget(self.output, 1)
        row = QHBoxLayout()
        prompt = QLabel("$")
        prompt.setStyleSheet("color:#23d18b;font-weight:bold")
        row.addWidget(prompt)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Enter a shell command…")
        self.input.setToolTip(
            "Type a command and press Enter. The shell keeps its current directory and environment."
        )
        self.input.returnPressed.connect(self.submit)
        self.input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.input.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(self.input, pos)
        )
        row.addWidget(self.input, 1)
        layout.addLayout(row)

    def start_shell(self, cwd=None):
        if cwd:
            self.cwd = str(Path(cwd).resolve())
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.process = QProcess(self)
        self.process.setWorkingDirectory(self.cwd)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "xterm-256color")
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.shell_finished)
        self.process.start("/bin/bash", ["--noprofile", "--norc"])
        if self.process.waitForStarted(1000):
            self.input.setEnabled(True)
            self.input.setFocus()
        else:
            self.append_text("Could not start /bin/bash.\n", QColor("#f14c4c"))

    def submit(self):
        command = self.input.text()
        self.input.clear()
        self.run_command(command)

    def run_command(self, command):
        if not command.strip():
            return
        if not self.process or self.process.state() == QProcess.NotRunning:
            self.start_shell()
        self.append_text(f"$ {command}\n", QColor("#29b8db"))
        self.process.write((command + "\n").encode("utf-8"))

    def read_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self.render_ansi(self._ansi_tail + data)

    def render_ansi(self, text):
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        pos = 0
        for match in self.ANSI_RE.finditer(text):
            self.append_text(text[pos : match.start()], cursor=cursor)
            self.apply_sgr(match.group(1))
            pos = match.end()
        tail = text[pos:]
        if tail.endswith("\x1b") or re.search(r"\x1b\[[0-9;]*$", tail):
            split = tail.rfind("\x1b")
            self._ansi_tail = tail[split:]
            tail = tail[:split]
        else:
            self._ansi_tail = ""
        tail = self.CSI_RE.sub("", tail).replace("\r\n", "\n").replace("\r", "\n")
        self.append_text(tail, cursor=cursor)
        self.output.setTextCursor(cursor)

    def apply_sgr(self, codes):
        for token in (codes or "0").split(";"):
            code = int(token or 0)
            if code == 0:
                self._fmt = QTextCharFormat()
            elif code == 1:
                self._fmt.setFontWeight(QFont.Bold)
            elif code == 22:
                self._fmt.setFontWeight(QFont.Normal)
            elif code in self.ANSI_COLORS:
                self._fmt.setForeground(QColor(self.ANSI_COLORS[code]))
            elif code == 39:
                self._fmt.clearForeground()
            elif 40 <= code <= 47:
                self._fmt.setBackground(
                    QColor(self.ANSI_COLORS.get(code - 10, "#111315"))
                )
            elif code == 49:
                self._fmt.clearBackground()

    def append_text(self, text, color=None, cursor=None):
        if not text:
            return
        if cursor is None:
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat(self._fmt)
        if color:
            fmt.setForeground(color)
        cursor.insertText(text, fmt)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def build_context_menu(self, source_widget):
        """Build the popup menu in sections so terminal actions stay easy to extend."""
        menu = QMenu(self)
        change_dir = menu.addAction("Change to current file folder")
        change_dir.setEnabled(bool(getattr(self.window(), "path", None)))
        change_dir.triggered.connect(self.change_to_current_file_folder)
        pwd = menu.addAction("Show current folder (pwd)")
        pwd.triggered.connect(lambda: self.run_command("pwd"))
        menu.addSeparator()
        if source_widget is self.input:
            selected = bool(self.input.selectedText())
            cut = menu.addAction("Cut")
            cut.setEnabled(selected)
            cut.triggered.connect(self.input.cut)
            copy = menu.addAction("Copy")
            copy.setEnabled(selected)
            copy.triggered.connect(self.input.copy)
            paste = menu.addAction("Paste")
            paste.setEnabled(bool(QApplication.clipboard().text()))
            paste.triggered.connect(self.input.paste)
            menu.addSeparator()
        clear = menu.addAction("Clear terminal output")
        clear.triggered.connect(self.output.clear)
        return menu

    def show_context_menu(self, source_widget, position):
        self.build_context_menu(source_widget).exec_(
            source_widget.mapToGlobal(position)
        )

    def change_to_current_file_folder(self):
        current_path = getattr(self.window(), "path", None)
        if current_path:
            self.run_command(
                f"cd {shlex.quote(str(Path(current_path).resolve().parent))}"
            )

    def shell_finished(self, code, status):
        self.append_text(f"\n[Shell exited with code {code}]\n", QColor("#e5e510"))
        self.input.setEnabled(False)


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle("Editor Settings")
        self.s = settings
        form = QFormLayout(self)
        self.font = QFontComboBox()
        self.font.setCurrentFont(
            QFont(settings.value("font_family", DEFAULTS["font_family"]))
        )
        self.size = QSpinBox()
        self.size.setRange(6, 48)
        self.size.setValue(int(settings.value("font_size", 12)))
        self.theme = QComboBox()
        self.theme.addItems(THEMES)
        saved_theme = {
            "Escuro": "Dark",
            "Claro": "Light",
            "Solarizado": "Solarized",
        }.get(settings.value("theme", "Dark"), settings.value("theme", "Dark"))
        self.theme.setCurrentText(saved_theme)
        self.command = QTextEdit()
        self.command.setFixedHeight(70)
        self.command.setPlainText(settings.value("command", DEFAULTS["command"]))
        self.passes = QSpinBox()
        self.passes.setRange(1, 5)
        self.passes.setValue(int(settings.value("passes", 1)))
        self.backend = QComboBox()
        self.backend.addItem("None", "none")
        self.backend.addItem("BibTeX", "bibtex")
        self.backend.addItem("Biber", "biber")
        current = self.backend.findData(settings.value("bibliography_backend", "none"))
        self.backend.setCurrentIndex(max(0, current))
        self.autosave = QCheckBox("Save automatically before compiling")
        self.autosave.setChecked(
            str(settings.value("auto_save", "true")).lower() not in ("false", "0")
        )
        form.addRow("Editor font", self.font)
        form.addRow("Font size (Ctrl + mouse wheel)", self.size)
        form.addRow("Syntax theme", self.theme)
        form.addRow("Compile command", self.command)
        form.addRow("Bibliography tool", self.backend)
        form.addRow("LaTeX passes", self.passes)
        form.addRow("", self.autosave)
        self.color_buttons = {}
        for key, label in [
            ("editor_bg", "Editor background"),
            ("editor_fg", "Editor text"),
            ("gutter_bg", "Line number background"),
            ("gutter_fg", "Line numbers"),
            ("selection_bg", "Selection"),
        ]:
            b = QPushButtonColor(settings.value(key, DEFAULTS[key]))
            b.clicked.connect(lambda _, k=key, btn=b: self.pick_color(k, btn))
            self.color_buttons[key] = b
            form.addRow(label, b)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def pick_color(self, key, button):
        c = QColorDialog.getColor(QColor(self.s.value(key, DEFAULTS[key])), self)
        if c.isValid():
            self.s.setValue(key, c.name())
            button.setStyleSheet(f"background:{c.name()};padding:6px")

    def save(self):
        self.s.setValue("font_family", self.font.currentFont().family())
        self.s.setValue("font_size", self.size.value())
        self.s.setValue("theme", self.theme.currentText())
        self.s.setValue("command", self.command.toPlainText().strip())
        self.s.setValue("passes", self.passes.value())
        self.s.setValue("bibliography_backend", self.backend.currentData())
        self.s.setValue("auto_save", self.autosave.isChecked())


from PyQt5.QtWidgets import QPushButton


class QPushButtonColor(QPushButton):
    def __init__(self, color):
        super().__init__("Choose…")
        self.setStyleSheet(f"background:{color};padding:6px")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("LaTeXStudio", "Editor")
        self.pdf_window = PdfWindow(self.settings)
        self.process = None
        self.main_file = None
        self.compiling_main_file = None
        self.editors = {}
        self._signatures = {}
        self._external_pending = set()
        self._pdf_watch_path = None
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self.queue_external_check)
        self.file_watcher.directoryChanged.connect(self.queue_directory_check)
        self._external_timer = QTimer(self)
        self._external_timer.setSingleShot(True)
        self._external_timer.timeout.connect(self.check_external_changes)

        self.setWindowTitle(about.__program_name__)
        self.resize(CONFIG["window_width"], CONFIG["window_height"])

        ## Icon
        # Get base directory for icons
        self.icon_path = resource_path("icons", "logo.png")
        self.setWindowIcon(QIcon(self.icon_path))

        self.source_tabs = QTabWidget()
        self.source_tabs.setTabsClosable(True)
        self.source_tabs.currentChanged.connect(self.current_tab_changed)
        self.source_tabs.tabCloseRequested.connect(self.close_tab)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.work_tabs = QTabWidget()
        self.work_tabs.addTab(self.source_tabs, "Files")
        self.work_tabs.addTab(self.log, "Build Output")
        self.terminal = TerminalWidget()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.work_tabs)
        split.addWidget(self.terminal)
        split.setSizes([650, 190])
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.pdf_window.canvas.clicked.connect(self.pdf_clicked)
        self.create_actions()
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self.sync_source_to_pdf)
        self.new_file()
        for p in sys.argv[1:]:
            self.open_file(p)
        initial_cwd = Path(self.main_file).parent if self.main_file else Path.cwd()
        self.terminal.start_shell(initial_cwd)

    @property
    def editor(self):
        w = self.source_tabs.currentWidget()
        return w if isinstance(w, EditorWithGutter) else None

    @property
    def path(self):
        return self.editors.get(self.editor) if self.editor else None

    def action(self, toolbar, qicon, text, tooltip, shortcut, slot):
        a = QAction(qicon, text, self)
        if shortcut is not None:
            a.setShortcut(shortcut)
            a.setToolTip(f"{tooltip} ({shortcut})")
        else:
            a.setToolTip(tooltip)

        a.triggered.connect(slot)
        self.addAction(a)
        toolbar.addAction(a)
        return a

    def create_actions(self):

        self.toolbar = self.addToolBar("Main")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            "New",
            "New",
            "Ctrl+N",
            self.new_file,
        )
        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            "Open",
            "Open",
            "Ctrl+O",
            self.open_dialog,
        )
        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            "Save",
            "Save",
            "Ctrl+S",
            self.save,
        )
        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            "Make Main",
            "Make Main",
            "Ctrl+Shift+M",
            self.set_current_as_main,
        )
        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            "Compile PDF",
            "Compile PDF",
            "F5",
            self.compile,
        )
        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            "View PDF",
            "View PDF",
            "Ctrl+Shift+P",
            self.activate_pdf,
        )
        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            "Settings",
            "Settings",
            "Ctrl+,",
            self.configure,
        )

        # Adicionar o espaçador
        self.toolbar_spacer = QWidget()
        self.toolbar_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toolbar.addWidget(self.toolbar_spacer)

        # Configure
        self.action(
            self.toolbar,
            QIcon.fromTheme("document-properties"),
            CONFIG["toolbar_configure"],
            CONFIG["toolbar_configure_tooltip"],
            None,
            self.open_configure_editor,
        )

        # About
        self.action(
            self.toolbar,
            QIcon.fromTheme("help-about"),
            CONFIG["toolbar_about"],
            CONFIG["toolbar_about_tooltip"],
            None,
            self.open_about,
        )

        #
        self.action(
            self.toolbar,
            QIcon.fromTheme("emblem-favorite"),
            CONFIG["toolbar_coffee"],
            CONFIG["toolbar_coffee_tooltip"],
            None,
            self.on_coffee_action_click,
        )

        # Conectar ao sinal de mudança de orientação
        self.toolbar.orientationChanged.connect(self.on_update_spacer_policy)
        self.on_update_spacer_policy()

        m = self.menuBar().addMenu("File")
        for a in self.toolbar.actions()[:5]:
            m.addAction(a)
        edit = self.menuBar().addMenu("Edit")
        for label, shortcut, method in (
            ("Cut", "Ctrl+X", "cut"),
            ("Copy", "Ctrl+C", "copy"),
            ("Paste", "Ctrl+V", "paste"),
        ):
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(
                lambda checked=False, name=method: self.edit_clipboard(name)
            )
            self.addAction(action)
            edit.addAction(action)
        edit.addSeparator()
        edit.addAction("Settings", self.configure)

    def on_update_spacer_policy(self):
        """Atualiza a política do espaçador baseado na orientação da toolbar"""
        if self.toolbar.orientation() == Qt.Horizontal:
            # Horizontal: expande na largura
            self.toolbar_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            # Vertical: expande na altura
            self.toolbar_spacer.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def _open_file_in_text_editor(self, filepath):
        if os.name == "nt":  # Windows
            os.startfile(filepath)
        elif os.name == "posix":  # Linux/macOS
            subprocess.run(["xdg-open", filepath])

    def open_configure_editor(self):
        self._open_file_in_text_editor(CONFIG_PATH)

    def open_about(self):
        data = {
            "version": about.__version__,
            "package": about.__package__,
            "program_name": about.__program_name__,
            "author": about.__author__,
            "email": about.__email__,
            "description": about.__description__,
            "url_source": about.__url_source__,
            "url_doc": about.__url_doc__,
            "url_funding": about.__url_funding__,
            "url_bugs": about.__url_bugs__,
        }
        show_about_window(data, self.icon_path)

    def on_coffee_action_click(self):
        QDesktopServices.openUrl(QUrl("https://ko-fi.com/trucomanx"))

    def edit_clipboard(self, operation):
        ed = self.editor
        if ed:
            getattr(ed, operation)()

    def add_editor(self, path=None, text=""):
        ed = EditorWithGutter(self.settings)
        self.editors[ed] = str(Path(path).resolve()) if path else None
        ed.sourceChanged.connect(self.update_position)
        ed.rightClicked.connect(self.sync_source_to_pdf_at)
        ed.setContextMenuPolicy(Qt.PreventContextMenu)
        ed.textChanged.connect(lambda e=ed: self.update_tab_label(e))
        ed.setPlainText(text)
        ed.document().setModified(False)
        if path:
            self.watch_file(self.editors[ed])
        label = Path(path).name if path else "Untitled.tex"
        index = self.source_tabs.addTab(ed, label)
        self.source_tabs.setCurrentIndex(index)
        self.update_tab_label(ed)
        if path and Path(path).suffix.lower() == ".tex" and self.main_file is None:
            self.main_file = self.editors[ed]
            self.update_tab_label(ed)
            self.watch_main_pdf()
        self.refresh_title()
        return ed

    def update_tab_label(self, ed):
        if ed not in self.editors:
            return
        path = self.editors[ed]
        name = Path(path).name if path else "Untitled.tex"
        prefix = "★ " if path and path == self.main_file else ""
        suffix = " *" if ed.document().isModified() else ""
        idx = self.source_tabs.indexOf(ed)
        if idx >= 0:
            self.source_tabs.setTabText(idx, prefix + name + suffix)
        if ed is self.editor:
            self.refresh_title()

    def refresh_title(self):
        path = self.path
        title = Path(path).name if path else "Untitled.tex"
        modified = " *" if self.editor and self.editor.document().isModified() else ""
        main = Path(self.main_file).name if self.main_file else "no main file selected"
        self.setWindowTitle(f"{title}{modified} — Main: {main} — LaTeX Studio")

    def current_tab_changed(self, index):
        if self.editor:
            self.editor.setFocus()
            self.status.showMessage(
                f"File: {self.path or 'Untitled'} | Main: {self.main_file or 'not selected'}"
            )
        self.refresh_title()

    def maybe_save(self, ed):
        if not ed.document().isModified():
            return True
        self.source_tabs.setCurrentWidget(ed)
        ans = QMessageBox.question(
            self,
            "Unsaved changes",
            f"Save changes to {Path(self.editors[ed]).name if self.editors[ed] else 'untitled file'}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if ans == QMessageBox.Save:
            return self.save()
        return ans == QMessageBox.Discard

    def new_file(self):
        self.add_editor()

    def open_dialog(self):
        p, _ = QFileDialog.getOpenFileName(
            self,
            "Open LaTeX or bibliography file",
            "",
            "TeX and bibliography (*.tex *.bib);;LaTeX (*.tex);;Bibliography (*.bib);;All files (*)",
        )
        if p:
            self.open_file(p)

    def open_file(self, path):
        try:
            resolved = str(Path(path).resolve())
            for ed, existing in self.editors.items():
                if existing == resolved:
                    self.source_tabs.setCurrentWidget(ed)
                    return ed
            ed = self.add_editor(resolved, Path(resolved).read_text(encoding="utf-8"))
            self._signatures[resolved] = self.file_signature(resolved)
            self.status.showMessage(resolved)
            return ed
        except Exception as e:
            QMessageBox.critical(self, "Erro ao abrir", str(e))

    @staticmethod
    def file_signature(path):
        try:
            st = Path(path).stat()
            return (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            return None

    def watch_file(self, path):
        path = str(Path(path).resolve())
        self._signatures.setdefault(path, self.file_signature(path))
        if Path(path).exists() and path not in self.file_watcher.files():
            self.file_watcher.addPath(path)
        directory = str(Path(path).parent)
        if (
            Path(directory).exists()
            and directory not in self.file_watcher.directories()
        ):
            self.file_watcher.addPath(directory)

    def unwatch_source(self, path):
        if path == self._pdf_watch_path:
            return
        if path in self.file_watcher.files():
            self.file_watcher.removePath(path)
        self._signatures.pop(path, None)

    def watch_main_pdf(self):
        new_path = (
            str(Path(self.main_file).with_suffix(".pdf").resolve())
            if self.main_file
            else None
        )
        old_path = self._pdf_watch_path
        if old_path and old_path != new_path:
            if old_path in self.file_watcher.files():
                self.file_watcher.removePath(old_path)
            if old_path not in self.editors.values():
                self._signatures.pop(old_path, None)
        self._pdf_watch_path = new_path
        if new_path:
            self.watch_file(new_path)

    def queue_external_check(self, path):
        self._external_pending.add(str(Path(path).resolve()))
        self._external_timer.start(250)

    def queue_directory_check(self, directory):
        directory = str(Path(directory).resolve())
        for path in self._signatures:
            if str(Path(path).parent) == directory:
                self._external_pending.add(path)
        if self._pdf_watch_path and str(Path(self._pdf_watch_path).parent) == directory:
            self._external_pending.add(self._pdf_watch_path)
        if self._external_pending:
            self._external_timer.start(250)

    def check_external_changes(self):
        changed = list(self._external_pending)
        self._external_pending.clear()
        for path in changed:
            if (
                self.process
                and self.process.state() != QProcess.NotRunning
                and self.compiling_main_file
                and path
                == str(Path(self.compiling_main_file).with_suffix(".pdf").resolve())
            ):
                continue
            current = self.file_signature(path)
            previous = self._signatures.get(path)
            if current == previous:
                continue
            self._signatures[path] = current
            if current is None:
                self.status.showMessage(
                    f"Monitored file was removed or is unavailable: {path}", 6000
                )
                continue
            self.watch_file(path)
            ed = next(
                (item for item, source in self.editors.items() if source == path), None
            )
            if ed:
                answer = QMessageBox.question(
                    self,
                    "Source file changed",
                    f"{Path(path).name} was modified outside the editor. Would you like to reload it?\n\nReloading discards unsaved local changes.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    try:
                        self.source_tabs.setCurrentWidget(ed)
                        ed.setPlainText(Path(path).read_text(encoding="utf-8"))
                        ed.document().setModified(False)
                        self.update_tab_label(ed)
                        self.status.showMessage(f"Reloaded: {path}", 4000)
                    except Exception as ex:
                        QMessageBox.warning(self, "Reload failed", str(ex))
            elif path == self._pdf_watch_path:
                answer = QMessageBox.question(
                    self,
                    "PDF changed",
                    f"{Path(path).name} was modified outside the editor. Would you like to reload it in the preview?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if answer == QMessageBox.Yes:
                    try:
                        self.pdf_window.load_pdf(path)
                        self.show_pdf()
                    except Exception as ex:
                        QMessageBox.warning(self, "PDF reload failed", str(ex))

    def save(self):
        ed = self.editor
        if not ed:
            return False
        path = self.editors[ed]
        if not path:
            p, _ = QFileDialog.getSaveFileName(
                self,
                "Save file",
                "",
                "TeX and bibliography (*.tex *.bib);;LaTeX (*.tex);;Bibliography (*.bib)",
            )
            if not p:
                return False
            path = p if Path(p).suffix else p + ".tex"
            path = str(Path(path).resolve())
            self.editors[ed] = path
            if Path(path).suffix.lower() == ".tex" and self.main_file is None:
                self.main_file = path
        try:
            Path(path).write_text(ed.toPlainText(), encoding="utf-8")
            ed.document().setModified(False)
            self._signatures[path] = self.file_signature(path)
            self.watch_file(path)
            self.update_tab_label(ed)
            self.status.showMessage("Salvo: " + path, 3000)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Erro ao salvar", str(e))
            return False

    def set_current_as_main(self):
        path = self.path
        if not path or Path(path).suffix.lower() != ".tex":
            QMessageBox.information(
                self, "Main file", "Select a saved .tex tab to make it the main file."
            )
            return
        self.main_file = path
        for ed in self.editors:
            self.update_tab_label(ed)
        self.watch_main_pdf()
        pdf = str(Path(path).with_suffix(".pdf"))
        if Path(pdf).exists():
            self.pdf_window.load_pdf(pdf)
        self.refresh_title()
        self.status.showMessage(f"Main file: {path}", 4000)

    def configure(self):
        d = SettingsDialog(self, self.settings)
        if d.exec_() == QDialog.Accepted:
            d.save()
            for ed in self.editors:
                ed.apply_appearance()
            self.status.showMessage("Settings applied", 2500)

    def show_pdf(self):
        if not self.pdf_window.isVisible():
            self.pdf_window.show()

    def activate_pdf(self):
        self.pdf_window.show()
        self.pdf_window.raise_()
        self.pdf_window.activateWindow()

    def compile(self):
        if not self.main_file:
            if self.path and Path(self.path).suffix.lower() == ".tex":
                self.set_current_as_main()
            else:
                QMessageBox.warning(
                    self,
                    "Main file",
                    "Open a .tex file and use 'Make Main File' before compiling.",
                )
                return
        if self.settings.value("auto_save", True):
            for ed in list(self.editors):
                if ed.document().isModified():
                    self.source_tabs.setCurrentWidget(ed)
                    if not self.save():
                        return
        self.compiling_main_file = self.main_file
        if self.process and self.process.state() != QProcess.NotRunning:
            return
        tpl = self.settings.value("command", DEFAULTS["command"])
        base = Path(self.compiling_main_file).stem
        out = Path(self.compiling_main_file).parent
        cmd = (
            tpl.replace("%filename%", shlex.quote(Path(self.compiling_main_file).name))
            .replace("%basename%", shlex.quote(base))
            .replace("%directory%", shlex.quote(str(out)))
        )
        passes = int(self.settings.value("passes", 1))
        backend = self.settings.value("bibliography_backend", "none")
        if backend in ("bibtex", "biber"):
            # Standard sequence: LaTeX creates aux data, bibliography tool
            # creates the bibliography, then LaTeX resolves citations/refs.
            bib_cmd = f"{backend} {shlex.quote(base)}"
            run_cmd = f"{cmd} && {bib_cmd} && {cmd} && {cmd}"
            if passes > 1:
                run_cmd += (
                    f" && for i in $(seq 1 {passes-1}); do {cmd} || exit $?; done"
                )
        else:
            run_cmd = (
                cmd
                if passes == 1
                else f"for i in $(seq 1 {passes}); do {cmd} || exit $?; done"
            )
        self.log.clear()
        self.log.appendPlainText(
            f"Main file: {self.compiling_main_file}\n$ {run_cmd}\n"
        )
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(out))
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(
            lambda: self.log.insertPlainText(
                bytes(self.process.readAllStandardOutput()).decode(errors="replace")
            )
        )
        self.process.finished.connect(self.compile_finished)
        self.process.start("/bin/sh", ["-lc", run_cmd])
        self.status.showMessage("Compiling…")

    def compile_finished(self, code, status):
        self.log.appendPlainText(f"\nCompilation finished (exit code {code}).")
        pdf = str(Path(self.compiling_main_file).with_suffix(".pdf"))
        if code == 0 and Path(pdf).exists():
            resolved_pdf = str(Path(pdf).resolve())
            self._signatures[resolved_pdf] = self.file_signature(resolved_pdf)
            self._external_pending.discard(resolved_pdf)
            self.watch_main_pdf()
            self.pdf_window.load_pdf(pdf)
            self.show_pdf()
            self.status.showMessage("PDF compilado com sucesso", 5000)
        else:
            self.status.showMessage(
                "Compilation finished with errors; see the Build Output tab", 7000
            )

    def synctex(self, args):
        try:
            return subprocess.run(
                ["synctex"] + args, capture_output=True, text=True, timeout=5
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def pdf_clicked(self, page, x, y):
        if not self.main_file:
            return
        pdf = str(Path(self.main_file).with_suffix(".pdf"))
        if not Path(pdf).exists():
            self.status.showMessage(
                "Compile the document first to generate the PDF and SyncTeX data", 5000
            )
            return
        out = self.synctex(["edit", "-o", f"{page}:{x:.2f}:{y:.2f}:{pdf}"])
        m = re.search(
            r"Input:\s*(.+?)\s*\n.*?Line:\s*(\d+)(?:.*?Column:\s*(\d+))?", out, re.S
        )
        if m:
            src = Path(m.group(1).strip())
            ed = self.open_file(src)
            if ed:
                ed.go_to(int(m.group(2)), int(m.group(3) or 1))
                self.work_tabs.setCurrentWidget(self.source_tabs)
            self.status.showMessage(
                f"SyncTeX: page {page} → {src.name}, line {m.group(2)}"
            )
        else:
            self.status.showMessage(
                "SyncTeX could not find source here. Make sure the PDF was compiled with -synctex=1.",
                6000,
            )

    def sync_source_to_pdf_at(self, line, col):
        if not self.path:
            return
        self._pending_position = (self.path, line, col)
        self.sync_source_to_pdf()

    def update_position(self, line, col):
        ed = self.sender()
        path = self.editors.get(ed)
        self.status.showMessage(f"Line {line}, column {col}")
        if path:
            self._pending_position = (path, line, col)
        self._sync_timer.start(250)

    def sync_source_to_pdf(self):
        if not hasattr(self, "_pending_position") or not self.main_file:
            return
        source, line, col = self._pending_position
        if Path(source).suffix.lower() == ".bib":
            return
        pdf = str(Path(self.main_file).with_suffix(".pdf"))
        if not Path(pdf).exists():
            self.status.showMessage(
                "Compile with SyncTeX before navigating to the PDF", 5000
            )
            return
        out = self.synctex(
            ["view", "-i", f"{line}:{col}:{Path(source).resolve()}", "-o", pdf]
        )
        m = re.search(r"Page:\s*(\d+).*?x:\s*([\d.]+).*?y:\s*([\d.]+)", out, re.S)
        if m:
            if self.pdf_window.pdf_path != str(Path(pdf).resolve()):
                self.pdf_window.load_pdf(pdf)
            self.show_pdf()
            self.pdf_window.go_position(
                int(m.group(1)), float(m.group(2)), float(m.group(3))
            )
            self.pdf_window.statusBar().showMessage(
                f"SyncTeX: {Path(source).name}, line {line}, column {col} → page {m.group(1)}"
            )
        elif out:
            self.status.showMessage(
                "SyncTeX could not find a PDF position for this source location", 5000
            )
        else:
            self.status.showMessage(
                "Could not run synctex. Install SyncTeX and compile with -synctex=1.",
                6000,
            )

    def closeEvent(self, e):
        for ed in list(self.editors):
            if not self.maybe_save(ed):
                e.ignore()
                return
        self.pdf_window.close()
        e.accept()

    def close_tab(self, index):
        ed = self.source_tabs.widget(index)
        if not self.maybe_save(ed):
            return
        path = self.editors.pop(ed, None)
        if path:
            self.unwatch_source(path)
        if path == self.main_file:
            self.main_file = None
            self.watch_main_pdf()
        self.source_tabs.removeTab(index)
        ed.deleteLater()
        if self.source_tabs.count() == 0:
            self.new_file()
        for item in self.editors:
            self.update_tab_label(item)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(about.__package__)

    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

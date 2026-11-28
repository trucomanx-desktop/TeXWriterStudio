#!/usr/bin/env python3
"""PyQt5 LaTeX editor with SyncTeX source/PDF navigation."""

from __future__ import annotations

import json
import glob
import os
import re
import shutil
import shlex
import subprocess
import sys
import signal
import uuid
from pathlib import Path

from PyQt5.QtCore import (
    Qt, QProcess, QSettings, QTimer, QRect, QSize, QFileSystemWatcher, QProcessEnvironment, QUrl, pyqtSignal,
)
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QPainter, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QSyntaxHighlighter, QIcon, QDesktopServices,
)
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFontComboBox, QHBoxLayout, QLabel,
    QMainWindow, QInputDialog, QMessageBox, QPlainTextEdit, QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QSpinBox, QSplitter,
    QTabWidget, QTabBar, QTextEdit, QToolBar, QVBoxLayout, QWidget, QAction, QStatusBar, QSizePolicy, QMenu,
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

from tex_writer_studio.mimetype import ensure_mime_type

# ---------- Path to config file ----------
CONFIG_DIRECTORY = os.path.join(
    os.path.expanduser("~"), ".config", about.__package__
)
CONFIG_PATH = os.path.join(CONFIG_DIRECTORY, "config.json")
CODES_DIRECTORY = os.path.join(CONFIG_DIRECTORY, "codes")
TEMPLATES_DIRECTORY = os.path.join(CONFIG_DIRECTORY, "templates")

def initialize_user_resources():
    """Seed per-user code snippets and templates from packaged resources when empty."""
    os.makedirs(CONFIG_DIRECTORY, exist_ok=True)
    packaged_codes = resource_path("codes")
    packaged_templates = resource_path("data")

    if os.path.isdir(packaged_codes):
        os.makedirs(CODES_DIRECTORY, exist_ok=True)
        with os.scandir(CODES_DIRECTORY) as entries:
            codes_empty = next(entries, None) is None
        if codes_empty:
            shutil.copytree(packaged_codes, CODES_DIRECTORY, dirs_exist_ok=True)

    if os.path.isdir(packaged_templates):
        os.makedirs(TEMPLATES_DIRECTORY, exist_ok=True)
        with os.scandir(TEMPLATES_DIRECTORY) as entries:
            templates_empty = next(entries, None) is None
        if templates_empty:
            for template in Path(packaged_templates).glob("*.tex"):
                if template.is_file():
                    shutil.copy2(template, TEMPLATES_DIRECTORY)

initialize_user_resources()

DEFAULT_CONTENT = {
    "window_width": 1024,
    "window_height": 800,
    "font_family": "DejaVu Sans Mono",
    "font_size": 12,
    "editor_bg": "#1e1e1e",
    "editor_fg": "#d4d4d4",
    "gutter_bg": "#252526",
    "gutter_fg": "#858585",
    "selection_bg": "#264f78",
    "current_line": "#282828",
    "current_line_color": "#808080",
    "current_line_intensity": 10,
    "flash_duration_ms": 720,
    "command": "pdflatex -synctex=1 -interaction=nonstopmode -file-line-error %filename%",
    "passes": 1,
    "auto_save": True,
    "highlight_matching_brackets": True,
    "highlight_selected_occurrences": True,
    "highlight_current_line": True,
    "flash_pdf_source_line": True,
    "theme": "Dark",
    "pdf_zoom": 1.0,
    "bibliography_backend": "none",
    "ui": {
        "about_ok": "OK",
        "window_title": about.__program_name__,
        "editor_tooltip": "LaTeX source editor. Right-click for editing and SyncTeX actions.",
        "editor_go_to_pdf": "Go to this position in PDF",
        "cut": "Cut",
        "copy": "Copy",
        "paste": "Paste",
        "pdf_tooltip": "PDF preview. Use Ctrl + mouse wheel to change zoom.",
        "pdf_window_title": "PDF Preview — SyncTeX",
        "pdf_zoom_hint": "Ctrl + mouse wheel: zoom",
        "pdf_zoom_status": "{pages} page(s) — Ctrl + mouse wheel to zoom",
        "pdf_unavailable_title": "PDF unavailable",
        "pdf_unavailable_message": "Could not open the PDF. Install PyMuPDF.\n\n{error}",
        "terminal_tooltip": "Run shell commands in a persistent Bash session.",
        "terminal_prompt": "$",
        "terminal_clear": "Clear",
        "terminal_clear_tooltip": "Clear terminal output",
        "terminal_restart": "Restart shell",
        "terminal_restart_tooltip": "Restart the Bash session",
        "terminal_input_placeholder": "Enter a shell command…",
        "terminal_input_tooltip": "Type a command and press Enter. The shell keeps its current directory and environment.",
        "terminal_start_error": "Could not start /bin/bash.\n",
        "terminal_command_echo": "$ {command}\n",
        "terminal_shell_exit": "\n[Shell exited with code {code}]\n",
        "terminal_change_folder": "Change to current file folder",
        "terminal_pwd": "Show current folder (pwd)",
        "terminal_clear_output": "Clear terminal output",
        "settings_title": "Editor Settings",
        "settings_font": "Editor font",
        "settings_font_size": "Font size (Ctrl + mouse wheel)",
        "settings_indentation": "Indentation",
        "settings_indent_2_spaces": "2 spaces",
        "settings_indent_4_spaces": "4 spaces",
        "settings_indent_8_spaces": "8 spaces",
        "settings_indent_tab": "Tab character",
        "settings_theme": "Syntax theme",
        "settings_command": "Compile command",
        "settings_backend": "Bibliography tool",
        "settings_passes": "LaTeX passes",
        "settings_autosave": "Save automatically before compiling",
        "settings_matching_brackets": "Highlight matching brackets",
        "settings_selected_occurrences": "Highlight occurrences of selected text",
        "settings_current_line": "Highlight the current line",
        "settings_current_line_color": "Color",
        "settings_current_line_intensity": "Intensity",
        "settings_percent_suffix": " %",
        "settings_flash_pdf_line": "Flash the source line after a PDF jump",
        "settings_flash_duration": "Duration",
        "settings_milliseconds_suffix": " ms",
        "settings_color_editor_bg": "Editor background",
        "settings_color_editor_fg": "Editor text",
        "settings_color_gutter_bg": "Line number background",
        "settings_color_gutter_fg": "Line numbers",
        "settings_color_selection_bg": "Selection",
        "settings_choose_color": "Choose…",
        "terminal_title": "Terminal",
        #
        "toolbar_new_shortcut": "Ctrl+N",
        "toolbar_new_tooltip": "Create a new document",
        "toolbar_new": "New",
        #
        "toolbar_open_shortcut": "Ctrl+O",
        "toolbar_open_tooltip": "Open a document",
        "toolbar_open": "Open",
        #
        "toolbar_save_shortcut": "Ctrl+S",
        "toolbar_save_tooltip": "Save the current document",
        "toolbar_save": "Save",
        #
        "toolbar_make_main_shortcut": "Ctrl+Shift+M",
        "toolbar_make_main_tooltip": "Set the current tab as the main LaTeX file",
        "toolbar_make_main": "Make Main",
        #
        "toolbar_compile_shortcut": "F5",
        "toolbar_compile_tooltip": "Compile the main LaTeX file to PDF",
        "toolbar_compile": "Compile PDF",
        #
        "toolbar_view_pdf_shortcut": "Ctrl+Shift+P",
        "toolbar_view_pdf_tooltip": "Show the PDF preview",
        "toolbar_view_pdf": "View PDF",
        #
        "toolbar_settings_shortcut": "Ctrl+,",
        "toolbar_settings_tooltip": "Configure editor and compilation settings",
        "toolbar_settings": "Settings",
        "toolbar_code_title": "Code",
        "toolbar_open_codes_folder": "Codes folder",
        "toolbar_open_codes_folder_tooltip": "Open the user codes folder",
        "toolbar_open_templates_folder": "Templates folder",
        "toolbar_open_templates_folder_tooltip": "Open the user templates folder",
        "dialog_code_json_error_title": "Could not load code action",
        "dialog_code_json_error_template": "Could not load {filename}: {error}",
        #
        "toolbar_from_template": "From Template",
        "toolbar_from_template_tooltip": "Create a new document from a LaTeX template",
        #
        "toolbar_configure": "Configure",
        "toolbar_configure_tooltip": "Open the program GUI configuration file",
        #
        "toolbar_about": "About",
        "toolbar_about_tooltip": "About the program",
        #
        "toolbar_coffee": "Coffee",
        "toolbar_coffee_tooltip": "Buy me a coffee (TrucomanX)",
        #        
        "toolbar_title": "Main",
        #
        "dialog_template_title": "Choose a template",
        "dialog_template_prompt": "Select a template to create a new document:",
        "dialog_template_empty_title": "No templates found",
        "dialog_template_empty_message": "No .tex templates were found in your templates folder.",
        "shortcut_cut": "Ctrl+X",
        "shortcut_copy": "Ctrl+C",
        "shortcut_paste": "Ctrl+V",
        "action_cut": "Cut",
        "action_copy": "Copy",
        "action_paste": "Paste",
        "window_title_template": "{document}{modified} — Main: {main} — TeX Writer Studio",
        "dialog_unsaved_template": "Save changes to {filename}?",
        "dialog_open_title": "Open LaTeX or bibliography file",
        "dialog_open_filter": "TeX and bibliography (*.tex *.bib);;LaTeX (*.tex);;Bibliography (*.bib);;All files (*)",
        "status_opened_template": "{path}",
        "status_missing_file_template": "Monitored file was removed or is unavailable: {path}",
        "dialog_source_changed_template": "{filename} was modified outside the editor. Would you like to reload it?\n\nReloading discards unsaved local changes.",
        "dialog_pdf_changed_template": "{filename} was modified outside the editor. Would you like to reload it in the preview?",
        "status_saved_template": "Saved: {path}",
        "status_main_file_template": "Main file: {path}",
        "status_synctex_pdf_to_source_template": "SyncTeX: page {page} → {source}, line {line}",
        "status_cursor_template": "Line {line}, column {column}",
        "status_synctex_source_to_pdf_template": "SyncTeX: {source}, line {line}, column {column} → page {page}",
        "about_window_title": "About",
        "about_package_template": "Package: {value}",
        "about_program_template": "Program: {value}",
        "about_version_template": "Version: {value}",
        "about_author_template": "Author: {value}",
        "about_email_template": "Email: <a href=\"mailto:{value}\">{value}</a>",
        "about_source_template": "Source: <a href=\"{value}\">{value}</a>",
        "about_documentation_template": "Documentation: <a href=\"{value}\">{value}</a>",
        "about_funding_template": "Funding: <a href=\"{value}\">{value}</a>",
        "about_bugs_template": "Bugs: <a href=\"{value}\">{value}</a>",
        "dialog_yes": "Yes",
        "dialog_no": "No",
        "dialog_save": "Save",
        "dialog_discard": "Discard",
        "dialog_cancel": "Cancel",
        "settings_save": "Save",
        "settings_cancel": "Cancel",
        "backend_none": "None",
        "backend_bibtex": "BibTeX",
        "backend_biber": "Biber",
        "theme_names": ["Dark", "Light", "Solarized"],
        "main_toolbar_title": "Main",
        "tab_files": "Files",
        "tab_build_output": "Build Output",
        "build_error_item": "{file}:{line}: {message}",
        "build_error_fallback": "{file}: {message}",
        "menu_file": "File",
        "menu_edit": "Edit",
        "action_find": "Find",
        "action_replace": "Replace",
        "shortcut_find": "Ctrl+F",
        "shortcut_replace": "Ctrl+H",
        "search_dialog_title": "Find and Replace",
        "search_find_label": "Find",
        "search_replace_label": "Replace with",
        "search_find_placeholder": "Search text",
        "search_replace_placeholder": "Replacement text",
        "search_case_sensitive": "Case sensitive",
        "search_highlight_matches": "Highlight all matches",
        "search_find_next": "Find Next",
        "search_replace_one": "Replace",
        "search_replace_all": "Replace All",
        "search_close": "Close",
        "search_not_found": "No matching text was found",
        "search_replaced_count": "Replaced {count} occurrence(s)",
        "action_new": "New",
        "action_open": "Open",
        "action_save": "Save",
        "action_make_main": "Make Main",
        "action_compile": "Compile PDF",
        "action_view_pdf": "View PDF",
        "action_settings": "Settings",
        "menu_cut": "Cut",
        "menu_copy": "Copy",
        "menu_paste": "Paste",
        "untitled_file": "Untitled.tex",
        "main_file_missing": "no main file selected",
        "title_document": "{document}{modified} — Main: {main} — TeX Writer Studio",
        "status_current_file": "File: {path} | Main: {main}",
        "status_no_file": "Untitled",
        "dialog_unsaved_title": "Unsaved changes",
        "dialog_unsaved_message": "Save changes to {filename}?",
        "dialog_open_file": "Open LaTeX or bibliography file",
        "filter_open_file": "TeX and bibliography (*.tex *.bib);;LaTeX (*.tex);;Bibliography (*.bib);;All files (*)",
        "dialog_open_error_title": "Could not open file",
        "dialog_save_file": "Save file",
        "filter_save_file": "TeX and bibliography (*.tex *.bib);;LaTeX (*.tex);;Bibliography (*.bib)",
        "status_file_opened": "{path}",
        "status_monitored_missing": "Monitored file was removed or is unavailable: {path}",
        "dialog_source_changed_title": "Source file changed",
        "dialog_source_changed_message": "{filename} was modified outside the editor. Would you like to reload it?\n\nReloading discards unsaved local changes.",
        "status_file_reloaded": "Reloaded: {path}",
        "status_pdf_reloaded": "PDF preview updated: {filename}",
        "status_pdf_reload_retry": "The PDF is still being written; retrying the preview update…",
        "status_pdf_reload_failed": "Could not update the PDF preview: {error}",
        "dialog_reload_error_title": "Reload failed",
        "dialog_pdf_changed_title": "PDF changed",
        "dialog_pdf_changed_message": "{filename} was modified outside the editor. Would you like to reload it in the preview?",
        "dialog_pdf_reload_error_title": "PDF reload failed",
        "status_file_saved": "Saved: {path}",
        "dialog_save_error_title": "Could not save file",
        "dialog_main_file_title": "Main file",
        "dialog_select_main_file": "Select a saved .tex tab to make it the main file.",
        "status_main_file": "Main file: {path}",
        "status_settings_applied": "Settings applied",
        "dialog_compile_main_file": "Open a .tex file and use 'Make Main File' before compiling.",
        "dialog_compile_empty_untitled": "The current main tab is empty and has not been saved. Add text and save it before compiling.",
        "log_main_file": "Main file: {path}\n$ {command}\n",
        "status_compiling": "Compiling…",
        "log_compile_finished": "\nCompilation finished (exit code {code}).",
        "status_compile_success": "PDF compiled successfully",
        "status_compile_errors": "Compilation finished with errors; see the Build Output tab",
        "status_compile_before_sync": "Compile the document first to generate the PDF and SyncTeX data",
        "status_synctex_pdf_to_source": "SyncTeX: page {page} → {source}, line {line}",
        "status_synctex_missing_source": "SyncTeX could not find source here. Make sure the PDF was compiled with -synctex=1.",
        "status_cursor_position": "Line {line}, column {column}",
        "status_sync_before_compile": "Compile with SyncTeX before navigating to the PDF",
        "status_synctex_source_to_pdf": "SyncTeX: {source}, line {line}, column {column} → page {page}",
        "status_synctex_missing_position": "SyncTeX could not find a PDF position for this source location",
        "status_synctex_unavailable": "Could not run synctex. Install SyncTeX and compile with -synctex=1.",
        "dialog_button_yes": "Yes",
        "dialog_button_no": "No",
        "dialog_button_save": "Save",
        "dialog_button_discard": "Discard",
        "dialog_button_cancel": "Cancel",
        "dialog_save_title": "Save file",
        "dialog_save_filter": "TeX and bibliography (*.tex *.bib);;LaTeX (*.tex);;Bibliography (*.bib)",
        "log_compile_finished_template": "\nCompilation finished (exit code {code}).",
        "status_reloaded_template": "Reloaded: {path}",
        "about_description": about.__description__,
        "status_untitled": "Untitled",
        "status_current_file_template": "File: {path} | Main: {main}",
        "log_main_file_template": "Main file: {path}\n$ {command}\n",
        "tab_main_marker": "★ ",
        "tab_modified_marker": " *",
    },
}

configure.verify_default_config(CONFIG_PATH, default_content=DEFAULT_CONTENT)

CONFIG = configure.load_config(CONFIG_PATH)


def ui_text(key, **values):
    """Return a translatable/configurable GUI string from the user config."""
    return CONFIG["ui"][key].format(**values)


def setting_enabled(settings, key):
    value = settings.value(key, CONFIG[key])
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "0", "no", "off", "")


def ask_question(parent, title, message, buttons, default_button):
    """Show a question dialog using configurable labels for standard buttons."""
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Question)
    dialog.setWindowTitle(title)
    dialog.setText(message)
    dialog.setStandardButtons(buttons)
    button_labels = {
        QMessageBox.Yes: "dialog_button_yes",
        QMessageBox.No: "dialog_button_no",
        QMessageBox.Save: "dialog_button_save",
        QMessageBox.Discard: "dialog_button_discard",
        QMessageBox.Cancel: "dialog_button_cancel",
    }
    for button, key in button_labels.items():
        if dialog.button(button):
            dialog.button(button).setText(ui_text(key))
    dialog.setDefaultButton(dialog.button(default_button))
    return dialog.exec_()

# ---------------------------------------


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


class FileDropTabBar(QTabBar):
    fileDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if not urls:
            super().dropEvent(event)
            return
        for url in urls:
            self.fileDropped.emit(url.toLocalFile())
        event.acceptProposedAction()


class CodeEditor(QPlainTextEdit):
    sourceChanged = pyqtSignal(int, int)
    fileDropped = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setAcceptDrops(True)
        self.search_highlight_selections = []
        self._bracket_selections = []
        self._selected_occurrence_selections = []
        self._current_line_selections = []
        self._flash_line_number = None
        self._flash_visible = False
        self._flash_steps_remaining = 0
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(180)
        self._flash_timer.timeout.connect(self._advance_line_flash)
        self.highlighter = LatexHighlighter(
            self.document(), settings.value("theme", CONFIG["theme"])
        )
        self.setToolTip(ui_text("editor_tooltip"))
        self.setTabStopDistance(QFontMetrics(self.font()).horizontalAdvance(" ") * 4)
        self.cursorPositionChanged.connect(self.report_cursor)
        self.selectionChanged.connect(self.refresh_editor_decorations)
        self.apply_appearance()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if not urls:
            super().dropEvent(event)
            return
        for url in urls:
            self.fileDropped.emit(url.toLocalFile())
        event.acceptProposedAction()

    def _indent_text(self):
        return str(self.settings.value("indent_text", "    "))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            cursor = self.textCursor()
            indent = self._indent_text() or "    "
            removing = event.key() == Qt.Key_Backtab or bool(event.modifiers() & Qt.ShiftModifier)
            if not cursor.hasSelection():
                if removing:
                    cursor.movePosition(QTextCursor.StartOfLine)
                    line = cursor.block().text()
                    amount = len(indent) if line.startswith(indent) else (1 if line.startswith("\t") else min(4, len(line) - len(line.lstrip(" "))))
                    if amount:
                        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, amount)
                        cursor.removeSelectedText()
                else:
                    cursor.insertText(indent)
                self.setTextCursor(cursor)
                return
            doc = self.document()
            original_anchor, original_position = cursor.anchor(), cursor.position()
            start, end = sorted((original_anchor, original_position))
            first, last = doc.findBlock(start), doc.findBlock(end)
            if end > start and end == last.position():
                last = last.previous()
            changes = []
            block = first
            while block.isValid() and block.position() <= last.position():
                line = block.text()
                if removing:
                    amount = len(indent) if line.startswith(indent) else (1 if line.startswith("\t") else min(4, len(line) - len(line.lstrip(" "))))
                    if amount:
                        changes.append((block.position(), -amount, ""))
                else:
                    changes.append((block.position(), len(indent), indent))
                block = block.next()
            def shifted(position):
                for at, delta, _ in changes:
                    if delta > 0 and position >= at:
                        position += delta
                    elif delta < 0:
                        removed = -delta
                        if position >= at + removed:
                            position -= removed
                        elif position > at:
                            position = at
                return position
            new_anchor, new_position = shifted(original_anchor), shifted(original_position)
            cursor.beginEditBlock()
            for at, delta, inserted in reversed(changes):
                cursor.setPosition(at)
                if delta > 0:
                    cursor.insertText(inserted)
                else:
                    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, -delta)
                    cursor.removeSelectedText()
            cursor.endEditBlock()
            cursor.setPosition(new_anchor)
            cursor.setPosition(new_position, QTextCursor.KeepAnchor)
            self.setTextCursor(cursor)
            return
        super().keyPressEvent(event)
    def apply_appearance(self):
        family = self.settings.value("font_family", CONFIG["font_family"])
        size = int(self.settings.value("font_size", CONFIG["font_size"]))
        self.setFont(QFont(family, size))
        bg = self.settings.value("editor_bg", CONFIG["editor_bg"])
        fg = self.settings.value("editor_fg", CONFIG["editor_fg"])
        sel = self.settings.value("selection_bg", CONFIG["selection_bg"])
        self.setStyleSheet(
            f"QPlainTextEdit {{background:{bg}; color:{fg}; selection-background-color:{sel}; border:0;}}"
        )
        self.highlighter.set_theme(self.settings.value("theme", CONFIG["theme"]))
        self.highlighter.rehighlight()
        self.refresh_editor_decorations()

    def set_search_highlight_selections(self, selections):
        self.search_highlight_selections = selections
        self.apply_extra_selections()

    def _character_at(self, position):
        return self.document().characterAt(position)

    def _is_escaped_bracket(self, position):
        backslashes = 0
        scan = position - 1
        while scan >= 0 and self._character_at(scan) == "\\":
            backslashes += 1
            scan -= 1
        return backslashes % 2 == 1

    def _matching_bracket_position(self, position, bracket):
        pairs = {"{": "}", "(": ")"}
        reverse_pairs = {closing: opening for opening, closing in pairs.items()}
        document_end = self.document().characterCount() - 1

        if bracket in pairs:
            stack = [pairs[bracket]]
            for scan in range(position + 1, document_end):
                current = self._character_at(scan)
                if current not in "{}()" or self._is_escaped_bracket(scan):
                    continue
                if current in pairs:
                    stack.append(pairs[current])
                elif stack and current == stack[-1]:
                    stack.pop()
                    if not stack:
                        return scan
        elif bracket in reverse_pairs:
            stack = [reverse_pairs[bracket]]
            for scan in range(position - 1, -1, -1):
                current = self._character_at(scan)
                if current not in "{}()" or self._is_escaped_bracket(scan):
                    continue
                if current in reverse_pairs:
                    stack.append(reverse_pairs[current])
                elif stack and current == stack[-1]:
                    stack.pop()
                    if not stack:
                        return scan
        return None

    def _make_character_selection(self, position, background, foreground=None):
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(self.document())
        selection.cursor.setPosition(position)
        selection.cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
        selection.format.setBackground(QColor(background))
        if foreground:
            selection.format.setForeground(QColor(foreground))
        return selection

    def _refresh_bracket_selections(self):
        self._bracket_selections = []
        if not setting_enabled(self.settings, "highlight_matching_brackets"):
            return
        cursor = self.textCursor()
        if cursor.hasSelection() or cursor.position() <= 0:
            return
        position = cursor.position() - 1
        bracket = self._character_at(position)
        if bracket not in "{}()" or self._is_escaped_bracket(position):
            return
        matching_position = self._matching_bracket_position(position, bracket)
        if matching_position is None:
            return
        self._bracket_selections = [
            self._make_character_selection(position, "#725aa6", "#ffffff"),
            self._make_character_selection(matching_position, "#725aa6", "#ffffff"),
        ]

    def _refresh_selected_occurrence_selections(self):
        self._selected_occurrence_selections = []
        if not setting_enabled(self.settings, "highlight_selected_occurrences"):
            return
        selected_text = self.textCursor().selectedText()
        if not selected_text or "\n" in selected_text or "\u2029" in selected_text:
            return
        document = self.document()
        cursor = QTextCursor(document)
        while True:
            cursor = document.find(selected_text, cursor)
            if cursor.isNull():
                break
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setBackground(QColor("#4c9a91"))
            selection.format.setForeground(QColor("#ffffff"))
            self._selected_occurrence_selections.append(selection)
            next_cursor = QTextCursor(document)
            next_cursor.setPosition(cursor.selectionEnd())
            cursor = next_cursor

    def _refresh_current_line_selection(self):
        self._current_line_selections = []
        if not setting_enabled(self.settings, "highlight_current_line"):
            return
        background = QColor(self.settings.value("editor_bg", CONFIG["editor_bg"]))
        overlay = QColor(
            self.settings.value("current_line_color", CONFIG["current_line_color"])
        )
        intensity = max(
            0,
            min(100, int(self.settings.value("current_line_intensity", CONFIG["current_line_intensity"]))),
        )
        ratio = intensity / 100
        line_color = QColor(
            round(background.red() * (1 - ratio) + overlay.red() * ratio),
            round(background.green() * (1 - ratio) + overlay.green() * ratio),
            round(background.blue() * (1 - ratio) + overlay.blue() * ratio),
        )
        selection = QTextEdit.ExtraSelection()
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        selection.format.setBackground(line_color)
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        self._current_line_selections.append(selection)

    def refresh_editor_decorations(self, *_):
        self._refresh_bracket_selections()
        self._refresh_selected_occurrence_selections()
        self._refresh_current_line_selection()
        self.apply_extra_selections()

    def apply_extra_selections(self):
        selections = (
            self._current_line_selections
            + ([self._flash_selection()] if self._flash_visible else [])
            + self._bracket_selections
            + self._selected_occurrence_selections
            + self.search_highlight_selections
        )
        self.setExtraSelections(selections)

    def _flash_selection(self):
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(self.document())
        if self._flash_line_number is not None:
            block = self.document().findBlockByNumber(self._flash_line_number)
            if block.isValid():
                selection.cursor.setPosition(block.position())
        selection.format.setBackground(QColor("#b78d32"))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        return selection

    def flash_current_line(self):
        if not setting_enabled(self.settings, "flash_pdf_source_line"):
            return
        self._flash_line_number = self.textCursor().blockNumber()
        self._flash_visible = True
        self._flash_steps_remaining = 4
        duration = max(
            200,
            int(self.settings.value("flash_duration_ms", CONFIG["flash_duration_ms"])),
        )
        self._flash_timer.setInterval(max(50, duration // 4))
        self.apply_extra_selections()
        self._flash_timer.start()

    def _advance_line_flash(self):
        self._flash_visible = not self._flash_visible
        self._flash_steps_remaining -= 1
        if self._flash_steps_remaining <= 0:
            self._flash_timer.stop()
            self._flash_visible = False
            self._flash_line_number = None
        self.apply_extra_selections()
        if self._flash_steps_remaining > 0:
            self._flash_timer.start()

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
        self.refresh_editor_decorations()


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
            QColor(self.settings.value("gutter_bg", CONFIG["gutter_bg"])),
        )
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())
        p.setPen(QColor(self.settings.value("gutter_fg", CONFIG["gutter_fg"])))
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
        jump = menu.addAction(ui_text("editor_go_to_pdf"))
        jump.triggered.connect(self.emit_right_click_position)
        return menu

    def add_clipboard_actions(self, menu):
        selected = self.textCursor().hasSelection()
        cut = menu.addAction(ui_text("cut"))
        cut.setEnabled(selected)
        cut.triggered.connect(self.cut)
        copy = menu.addAction(ui_text("copy"))
        copy.setEnabled(selected)
        copy.triggered.connect(self.copy)
        paste = menu.addAction(ui_text("paste"))
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
        self.setToolTip(ui_text("pdf_tooltip"))

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
        self.last_pdf_error = ""
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render_pages)
        self.setWindowTitle(ui_text("pdf_window_title"))
        self.canvas = PdfCanvas()
        self.canvas.zoomChanged.connect(self.zoom_changed)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.setCentralWidget(self.scroll)
        self.setMinimumSize(600, 700)
        self.canvas.zoom = float(settings.value("pdf_zoom", CONFIG["pdf_zoom"]))
        self.statusBar().showMessage(ui_text("pdf_zoom_hint"))

    def load_pdf(self, path, show_error=True):
        try:
            import fitz

            new_document = fitz.open(path)
            if self.document:
                self.document.close()
            self.document = new_document
            self.pdf_path = str(Path(path).resolve())
            self.last_pdf_error = ""
            self.statusBar().showMessage(
                ui_text("pdf_zoom_status", pages=len(self.document))
            )
            self.render_pages()
            return True
        except Exception as ex:
            self.last_pdf_error = str(ex)
            if show_error:
                QMessageBox.warning(
                    self,
                    ui_text("pdf_unavailable_title"),
                    ui_text("pdf_unavailable_message", error=ex),
                )
            return False

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
        self.setToolTip(ui_text("terminal_tooltip"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(4)
        header = QHBoxLayout()
        title = QLabel(ui_text("terminal_title"))
        title.setStyleSheet("font-weight:bold")
        header.addWidget(title)
        header.addStretch()
        clear = QPushButton(ui_text("terminal_clear"))
        clear.setToolTip(ui_text("terminal_clear_tooltip"))
        clear.clicked.connect(lambda: self.output.clear())
        header.addWidget(clear)
        restart = QPushButton(ui_text("terminal_restart"))
        restart.setToolTip(ui_text("terminal_restart_tooltip"))
        restart.clicked.connect(self.start_shell)
        header.addWidget(restart)
        layout.addLayout(header)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)
        self.output.setFont(QFont(CONFIG["font_family"], CONFIG["font_size"]))
        self.output.setStyleSheet(
            "QPlainTextEdit {background:#111315;color:#d4d4d4;border:1px solid #444;}"
        )
        self.output.setContextMenuPolicy(Qt.CustomContextMenu)
        self.output.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(self.output, pos)
        )
        layout.addWidget(self.output, 1)
        row = QHBoxLayout()
        prompt = QLabel(ui_text("terminal_prompt"))
        prompt.setStyleSheet("color:#23d18b;font-weight:bold")
        row.addWidget(prompt)
        self.input = QLineEdit()
        self.input.setPlaceholderText(ui_text("terminal_input_placeholder"))
        self.input.setToolTip(ui_text("terminal_input_tooltip"))
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
            self.append_text(ui_text("terminal_start_error"), QColor("#f14c4c"))

    def submit(self):
        command = self.input.text()
        self.input.clear()
        self.run_command(command)

    def run_command(self, command):
        if not command.strip():
            return
        if not self.process or self.process.state() == QProcess.NotRunning:
            self.start_shell()
        self.append_text(
            ui_text("terminal_command_echo", command=command), QColor("#29b8db")
        )
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
        change_dir = menu.addAction(ui_text("terminal_change_folder"))
        change_dir.setEnabled(bool(getattr(self.window(), "path", None)))
        change_dir.triggered.connect(self.change_to_current_file_folder)
        pwd = menu.addAction(ui_text("terminal_pwd"))
        pwd.triggered.connect(lambda: self.run_command("pwd"))
        menu.addSeparator()
        if source_widget is self.input:
            selected = bool(self.input.selectedText())
            cut = menu.addAction(ui_text("cut"))
            cut.setEnabled(selected)
            cut.triggered.connect(self.input.cut)
            copy = menu.addAction(ui_text("copy"))
            copy.setEnabled(selected)
            copy.triggered.connect(self.input.copy)
            paste = menu.addAction(ui_text("paste"))
            paste.setEnabled(bool(QApplication.clipboard().text()))
            paste.triggered.connect(self.input.paste)
            menu.addSeparator()
        clear = menu.addAction(ui_text("terminal_clear_output"))
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
        self.append_text(
            ui_text("terminal_shell_exit", code=code), QColor("#e5e510")
        )
        self.input.setEnabled(False)


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle(ui_text("settings_title"))
        self.s = settings
        form = QFormLayout(self)
        self.font = QFontComboBox()
        self.font.setCurrentFont(
            QFont(settings.value("font_family", CONFIG["font_family"]))
        )
        self.size = QSpinBox()
        self.size.setRange(6, 48)
        self.size.setValue(int(settings.value("font_size", CONFIG["font_size"])))
        self.theme = QComboBox()
        self.theme.addItems(CONFIG["ui"]["theme_names"])
        saved_theme = {
            "Escuro": "Dark",
            "Claro": "Light",
            "Solarizado": "Solarized",
        }.get(settings.value("theme", CONFIG["theme"]), settings.value("theme", CONFIG["theme"]))
        self.theme.setCurrentText(saved_theme)
        self.indentation = QComboBox()
        for label, value in [
            (ui_text("settings_indent_2_spaces"), "  "),
            (ui_text("settings_indent_4_spaces"), "    "),
            (ui_text("settings_indent_8_spaces"), "        "),
            (ui_text("settings_indent_tab"), "\t"),
        ]:
            self.indentation.addItem(label, value)
        indent_index = self.indentation.findData(settings.value("indent_text", "    "))
        self.indentation.setCurrentIndex(max(0, indent_index))
        self.command = QTextEdit()
        self.command.setFixedHeight(70)
        self.command.setPlainText(settings.value("command", CONFIG["command"]))
        self.passes = QSpinBox()
        self.passes.setRange(1, 5)
        self.passes.setValue(int(settings.value("passes", CONFIG["passes"])))
        self.backend = QComboBox()
        self.backend.addItem(ui_text("backend_none"), "none")
        self.backend.addItem(ui_text("backend_bibtex"), "bibtex")
        self.backend.addItem(ui_text("backend_biber"), "biber")
        current = self.backend.findData(
            settings.value("bibliography_backend", CONFIG["bibliography_backend"])
        )
        self.backend.setCurrentIndex(max(0, current))
        self.autosave = QCheckBox(ui_text("settings_autosave"))
        self.autosave.setChecked(setting_enabled(settings, "auto_save"))
        self.highlight_matching_brackets = QCheckBox(
            ui_text("settings_matching_brackets")
        )
        self.highlight_matching_brackets.setChecked(
            setting_enabled(settings, "highlight_matching_brackets")
        )
        self.highlight_selected_occurrences = QCheckBox(
            ui_text("settings_selected_occurrences")
        )
        self.highlight_selected_occurrences.setChecked(
            setting_enabled(settings, "highlight_selected_occurrences")
        )
        self.highlight_current_line = QCheckBox(ui_text("settings_current_line"))
        self.highlight_current_line.setChecked(
            setting_enabled(settings, "highlight_current_line")
        )
        self.current_line_color = QColor(
            settings.value("current_line_color", CONFIG["current_line_color"])
        )
        self.current_line_color_button = QPushButtonColor(self.current_line_color.name())
        self.current_line_color_button.clicked.connect(self.pick_current_line_color)
        self.current_line_intensity = QSpinBox()
        self.current_line_intensity.setRange(0, 100)
        self.current_line_intensity.setSuffix(ui_text("settings_percent_suffix"))
        self.current_line_intensity.setValue(
            int(settings.value("current_line_intensity", CONFIG["current_line_intensity"]))
        )
        self.flash_pdf_source_line = QCheckBox(ui_text("settings_flash_pdf_line"))
        self.flash_pdf_source_line.setChecked(
            setting_enabled(settings, "flash_pdf_source_line")
        )
        self.flash_duration = QSpinBox()
        self.flash_duration.setRange(200, 5000)
        self.flash_duration.setSingleStep(100)
        self.flash_duration.setSuffix(ui_text("settings_milliseconds_suffix"))
        self.flash_duration.setValue(
            int(settings.value("flash_duration_ms", CONFIG["flash_duration_ms"]))
        )
        form.addRow(ui_text("settings_font"), self.font)
        form.addRow(ui_text("settings_font_size"), self.size)
        form.addRow(ui_text("settings_theme"), self.theme)
        form.addRow(ui_text("settings_indentation"), self.indentation)
        form.addRow(ui_text("settings_command"), self.command)
        form.addRow(ui_text("settings_backend"), self.backend)
        form.addRow(ui_text("settings_passes"), self.passes)
        form.addRow("", self.autosave)
        form.addRow("", self.highlight_matching_brackets)
        form.addRow("", self.highlight_selected_occurrences)
        current_line_options = QHBoxLayout()
        current_line_options.addWidget(self.highlight_current_line)
        current_line_options.addSpacing(12)
        current_line_options.addWidget(QLabel(ui_text("settings_current_line_color")))
        current_line_options.addWidget(self.current_line_color_button)
        current_line_options.addWidget(QLabel(ui_text("settings_current_line_intensity")))
        current_line_options.addWidget(self.current_line_intensity)
        current_line_options.addStretch(1)
        form.addRow("", current_line_options)
        flash_options = QHBoxLayout()
        flash_options.addWidget(self.flash_pdf_source_line)
        flash_options.addSpacing(12)
        flash_options.addWidget(QLabel(ui_text("settings_flash_duration")))
        flash_options.addWidget(self.flash_duration)
        flash_options.addStretch(1)
        form.addRow("", flash_options)
        self.highlight_current_line.toggled.connect(
            self.current_line_color_button.setEnabled
        )
        self.highlight_current_line.toggled.connect(
            self.current_line_intensity.setEnabled
        )
        self.current_line_color_button.setEnabled(self.highlight_current_line.isChecked())
        self.current_line_intensity.setEnabled(self.highlight_current_line.isChecked())
        self.flash_pdf_source_line.toggled.connect(self.flash_duration.setEnabled)
        self.flash_duration.setEnabled(self.flash_pdf_source_line.isChecked())
        self.color_buttons = {}
        for key, label in [
            ("editor_bg", ui_text("settings_color_editor_bg")),
            ("editor_fg", ui_text("settings_color_editor_fg")),
            ("gutter_bg", ui_text("settings_color_gutter_bg")),
            ("gutter_fg", ui_text("settings_color_gutter_fg")),
            ("selection_bg", ui_text("settings_color_selection_bg")),
        ]:
            b = QPushButtonColor(settings.value(key, CONFIG[key]))
            b.clicked.connect(lambda _, k=key, btn=b: self.pick_color(k, btn))
            self.color_buttons[key] = b
            form.addRow(label, b)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ui_text("dialog_button_save"))
        buttons.button(QDialogButtonBox.Cancel).setText(ui_text("dialog_button_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def pick_color(self, key, button):
        c = QColorDialog.getColor(QColor(self.s.value(key, CONFIG[key])), self)
        if c.isValid():
            self.s.setValue(key, c.name())
            button.setStyleSheet(f"background:{c.name()};padding:6px")

    def pick_current_line_color(self):
        color = QColorDialog.getColor(self.current_line_color, self)
        if color.isValid():
            self.current_line_color = color
            self.current_line_color_button.setStyleSheet(
                f"background:{color.name()};padding:6px"
            )

    def save(self):
        self.s.setValue("font_family", self.font.currentFont().family())
        self.s.setValue("font_size", self.size.value())
        self.s.setValue("theme", self.theme.currentText())
        self.s.setValue("indent_text", self.indentation.currentData())
        self.s.setValue("command", self.command.toPlainText().strip())
        self.s.setValue("passes", self.passes.value())
        self.s.setValue("bibliography_backend", self.backend.currentData())
        self.s.setValue("auto_save", self.autosave.isChecked())
        self.s.setValue(
            "highlight_matching_brackets",
            self.highlight_matching_brackets.isChecked(),
        )
        self.s.setValue(
            "highlight_selected_occurrences",
            self.highlight_selected_occurrences.isChecked(),
        )
        self.s.setValue("highlight_current_line", self.highlight_current_line.isChecked())
        self.s.setValue("flash_pdf_source_line", self.flash_pdf_source_line.isChecked())
        self.s.setValue("current_line_color", self.current_line_color.name())
        self.s.setValue("current_line_intensity", self.current_line_intensity.value())
        self.s.setValue("flash_duration_ms", self.flash_duration.value())


from PyQt5.QtWidgets import QPushButton


class QPushButtonColor(QPushButton):
    def __init__(self, color):
        super().__init__(ui_text("settings_choose_color"))
        self.setStyleSheet(f"background:{color};padding:6px")


class SearchReplaceDialog(QDialog):
    optionsChanged = pyqtSignal(str, bool, bool)
    findNextRequested = pyqtSignal(str, bool)
    replaceRequested = pyqtSignal(str, str, bool)
    replaceAllRequested = pyqtSignal(str, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(ui_text("search_dialog_title"))
        self.setModal(False)

        form = QFormLayout(self)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText(ui_text("search_find_placeholder"))
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText(ui_text("search_replace_placeholder"))
        self.case_sensitive = QCheckBox(ui_text("search_case_sensitive"))
        self.highlight_matches = QCheckBox(ui_text("search_highlight_matches"))
        self.highlight_matches.setChecked(True)

        form.addRow(ui_text("search_find_label"), self.find_input)
        form.addRow(ui_text("search_replace_label"), self.replace_input)
        form.addRow(self.case_sensitive)
        form.addRow(self.highlight_matches)

        buttons = QHBoxLayout()
        self.find_next_button = QPushButton(ui_text("search_find_next"))
        self.replace_button = QPushButton(ui_text("search_replace_one"))
        self.replace_all_button = QPushButton(ui_text("search_replace_all"))
        self.close_button = QPushButton(ui_text("search_close"))
        for button in (
            self.find_next_button,
            self.replace_button,
            self.replace_all_button,
            self.close_button,
        ):
            buttons.addWidget(button)
        form.addRow(buttons)

        self.find_input.textChanged.connect(self.emit_options)
        self.case_sensitive.toggled.connect(self.emit_options)
        self.highlight_matches.toggled.connect(self.emit_options)
        self.find_next_button.clicked.connect(self.request_find_next)
        self.replace_button.clicked.connect(self.request_replace)
        self.replace_all_button.clicked.connect(self.request_replace_all)
        self.close_button.clicked.connect(self.hide)
        self.find_input.returnPressed.connect(self.request_find_next)

    def emit_options(self, *_):
        self.optionsChanged.emit(
            self.find_input.text(),
            self.case_sensitive.isChecked(),
            self.highlight_matches.isChecked(),
        )

    def request_find_next(self):
        self.findNextRequested.emit(
            self.find_input.text(), self.case_sensitive.isChecked()
        )

    def request_replace(self):
        self.replaceRequested.emit(
            self.find_input.text(),
            self.replace_input.text(),
            self.case_sensitive.isChecked(),
        )

    def request_replace_all(self):
        self.replaceAllRequested.emit(
            self.find_input.text(),
            self.replace_input.text(),
            self.case_sensitive.isChecked(),
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(about.__package__, "Editor")
        saved_directory = self.settings.value("last_open_directory", str(Path.home()))
        self.last_open_directory = (
            str(Path(saved_directory).expanduser())
            if Path(saved_directory).expanduser().is_dir()
            else str(Path.home())
        )
        self.pdf_window = PdfWindow(self.settings)
        self.process = None
        self.main_file = None
        self.compiling_main_file = None
        self.editors = {}
        self._signatures = {}
        self._external_pending = set()
        self._pdf_watch_path = None
        self._pdf_reload_attempts = 0
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.fileChanged.connect(self.queue_external_check)
        self.file_watcher.directoryChanged.connect(self.queue_directory_check)
        self._external_timer = QTimer(self)
        self._external_timer.setSingleShot(True)
        self._external_timer.timeout.connect(self.check_external_changes)

        self.setWindowTitle(ui_text("window_title"))
        self.resize(CONFIG["window_width"], CONFIG["window_height"])

        ## Icon
        # Get base directory for icons
        self.icon_path = resource_path("icons", "logo.png")
        self.setWindowIcon(QIcon(self.icon_path))

        self.source_tabs = QTabWidget()
        self.source_tab_bar = FileDropTabBar(self.source_tabs)
        self.source_tabs.setTabBar(self.source_tab_bar)
        self.source_tab_bar.fileDropped.connect(self.open_file)
        self.source_tabs.setTabsClosable(True)
        self.source_tabs.currentChanged.connect(self.current_tab_changed)
        self.source_tabs.tabCloseRequested.connect(self.close_tab)
        self.search_dialog = SearchReplaceDialog(self)
        self.search_dialog.optionsChanged.connect(self.refresh_search_highlights)
        self.search_dialog.findNextRequested.connect(self.find_next)
        self.search_dialog.replaceRequested.connect(self.replace_one)
        self.search_dialog.replaceAllRequested.connect(self.replace_all)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.error_list = QListWidget()
        self.error_list.itemClicked.connect(self.open_build_error)
        build_output = QWidget()
        build_layout = QVBoxLayout(build_output)
        build_layout.setContentsMargins(0, 0, 0, 0)
        build_layout.addWidget(self.log, 4)
        build_layout.addWidget(self.error_list, 1)
        self.work_tabs = QTabWidget()
        self.work_tabs.addTab(self.source_tabs, ui_text("tab_files"))
        self.work_tabs.addTab(build_output, ui_text("tab_build_output"))
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
        self.create_actions_codes()
        self.toolbar.setObjectName("mainToolbar")
        self.code_toolbar.setObjectName("codeToolbar")
        saved_toolbar_state = self.settings.value("toolbar_state")
        if saved_toolbar_state:
            self.restoreState(saved_toolbar_state)
        if not self.settings.value("code_toolbar_position_initialized", False, type=bool):
            self.addToolBar(Qt.RightToolBarArea, self.code_toolbar)
            self.code_toolbar.setOrientation(Qt.Vertical)
            self.settings.setValue("toolbar_state", self.saveState())
            self.settings.setValue("code_toolbar_position_initialized", True)
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
        self.toolbar = self.addToolBar(ui_text("toolbar_title"))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        
        # New
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "new_file.png")),
            ui_text("toolbar_new"),
            ui_text("toolbar_new_tooltip"),
            ui_text("toolbar_new_shortcut"),
            self.new_file,
        )

        # From tempalte
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "new_file.png")),
            ui_text("toolbar_from_template"),
            ui_text("toolbar_from_template_tooltip"),
            None,
            self.create_from_template,
        )

        # open
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "open_file.png")),
            ui_text("toolbar_open"),
            ui_text("toolbar_open_tooltip"),
            ui_text("toolbar_open_shortcut"),
            self.open_dialog,
        )
        
        # Save
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "media-flash.png")),
            ui_text("toolbar_save"),
            ui_text("toolbar_save_tooltip"),
            ui_text("toolbar_save_shortcut"),
            self.save,
        )
        
        # make main
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "go-home.svg")),
            ui_text("toolbar_make_main"),
            ui_text("toolbar_make_main_tooltip"),
            ui_text("toolbar_make_main_shortcut"),
            self.set_current_as_main,
        )
        
        # Compile
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "system-run.svg")),
            ui_text("toolbar_compile"),
            ui_text("toolbar_compile_tooltip"),
            ui_text("toolbar_compile_shortcut"),
            self.compile,
        )

        # Show PDF
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "pdf1.svg")),
            ui_text("toolbar_view_pdf"),
            ui_text("toolbar_view_pdf_tooltip"),
            ui_text("toolbar_view_pdf_shortcut"),
            self.activate_pdf,
        )

        # Properties
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "document-page-setup.png")),
            ui_text("toolbar_settings"),
            ui_text("toolbar_settings_tooltip"),
            ui_text("toolbar_settings_shortcut"),
            self.configure,
        )


        # Adicionar o espaçador
        self.toolbar_spacer = QWidget()
        self.toolbar_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toolbar.addWidget(self.toolbar_spacer)

        self.action(
            self.toolbar,
            QIcon.fromTheme("folder-open"),
            ui_text("toolbar_open_codes_folder"),
            ui_text("toolbar_open_codes_folder_tooltip"),
            None,
            lambda: self.open_user_folder(CODES_DIRECTORY),
        )
        self.action(
            self.toolbar,
            QIcon.fromTheme("folder-open"),
            ui_text("toolbar_open_templates_folder"),
            ui_text("toolbar_open_templates_folder_tooltip"),
            None,
            lambda: self.open_user_folder(TEMPLATES_DIRECTORY),
        )

        # Configure
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "text-configure.png")),
            ui_text("toolbar_configure"),
            ui_text("toolbar_configure_tooltip"),
            None,
            self.open_configure_editor,
        )

        # About
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "status_help.png")),
            ui_text("toolbar_about"),
            ui_text("toolbar_about_tooltip"),
            None,
            self.open_about,
        )

        #
        self.action(
            self.toolbar,
            QIcon(resource_path("icons", "emote-love.png")),
            ui_text("toolbar_coffee"),
            ui_text("toolbar_coffee_tooltip"),
            None,
            self.on_coffee_action_click,
        )

        # Conectar ao sinal de mudança de orientação
        self.toolbar.orientationChanged.connect(self.on_update_spacer_policy)
        self.on_update_spacer_policy()

        m = self.menuBar().addMenu(ui_text("menu_file"))
        for a in self.toolbar.actions()[:5]:
            m.addAction(a)
        edit = self.menuBar().addMenu(ui_text("menu_edit"))
        for label, shortcut, method in (
            (ui_text("action_cut"), ui_text("shortcut_cut"), "cut"),
            (ui_text("action_copy"), ui_text("shortcut_copy"), "copy"),
            (ui_text("action_paste"), ui_text("shortcut_paste"), "paste"),
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
        find_action = QAction(ui_text("action_find"), self)
        find_action.setShortcut(ui_text("shortcut_find"))
        find_action.triggered.connect(
            lambda checked=False: self.show_search_dialog()
        )
        self.addAction(find_action)
        edit.addAction(find_action)
        replace_action = QAction(ui_text("action_replace"), self)
        replace_action.setShortcut(ui_text("shortcut_replace"))
        replace_action.triggered.connect(
            lambda checked=False: self.show_search_dialog(focus_replace=True)
        )
        self.addAction(replace_action)
        edit.addAction(replace_action)
        edit.addSeparator()
        edit.addAction(ui_text("action_settings"), self.configure)

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

    def create_actions_codes(self):
        """Build code-insertion actions from JSON files in the codes folder."""
        self.code_toolbar = self.addToolBar(ui_text("toolbar_code_title"))
        self.code_toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        codes_directory = CODES_DIRECTORY

        for json_path in sorted(glob.glob(os.path.join(codes_directory, "*.json"))):
            try:
                with open(json_path, "r", encoding="utf-8") as code_file:
                    action_data = json.load(code_file)

                if not isinstance(action_data, dict):
                    raise ValueError("the JSON root must be an object")
                name = action_data.get("name")
                tooltip = action_data.get("tooltip")
                code = action_data.get("code")
                shortcut = action_data.get("shortcut")
                icon_name = action_data.get("icon")
                if not all(isinstance(value, str) for value in (name, tooltip, code)):
                    raise ValueError("'name', 'tooltip', and 'code' must be strings")
                if shortcut is not None and not isinstance(shortcut, str):
                    raise ValueError("'shortcut' must be a string or null")
                if icon_name is not None and not isinstance(icon_name, str):
                    raise ValueError("'icon' must be a filename or null")
            except (OSError, json.JSONDecodeError, ValueError) as error:
                QMessageBox.warning(
                    self,
                    ui_text("dialog_code_json_error_title"),
                    ui_text(
                        "dialog_code_json_error_template",
                        filename=Path(json_path).name,
                        error=error,
                    ),
                )
                continue

            icon = QIcon.fromTheme("insert-text")
            if icon_name:
                icon_path = os.path.join(codes_directory, icon_name)
                if os.path.isfile(icon_path):
                    icon = QIcon(icon_path)

            self.action(
                self.code_toolbar,
                icon,
                name,
                tooltip,
                shortcut,
                lambda checked=False, snippet=code: self.insert_code_snippet(snippet),
            )



    def open_user_folder(self, folder):
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def insert_code_snippet(self, snippet):
        editor = self.editor
        if editor is not None:
            snippet = snippet.replace("{{UUID}}", uuid.uuid4().hex[:12])
            editor.insertPlainText(snippet)
            editor.setFocus()

    def open_about(self):
        data = {
            "version": about.__version__,
            "package": about.__package__,
            "program_name": about.__program_name__,
            "author": about.__author__,
            "email": about.__email__,
            "description": ui_text("about_description"),
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
        ed.fileDropped.connect(self.open_file)
        self.editors[ed] = str(Path(path).resolve()) if path else None
        ed.sourceChanged.connect(self.update_position)
        ed.rightClicked.connect(self.sync_source_to_pdf_at)
        ed.setContextMenuPolicy(Qt.PreventContextMenu)
        ed.textChanged.connect(lambda e=ed: self.on_editor_text_changed(e))
        ed.setPlainText(text)
        ed.document().setModified(False)
        if path:
            self.watch_file(self.editors[ed])
        label = Path(path).name if path else ui_text("untitled_file")
        index = self.source_tabs.addTab(ed, label)
        self.source_tabs.setCurrentIndex(index)
        self.update_tab_label(ed)
        if path and Path(path).suffix.lower() == ".tex" and self.main_file is None:
            self.main_file = self.editors[ed]
            self.update_tab_label(ed)
            self.watch_main_pdf()
        self.refresh_title()
        return ed

    def on_editor_text_changed(self, ed):
        self.update_tab_label(ed)
        ed.refresh_editor_decorations()
        if ed is self.editor:
            self.refresh_search_highlights()

    def update_tab_label(self, ed):
        if ed not in self.editors:
            return
        path = self.editors[ed]
        name = Path(path).name if path else ui_text("untitled_file")
        prefix = ui_text("tab_main_marker") if path and path == self.main_file else ""
        suffix = ui_text("tab_modified_marker") if ed.document().isModified() else ""
        idx = self.source_tabs.indexOf(ed)
        if idx >= 0:
            self.source_tabs.setTabText(idx, prefix + name + suffix)
        if ed is self.editor:
            self.refresh_title()

    def refresh_title(self):
        path = self.path
        title = Path(path).name if path else ui_text("untitled_file")
        modified = ui_text("tab_modified_marker") if self.editor and self.editor.document().isModified() else ""
        main = Path(self.main_file).name if self.main_file else ui_text("main_file_missing")
        self.setWindowTitle(
            ui_text(
                "window_title_template",
                document=title,
                modified=modified,
                main=main,
            )
        )

    def current_tab_changed(self, index):
        if self.editor:
            self.editor.setFocus()
            self.status.showMessage(
                ui_text(
                    "status_current_file_template",
                    path=self.path or ui_text("status_untitled"),
                    main=self.main_file or ui_text("main_file_missing"),
                )
            )
        self.refresh_title()
        self.refresh_search_highlights()

    def show_search_dialog(self, focus_replace=False):
        editor = self.editor
        selected_text = editor.textCursor().selectedText() if editor else ""
        if selected_text and "\n" not in selected_text:
            self.search_dialog.find_input.setText(selected_text)
        self.search_dialog.show()
        self.search_dialog.raise_()
        self.search_dialog.activateWindow()
        target = (
            self.search_dialog.replace_input
            if focus_replace
            else self.search_dialog.find_input
        )
        target.setFocus()
        target.selectAll()

    def _search_flags(self, case_sensitive):
        flags = QTextDocument.FindFlags()
        if case_sensitive:
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def refresh_search_highlights(self, text=None, case_sensitive=None, enabled=None):
        editor = self.editor
        if editor is None:
            return
        if text is None:
            text = self.search_dialog.find_input.text()
        if case_sensitive is None:
            case_sensitive = self.search_dialog.case_sensitive.isChecked()
        if enabled is None:
            enabled = self.search_dialog.highlight_matches.isChecked()

        selections = []
        if text and enabled:
            document = editor.document()
            cursor = QTextCursor(document)
            flags = self._search_flags(case_sensitive)
            while True:
                cursor = document.find(text, cursor, flags)
                if cursor.isNull():
                    break
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setBackground(QColor("#f2c94c"))
                selection.format.setForeground(QColor("#1e1e1e"))
                selections.append(selection)
                next_cursor = QTextCursor(document)
                next_cursor.setPosition(cursor.selectionEnd())
                cursor = next_cursor
        editor.set_search_highlight_selections(selections)

    def find_next(self, text, case_sensitive=False):
        editor = self.editor
        if editor is None or not text:
            return
        flags = self._search_flags(case_sensitive)
        match = editor.document().find(text, editor.textCursor(), flags)
        if match.isNull():
            start = QTextCursor(editor.document())
            start.movePosition(QTextCursor.Start)
            match = editor.document().find(text, start, flags)
        if match.isNull():
            self.status.showMessage(ui_text("search_not_found"), 4000)
            return
        editor.setTextCursor(match)
        editor.setFocus()

    def replace_one(self, text, replacement, case_sensitive=False):
        editor = self.editor
        if editor is None or not text:
            return
        cursor = editor.textCursor()
        selected = cursor.selectedText()
        matches = selected == text if case_sensitive else selected.casefold() == text.casefold()
        if not matches:
            self.find_next(text, case_sensitive)
            return
        cursor.insertText(replacement)
        editor.setTextCursor(cursor)
        editor.setFocus()
        self.refresh_search_highlights()
        self.find_next(text, case_sensitive)

    def replace_all(self, text, replacement, case_sensitive=False):
        editor = self.editor
        if editor is None or not text:
            return
        document = editor.document()
        flags = self._search_flags(case_sensitive)
        cursor = QTextCursor(document)
        count = 0
        while True:
            cursor = document.find(text, cursor, flags)
            if cursor.isNull():
                break
            cursor.insertText(replacement)
            count += 1
            next_cursor = QTextCursor(document)
            next_cursor.setPosition(cursor.position())
            cursor = next_cursor
        self.refresh_search_highlights()
        if count:
            self.status.showMessage(
                ui_text("search_replaced_count", count=count), 5000
            )
        else:
            self.status.showMessage(ui_text("search_not_found"), 4000)

    def maybe_save(self, ed):
        if not ed.document().isModified():
            return True
        self.source_tabs.setCurrentWidget(ed)
        ans = ask_question(
            self,
            ui_text("dialog_unsaved_title"),
            ui_text(
                "dialog_unsaved_template",
                filename=(
                    Path(self.editors[ed]).name
                    if self.editors[ed]
                    else ui_text("status_untitled")
                ),
            ),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if ans == QMessageBox.Save:
            return self.save()
        return ans == QMessageBox.Discard

    def new_file(self):
        self.add_editor()

    def create_from_template(self):
        """Create an untitled editor tab populated from an installed template."""
        template_paths = sorted(
            glob.glob(os.path.join(TEMPLATES_DIRECTORY, "*.tex")),
            key=lambda path: Path(path).name.casefold(),
        )
        if not template_paths:
            QMessageBox.information(
                self,
                ui_text("dialog_template_empty_title"),
                ui_text("dialog_template_empty_message"),
            )
            return

        template_by_name = {Path(path).name: path for path in template_paths}
        template_name, accepted = QInputDialog.getItem(
            self,
            ui_text("dialog_template_title"),
            ui_text("dialog_template_prompt"),
            list(template_by_name),
            0,
            False,
        )
        if not accepted:
            return

        try:
            template_text = Path(template_by_name[template_name]).read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeError) as error:
            QMessageBox.warning(
                self, ui_text("dialog_open_error_title"), str(error)
            )
            return

        self.remove_empty_untitled_tabs()
        self.add_editor(text=template_text)

    def open_dialog(self):
        p, _ = QFileDialog.getOpenFileName(
            self,
            ui_text("dialog_open_title"),
            self.last_open_directory,
            ui_text("dialog_open_filter"),
        )
        if p:
            self.open_file(p)

    def remove_empty_untitled_tabs(self, exclude=None):
        """Remove untouched, empty tabs that have never been saved."""
        for index in range(self.source_tabs.count() - 1, -1, -1):
            ed = self.source_tabs.widget(index)
            if ed is exclude or self.editors.get(ed) is not None:
                continue
            if ed.toPlainText().strip() or ed.document().isModified():
                continue
            self.editors.pop(ed, None)
            self.source_tabs.removeTab(index)
            ed.deleteLater()

    def remember_open_directory(self, path):
        directory = str(Path(path).resolve().parent)
        self.last_open_directory = directory
        self.settings.setValue("last_open_directory", directory)

    def open_file(self, path):
        try:
            resolved = str(Path(path).resolve())
            for ed, existing in self.editors.items():
                if existing == resolved:
                    self.remember_open_directory(resolved)
                    self.remove_empty_untitled_tabs(exclude=ed)
                    self.source_tabs.setCurrentWidget(ed)
                    return ed
            file_text = Path(resolved).read_text(encoding="utf-8")
            self.remember_open_directory(resolved)
            self.remove_empty_untitled_tabs()
            ed = self.add_editor(resolved, file_text)
            self._signatures[resolved] = self.file_signature(resolved)
            self.status.showMessage(ui_text("status_opened_template", path=resolved))
            return ed
        except Exception as e:
            QMessageBox.critical(self, ui_text("dialog_open_error_title"), str(e))

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
            if current is None:
                self._signatures[path] = current
                self.status.showMessage(
                    ui_text("status_missing_file_template", path=path), 6000
                )
                continue
            self.watch_file(path)
            if path == self._pdf_watch_path:
                if self.pdf_window.load_pdf(path, show_error=False):
                    self._signatures[path] = current
                    self._pdf_reload_attempts = 0
                    self.show_pdf()
                    self.status.showMessage(
                        ui_text("status_pdf_reloaded", filename=Path(path).name),
                        5000,
                    )
                else:
                    self._pdf_reload_attempts += 1
                    if self._pdf_reload_attempts <= 5:
                        self._external_pending.add(path)
                        self._external_timer.start(350)
                        self.status.showMessage(
                            ui_text("status_pdf_reload_retry"), 2500
                        )
                    else:
                        self._signatures[path] = current
                        self._pdf_reload_attempts = 0
                        self.status.showMessage(
                            ui_text(
                                "status_pdf_reload_failed",
                                error=self.pdf_window.last_pdf_error,
                            ),
                            7000,
                        )
                continue

            self._signatures[path] = current
            ed = next(
                (item for item, source in self.editors.items() if source == path), None
            )
            if ed:
                answer = ask_question(
                    self,
                    ui_text("dialog_source_changed_title"),
                    ui_text(
                        "dialog_source_changed_template",
                        filename=Path(path).name,
                    ),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    try:
                        self.source_tabs.setCurrentWidget(ed)
                        ed.setPlainText(Path(path).read_text(encoding="utf-8"))
                        ed.document().setModified(False)
                        self.update_tab_label(ed)
                        self.status.showMessage(
                            ui_text("status_reloaded_template", path=path), 4000
                        )
                    except Exception as ex:
                        QMessageBox.warning(
                            self, ui_text("dialog_reload_error_title"), str(ex)
                        )

    def save(self):
        ed = self.editor
        if not ed:
            return False
        path = self.editors[ed]
        if not path:
            p, _ = QFileDialog.getSaveFileName(
                self,
                ui_text("dialog_save_title"),
                self.last_open_directory,
                ui_text("dialog_save_filter"),
            )
            if not p:
                return False
            path = p if Path(p).suffix else p + ".tex"
            path = str(Path(path).resolve())
            self.remember_open_directory(path)
            self.editors[ed] = path
            if Path(path).suffix.lower() == ".tex" and self.main_file is None:
                self.main_file = path
        try:
            Path(path).write_text(ed.toPlainText(), encoding="utf-8")
            self.remember_open_directory(path)
            ed.document().setModified(False)
            self._signatures[path] = self.file_signature(path)
            self.watch_file(path)
            self.update_tab_label(ed)
            self.status.showMessage(
                ui_text("status_saved_template", path=path), 3000
            )
            return True
        except Exception as e:
            QMessageBox.critical(self, ui_text("dialog_save_error_title"), str(e))
            return False

    def set_current_as_main(self):
        path = self.path
        if not path or Path(path).suffix.lower() != ".tex":
            QMessageBox.information(
                self,
                ui_text("dialog_main_file_title"),
                ui_text("dialog_select_main_file"),
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
        self.status.showMessage(
            ui_text("status_main_file_template", path=path), 4000
        )

    def configure(self):
        d = SettingsDialog(self, self.settings)
        if d.exec_() == QDialog.Accepted:
            d.save()
            for ed in self.editors:
                ed.apply_appearance()
            self.refresh_search_highlights()
            self.status.showMessage(ui_text("status_settings_applied"), 2500)

    def show_pdf(self):
        if not self.pdf_window.isVisible():
            self.pdf_window.show()

    def activate_pdf(self):
        self.pdf_window.show()
        self.pdf_window.raise_()
        self.pdf_window.activateWindow()

    def compile(self):
        if not self.main_file:
            current_editor = self.editor
            if (
                current_editor
                and self.editors.get(current_editor) is None
                and not current_editor.toPlainText().strip()
            ):
                QMessageBox.warning(
                    self,
                    ui_text("dialog_main_file_title"),
                    ui_text("dialog_compile_empty_untitled"),
                )
                return
            if self.path and Path(self.path).suffix.lower() == ".tex":
                self.set_current_as_main()
            else:
                QMessageBox.warning(
                    self,
                    ui_text("dialog_main_file_title"),
                    ui_text("dialog_compile_main_file"),
                )
                return
        if self.settings.value("auto_save", CONFIG["auto_save"]):
            for ed in list(self.editors):
                if ed.document().isModified():
                    self.source_tabs.setCurrentWidget(ed)
                    if not self.save():
                        return
        self.compiling_main_file = self.main_file
        if self.process and self.process.state() != QProcess.NotRunning:
            return
        tpl = self.settings.value("command", CONFIG["command"])
        base = Path(self.compiling_main_file).stem
        out = Path(self.compiling_main_file).parent
        cmd = (
            tpl.replace("%filename%", shlex.quote(Path(self.compiling_main_file).name))
            .replace("%basename%", shlex.quote(base))
            .replace("%directory%", shlex.quote(str(out)))
        )
        passes = int(self.settings.value("passes", CONFIG["passes"]))
        backend = self.settings.value(
            "bibliography_backend", CONFIG["bibliography_backend"]
        )
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
        self.error_list.clear()
        self.log.appendPlainText(
            ui_text(
                "log_main_file_template",
                path=self.compiling_main_file,
                command=run_cmd,
            )
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
        self.status.showMessage(ui_text("status_compiling"))

    def compile_finished(self, code, status):
        self.log.appendPlainText(ui_text("log_compile_finished_template", code=code))
        self.collect_build_errors()
        pdf = str(Path(self.compiling_main_file).with_suffix(".pdf"))
        if code == 0 and Path(pdf).exists():
            resolved_pdf = str(Path(pdf).resolve())
            self._signatures[resolved_pdf] = self.file_signature(resolved_pdf)
            self._external_pending.discard(resolved_pdf)
            self.watch_main_pdf()
            self.pdf_window.load_pdf(pdf)
            self.show_pdf()
            self.status.showMessage(ui_text("status_compile_success"), 5000)
        else:
            self.work_tabs.setCurrentWidget(self.work_tabs.widget(1))
            self.status.showMessage(
                ui_text("status_compile_errors"), 7000
            )

    def collect_build_errors(self):
        """Extract clickable file/line diagnostics from common LaTeX log formats."""
        lines = self.log.toPlainText().splitlines()
        pending_message = None
        pending_file = self.compiling_main_file
        seen = set()
        file_line_error = re.compile(r"^(.+?):(\d+):\s*(.+?)\s*$")
        latex_line = re.compile(r"^l\.(\d+)\s*(.*)$")
        for line in lines:
            match = file_line_error.match(line.strip())
            if match:
                message = match.group(3)
                normalized = message.lower()
                if any(word in normalized for word in (
                    "error", "undefined", "missing", "runaway", "emergency",
                    "fatal", "not found", "cannot",
                )):
                    self.add_build_error(match.group(1), int(match.group(2)), message, seen)
                continue
            stripped = line.strip()
            if stripped.startswith("!"):
                pending_message = stripped.lstrip("! ") or "LaTeX error"
            elif pending_message:
                location = latex_line.match(stripped)
                if location:
                    self.add_build_error(
                        pending_file, int(location.group(1)), pending_message, seen
                    )
                    pending_message = None

    def add_build_error(self, source_path, line, message, seen):
        if not source_path:
            return
        resolved = Path(source_path)
        if not resolved.is_absolute():
            resolved = Path(self.compiling_main_file).parent / resolved
        resolved = resolved.resolve()
        key = (str(resolved), line, message)
        if key in seen:
            return
        seen.add(key)
        item = QListWidgetItem(
            ui_text(
                "build_error_item",
                file=resolved.name,
                line=line,
                message=message,
            )
        )
        item.setData(Qt.UserRole, (str(resolved), line))
        self.error_list.addItem(item)

    def open_build_error(self, item):
        location = item.data(Qt.UserRole)
        if not location:
            return
        source_path, line = location
        editor = self.open_file(source_path)
        if editor:
            self.source_tabs.setCurrentWidget(editor)
            editor.go_to(line)
            self.work_tabs.setCurrentWidget(self.source_tabs)

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
                ui_text("status_compile_before_sync"), 5000
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
                ed.flash_current_line()
                self.work_tabs.setCurrentWidget(self.source_tabs)
            self.status.showMessage(
                ui_text(
                    "status_synctex_pdf_to_source_template",
                    page=page,
                    source=src.name,
                    line=m.group(2),
                )
            )
        else:
            self.status.showMessage(
                ui_text("status_synctex_missing_source"),
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
        self.status.showMessage(
            ui_text("status_cursor_template", line=line, column=col)
        )
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
                ui_text("status_sync_before_compile"), 5000
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
                ui_text(
                    "status_synctex_source_to_pdf_template",
                    source=Path(source).name,
                    line=line,
                    column=col,
                    page=m.group(1),
                )
            )
        elif out:
            self.status.showMessage(
                ui_text("status_synctex_missing_position"), 5000
            )
        else:
            self.status.showMessage(
                ui_text("status_synctex_unavailable"),
                6000,
            )

    def closeEvent(self, e):
        for ed in list(self.editors):
            if not self.maybe_save(ed):
                e.ignore()
                return
        self.settings.setValue("toolbar_state", self.saveState())
        self.settings.sync()
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
    
    signal.signal(signal.SIGINT, signal.SIG_DFL)
       
    ensure_mime_type("tex", "text/x-tex", "LaTeX document")
    icon_path = resource_path("icons", "logo.png")
    extras = "MimeType=text/x-tex;"
    
    create_desktop_directory()    
    create_desktop_menu()
    create_desktop_file(os.path.join("~",".local","share","applications"), 
                        program_name=about.__program_name__,
                        extras=extras,
                        icon_path=icon_path)
    
    for n in range(len(sys.argv)):
        if sys.argv[n] == "--autostart":
            create_desktop_directory(overwrite = True)
            create_desktop_menu(overwrite = True)
            create_desktop_file(os.path.join("~",".config","autostart"), 
                                overwrite=True, 
                                program_name=about.__program_name__,
                                extras=extras,
                                icon_path=icon_path)
            return
        if sys.argv[n] == "--applications":
            create_desktop_directory(overwrite = True)
            create_desktop_menu(overwrite = True)
            create_desktop_file(os.path.join("~",".local","share","applications"), 
                                overwrite=True, 
                                program_name=about.__program_name__,
                                extras=extras,
                                icon_path=icon_path)
            return
       
    app = QApplication(sys.argv)
    app.setApplicationName(about.__package__)

    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

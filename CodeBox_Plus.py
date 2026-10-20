#!/usr/bin/env python3
"""
CodeBox Nexus Studio
A broad-language desktop coding workspace with mandatory shared-account login and:
- Multi-tab editor, open/save files, syntax highlighting, find/replace
- Local project explorer
- Original gamified learning center
- GitHub repository listing, repository creation, and file upload
- Optional OS keyring secret storage
- AI Lab for Gemini and Groq with user-provided API keys
- Local terminal/file runner, vector logo, OAuth setup, SMTP email OTP
- Local project vault, Git initialization, and ZIP snapshots
- Separate Free and Plus build profiles; shared server account login and server-gated downloads

Install:
    py -m pip install PySide6 requests keyring pygments
Optional secure token storage:
    py -m pip install keyring

Run:
    py codebox.py

Build:
    py -m pip install pyinstaller
    py -m PyInstaller --noconfirm --windowed --onefile --name CodeBox codebox.py

GitHub actions use the official GitHub REST API. Use a fine-grained token with
only the repository permissions required for the operations you want. Never
share your token. This app does not provide a secure sandbox for running code.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import traceback
import urllib.parse
import hashlib
import hmac
import secrets
import smtplib
import ssl
import threading
import time
import webbrowser
import zipfile
import shutil
import tempfile
import subprocess
from datetime import datetime
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QDir, QSize, QProcess, QUrl
from PySide6.QtGui import (
    QAction, QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
    QTextCursor, QKeySequence, QPainter, QPen, QBrush, QLinearGradient, QPixmap, QIcon, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QPlainTextEdit, QTextEdit, QFileDialog,
    QMessageBox, QTreeView, QFileSystemModel, QToolBar, QStatusBar,
    QLabel, QPushButton, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QStackedWidget, QFrame, QFormLayout, QCheckBox, QDialog, QDialogButtonBox,
    QInputDialog, QProgressBar, QGroupBox, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView
)

APP_NAME = "CodeBox Nexus Studio"
ORG_NAME = "CodeBox"
DEFAULT_EDITION = "Free"
# Build label is replaced for the Free and Plus distributions below.
APP_BUILD_EDITION = "Plus"
ALLOW_PLUS_PREVIEW = False
AUTH_SESSION = {}
AUTH_API_BASE = os.environ.get("CODEBOX_API_URL", "http://127.0.0.1:8765")
GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


DARK_STYLE = """
QWidget { background: #10111b; color: #e8e9f3; font-size: 10pt; }
QMainWindow { background: #10111b; }
QFrame#Card, QGroupBox {
    background: #191b2a; border: 1px solid #2c2f46; border-radius: 12px;
}
QGroupBox { margin-top: 12px; padding: 12px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #a78bfa; }
QPushButton {
    background: #272a40; border: 1px solid #393d5a; border-radius: 8px;
    padding: 8px 12px; color: #f4f4fb;
}
QPushButton:hover { background: #343852; border-color: #8b5cf6; }
QPushButton#Primary { background: #7048e8; border-color: #8b5cf6; font-weight: bold; }
QPushButton#Primary:hover { background: #805cf0; }
QLineEdit, QComboBox, QSpinBox {
    background: #151725; border: 1px solid #34374f; border-radius: 7px;
    padding: 7px; selection-background-color: #7048e8;
}
QPlainTextEdit, QTextEdit {
    background: #0d0f17; color: #e5e7eb; border: 1px solid #2c3045;
    selection-background-color: #49348d; font-family: Consolas, 'Cascadia Code', monospace;
}
QListWidget, QTreeView, QTableWidget {
    background: #151725; border: 1px solid #2c3045; border-radius: 8px;
    alternate-background-color: #191b2a;
}
QListWidget::item { padding: 8px; border-radius: 5px; }
QListWidget::item:selected, QTreeView::item:selected { background: #49348d; }
QTabWidget::pane { border: 1px solid #2c3045; border-radius: 7px; }
QTabBar::tab { background: #191b2a; padding: 9px 14px; margin-right: 3px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #30234f; color: #d9c8ff; }
QToolBar { background: #151725; border: none; spacing: 6px; padding: 6px; }
QStatusBar { background: #151725; color: #b8bdd2; }
QProgressBar { border: 1px solid #34374f; border-radius: 6px; text-align: center; background: #151725; }
QProgressBar::chunk { background: #8b5cf6; border-radius: 5px; }
QHeaderView::section { background: #202338; padding: 7px; border: 0; }
QCheckBox { spacing: 8px; }
"""


class LogoWidget(QWidget):
    """An original vector logo drawn in Qt; no external image file is required."""
    def __init__(self, compact=False, parent=None):
        super().__init__(parent)
        self.compact = compact
        self.setMinimumHeight(58 if compact else 76)
        self.setMinimumWidth(150 if compact else 250)
        self.setMaximumHeight(84)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        size = min(46, h - 12)
        x, y = 7, (h-size)//2
        grad = QLinearGradient(x, y, x+size, y+size)
        grad.setColorAt(0.0, QColor("#8b5cf6"))
        grad.setColorAt(1.0, QColor("#06b6d4"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(x, y, size, size, 13, 13)
        painter.setPen(QPen(QColor("#ffffff"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.moveTo(x+17, y+13); path.lineTo(x+10, y+23); path.lineTo(x+17, y+33)
        path.moveTo(x+29, y+13); path.lineTo(x+36, y+23); path.lineTo(x+29, y+33)
        painter.drawPath(path)
        painter.setPen(QColor("#f3f4ff"))
        painter.setFont(QFont("Segoe UI", 14 if not self.compact else 12, QFont.Weight.Bold))
        text_x = x + size + 11
        painter.drawText(text_x, y+22, "CODEBOX")
        painter.setPen(QColor("#9ca3c8"))
        painter.setFont(QFont("Segoe UI", 7 if not self.compact else 6, QFont.Weight.DemiBold))
        painter.drawText(text_x+1, y+36, "ULTIMATE DEVELOPER STUDIO")
        painter.end()


class AIWorker(QThread):
    done = Signal(str, str)
    progress = Signal(str)

    def __init__(self, provider, api_key, model, prompt, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.prompt = prompt

    def run(self):
        if requests is None:
            self.done.emit("", "The requests package is missing. Install it with: py -m pip install requests")
            return
        try:
            self.progress.emit(f"Contacting {self.provider}…")
            if self.provider == "gemini":
                model = self.model.strip() or "gemini-2.5-flash"
                url = "https://generativelanguage.googleapis.com/v1beta/models/" + urllib.parse.quote(model, safe="") + ":generateContent"
                response = requests.post(url, params={"key": self.api_key}, json={
                    "contents": [{"role": "user", "parts": [{"text": self.prompt}]}],
                    "generationConfig": {"temperature": 0.3}
                }, timeout=90)
                if not response.ok:
                    try: msg = response.json().get("error", {}).get("message", response.text)
                    except Exception: msg = response.text
                    raise RuntimeError(f"Gemini returned HTTP {response.status_code}: {msg}")
                data = response.json()
                answer = "\n".join(p.get("text", "") for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", []) if p.get("text"))
            elif self.provider == "groq":
                model = self.model.strip() or "llama-3.3-70b-versatile"
                response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={
                    "Authorization": "Bearer " + self.api_key,
                    "Content-Type": "application/json"
                }, json={"model": model, "messages": [{"role": "user", "content": self.prompt}], "temperature": 0.3}, timeout=90)
                if not response.ok:
                    try: msg = response.json().get("error", {}).get("message", response.text)
                    except Exception: msg = response.text
                    raise RuntimeError(f"Groq returned HTTP {response.status_code}: {msg}")
                answer = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                raise RuntimeError("Unknown AI provider.")
            if not answer.strip():
                raise RuntimeError("The provider returned an empty response. Check the model name and API key.")
            self.done.emit(answer, "")
        except Exception as exc:
            self.done.emit("", str(exc))


class OAuthWorker(QThread):
    done = Signal(object, str)
    progress = Signal(str)

    def __init__(self, provider, client_id, client_secret="", parent=None):
        super().__init__(parent)
        self.provider = provider
        self.client_id = client_id.strip()
        self.client_secret = client_secret

    def run(self):
        if requests is None:
            self.done.emit(None, "The requests package is missing. Install it with: py -m pip install requests")
            return
        try:
            if self.provider == "github":
                self._github_device_flow()
            elif self.provider == "google":
                self._google_loopback_flow()
            else:
                raise RuntimeError("Unsupported sign-in provider.")
        except Exception as exc:
            self.done.emit(None, str(exc))

    def _github_device_flow(self):
        self.progress.emit("Requesting a GitHub device code…")
        headers = {"Accept": "application/json", "User-Agent": "CodeBox-Ultimate-X"}
        resp = requests.post("https://github.com/login/device/code", headers=headers,
                             data={"client_id": self.client_id, "scope": "read:user user:email repo"}, timeout=25)
        if not resp.ok:
            raise RuntimeError(f"GitHub device flow returned HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        device_code = data.get("device_code")
        user_code = data.get("user_code")
        verify_uri = data.get("verification_uri", "https://github.com/login/device")
        if not device_code or not user_code:
            raise RuntimeError(data.get("error_description") or "GitHub did not return a device code. Enable Device Flow in your OAuth App settings.")
        self.progress.emit(f"Open {verify_uri} and enter code: {user_code}")
        webbrowser.open(verify_uri)
        interval = max(5, int(data.get("interval", 5)))
        deadline = time.time() + int(data.get("expires_in", 900))
        while time.time() < deadline:
            time.sleep(interval)
            token_resp = requests.post("https://github.com/login/oauth/access_token", headers=headers, data={
                "client_id": self.client_id, "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
            }, timeout=25)
            token_data = token_resp.json()
            if token_data.get("access_token"):
                token = token_data["access_token"]
                self.progress.emit("GitHub approved. Loading profile…")
                user_resp = requests.get("https://api.github.com/user", headers={
                    "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION, "User-Agent": "CodeBox-Ultimate-X"
                }, timeout=25)
                if not user_resp.ok:
                    raise RuntimeError(f"GitHub profile lookup failed: HTTP {user_resp.status_code}")
                user = user_resp.json()
                self.done.emit({"provider": "github", "token": token, "user": user, "email": user.get("email", "")}, "")
                return
            err = token_data.get("error", "")
            if err == "authorization_pending":
                self.progress.emit(f"Waiting for approval in browser… code {user_code}")
                continue
            if err == "slow_down":
                interval += 5
                continue
            if err in ("access_denied", "expired_token"):
                raise RuntimeError(token_data.get("error_description") or f"GitHub authorization {err.replace('_', ' ')}.")
            if err:
                raise RuntimeError(token_data.get("error_description") or f"GitHub authorization error: {err}")
        raise RuntimeError("GitHub device code expired. Start sign-in again.")

    def _google_loopback_flow(self):
        state = secrets.token_urlsafe(24)
        result = {}
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(handler_self):
                parsed = urlparse(handler_self.path)
                params = parse_qs(parsed.query)
                result["state"] = params.get("state", [""])[0]
                result["code"] = params.get("code", [""])[0]
                result["error"] = params.get("error", [""])[0]
                body = ("<html><body style='font-family:Segoe UI;background:#10111b;color:#eee;padding:40px'>"
                        "<h2>CodeBox authentication response received</h2><p>You can close this tab and return to CodeBox.</p></body></html>").encode("utf-8")
                handler_self.send_response(200)
                handler_self.send_header("Content-Type", "text/html; charset=utf-8")
                handler_self.send_header("Content-Length", str(len(body)))
                handler_self.end_headers()
                handler_self.wfile.write(body)
            def log_message(self, *args):
                return
        server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
        server.timeout = 1
        redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
        auth_params = {"client_id": self.client_id, "redirect_uri": redirect_uri,
                       "response_type": "code", "scope": "openid email profile", "state": state,
                       "access_type": "online", "prompt": "select_account"}
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(auth_params)
        self.progress.emit("Opening Google sign-in in your browser…")
        webbrowser.open(auth_url)
        try:
            deadline = time.time() + 240
            while time.time() < deadline and not result:
                server.handle_request()
            if not result:
                raise RuntimeError("Google sign-in timed out. Check OAuth client settings and try again.")
        finally:
            server.server_close()
        if result.get("state") != state:
            raise RuntimeError("OAuth state validation failed. Sign-in was stopped for safety.")
        if result.get("error"):
            raise RuntimeError("Google sign-in was cancelled or denied: " + result["error"])
        if not result.get("code"):
            raise RuntimeError("Google did not return an authorization code.")
        self.progress.emit("Exchanging Google authorization code…")
        token_resp = requests.post("https://oauth2.googleapis.com/token", data={
            "code": result["code"], "client_id": self.client_id,
            "client_secret": self.client_secret, "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }, timeout=25)
        if not token_resp.ok:
            raise RuntimeError(f"Google token exchange failed: HTTP {token_resp.status_code}: {token_resp.text[:400]}")
        access = token_resp.json().get("access_token")
        if not access:
            raise RuntimeError("Google did not return an access token.")
        user_resp = requests.get("https://openidconnect.googleapis.com/v1/userinfo",
                                 headers={"Authorization": "Bearer " + access}, timeout=25)
        if not user_resp.ok:
            raise RuntimeError("Google profile lookup failed.")
        user = user_resp.json()
        self.done.emit({"provider": "google", "token": "", "user": user,
                        "email": user.get("email", "")}, "")


class EmailSendWorker(QThread):
    done = Signal(bool, str)
    def __init__(self, smtp_host, smtp_port, smtp_user, smtp_password, sender, recipient, code, parent=None):
        super().__init__(parent)
        self.smtp_host, self.smtp_port = smtp_host, int(smtp_port)
        self.smtp_user, self.smtp_password = smtp_user, smtp_password
        self.sender, self.recipient, self.code = sender, recipient, code
    def run(self):
        try:
            msg = EmailMessage()
            msg["Subject"] = "Your CodeBox sign-in code"
            msg["From"] = self.sender
            msg["To"] = self.recipient
            msg.set_content(f"Your CodeBox verification code is: {self.code}\n\nIt expires in 5 minutes. If you did not request it, ignore this email.")
            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=20, context=ssl.create_default_context()) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as server:
                    server.ehlo(); server.starttls(context=ssl.create_default_context()); server.ehlo()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            self.done.emit(True, "Verification code sent.")
        except Exception as exc:
            self.done.emit(False, str(exc))


class CodeHighlighter(QSyntaxHighlighter):
    """Pygments-backed highlighting for hundreds of lexer names, with a safe fallback."""
    def __init__(self, document, language=""):
        super().__init__(document)
        self.language = (language or "text").lower()
        self.pygments_lexer = None
        self._pygments_lex = None
        try:
            from pygments import lex
            from pygments.lexers import get_lexer_by_name, TextLexer
            aliases = {
                "js": "javascript", "ts": "typescript", "jsx": "jsx", "tsx": "tsx",
                "py": "python", "c++": "cpp", "c#": "csharp", "cs": "csharp",
                "shell": "bash", "sh": "bash", "ps1": "powershell", "yml": "yaml",
                "dockerfile": "docker", "makefile": "make", "md": "markdown",
                "h": "c", "hpp": "cpp", "m": "objective-c", "mm": "objective-c++",
                "kt": "kotlin", "kts": "kotlin", "rs": "rust", "golang": "go",
                "ex": "elixir", "exs": "elixir", "erl": "erlang", "hrl": "erlang",
                "pl": "perl", "pm": "perl", "r": "r", "R": "r", "jl": "julia",
                "sol": "solidity", "tf": "terraform", "toml": "toml", "graphql": "graphql",
                "proto": "proto", "vue": "html", "svelte": "html"
            }
            alias_name = aliases.get(self.language, self.language)
            try:
                self.pygments_lexer = get_lexer_by_name(alias_name, stripall=False)
            except Exception:
                self.pygments_lexer = TextLexer()
            self._pygments_lex = lex
        except Exception:
            self.pygments_lexer = None
        self.rules = []
        self._build_rules()

    def fmt(self, color, bold=False, italic=False):
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    def add(self, pattern, color, bold=False, italic=False):
        self.rules.append((re.compile(pattern), self.fmt(color, bold, italic)))

    def _build_rules(self):
        self.add(r"\b(if|else|elif|for|while|return|def|class|import|from|as|try|except|finally|with|pass|break|continue|lambda|yield|async|await|raise|in|is|not|and|or|global|nonlocal|assert|del|match|case)\b", "#c4a7ff", True)
        self.add(r"\b(True|False|None|true|false|null|undefined|this|self|super)\b", "#f0abfc")
        self.add(r"\b(print|len|range|str|int|float|list|dict|set|tuple|open|type|input|enumerate|zip|map|filter|console|function|const|let|var|new|export|default|public|private|static|void|boolean)\b", "#67e8f9")
        self.add(r"\b\d+(\.\d+)?\b", "#fbbf24")
        self.add(r"#[^\n]*|//[^\n]*", "#7f8caa", False, True)
        self.add(r"\b[A-Z][A-Za-z0-9_]*\b", "#86efac")
        self.add(r'"([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\'|`([^`\\]|\\.)*`', "#fda4af")
        self.add(r"[+\-*/%=<>!&|^~?:]+", "#fb923c")

    def highlightBlock(self, text):
        if self.pygments_lexer and self._pygments_lex:
            palette = [
                ("Comment", "#7f8caa", False, True),
                ("Keyword", "#c4a7ff", True, False),
                ("Name.Function", "#67e8f9", True, False),
                ("Name.Class", "#86efac", True, False),
                ("Name.Builtin", "#67e8f9", False, False),
                ("String", "#fda4af", False, False),
                ("Number", "#fbbf24", False, False),
                ("Operator", "#fb923c", False, False),
                ("Generic.Error", "#fb7185", True, False),
                ("Name.Decorator", "#f0abfc", False, False),
            ]
            try:
                pos = 0
                for token, value in self._pygments_lex(text, self.pygments_lexer):
                    length = len(value)
                    if length and pos < len(text):
                        name = str(token)
                        selected = None
                        for prefix, color, bold, italic in palette:
                            if name == prefix or name.startswith(prefix + "."):
                                selected = self.fmt(color, bold, italic)
                                break
                        if selected is not None:
                            self.setFormat(pos, min(length, len(text) - pos), selected)
                    pos += length
            except Exception:
                for rx, fmt in self.rules:
                    for match in rx.finditer(text):
                        self.setFormat(match.start(), match.end() - match.start(), fmt)
            return
        for rx, fmt in self.rules:
            for match in rx.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class CodeEditor(QPlainTextEdit):
    def __init__(self, path: Optional[str] = None):
        super().__init__()
        self.path = path
        self.highlighter = CodeHighlighter(self.document(), self._language_from_path(path))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Consolas", 11))
        self.document().setModified(False)

    def _language_from_path(self, path):
        ext = Path(path).suffix.lower() if path else ""
        return {
            ".py": "python", ".pyw": "python", ".pyi": "python", ".ipynb": "json",
            ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "jsx",
            ".ts": "typescript", ".tsx": "tsx", ".html": "html", ".htm": "html",
            ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less", ".vue": "html", ".svelte": "html",
            ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala", ".groovy": "groovy",
            ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
            ".cs": "csharp", ".fs": "fsharp", ".vb": "vbnet", ".php": "php", ".phtml": "php",
            ".go": "go", ".rs": "rust", ".swift": "swift", ".m": "objective-c", ".mm": "objective-c++",
            ".dart": "dart", ".lua": "lua", ".rb": "ruby", ".rake": "ruby", ".pl": "perl", ".pm": "perl",
            ".sql": "sql", ".mysql": "sql", ".pgsql": "sql", ".sh": "bash", ".bash": "bash", ".zsh": "bash",
            ".ps1": "powershell", ".psm1": "powershell", ".bat": "batch", ".cmd": "batch",
            ".json": "json", ".jsonc": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
            ".xml": "xml", ".xsl": "xml", ".svg": "xml", ".md": "markdown", ".mdx": "markdown",
            ".txt": "text", ".rst": "restructuredtext", ".tex": "latex", ".ipynb": "json",
            ".r": "r", ".jl": "julia", ".f": "fortran", ".f90": "fortran", ".cob": "cobol", ".pas": "pascal",
            ".ex": "elixir", ".exs": "elixir", ".erl": "erlang", ".hrl": "erlang", ".clj": "clojure",
            ".hs": "haskell", ".lhs": "haskell", ".elm": "elm", ".sol": "solidity", ".proto": "proto",
            ".tf": "terraform", ".hcl": "terraform", ".dockerfile": "docker", ".makefile": "make",
            ".gradle": "groovy", ".cmake": "cmake", ".diff": "diff", ".patch": "diff",
            ".graphql": "graphql", ".gql": "graphql", ".asm": "nasm", ".s": "asm", ".v": "verilog",
            ".vhd": "vhdl", ".vhdl": "vhdl", ".plsql": "plsql", ".psql": "psql"
        }.get(ext, "text")

    def set_path(self, path):
        self.path = path
        self.highlighter = CodeHighlighter(self.document(), self._language_from_path(path))


class GitHubWorker(QThread):
    done = Signal(object, str)
    progress = Signal(str)

    def __init__(self, operation, token, **kwargs):
        super().__init__()
        self.operation = operation
        self.token = token
        self.kwargs = kwargs

    def api(self, method, endpoint, **kwargs):
        if requests is None:
            raise RuntimeError("The 'requests' package is missing. Install it with: py -m pip install requests")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "CodeBox-Ultimate-X"
        }
        response = requests.request(method, GITHUB_API + endpoint, headers=headers, timeout=30, **kwargs)
        if not response.ok:
            try:
                message = response.json().get("message", response.text)
            except Exception:
                message = response.text
            raise RuntimeError(f"GitHub API returned HTTP {response.status_code}: {message}")
        if response.status_code == 204 or not response.text:
            return {}
        return response.json()

    def run(self):
        try:
            op = self.operation
            if op == "repos":
                self.progress.emit("Loading repositories from GitHub…")
                data = self.api("GET", "/user/repos", params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"})
            elif op == "create_repo":
                self.progress.emit("Creating repository…")
                data = self.api("POST", "/user/repos", json={
                    "name": self.kwargs["name"],
                    "description": self.kwargs.get("description", ""),
                    "private": self.kwargs.get("private", True),
                    "auto_init": True
                })
            elif op == "upload":
                self.progress.emit("Checking destination file…")
                owner = self.kwargs["owner"]
                repo = self.kwargs["repo"]
                path = self.kwargs["repo_path"].strip("/")
                local_path = Path(self.kwargs["local_path"])
                if not local_path.is_file():
                    raise RuntimeError("Select a single existing file to upload.")
                if local_path.stat().st_size > 20 * 1024 * 1024:
                    raise RuntimeError("This simple Contents API uploader limits files to 20 MB. Use Git LFS or another supported workflow for larger files.")
                endpoint = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/contents/{urllib.parse.quote(path, safe='/')}"
                existing = None
                check = requests.get(GITHUB_API + endpoint, headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION
                }, timeout=30)
                if check.status_code == 200:
                    existing = check.json().get("sha")
                elif check.status_code not in (404,):
                    try:
                        msg = check.json().get("message", check.text)
                    except Exception:
                        msg = check.text
                    raise RuntimeError(f"Could not check destination (HTTP {check.status_code}): {msg}")
                self.progress.emit("Uploading file to GitHub…")
                payload = {
                    "message": self.kwargs.get("message") or f"Upload {local_path.name} with CodeBox",
                    "content": base64.b64encode(local_path.read_bytes()).decode("ascii")
                }
                if existing:
                    payload["sha"] = existing
                branch = self.kwargs.get("branch", "").strip()
                if branch:
                    payload["branch"] = branch
                data = self.api("PUT", endpoint, json=payload)
            elif op == "upload_folder":
                self.progress.emit("Preparing folder upload…")
                owner = self.kwargs["owner"]
                repo = self.kwargs["repo"]
                branch = self.kwargs["branch"]
                folder = Path(self.kwargs["local_path"])
                remote_root = self.kwargs.get("remote_root", "").strip("/")
                if not folder.is_dir():
                    raise RuntimeError("Choose an existing project folder.")
                excluded_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
                excluded_names = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
                files = []
                for root, dirs, names in os.walk(folder):
                    dirs[:] = [d for d in dirs if d not in excluded_dirs]
                    for filename in names:
                        local = Path(root) / filename
                        rel = local.relative_to(folder).as_posix()
                        if filename.lower() in excluded_names or local.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
                            continue
                        try:
                            if local.stat().st_size > 10 * 1024 * 1024:
                                continue
                        except OSError:
                            continue
                        files.append((local, rel))
                if not files:
                    raise RuntimeError("No uploadable files were found after excluding secrets, build folders, and files over 10 MB.")
                if len(files) > 100:
                    raise RuntimeError(f"This UI limits one folder commit to 100 files; found {len(files)}. Split the folder into smaller commits.")
                branch_q = urllib.parse.quote(branch, safe="")
                base = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/git"
                ref = self.api("GET", f"{base}/ref/heads/{branch_q}")
                parent_sha = ref["object"]["sha"]
                parent = self.api("GET", f"{base}/commits/{parent_sha}")
                base_tree = parent["tree"]["sha"]
                entries = []
                for idx, (local, rel) in enumerate(files, 1):
                    self.progress.emit(f"Uploading blobs: {idx}/{len(files)} · {rel}")
                    blob = self.api("POST", f"{base}/blobs", json={
                        "content": base64.b64encode(local.read_bytes()).decode("ascii"),
                        "encoding": "base64"
                    })
                    remote_path = f"{remote_root}/{rel}" if remote_root else rel
                    entries.append({"path": remote_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
                self.progress.emit("Creating Git tree and commit…")
                tree = self.api("POST", f"{base}/trees", json={"base_tree": base_tree, "tree": entries})
                commit = self.api("POST", f"{base}/commits", json={
                    "message": self.kwargs.get("message") or "Upload project folder with CodeBox",
                    "tree": tree["sha"], "parents": [parent_sha]
                })
                data = self.api("PATCH", f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/git/refs/heads/{branch_q}", json={"sha": commit["sha"], "force": False})
                data["uploaded_count"] = len(files)
                data["commit_url"] = commit.get("html_url", "")
            elif op == "download_repo_zip":
                self.progress.emit("Downloading repository archive…")
                owner = self.kwargs["owner"]
                repo = self.kwargs["repo"]
                branch = self.kwargs["branch"]
                destination = Path(self.kwargs["destination"])
                endpoint = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/zipball/{urllib.parse.quote(branch, safe='')}"
                response = requests.get(GITHUB_API + endpoint, headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                    "User-Agent": "CodeBox-Ultimate-X"
                }, timeout=60, stream=True)
                if not response.ok:
                    raise RuntimeError(f"Download failed: HTTP {response.status_code}")
                archive_bytes = response.content
                if len(archive_bytes) > 100 * 1024 * 1024:
                    raise RuntimeError("Repository archive is larger than the 100 MB safety limit.")
                import io
                destination.mkdir(parents=True, exist_ok=True)
                written = 0
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                    members = archive.infolist()
                    roots = set()
                    for member in members:
                        parts = Path(member.filename.replace("\\", "/")).parts
                        if not parts or ".." in parts or member.filename.startswith(("/", "\\")):
                            continue
                        roots.add(parts[0])
                    root_prefix = next(iter(roots)) if len(roots) == 1 else ""
                    for member in members:
                        if member.is_dir():
                            continue
                        parts = Path(member.filename.replace("\\", "/")).parts
                        if not parts or ".." in parts or member.filename.startswith(("/", "\\")):
                            continue
                        rel_parts = parts[1:] if root_prefix and parts[0] == root_prefix else parts
                        if not rel_parts:
                            continue
                        target = destination.joinpath(*rel_parts)
                        try:
                            target.resolve().relative_to(destination.resolve())
                        except Exception:
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as src, target.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                        written += 1
                data = {"destination": str(destination), "files": written}
            elif op == "user":
                self.progress.emit("Checking GitHub credentials…")
                data = self.api("GET", "/user")
            else:
                raise RuntimeError("Unknown GitHub operation.")
            self.done.emit(data, "")
        except Exception as exc:
            self.done.emit(None, str(exc))


@dataclass
class Lesson:
    title: str
    level: str
    topic: str
    body: str
    task: str
    answer: str
    xp: int = 25


LESSONS = [
    Lesson("Python: Your First Output", "Beginner", "Python",
           "The print() function displays information in the console. Text is usually written inside quotes.",
           'Write one line that prints Hello, CodeBox!', 'print("Hello, CodeBox!")', 20),
    Lesson("Python: Variables", "Beginner", "Python",
           "A variable gives a value a name. Example: score = 10. Python figures out the type automatically.",
           "Create a variable named score with the value 42.", "score = 42", 25),
    Lesson("Python: Conditions", "Beginner", "Python",
           "An if statement runs a block when its condition is true. Indentation defines the block.",
           "Write an if statement that prints YES when ready is True.", "if ready:\\n    print('YES')", 30),
    Lesson("HTML: Page Structure", "Beginner", "Web",
           "HTML describes page structure. A basic page commonly includes html, head, title, and body elements.",
           "Write a heading that says Welcome using an h1 element.", "<h1>Welcome</h1>", 20),
    Lesson("JavaScript: Constants", "Beginner", "JavaScript",
           "Use const when a binding should not be reassigned. JavaScript statements can end with semicolons.",
           "Declare a constant named answer with the value 42.", "const answer = 42;", 25),
    Lesson("Git: First Commit", "Beginner", "Git",
           "Git tracks changes over time. A commit records a snapshot with a message.",
           "Write a clear example commit message for adding a README.", "Add README documentation", 25),
    Lesson("Python: Loops", "Intermediate", "Python",
           "A for loop iterates over items. range(3) produces 0, 1, and 2.",
           "Write a loop that prints each number in range(3).", "for i in range(3):\\n    print(i)", 35),
    Lesson("Web: CSS Class", "Beginner", "Web",
           "A CSS class selector begins with a dot. HTML elements can reference it with the class attribute.",
           "Write a CSS rule that makes .card use a 12px border radius.", ".card { border-radius: 12px; }", 25),
]


class LessonDialog(QDialog):
    completed = Signal(str, int)

    def __init__(self, lesson: Lesson, already_done=False, parent=None):
        super().__init__(parent)
        self.lesson = lesson
        self.setWindowTitle(lesson.title)
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        title = QLabel(f"<h2>{lesson.title}</h2><span style='color:#a78bfa'>{lesson.topic} · {lesson.level} · {lesson.xp} XP</span>")
        title.setWordWrap(True)
        layout.addWidget(title)
        body = QLabel(lesson.body)
        body.setWordWrap(True)
        body.setStyleSheet("background:#191b2a;padding:14px;border-radius:8px;")
        layout.addWidget(body)
        prompt = QLabel("<b>Your challenge</b><br>" + lesson.task)
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        self.answer = QPlainTextEdit()
        self.answer.setPlaceholderText("Write your answer here…")
        self.answer.setMinimumHeight(130)
        layout.addWidget(self.answer)
        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        row = QHBoxLayout()
        hint = QPushButton("Show Hint")
        check = QPushButton("Check Answer")
        check.setObjectName("Primary")
        close = QPushButton("Close")
        row.addWidget(hint)
        row.addStretch()
        row.addWidget(close)
        row.addWidget(check)
        layout.addLayout(row)
        hint.clicked.connect(lambda: QMessageBox.information(self, "Hint", "Think about the example in the lesson. Keep the syntax simple and focus on the requested result."))
        close.clicked.connect(self.reject)
        check.clicked.connect(self.check_answer)
        self.already_done = already_done
        if already_done:
            self.feedback.setText("✓ You have already completed this lesson. You can practice it again.")

    def check_answer(self):
        typed = self.answer.toPlainText().strip()
        expected = self.lesson.answer.strip()
        normalized = lambda s: re.sub(r"\s+", "", s).replace('"', "'")
        if normalized(typed) == normalized(expected):
            self.feedback.setText(f"✓ Correct! You earned {self.lesson.xp} XP." if not self.already_done else "✓ Correct! This lesson is already in your progress.")
            if not self.already_done:
                self.completed.emit(self.lesson.title, self.lesson.xp)
                self.already_done = True
        else:
            self.feedback.setText("Not quite yet. Review the lesson, check punctuation and indentation, then try again.")


class SettingsDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 28)
        self.font_size.setValue(int(settings.value("editor/font_size", 11)))
        self.wrap = QCheckBox("Enable line wrapping")
        self.wrap.setChecked(settings.value("editor/wrap", False, type=bool))
        self.save_token = QCheckBox("Allow optional OS keyring storage for GitHub token")
        self.save_token.setChecked(settings.value("github/save_token", True, type=bool))
        form.addRow("Editor font size", self.font_size)
        form.addRow("Editor", self.wrap)
        form.addRow("Credentials", self.save_token)
        layout.addLayout(form)
        note = QLabel("Secrets are not written to the app settings file. If keyring is unavailable, the token is kept only in memory for this session.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#a7adc6")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        self.settings.setValue("editor/font_size", self.font_size.value())
        self.settings.setValue("editor/wrap", self.wrap.isChecked())
        self.settings.setValue("github/save_token", self.save_token.isChecked())
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(980, 650)
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.auth_session = dict(AUTH_SESSION)
        self.auth_api_base = str(self.auth_session.get("api_base") or AUTH_API_BASE).rstrip("/")
        self.server_plan = str(self.auth_session.get("plan", "free")).lower()
        self.current_project = ""
        self.github_token = ""
        self.github_user = None
        self.repos = []
        self.worker = None
        self.ai_worker = None
        self.oauth_worker = None
        self.email_worker = None
        self.secret_cache = {}
        self.email_otp = None
        self.ai_last_response = ""
        self.signed_in_user = str(self.auth_session.get("email") or self.auth_session.get("username") or "Signed-in user")
        self.signed_in_provider = str(self.auth_session.get("provider", "CodeBox Account"))
        self.plan = "Plus" if self.server_plan == "plus" and APP_BUILD_EDITION == "Plus" else "Free"
        today = datetime.now().strftime("%Y-%m-%d")
        if self.settings.value("ai/day", "") != today:
            self.settings.setValue("ai/day", today)
            self.settings.setValue("ai/count", 0)
        self.vault_dir = Path.home() / "Documents" / "CodeBox" / "Repositories"
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.terminal_process = QProcess(self)
        self.terminal_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.completed_lessons = set(self.settings.value("learning/completed", []))
        if isinstance(self.completed_lessons, str):
            self.completed_lessons = {self.completed_lessons}
        self.xp = int(self.settings.value("learning/xp", 0))
        self._load_keyring_token()
        self._build_ui()
        self._restore_recent_files()
        self._refresh_learning_stats()

    def _load_keyring_token(self):
        if not self.settings.value("github/save_token", True, type=bool):
            return
        try:
            import keyring
            self.github_token = keyring.get_password("CodeBoxUltimateX", "github") or ""
        except Exception:
            self.github_token = ""

    def _store_keyring_token(self, token):
        # Never persist a new token when storage is disabled, but always honor a clear request.
        if token and not self.settings.value("github/save_token", True, type=bool):
            return
        try:
            import keyring
            if token:
                keyring.set_password("CodeBoxUltimateX", "github", token)
            else:
                try:
                    keyring.delete_password("CodeBoxUltimateX", "github")
                except Exception:
                    pass
        except Exception:
            QMessageBox.warning(self, "Secure storage unavailable",
                                "The OS keyring could not store the token. It will remain in memory for this session only.")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        side_frame = QFrame()
        side_frame.setObjectName("Card")
        side_frame.setFixedWidth(218)
        side_layout = QVBoxLayout(side_frame)
        side_layout.setContentsMargins(8, 8, 8, 8)
        side_layout.addWidget(LogoWidget(compact=True))
        self.sidebar = QListWidget()
        self.sidebar.addItems([
            "⌂  Dashboard", "⌨  Editor", "📁  Projects", "🐙  GitHub",
            "🎓  Learning", "🏆  Achievements", "🤖  AI Lab", "▶  Terminal",
            "🗃  Local Vault", "👤  Account & Plans", "⚙  Settings"
        ])
        self.sidebar.setCurrentRow(0)
        side_layout.addWidget(self.sidebar, 1)
        tier = QLabel("PLUS ACTIVE" if self._is_plus() else "FREE EDITION")
        tier.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tier.setStyleSheet("color:#c4b5fd;background:#202338;border:1px solid #34374f;border-radius:7px;padding:7px;font-weight:bold")
        self.sidebar_tier_label = tier
        side_layout.addWidget(tier)
        root.addWidget(side_frame)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._dashboard_page())        # 0
        self.pages.addWidget(self._editor_page())           # 1
        self.pages.addWidget(self._projects_page())         # 2
        self.pages.addWidget(self._github_page())           # 3
        self.pages.addWidget(self._learning_page())         # 4
        self.pages.addWidget(self._achievements_page())     # 5
        self.pages.addWidget(self._ai_page())               # 6
        self.pages.addWidget(self._terminal_page())         # 7
        self.pages.addWidget(self._vault_page())            # 8
        self.pages.addWidget(self._account_page())          # 9
        self.pages.addWidget(self._settings_page())         # 10
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)

        toolbar = QToolBar("Main")
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)
        for label, slot in [
            ("New File", self.new_file), ("Open File", self.open_file),
            ("Open Project", self.open_project), ("Save", self.save_current),
            ("Find", self.find_text), ("GitHub", lambda: self.sidebar.setCurrentRow(3)),
            ("AI Lab", lambda: self.sidebar.setCurrentRow(6)),
            ("Run Current File", self.run_current_file)
        ]:
            act = QAction(label, self)
            act.triggered.connect(slot)
            toolbar.addAction(act)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready · Local-first workspace · Secrets are never hardcoded")
        self.terminal_process.readyReadStandardOutput.connect(self._terminal_read)
        self.terminal_process.finished.connect(self._terminal_finished)
        self.terminal_process.errorOccurred.connect(lambda error: self._terminal_append(f"\n[Process error: {error}]\n"))
        logo = LogoWidget(compact=True)
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        logo.render(pixmap)
        self.setWindowIcon(QIcon(pixmap))

    def _card(self, title, value, description=""):
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        a = QLabel(title.upper())
        a.setStyleSheet("color:#9ca3c8;font-size:9pt;font-weight:bold")
        b = QLabel(value)
        b.setStyleSheet("font-size:22pt;font-weight:bold;color:#c4b5fd")
        c = QLabel(description)
        c.setStyleSheet("color:#a7adc6")
        c.setWordWrap(True)
        layout.addWidget(a)
        layout.addWidget(b)
        layout.addWidget(c)
        return frame, b

    def _dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(LogoWidget())
        heading = QLabel("<h2>Build. Learn. Ship.</h2><p>Your local-first developer command center, with GitHub and AI tools.</p>")
        layout.addWidget(heading)
        cards = QHBoxLayout()
        c1, self.card_projects = self._card("Workspace", "0", "Files opened this session")
        c2, self.card_xp = self._card("Learning XP", str(self.xp), "Earn XP by completing lessons")
        c3, self.card_lessons = self._card("Lessons", str(len(self.completed_lessons)), "Lessons completed")
        c4, self.card_github = self._card("GitHub", "Offline", "Connect with a personal access token")
        for c in (c1, c2, c3, c4):
            cards.addWidget(c)
        layout.addLayout(cards)
        quick = QGroupBox("Quick actions")
        qrow = QHBoxLayout(quick)
        for label, callback in [
            ("＋ New File", self.new_file), ("Open File", self.open_file),
            ("Open Project", self.open_project), ("Connect GitHub", lambda: self.sidebar.setCurrentRow(3)),
            ("AI Assistant", lambda: self.sidebar.setCurrentRow(6)),
            ("Open Terminal", lambda: self.sidebar.setCurrentRow(7)),
            ("Local Vault", lambda: self.sidebar.setCurrentRow(8)),
            ("Start Learning", lambda: self.sidebar.setCurrentRow(4))
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            qrow.addWidget(btn)
        layout.addWidget(quick)
        info = QGroupBox("Workspace notes")
        il = QVBoxLayout(info)
        il.addWidget(QLabel("• Local files stay on your device unless you explicitly upload them.\n"
                            "• GitHub operations use the official API after you authorize them.\n"
                            "• AI calls use keys you provide and are sent to the selected AI provider.\n"
                            "• The terminal runs commands locally with your Windows account permissions.\n"
                            "• Free / Plus selection is a local preview, not verified billing."))
        layout.addWidget(info)
        layout.addStretch()
        return page

    def _editor_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        self.editor_hint = QLabel("No file selected")
        top.addWidget(self.editor_hint, 1)
        for label, callback in [("New", self.new_file), ("Open", self.open_file), ("Save", self.save_current), ("Find", self.find_text), ("Replace", self.replace_text)]:
            b = QPushButton(label)
            b.clicked.connect(callback)
            top.addWidget(b)
        layout.addLayout(top)
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self.close_tab)
        self.editor_tabs.currentChanged.connect(self._editor_changed)
        layout.addWidget(self.editor_tabs, 1)
        self._add_editor(None, "")
        return page

    def _projects_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>Project Explorer</h2>Open a local folder to browse and edit its files."))
        row = QHBoxLayout()
        open_btn = QPushButton("Open Project Folder")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self.open_project)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_project)
        row.addWidget(open_btn)
        row.addWidget(refresh)
        row.addStretch()
        layout.addLayout(row)
        self.project_path_label = QLabel("No project folder selected")
        self.project_path_label.setWordWrap(True)
        layout.addWidget(self.project_path_label)
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.homePath())
        self.fs_model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.project_tree = QTreeView()
        self.project_tree.setModel(self.fs_model)
        self.project_tree.setRootIndex(self.fs_model.index(QDir.homePath()))
        self.project_tree.setColumnWidth(0, 320)
        self.project_tree.doubleClicked.connect(self._project_item_open)
        layout.addWidget(self.project_tree, 1)
        return page

    def _github_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>GitHub Workspace</h2><p>Connect securely, browse your repositories, create repos, and upload a file.</p>"))
        conn = QGroupBox("Connection")
        form = QVBoxLayout(conn)
        row = QHBoxLayout()
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("GitHub Personal Access Token (hidden)")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setText(self.github_token)
        row.addWidget(self.token_edit, 1)
        connect = QPushButton("Connect")
        connect.setObjectName("Primary")
        connect.clicked.connect(self.connect_github)
        row.addWidget(connect)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.clear_github_token)
        row.addWidget(clear)
        form.addLayout(row)
        self.github_status = QLabel("Not connected")
        self.github_status.setStyleSheet("color:#a7adc6")
        form.addWidget(self.github_status)
        layout.addWidget(conn)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Repositories"))
        self.repo_list = QListWidget()
        self.repo_list.currentItemChanged.connect(self._repo_selected)
        ll.addWidget(self.repo_list, 1)
        reload_btn = QPushButton("Refresh Repositories")
        reload_btn.clicked.connect(self.load_repos)
        ll.addWidget(reload_btn)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.repo_detail = QLabel("Select a repository after connecting.")
        self.repo_detail.setWordWrap(True)
        self.repo_detail.setStyleSheet("background:#191b2a;padding:12px;border-radius:8px")
        rl.addWidget(self.repo_detail)
        create_group = QGroupBox("Create repository")
        cg = QFormLayout(create_group)
        self.new_repo_name = QLineEdit()
        self.new_repo_name.setPlaceholderText("my-new-project")
        self.new_repo_desc = QLineEdit()
        self.new_repo_desc.setPlaceholderText("Optional description")
        self.new_repo_private = QCheckBox("Private repository")
        self.new_repo_private.setChecked(True)
        create_btn = QPushButton("Create Repository")
        create_btn.clicked.connect(self.create_repo)
        cg.addRow("Name", self.new_repo_name)
        cg.addRow("Description", self.new_repo_desc)
        cg.addRow("", self.new_repo_private)
        cg.addRow("", create_btn)
        rl.addWidget(create_group)
        upload_group = QGroupBox("Upload one file")
        ug = QFormLayout(upload_group)
        self.upload_local_path = QLineEdit()
        self.upload_local_path.setPlaceholderText("Choose a local file")
        choose = QPushButton("Browse…")
        choose.clicked.connect(self.choose_upload_file)
        path_row = QHBoxLayout()
        path_row.addWidget(self.upload_local_path, 1)
        path_row.addWidget(choose)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        self.upload_remote_path = QLineEdit()
        self.upload_remote_path.setPlaceholderText("folder/filename.ext")
        self.upload_branch = QLineEdit()
        self.upload_branch.setPlaceholderText("Optional branch (blank = default)")
        self.upload_commit = QLineEdit()
        self.upload_commit.setPlaceholderText("Commit message")
        upload_btn = QPushButton("Upload to Selected Repository")
        upload_btn.setObjectName("Primary")
        upload_btn.clicked.connect(self.upload_file)
        ug.addRow("Local file", path_widget)
        ug.addRow("Repository path", self.upload_remote_path)
        ug.addRow("Branch", self.upload_branch)
        ug.addRow("Commit", self.upload_commit)
        ug.addRow("", upload_btn)
        rl.addWidget(upload_group)
        folder_group = QGroupBox("Upload a complete project folder")
        fg = QFormLayout(folder_group)
        self.upload_folder_path = QLineEdit()
        self.upload_folder_path.setPlaceholderText("Choose a local project folder")
        choose_folder_btn = QPushButton("Browse…")
        choose_folder_btn.clicked.connect(self.choose_upload_folder)
        folder_path_row = QHBoxLayout()
        folder_path_row.addWidget(self.upload_folder_path, 1)
        folder_path_row.addWidget(choose_folder_btn)
        folder_path_widget = QWidget()
        folder_path_widget.setLayout(folder_path_row)
        self.upload_folder_remote_root = QLineEdit()
        self.upload_folder_remote_root.setPlaceholderText("Optional remote root folder")
        self.upload_folder_branch = QLineEdit()
        self.upload_folder_branch.setPlaceholderText("Default branch if blank")
        self.upload_folder_commit = QLineEdit("Upload project with CodeBox")
        folder_upload_btn = QPushButton("Commit Folder to GitHub")
        folder_upload_btn.setObjectName("Primary")
        folder_upload_btn.clicked.connect(self.upload_folder)
        fg.addRow("Local folder", folder_path_widget)
        fg.addRow("Remote root", self.upload_folder_remote_root)
        fg.addRow("Branch", self.upload_folder_branch)
        fg.addRow("Commit message", self.upload_folder_commit)
        fg.addRow("", folder_upload_btn)
        rl.addWidget(folder_group)
        repo_actions = QHBoxLayout()
        download_btn = QPushButton("Download Selected Repository ZIP…")
        download_btn.clicked.connect(self.download_selected_repo)
        repo_actions.addWidget(download_btn)
        repo_actions.addStretch()
        rl.addLayout(repo_actions)
        split.addWidget(right)
        split.setSizes([330, 700])
        layout.addWidget(split, 1)
        self.github_progress = QProgressBar()
        self.github_progress.setRange(0, 1)
        self.github_progress.setValue(0)
        layout.addWidget(self.github_progress)
        return page

    def _learning_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>Learning Center</h2><p>Original bite-sized lessons with practice challenges and XP.</p>"))
        stats = QHBoxLayout()
        self.learning_xp_label = QLabel(f"⭐ {self.xp} XP")
        self.learning_done_label = QLabel(f"✓ {len(self.completed_lessons)} lessons completed")
        for w in (self.learning_xp_label, self.learning_done_label):
            w.setStyleSheet("background:#191b2a;padding:10px;border-radius:8px;color:#c4b5fd;font-weight:bold")
            stats.addWidget(w)
        stats.addStretch()
        layout.addLayout(stats)
        self.lesson_list = QListWidget()
        for lesson in LESSONS:
            done = lesson.title in self.completed_lessons
            item = QListWidgetItem(f"{'✓ ' if done else '◇ '}{lesson.title}   ·   {lesson.level}   ·   {lesson.xp} XP")
            item.setData(Qt.ItemDataRole.UserRole, lesson.title)
            self.lesson_list.addItem(item)
        self.lesson_list.itemDoubleClicked.connect(lambda item: self.open_lesson(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.lesson_list, 1)
        row = QHBoxLayout()
        open_btn = QPushButton("Open Selected Lesson")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self.open_selected_lesson)
        review = QPushButton("Review Completed")
        review.clicked.connect(self.review_completed)
        row.addWidget(open_btn)
        row.addWidget(review)
        row.addStretch()
        layout.addLayout(row)
        note = QLabel("XP and lesson progress are stored locally. This is an original learning library, not an official Codédex integration.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9ca3c8")
        layout.addWidget(note)
        return page

    def _achievements_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>Achievements</h2><p>Earn badges by completing real actions in CodeBox.</p>"))
        self.achievement_list = QListWidget()
        layout.addWidget(self.achievement_list, 1)
        self._refresh_achievements()
        return page

    def _secret_get(self, key):
        if key in self.secret_cache:
            return self.secret_cache[key]
        try:
            import keyring
            value = keyring.get_password("CodeBoxUltimateX", key) or ""
            if value:
                self.secret_cache[key] = value
            return value
        except Exception:
            return ""

    def _secret_set(self, key, value):
        value = value or ""
        if value:
            self.secret_cache[key] = value
        else:
            self.secret_cache.pop(key, None)
        try:
            import keyring
            if value:
                keyring.set_password("CodeBoxUltimateX", key, value)
            else:
                try: keyring.delete_password("CodeBoxUltimateX", key)
                except Exception: pass
            return True
        except Exception:
            return False

    def _ai_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>AI Lab</h2><p>Ask an AI provider to explain, review, debug, or generate code. API keys are never embedded in the source.</p>"))
        settings_box = QGroupBox("Provider & key vault")
        form = QFormLayout(settings_box)
        self.ai_provider = QComboBox()
        self.ai_provider.addItem("Google Gemini", "gemini")
        self.ai_provider.addItem("Groq", "groq")
        self.ai_provider.currentIndexChanged.connect(self._ai_provider_changed)
        self.ai_key_edit = QLineEdit()
        self.ai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key_edit.setPlaceholderText("Paste your own API key")
        self.ai_model_edit = QLineEdit("gemini-2.5-flash")
        self.ai_model_hint = QLabel("Default model: gemini-2.5-flash")
        self.ai_model_hint.setStyleSheet("color:#9ca3c8")
        form.addRow("Provider", self.ai_provider)
        form.addRow("API key", self.ai_key_edit)
        form.addRow("Model", self.ai_model_edit)
        form.addRow("", self.ai_model_hint)
        key_row = QHBoxLayout()
        save_key = QPushButton("Save Key to OS Keyring")
        save_key.clicked.connect(self._save_ai_key)
        clear_key = QPushButton("Forget Key")
        clear_key.clicked.connect(self._clear_ai_key)
        key_row.addWidget(save_key)
        key_row.addWidget(clear_key)
        key_row.addStretch()
        form.addRow("", key_row)
        self.ai_key_status = QLabel("Keys are saved in your operating system keyring when available; otherwise only in memory.")
        self.ai_key_status.setWordWrap(True)
        self.ai_key_status.setStyleSheet("color:#9ca3c8")
        form.addRow("Storage", self.ai_key_status)
        layout.addWidget(settings_box)

        prompt_box = QGroupBox("Prompt")
        pl = QVBoxLayout(prompt_box)
        self.ai_prompt = QPlainTextEdit()
        self.ai_prompt.setPlaceholderText("Example: Review this Python code, explain the bug, and propose a safe fix…")
        self.ai_prompt.setMinimumHeight(95)
        self.ai_include_editor = QCheckBox("Include the current editor contents")
        run_row = QHBoxLayout()
        run_btn = QPushButton("Run AI Request")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self._request_ai)
        insert_btn = QPushButton("Insert Response into Editor")
        insert_btn.clicked.connect(self._insert_ai_response)
        clear_btn = QPushButton("Clear Output")
        clear_btn.clicked.connect(lambda: self.ai_output.clear())
        run_row.addWidget(run_btn)
        run_row.addWidget(insert_btn)
        run_row.addWidget(clear_btn)
        run_row.addStretch()
        pl.addWidget(self.ai_prompt)
        pl.addWidget(self.ai_include_editor)
        pl.addLayout(run_row)
        layout.addWidget(prompt_box)
        output_group = QGroupBox("Response")
        ol = QVBoxLayout(output_group)
        self.ai_output = QPlainTextEdit()
        self.ai_output.setReadOnly(True)
        self.ai_output.setPlaceholderText("AI response will appear here…")
        ol.addWidget(self.ai_output)
        self.ai_status = QLabel("Ready")
        self.ai_status.setStyleSheet("color:#9ca3c8")
        ol.addWidget(self.ai_status)
        layout.addWidget(output_group, 1)
        self._ai_provider_changed()
        return page

    def _ai_provider_changed(self, *args):
        if not hasattr(self, "ai_provider"):
            return
        provider = self.ai_provider.currentData()
        if provider == "gemini":
            self.ai_model_edit.setText("gemini-2.5-flash")
            self.ai_model_hint.setText("Default model: gemini-2.5-flash · Google AI Studio key required")
        else:
            self.ai_model_edit.setText("llama-3.3-70b-versatile")
            self.ai_model_hint.setText("Default model: llama-3.3-70b-versatile · Groq key required")
        key = self._secret_get("ai_" + str(provider))
        self.ai_key_edit.setText(key)
        self.ai_key_status.setText("Saved key loaded from OS keyring." if key else "No saved key. Enter your own provider key. It is not written into code or settings.")

    def _save_ai_key(self):
        provider = self.ai_provider.currentData()
        key = self.ai_key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "API key required", "Paste the API key you created with the selected provider.")
            return
        stored = self._secret_set("ai_" + str(provider), key)
        self.ai_key_status.setText("Key stored in OS keyring." if stored else "Key will stay in memory for this session. Install keyring for OS-backed storage: py -m pip install keyring")
        QMessageBox.information(self, "Key storage", self.ai_key_status.text())

    def _clear_ai_key(self):
        provider = self.ai_provider.currentData()
        self._secret_set("ai_" + str(provider), "")
        self.ai_key_edit.clear()
        self.ai_key_status.setText("Saved key cleared for this provider.")

    def _request_ai(self):
        if self.ai_worker and self.ai_worker.isRunning():
            QMessageBox.information(self, "AI Lab", "An AI request is already running.")
            return
        provider = self.ai_provider.currentData()
        key = self.ai_key_edit.text().strip() or self._secret_get("ai_" + str(provider))
        if not key:
            QMessageBox.warning(self, "API key required", "Enter your own Gemini or Groq API key, then choose Save Key to OS Keyring.")
            return
        prompt = self.ai_prompt.toPlainText().strip()
        if self.ai_include_editor.isChecked():
            ed = self.current_editor()
            if ed:
                prompt += "\n\nCurrent editor contents:\n```\n" + ed.toPlainText() + "\n```"
        if not prompt:
            QMessageBox.warning(self, "Prompt required", "Write a prompt or include the current editor contents.")
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if self.settings.value("ai/day", "") != today:
            self.settings.setValue("ai/day", today)
            self.settings.setValue("ai/count", 0)
        count = int(self.settings.value("ai/count", 0))
        limit = 100 if "Plus" in str(self.plan) else 15
        if count >= limit:
            QMessageBox.warning(self, "Daily local limit", f"You've reached the local {limit}-request daily limit for this edition.\nThe Plus indicator is only a local preview, not a paid license.")
            return
        self.ai_output.setPlainText("Waiting for provider response…")
        self.ai_status.setText("Starting request…")
        self.ai_worker = AIWorker(provider, key, self.ai_model_edit.text().strip(), prompt, self)
        self.ai_worker.progress.connect(self.ai_status.setText)
        self.ai_worker.done.connect(self._ai_finished)
        self.ai_worker.start()

    def _ai_finished(self, answer, error):
        if error:
            self.ai_output.setPlainText("Request failed:\n" + error)
            self.ai_status.setText("Request failed")
            return
        self.ai_last_response = answer
        self.ai_output.setPlainText(answer)
        today = datetime.now().strftime("%Y-%m-%d")
        count = int(self.settings.value("ai/count", 0)) if self.settings.value("ai/day", "") == today else 0
        self.settings.setValue("ai/day", today)
        self.settings.setValue("ai/count", count + 1)
        self.ai_status.setText(f"Complete · {count+1} AI requests today · Remember provider usage may be billed by that provider.")

    def _insert_ai_response(self):
        if not self.ai_last_response.strip():
            QMessageBox.information(self, "Nothing to insert", "Run an AI request first.")
            return
        self.sidebar.setCurrentRow(1)
        editor = self.current_editor()
        if editor:
            editor.insertPlainText(self.ai_last_response)

    def _terminal_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>Terminal & Run</h2><p>Commands run locally with your account permissions. Only run code you trust.</p>"))
        cmd_row = QHBoxLayout()
        self.terminal_command = QLineEdit()
        self.terminal_command.setPlaceholderText("Enter a command, e.g. python --version")
        self.terminal_command.returnPressed.connect(self.run_terminal_command)
        run_cmd = QPushButton("Run Command")
        run_cmd.setObjectName("Primary")
        run_cmd.clicked.connect(self.run_terminal_command)
        run_file = QPushButton("Run Current File")
        run_file.clicked.connect(self.run_current_file)
        clear = QPushButton("Clear Output")
        clear.clicked.connect(lambda: self.terminal_output.clear())
        cmd_row.addWidget(self.terminal_command, 1)
        cmd_row.addWidget(run_cmd)
        cmd_row.addWidget(run_file)
        cmd_row.addWidget(clear)
        layout.addLayout(cmd_row)
        self.terminal_output = QPlainTextEdit()
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setPlaceholderText("Command output appears here…")
        layout.addWidget(self.terminal_output, 1)
        tip = QLabel("CodeBox uses available local runtimes and compilers (Python, Node.js, Java, C/C++, Go, Rust, PHP, Ruby, PowerShell, Bash, etc.). Install each toolchain separately; Pygments supplies broad syntax highlighting.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9ca3c8")
        layout.addWidget(tip)
        return page

    def _terminal_append(self, text):
        if hasattr(self, "terminal_output"):
            self.terminal_output.moveCursor(QTextCursor.MoveOperation.End)
            self.terminal_output.insertPlainText(text)
            self.terminal_output.moveCursor(QTextCursor.MoveOperation.End)

    def _terminal_read(self):
        data = bytes(self.terminal_process.readAllStandardOutput()).decode(errors="replace")
        self._terminal_append(data)

    def _terminal_finished(self, exit_code, exit_status):
        self._terminal_append(f"\n[Process finished with exit code {exit_code}]\n")

    def run_terminal_command(self):
        command = self.terminal_command.text().strip()
        if not command:
            return
        if self.terminal_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "Terminal busy", "Wait for the current command to finish before starting another.")
            return
        self._terminal_append(f"\n> {command}\n")
        if os.name == "nt":
            self.terminal_process.start("cmd.exe", ["/d", "/s", "/c", command])
        else:
            self.terminal_process.start("bash", ["-lc", command])
        self.terminal_command.clear()

    def run_current_file(self):
        editor = self.current_editor()
        if not editor:
            QMessageBox.information(self, "Run file", "Open a file first.")
            return
        if editor.document().isModified() or not editor.path:
            self.save_current()
        path = Path(editor.path) if editor.path else None
        if not path or not path.is_file():
            return
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm", ".svg"):
            try:
                webbrowser.open(path.resolve().as_uri())
                self._terminal_append(f"Opened in the default browser: {path}\n")
            except Exception as exc:
                self._terminal_append(f"Could not open browser: {exc}\n")
            self.sidebar.setCurrentRow(7)
            return
        if self.terminal_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "Terminal busy", "Wait for the current command to finish first.")
            return
        suffix = suffix or ""
        p = str(path.resolve())
        temp_build = Path(tempfile.gettempdir()) / "CodeBoxNexusBuild"
        temp_build.mkdir(parents=True, exist_ok=True)
        exe_out = str(temp_build / (path.stem + (".exe" if os.name == "nt" else "")))
        jar_out = str(temp_build / (path.stem + ".jar"))
        if suffix in (".py", ".pyw", ".pyi"):
            command = [sys.executable, p]
        elif suffix in (".js", ".mjs", ".cjs", ".jsx"):
            command = ["node", p]
        elif suffix in (".ts", ".tsx"):
            if shutil.which("tsx"):
                command = ["tsx", p]
            elif shutil.which("npx"):
                command = ["npx", "--yes", "tsx", p]
            else:
                command = None
        elif suffix in (".php",): command = ["php", p]
        elif suffix in (".rb", ".rake"): command = ["ruby", p]
        elif suffix in (".pl", ".pm"): command = ["perl", p]
        elif suffix == ".lua": command = ["lua", p]
        elif suffix == ".r": command = ["Rscript", p]
        elif suffix == ".go": command = ["go", "run", p]
        elif suffix == ".swift": command = ["swift", p]
        elif suffix == ".dart": command = ["dart", p]
        elif suffix in (".sh", ".bash"): command = ["bash", p]
        elif suffix in (".bat", ".cmd"): command = ["cmd.exe", "/d", "/s", "/c", p]
        elif suffix in (".ps1", ".psm1"): command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "RemoteSigned", "-File", p]
        elif suffix == ".java":
            command = ["cmd.exe", "/d", "/s", "/c", f'javac -d "{temp_build}" "{p}" && java -cp "{temp_build}" "{path.stem}"'] if os.name == "nt" else ["bash", "-lc", f'javac -d "{temp_build}" "{p}" && java -cp "{temp_build}" "{path.stem}"']
        elif suffix in (".c", ".h"):
            compiler = shutil.which("gcc") or shutil.which("clang")
            command = ["cmd.exe", "/d", "/s", "/c", f'"{compiler}" "{p}" -o "{exe_out}" && "{exe_out}"'] if compiler and os.name == "nt" else ( ["bash", "-lc", f'"{compiler}" "{p}" -o "{exe_out}" && "{exe_out}"'] if compiler else None )
        elif suffix in (".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh"):
            compiler = shutil.which("g++") or shutil.which("clang++") or shutil.which("clang++")
            command = ["cmd.exe", "/d", "/s", "/c", f'"{compiler}" -std=c++17 "{p}" -o "{exe_out}" && "{exe_out}"'] if compiler and os.name == "nt" else ( ["bash", "-lc", f'"{compiler}" -std=c++17 "{p}" -o "{exe_out}" && "{exe_out}"'] if compiler else None )
        elif suffix == ".rs":
            compiler = shutil.which("rustc")
            command = ["cmd.exe", "/d", "/s", "/c", f'"{compiler}" "{p}" -o "{exe_out}" && "{exe_out}"'] if compiler and os.name == "nt" else ( ["bash", "-lc", f'"{compiler}" "{p}" -o "{exe_out}" && "{exe_out}"'] if compiler else None )
        elif suffix in (".kt", ".kts"):
            compiler = shutil.which("kotlinc")
            command = ["cmd.exe", "/d", "/s", "/c", f'"{compiler}" "{p}" -include-runtime -d "{jar_out}" && java -jar "{jar_out}"'] if compiler and os.name == "nt" else ( ["bash", "-lc", f'"{compiler}" "{p}" -include-runtime -d "{jar_out}" && java -jar "{jar_out}"'] if compiler else None )
        elif suffix == ".sql":
            QMessageBox.information(self, "SQL file", "SQL scripts need a database connection. Configure SQLite/PostgreSQL/MySQL in the terminal or use a database client.")
            self.sidebar.setCurrentRow(7)
            return
        else:
            command = None
        if not command:
            QMessageBox.information(
                self, "Run file",
                f"Automatic run is not configured or a runtime/compiler is missing for {suffix or 'this file type'}.\n\n"
                "Install the language runtime/compiler and use the terminal command box. Pygments highlights many additional languages."
            )
            self.sidebar.setCurrentRow(7)
            return
        program, args = command[0], command[1:]
        if not shutil.which(program) and not Path(program).is_file():
            QMessageBox.warning(self, "Runtime not found", f"Could not find '{program}'. Install the runtime/compiler or add it to PATH.")
            self.sidebar.setCurrentRow(7)
            return
        self.sidebar.setCurrentRow(7)
        self._terminal_append(f"\n> {' '.join(command)}\n")
        self.terminal_process.setWorkingDirectory(str(path.parent))
        self.terminal_process.start(program, args)

    def _vault_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>Local Vault</h2><p>Your local project repository. It is stored on this computer and is separate from GitHub.</p>"))
        self.vault_path_label = QLabel(str(self.vault_dir))
        self.vault_path_label.setWordWrap(True)
        self.vault_path_label.setStyleSheet("color:#9ca3c8")
        layout.addWidget(self.vault_path_label)
        create_box = QGroupBox("Create local repository")
        cr = QHBoxLayout(create_box)
        self.vault_new_name = QLineEdit()
        self.vault_new_name.setPlaceholderText("my-project")
        self.vault_git_checkbox = QCheckBox("Initialize Git repository when Git is installed")
        self.vault_git_checkbox.setChecked(True)
        make = QPushButton("Create Repository")
        make.setObjectName("Primary")
        make.clicked.connect(self.create_local_repo)
        cr.addWidget(self.vault_new_name, 1)
        cr.addWidget(make)
        layout.addWidget(create_box)
        self.vault_git_checkbox.setStyleSheet("color:#b7bdd5")
        layout.addWidget(self.vault_git_checkbox)
        self.vault_list = QListWidget()
        layout.addWidget(self.vault_list, 1)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_vault)
        open_btn = QPushButton("Open Selected")
        open_btn.clicked.connect(self.open_vault_repo)
        save_btn = QPushButton("Save Current Editor Here")
        save_btn.clicked.connect(self.save_editor_to_vault)
        save_all_btn = QPushButton("Save All Open Editors")
        save_all_btn.clicked.connect(self.save_all_editors_to_vault)
        snapshot_btn = QPushButton("Snapshot Current Project")
        snapshot_btn.clicked.connect(self.snapshot_project)
        row.addWidget(refresh)
        row.addWidget(open_btn)
        row.addWidget(save_btn)
        row.addWidget(save_all_btn)
        row.addWidget(snapshot_btn)
        layout.addLayout(row)
        note = QLabel("The vault can initialize Git locally. It does not push to GitHub automatically. Review files before publishing, and never store API keys or .env files in repositories.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9ca3c8")
        layout.addWidget(note)
        self._refresh_vault()
        return page

    def _refresh_vault(self):
        if not hasattr(self, "vault_list"):
            return
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.vault_list.clear()
        for path in sorted(self.vault_dir.iterdir(), key=lambda x: x.name.lower()):
            if path.is_dir():
                item = QListWidgetItem("📁  " + path.name)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.vault_list.addItem(item)
        if self.vault_list.count() == 0:
            self.vault_list.addItem("No repositories yet. Create your first local repository above.")

    def _selected_vault_path(self):
        if not hasattr(self, "vault_list"):
            return None
        item = self.vault_list.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and Path(path).is_dir():
                return Path(path)
        return None

    def create_local_repo(self):
        name = self.vault_new_name.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
            QMessageBox.warning(self, "Invalid repository name", "Use 1–80 letters, numbers, dots, underscores, or hyphens.")
            return
        target = self.vault_dir / name
        if target.exists():
            QMessageBox.warning(self, "Already exists", "A local repository with that name already exists.")
            return
        try:
            target.mkdir(parents=True)
            (target / "README.md").write_text(f"# {name}\n\nCreated with CodeBox Nexus Studio.\n", encoding="utf-8")
            (target / ".gitignore").write_text(".env\n__pycache__/\n*.py[cod]\n.venv/\nvenv/\nnode_modules/\n", encoding="utf-8")
            git_note = ""
            if self.vault_git_checkbox.isChecked():
                try:
                    result = subprocess.run(["git", "init"], cwd=str(target), capture_output=True, text=True, timeout=15)
                    git_note = " Git initialized." if result.returncode == 0 else " Git was not initialized because Git is unavailable or failed."
                except Exception:
                    git_note = " Git was not initialized; you can use the folder without Git."
            self.vault_new_name.clear()
            self._refresh_vault()
            for i in range(self.vault_list.count()):
                item = self.vault_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == str(target):
                    self.vault_list.setCurrentItem(item); break
            self.statusBar().showMessage(f"Local repository created: {target}", 5000)
            QMessageBox.information(self, "Repository created", f"Created {target}.{git_note}")
        except Exception as exc:
            QMessageBox.critical(self, "Create failed", str(exc))

    def open_vault_repo(self):
        path = self._selected_vault_path()
        if not path:
            QMessageBox.information(self, "Select repository", "Select a repository from the list first.")
            return
        self.current_project = str(path)
        self.project_path_label.setText(str(path))
        self.project_tree.setRootIndex(self.fs_model.index(str(path)))
        self.settings.setValue("project/last", str(path))
        self.sidebar.setCurrentRow(2)
        self.statusBar().showMessage(f"Opened local repository: {path}", 4000)

    def save_editor_to_vault(self):
        repo = self._selected_vault_path()
        editor = self.current_editor()
        if not repo:
            QMessageBox.information(self, "Select repository", "Choose a local repository first.")
            return
        if not editor:
            QMessageBox.information(self, "No editor", "Open or create a file first.")
            return
        name = Path(editor.path).name if editor.path else "untitled.py"
        if name.lower() in {".env", "credentials.json", "id_rsa", "id_ed25519"}:
            QMessageBox.warning(self, "Sensitive filename", "This filename looks sensitive and will not be copied into the repository.")
            return
        target = repo / name
        if target.exists():
            answer = QMessageBox.question(self, "Overwrite file?", f"{target} already exists. Replace it?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            target.write_text(editor.toPlainText(), encoding="utf-8", newline="")
            self._refresh_vault()
            self.statusBar().showMessage(f"Saved to local repository: {target}", 5000)
            QMessageBox.information(self, "Saved", f"Saved the current editor contents to:\n{target}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def save_all_editors_to_vault(self):
        if not self._require_plus("Save all open editors to the local vault"):
            return
        repo = self._selected_vault_path()
        if not repo:
            QMessageBox.information(self, "Select repository", "Choose a local repository first.")
            return
        editors = []
        seen = set()
        for i in range(self.editor_tabs.count()):
            editor = self.editor_tabs.widget(i)
            if not isinstance(editor, CodeEditor):
                continue
            name = Path(editor.path).name if editor.path else f"untitled-{i+1}.py"
            if name.lower() in {".env", ".env.local", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"} or Path(name).suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
                continue
            base = name
            counter = 2
            while name.casefold() in seen:
                stem, suffix = Path(base).stem, Path(base).suffix
                name = f"{stem}-{counter}{suffix}"
                counter += 1
            seen.add(name.casefold())
            editors.append((editor, name))
        if not editors:
            QMessageBox.information(self, "Nothing to save", "There are no open editors with safe filenames to save.")
            return
        overwrites = [name for _, name in editors if (repo / name).exists()]
        note = f"Save {len(editors)} open editor(s) to {repo}?"
        if overwrites:
            note += "\n\nThe following existing files may be overwritten:\n" + "\n".join(overwrites[:12])
            if len(overwrites) > 12:
                note += f"\n…and {len(overwrites)-12} more"
        note += "\n\nReview the files before uploading them to a remote repository."
        answer = QMessageBox.question(self, "Save all open editors", note, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            for editor, name in editors:
                (repo / name).write_text(editor.toPlainText(), encoding="utf-8", newline="")
            self._refresh_vault()
            QMessageBox.information(self, "Saved", f"Saved {len(editors)} editor(s) to:\n{repo}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def snapshot_project(self):
        if not self._require_plus("Project ZIP snapshots"):
            return
        if not self.current_project or not Path(self.current_project).is_dir():
            QMessageBox.information(self, "No project", "Open a project folder first, then create a snapshot.")
            return
        src = Path(self.current_project)
        base = self.vault_dir / (src.name + "-snapshots")
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = base / f"{src.name}-{stamp}.zip"
        sensitive_names = {".env", "credentials.json", "id_rsa", "id_ed25519", "secrets.json"}
        exclude_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
        try:
            file_count = 0
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                for root, dirs, files in os.walk(src):
                    dirs[:] = [d for d in dirs if d not in exclude_dirs]
                    for filename in files:
                        if filename.lower() in sensitive_names or filename.endswith((".pem", ".key")):
                            continue
                        path = Path(root) / filename
                        try:
                            if path.stat().st_size > 25 * 1024 * 1024:
                                continue
                            archive.write(path, path.relative_to(src))
                            file_count += 1
                        except (OSError, ValueError):
                            continue
            QMessageBox.information(self, "Snapshot created", f"Saved {file_count} files to:\n{destination}\n\nCommon secret files and build folders were excluded.")
        except Exception as exc:
            QMessageBox.critical(self, "Snapshot failed", str(exc))

    def _account_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>Account, Sign-in & Plans</h2><p>Configure your own OAuth applications or SMTP account. Client IDs and service setup are required; no credentials are preloaded.</p>"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        box_layout = QVBoxLayout(content)

        state_box = QGroupBox("Current local session")
        sl = QVBoxLayout(state_box)
        self.account_status = QLabel(self._account_status_text())
        self.account_status.setWordWrap(True)
        sl.addWidget(self.account_status)
        logout = QPushButton("Sign Out of Local Session")
        logout.clicked.connect(self.sign_out)
        sl.addWidget(logout)
        box_layout.addWidget(state_box)

        oauth_box = QGroupBox("Google & GitHub OAuth")
        of = QFormLayout(oauth_box)
        self.github_oauth_id = QLineEdit(self.settings.value("oauth/github_client_id", ""))
        self.google_oauth_id = QLineEdit(self.settings.value("oauth/google_client_id", ""))
        self.google_oauth_secret = QLineEdit()
        self.google_oauth_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.google_oauth_secret.setPlaceholderText("Google OAuth client secret (stored in keyring if available)")
        saved_secret = self._secret_get("oauth_google_client_secret")
        if saved_secret:
            self.google_oauth_secret.setPlaceholderText("Saved secret loaded; enter a new one only to replace it")
        of.addRow("GitHub OAuth Client ID", self.github_oauth_id)
        of.addRow("Google OAuth Client ID", self.google_oauth_id)
        of.addRow("Google OAuth Client Secret", self.google_oauth_secret)
        oauth_buttons = QHBoxLayout()
        save_oauth = QPushButton("Save OAuth Settings")
        save_oauth.clicked.connect(self.save_oauth_settings)
        gh_login = QPushButton("Sign in with GitHub")
        gh_login.setObjectName("Primary")
        gh_login.clicked.connect(lambda: self.start_oauth("github"))
        google_login = QPushButton("Sign in with Google")
        google_login.clicked.connect(lambda: self.start_oauth("google"))
        oauth_buttons.addWidget(save_oauth)
        oauth_buttons.addWidget(gh_login)
        oauth_buttons.addWidget(google_login)
        of.addRow("", oauth_buttons)
        self.oauth_status = QLabel("GitHub: create an OAuth App and enable Device Flow. Google: create an OAuth client for a desktop/loopback app and configure the consent screen.")
        self.oauth_status.setWordWrap(True)
        self.oauth_status.setStyleSheet("color:#9ca3c8")
        of.addRow("Status", self.oauth_status)
        box_layout.addWidget(oauth_box)

        email_box = QGroupBox("Email verification code (SMTP)")
        ef = QFormLayout(email_box)
        self.smtp_host = QLineEdit(self.settings.value("smtp/host", "smtp.gmail.com"))
        self.smtp_port = QLineEdit(str(self.settings.value("smtp/port", "587")))
        self.smtp_sender = QLineEdit(self.settings.value("smtp/sender", ""))
        self.smtp_user = QLineEdit(self.settings.value("smtp/user", ""))
        self.smtp_password = QLineEdit()
        self.smtp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.smtp_password.setPlaceholderText("App password; stored in keyring if available")
        self.email_address = QLineEdit()
        self.email_address.setPlaceholderText("you@example.com")
        self.email_code = QLineEdit()
        self.email_code.setMaxLength(6)
        self.email_code.setPlaceholderText("6-digit code from your email")
        ef.addRow("SMTP Host", self.smtp_host)
        ef.addRow("SMTP Port", self.smtp_port)
        ef.addRow("Sender Email", self.smtp_sender)
        ef.addRow("SMTP Username", self.smtp_user)
        ef.addRow("SMTP Password / App Password", self.smtp_password)
        ef.addRow("Sign-in Email", self.email_address)
        ef.addRow("Verification Code", self.email_code)
        mail_buttons = QHBoxLayout()
        save_smtp = QPushButton("Save SMTP Settings")
        save_smtp.clicked.connect(self.save_smtp_settings)
        send_code = QPushButton("Send Verification Code")
        send_code.setObjectName("Primary")
        send_code.clicked.connect(self.send_email_code)
        verify_code = QPushButton("Verify & Sign In")
        verify_code.clicked.connect(self.verify_email_code)
        mail_buttons.addWidget(save_smtp)
        mail_buttons.addWidget(send_code)
        mail_buttons.addWidget(verify_code)
        ef.addRow("", mail_buttons)
        self.email_status = QLabel("SMTP delivery requires a mail provider. For Gmail, use an App Password, not your normal account password. This verifies a local desktop session; shared accounts require a backend.")
        self.email_status.setWordWrap(True)
        self.email_status.setStyleSheet("color:#9ca3c8")
        ef.addRow("Status", self.email_status)
        box_layout.addWidget(email_box)

        plans = QGroupBox("Free vs Plus")
        pl = QHBoxLayout(plans)
        free = QVBoxLayout()
        free.addWidget(QLabel("<h3>Free</h3><p>Editor, terminal, local vault, GitHub tools, learning and limited AI.</p>"))
        choose_free = QPushButton("Use Free")
        choose_free.clicked.connect(lambda: self.choose_plan("Free"))
        free.addWidget(choose_free)
        plus = QVBoxLayout()
        plus.addWidget(QLabel("<h3>Plus</h3><p>Plus-only actions require an active account entitlement confirmed by the shared CodeBox server.</p>"))
        choose_plus = QPushButton("Plus Active" if self._is_plus() else "Locked · Activate on Website")
        choose_plus.setEnabled(False)
        choose_plus.setToolTip("Plan status is controlled by the CodeBox account server, not by a local preview switch.")
        plus.addWidget(choose_plus)
        pl.addLayout(free)
        pl.addLayout(plus)
        box_layout.addWidget(plans)
        disclaimer = QLabel("Plus downloads are server-gated. Paid billing is not connected yet; a real commercial launch needs a payment provider and webhook-based entitlement updates. Do not treat this local app as a secure code sandbox.")
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color:#fbbf24;background:#252216;border-radius:7px;padding:10px")
        box_layout.addWidget(disclaimer)
        box_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def _account_status_text(self):
        who = self.signed_in_user or "Not signed in"
        provider = self.signed_in_provider or "local"
        return f"Account: {who}\nProvider: {provider}\nEdition: {self.plan}"

    def _refresh_account_status(self):
        if hasattr(self, "account_status"):
            self.account_status.setText(self._account_status_text())
        if hasattr(self, "sidebar_tier_label"):
            self.sidebar_tier_label.setText("PLUS ACTIVE" if self._is_plus() else "FREE EDITION")

    def _is_plus(self):
        # The edition granted by the server is checked at login. The Plus build is
        # still only a client; paid distribution should also validate entitlement server-side.
        return APP_BUILD_EDITION == "Plus" and self.server_plan == "plus" and "Plus" in str(self.plan)

    def _require_plus(self, feature_name):
        # Re-check the server entitlement before protected actions, so revocation/expiry
        # takes effect without trusting a local checkbox or saved UI preference.
        if APP_BUILD_EDITION == "Plus" and self.auth_session.get("token") and requests is not None:
            try:
                response = requests.get(
                    self.auth_api_base + "/api/me",
                    headers={"Authorization": "Bearer " + self.auth_session["token"]},
                    timeout=8,
                )
                if response.ok:
                    data = response.json().get("user", {})
                    self.server_plan = str(data.get("plan", "free")).lower()
                    self.plan = "Plus" if self.server_plan == "plus" else "Free"
                    self._refresh_account_status()
                    if self.server_plan == "plus":
                        return True
                else:
                    self.server_plan = "free"
                    self.plan = "Free"
                    self._refresh_account_status()
            except Exception:
                QMessageBox.warning(self, "Entitlement check failed", "Could not verify Plus access with the CodeBox server. Connect to the server and retry.")
                return False
        QMessageBox.information(
            self, "Plus feature locked",
            f"{feature_name} requires an active CodeBox Plus account.\n\n"
            "Sign in with an account that has Plus enabled on the CodeBox server."
        )
        return False

    def choose_plan(self, plan):
        if "Plus" in str(plan):
            if APP_BUILD_EDITION != "Plus" or self.server_plan != "plus":
                QMessageBox.information(
                    self, "Plus locked",
                    "Plus is locked for this account or build. You cannot unlock a paid plan from the app UI.\n\n"
                    "Sign in on the CodeBox website and activate a valid Plus entitlement."
                )
                return
            self.plan = "Plus"
        else:
            self.plan = "Free"
        self.settings.setValue("account/plan", self.plan)
        self._refresh_account_status()
        QMessageBox.information(self, "Edition", f"Current edition: {self.plan}")

    def save_oauth_settings(self):
        self.settings.setValue("oauth/github_client_id", self.github_oauth_id.text().strip())
        self.settings.setValue("oauth/google_client_id", self.google_oauth_id.text().strip())
        secret = self.google_oauth_secret.text().strip()
        if secret:
            stored = self._secret_set("oauth_google_client_secret", secret)
            self.google_oauth_secret.clear()
            self.google_oauth_secret.setPlaceholderText("Saved secret in OS keyring" if stored else "Secret kept in memory for this session only")
        QMessageBox.information(self, "OAuth settings", "Client IDs saved. The Google client secret is stored through the OS keyring when available; it is never written into the Python source.")

    def start_oauth(self, provider):
        if self.oauth_worker and self.oauth_worker.isRunning():
            QMessageBox.information(self, "Sign-in running", "Finish or cancel the current sign-in in your browser first.")
            return
        if provider == "github":
            client_id = self.github_oauth_id.text().strip()
            secret = ""
        else:
            client_id = self.google_oauth_id.text().strip()
            secret = self.google_oauth_secret.text().strip() or self._secret_get("oauth_google_client_secret")
        if not client_id or (provider == "google" and not secret):
            QMessageBox.warning(self, "OAuth settings required", "Enter the OAuth Client ID" + (" and Google Client Secret" if provider == "google" else "") + ", then click Save OAuth Settings.")
            return
        self.save_oauth_settings()
        self.oauth_status.setText(f"Starting {provider.title()} authorization…")
        self.oauth_worker = OAuthWorker(provider, client_id, secret, self)
        self.oauth_worker.progress.connect(self.oauth_status.setText)
        self.oauth_worker.done.connect(self._oauth_finished)
        self.oauth_worker.start()

    def _oauth_finished(self, data, error):
        if error:
            self.oauth_status.setText("Sign-in failed: " + error)
            QMessageBox.warning(self, "Sign-in failed", error)
            return
        provider = data.get("provider", "OAuth")
        user = data.get("user", {})
        if provider == "github":
            self.github_token = data.get("token", "")
            self.github_user = user
            self._store_keyring_token(self.github_token)
            if hasattr(self, "token_edit"):
                self.token_edit.setText(self.github_token)
            if hasattr(self, "github_status"):
                self.github_status.setText(f"Connected as @{user.get('login', 'unknown')}")
            self.card_github.setText("Connected")
            self._run_github("repos")
            self.signed_in_user = "@" + user.get("login", "GitHub user")
        else:
            self.signed_in_user = data.get("email") or user.get("name") or "Google user"
        self.signed_in_provider = provider.title()
        self.settings.setValue("account/user", self.signed_in_user)
        self.settings.setValue("account/provider", self.signed_in_provider)
        self._refresh_account_status()
        self._refresh_achievements()
        self.oauth_status.setText(f"Signed in with {provider.title()} as {self.signed_in_user}.")
        QMessageBox.information(self, "Sign-in successful", f"Signed in with {provider.title()} as {self.signed_in_user}.")

    def save_smtp_settings(self):
        host = self.smtp_host.text().strip()
        sender = self.smtp_sender.text().strip()
        username = self.smtp_user.text().strip()
        try:
            port = int(self.smtp_port.text().strip())
            if not (1 <= port <= 65535): raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Invalid SMTP port", "Enter a port number between 1 and 65535.")
            return
        if not host or not sender or not username:
            QMessageBox.warning(self, "Missing settings", "SMTP Host, Sender Email, and SMTP Username are required.")
            return
        self.settings.setValue("smtp/host", host)
        self.settings.setValue("smtp/port", str(port))
        self.settings.setValue("smtp/sender", sender)
        self.settings.setValue("smtp/user", username)
        password = self.smtp_password.text().strip()
        stored = self._secret_set("smtp_password", password) if password else bool(self._secret_get("smtp_password"))
        self.email_status.setText("SMTP settings saved. Password stored in OS keyring." if stored else "SMTP settings saved; no keyring password is available. Enter the password at send time or install keyring.")
        if password:
            self.smtp_password.clear()

    def send_email_code(self):
        if self.email_worker and self.email_worker.isRunning():
            QMessageBox.information(self, "Please wait", "An email is already being sent.")
            return
        email = self.email_address.text().strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            QMessageBox.warning(self, "Invalid email", "Enter a valid email address.")
            return
        if self.email_otp and self.email_otp.get("email") == email and time.time() - self.email_otp.get("sent_at", 0) < 60:
            remaining = 60 - int(time.time() - self.email_otp.get("sent_at", 0))
            QMessageBox.information(self, "Resend cooldown", f"Wait {remaining} seconds before requesting another code.")
            return
        host = self.smtp_host.text().strip()
        sender = self.smtp_sender.text().strip()
        username = self.smtp_user.text().strip()
        try: port = int(self.smtp_port.text().strip())
        except Exception:
            QMessageBox.warning(self, "Invalid SMTP port", "Enter a valid SMTP port."); return
        password = self.smtp_password.text().strip() or self._secret_get("smtp_password")
        if not host or not sender or not username or not password:
            QMessageBox.warning(self, "SMTP setup incomplete", "Configure SMTP host, sender, username, and password. For Gmail, use a Google App Password.")
            return
        self.save_smtp_settings()
        code = f"{secrets.randbelow(1000000):06d}"
        self.pending_email_code = code
        self.pending_email_address = email
        self.email_status.setText("Sending a verification email…")
        self.email_worker = EmailSendWorker(host, port, username, password, sender, email, code, self)
        self.email_worker.done.connect(self._email_send_finished)
        self.email_worker.start()

    def _email_send_finished(self, success, message):
        if not success:
            self.pending_email_code = ""
            self.email_status.setText("Email delivery failed: " + message)
            QMessageBox.warning(self, "Email delivery failed", message)
            return
        self.email_otp = {"email": self.pending_email_address,
                          "hash": hashlib.sha256(self.pending_email_code.encode()).hexdigest(),
                          "expires": time.time() + 300, "attempts": 0, "sent_at": time.time()}
        self.pending_email_code = ""
        self.email_status.setText("Verification code sent. It expires in 5 minutes and allows up to 5 attempts.")
        QMessageBox.information(self, "Code sent", "Check your inbox and spam folder for the CodeBox verification code.")

    def verify_email_code(self):
        email = self.email_address.text().strip()
        code = self.email_code.text().strip()
        record = self.email_otp
        if not record or record.get("email") != email:
            QMessageBox.warning(self, "Request a code first", "Send a verification code to this email address first.")
            return
        if time.time() > record.get("expires", 0):
            self.email_otp = None
            self.email_status.setText("That code expired. Request a new one.")
            QMessageBox.warning(self, "Code expired", "Request a new verification code.")
            return
        if record["attempts"] >= 5:
            self.email_otp = None
            QMessageBox.warning(self, "Too many attempts", "This code has been disabled. Request a new code.")
            return
        record["attempts"] += 1
        digest = hashlib.sha256(code.encode()).hexdigest()
        if not hmac.compare_digest(digest, record["hash"]):
            self.email_status.setText(f"Incorrect code. Attempts remaining: {max(0, 5-record['attempts'])}")
            QMessageBox.warning(self, "Incorrect code", "The verification code does not match.")
            return
        self.signed_in_user = email
        self.signed_in_provider = "Email OTP (local session)"
        self.settings.setValue("account/user", self.signed_in_user)
        self.settings.setValue("account/provider", self.signed_in_provider)
        self.email_otp = None
        self.email_code.clear()
        self._refresh_account_status()
        self.email_status.setText("Email verified for this local app session.")
        QMessageBox.information(self, "Signed in", f"Email verified: {email}\n\nThis session is local to this installation; shared accounts require a backend.")

    def sign_out(self):
        self.signed_in_user = ""
        self.signed_in_provider = ""
        self.settings.setValue("account/user", "")
        self.settings.setValue("account/provider", "")
        self._refresh_account_status()
        QMessageBox.information(self, "Signed out", "The local CodeBox session has been signed out. Your GitHub token remains saved until you clear it separately.")

    def _settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h2>Settings & Privacy</h2>"))
        box = QGroupBox("Application")
        bl = QVBoxLayout(box)
        settings_btn = QPushButton("Editor and credential settings")
        settings_btn.clicked.connect(self.open_settings_dialog)
        export_btn = QPushButton("Export learning progress")
        export_btn.clicked.connect(self.export_progress)
        clear_progress = QPushButton("Reset learning progress")
        clear_progress.clicked.connect(self.reset_progress)
        bl.addWidget(settings_btn)
        bl.addWidget(export_btn)
        bl.addWidget(clear_progress)
        layout.addWidget(box)
        security = QGroupBox("Security notes")
        sl = QVBoxLayout(security)
        sl.addWidget(QLabel(
            "• API keys are never embedded in source code. OS keyring storage is recommended.\n"
            "• The terminal runs arbitrary local commands with your account permissions. Run only code you trust.\n"
            "• Review files before uploading them to a remote repository.\n"
            "• OAuth requires credentials configured by you in the provider console.\n"
            "• Email OTP uses your SMTP provider and is local-session verification; shared accounts need a backend.\n"
            "• Plus is a development preview, not a verified subscription or payment system."
        ))
        layout.addWidget(security)
        layout.addStretch()
        return page

    def _add_editor(self, path, text):
        editor = CodeEditor(path)
        editor.cursorPositionChanged.connect(self._update_editor_cursor_status)
        editor.setPlainText(text)
        editor.document().setModified(False)
        editor.setFont(QFont("Consolas", int(self.settings.value("editor/font_size", 11))))
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if self.settings.value("editor/wrap", False, type=bool) else QPlainTextEdit.LineWrapMode.NoWrap)
        label = Path(path).name if path else "Untitled"
        index = self.editor_tabs.addTab(editor, label)
        self.editor_tabs.setCurrentIndex(index)
        editor.document().modificationChanged.connect(lambda modified, e=editor: self._mark_tab(e, modified))
        self._editor_changed(index)
        return editor

    def _mark_tab(self, editor, modified):
        idx = self.editor_tabs.indexOf(editor)
        if idx >= 0:
            name = Path(editor.path).name if editor.path else "Untitled"
            self.editor_tabs.setTabText(idx, ("● " if modified else "") + name)

    def current_editor(self):
        widget = self.editor_tabs.currentWidget() if hasattr(self, "editor_tabs") else None
        return widget if isinstance(widget, CodeEditor) else None

    def _update_editor_cursor_status(self):
        editor = self.current_editor()
        if editor:
            cursor = editor.textCursor()
            self.statusBar().showMessage(
                f"Line {cursor.blockNumber() + 1} · Column {cursor.positionInBlock() + 1}"
            )

    def _editor_changed(self, index):
        editor = self.current_editor()
        if editor:
            self.editor_hint.setText(editor.path or "Untitled · unsaved file")
            self.statusBar().showMessage(f"Line {editor.textCursor().blockNumber()+1} · Column {editor.textCursor().positionInBlock()+1}")
            self.card_projects.setText(str(self.editor_tabs.count()) if hasattr(self, "card_projects") else "0")

    def new_file(self):
        self.sidebar.setCurrentRow(1)
        self._add_editor(None, "")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open File", self.current_project or str(Path.home()), "All files (*.*)")
        if not path:
            return
        self.open_path(path)

    def open_path(self, path):
        path = str(Path(path))
        for i in range(self.editor_tabs.count()):
            ed = self.editor_tabs.widget(i)
            if isinstance(ed, CodeEditor) and ed.path == path:
                self.sidebar.setCurrentRow(1)
                self.editor_tabs.setCurrentIndex(i)
                return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            QMessageBox.warning(self, "Cannot open as text", "This file does not appear to be UTF-8 text.")
            return
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.sidebar.setCurrentRow(1)
        self._add_editor(path, content)
        self._remember_file(path)

    def save_current(self):
        editor = self.current_editor()
        if not editor:
            return
        path = editor.path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save File", str(Path.home() / "untitled.py"), "All files (*.*)")
            if not path:
                return
            editor.set_path(path)
        try:
            Path(path).write_text(editor.toPlainText(), encoding="utf-8", newline="")
            editor.document().setModified(False)
            self._mark_tab(editor, False)
            self.editor_hint.setText(path)
            self._remember_file(path)
            self.statusBar().showMessage(f"Saved: {path}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def close_tab(self, index):
        editor = self.editor_tabs.widget(index)
        if isinstance(editor, CodeEditor) and editor.document().isModified():
            answer = QMessageBox.question(self, "Unsaved changes", "Save changes before closing this tab?",
                                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save:
                self.editor_tabs.setCurrentIndex(index)
                self.save_current()
                if editor.document().isModified():
                    return
        self.editor_tabs.removeTab(index)
        if self.editor_tabs.count() == 0:
            self._add_editor(None, "")

    def find_text(self):
        editor = self.current_editor()
        if not editor:
            return
        text, ok = QInputDialog.getText(self, "Find", "Text to find:")
        if not ok or not text:
            return
        if not editor.find(text):
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            editor.setTextCursor(cursor)
            if not editor.find(text):
                QMessageBox.information(self, "Find", "No match found.")

    def replace_text(self):
        editor = self.current_editor()
        if not editor:
            return
        find, ok = QInputDialog.getText(self, "Replace", "Find:")
        if not ok or not find:
            return
        replace, ok = QInputDialog.getText(self, "Replace", "Replace with:")
        if not ok:
            return
        content = editor.toPlainText()
        editor.setPlainText(content.replace(find, replace))

    def open_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Project Folder", self.current_project or str(Path.home()))
        if not folder:
            return
        self.current_project = folder
        self.project_path_label.setText(folder)
        self.project_tree.setRootIndex(self.fs_model.index(folder))
        self.sidebar.setCurrentRow(2)
        self.settings.setValue("project/last", folder)
        self.statusBar().showMessage(f"Project opened: {folder}", 4000)

    def refresh_project(self):
        if self.current_project:
            self.fs_model.setRootPath("")
            self.fs_model.setRootPath(self.current_project)
            self.project_tree.setRootIndex(self.fs_model.index(self.current_project))

    def _project_item_open(self, index):
        path = self.fs_model.filePath(index)
        if Path(path).is_file():
            self.open_path(path)

    def _remember_file(self, path):
        recent = self.settings.value("recent/files", [])
        if isinstance(recent, str):
            recent = [recent]
        recent = [p for p in recent if p != path]
        recent.insert(0, path)
        self.settings.setValue("recent/files", recent[:12])
        if hasattr(self, "card_projects"):
            self.card_projects.setText(str(self.editor_tabs.count()))

    def _restore_recent_files(self):
        recent = self.settings.value("recent/files", [])
        if isinstance(recent, str):
            recent = [recent]
        self.recent_files = [p for p in recent if Path(p).is_file()]
        last = self.settings.value("project/last", "")
        if last and Path(last).is_dir():
            self.current_project = last
            self.project_path_label.setText(last)
            self.project_tree.setRootIndex(self.fs_model.index(last))

    def connect_github(self):
        token = self.token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "Token required", "Create a GitHub Personal Access Token on GitHub and paste it here. Never share it.")
            return
        self.github_token = token
        self._run_github("user")

    def clear_github_token(self):
        self.github_token = ""
        self.token_edit.clear()
        self._store_keyring_token("")
        self.github_status.setText("Token cleared.")
        self.github_user = None
        self.repos = []
        self.repo_list.clear()
        self.card_github.setText("Offline")

    def _run_github(self, operation, **kwargs):
        if not self.github_token:
            QMessageBox.warning(self, "Not connected", "Enter your GitHub token and press Connect first.")
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Please wait", "A GitHub operation is already running.")
            return
        self.github_progress.setRange(0, 0)
        self.worker = GitHubWorker(operation, self.github_token, **kwargs)
        self.worker.progress.connect(self.github_status.setText)
        self.worker.done.connect(lambda data, error, op=operation: self._github_finished(op, data, error))
        self.worker.start()

    def _github_finished(self, operation, data, error):
        self.github_progress.setRange(0, 1)
        self.github_progress.setValue(1)
        if error:
            self.github_status.setText("Operation failed.")
            QMessageBox.critical(self, "GitHub operation failed", error)
            return
        if operation == "user":
            self.github_user = data
            self.github_status.setText(f"Connected as @{data.get('login', 'unknown')}")
            self.card_github.setText("Connected")
            self._store_keyring_token(self.github_token)
            self.load_repos()
        elif operation == "repos":
            self.repos = data or []
            self.repo_list.clear()
            for repo in self.repos:
                item = QListWidgetItem(("🔒 " if repo.get("private") else "🌐 ") + repo.get("full_name", repo.get("name", "repository")))
                item.setData(Qt.ItemDataRole.UserRole, repo)
                self.repo_list.addItem(item)
            self.github_status.setText(f"Loaded {len(self.repos)} repositories.")
        elif operation == "create_repo":
            QMessageBox.information(self, "Repository created", f"GitHub confirmed creation of {data.get('full_name', data.get('name'))}.")
            self.load_repos()
        elif operation == "upload":
            html = data.get("content", {}).get("html_url", "")
            QMessageBox.information(self, "Upload successful", f"GitHub confirmed the commit.\n\n{html}")
            self.github_status.setText("Upload completed successfully.")
        elif operation == "upload_folder":
            count = data.get("uploaded_count", "some")
            commit_url = data.get("commit_url", "")
            QMessageBox.information(self, "Folder uploaded", f"GitHub accepted the folder commit. Files uploaded: {count}\n{commit_url}")
            self.github_status.setText(f"Folder commit completed · {count} files.")
        elif operation == "download_repo_zip":
            QMessageBox.information(self, "Repository downloaded", f"Downloaded {data.get('files', 0)} files to:\n{data.get('destination', '')}")
            self.github_status.setText("Repository ZIP downloaded.")

    def load_repos(self):
        self._run_github("repos")

    def _repo_selected(self, current, previous=None):
        if not current:
            return
        repo = current.data(Qt.ItemDataRole.UserRole)
        if not repo:
            return
        self.repo_detail.setText(
            f"<b>{repo.get('full_name')}</b><br>"
            f"{repo.get('description') or 'No description'}<br><br>"
            f"Visibility: {'Private' if repo.get('private') else 'Public'}<br>"
            f"Default branch: {repo.get('default_branch', 'unknown')}<br>"
            f"Updated: {repo.get('updated_at', 'unknown')}<br>"
            f"<a href='{repo.get('html_url', '')}'>Open on GitHub</a>"
        )
        self.repo_detail.setOpenExternalLinks(True)

    def create_repo(self):
        name = self.new_repo_name.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name):
            QMessageBox.warning(self, "Invalid name", "Use 1–100 letters, numbers, dots, underscores, or hyphens.")
            return
        self._run_github("create_repo", name=name, description=self.new_repo_desc.text().strip(), private=self.new_repo_private.isChecked())

    def choose_upload_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose file to upload", self.current_project or str(Path.home()), "All files (*.*)")
        if path:
            self.upload_local_path.setText(path)
            if not self.upload_remote_path.text().strip():
                self.upload_remote_path.setText(Path(path).name)

    def choose_upload_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose project folder to upload", self.current_project or str(Path.home()))
        if folder:
            self.upload_folder_path.setText(folder)
            if not self.upload_folder_remote_root.text().strip():
                self.upload_folder_remote_root.setText(Path(folder).name)

    def upload_folder(self):
        if not self._require_plus("Multi-file GitHub commits"):
            return
        current = self.repo_list.currentItem()
        if not current:
            QMessageBox.warning(self, "Select repository", "Select a GitHub repository first.")
            return
        repo = current.data(Qt.ItemDataRole.UserRole)
        local_path = Path(self.upload_folder_path.text().strip())
        if not local_path.is_dir():
            QMessageBox.warning(self, "Choose folder", "Choose an existing local project folder.")
            return
        remote_root = self.upload_folder_remote_root.text().strip().strip("/")
        if remote_root and (".." in Path(remote_root).parts or remote_root.startswith("/")):
            QMessageBox.warning(self, "Invalid remote path", "Use a safe relative repository path.")
            return
        branch = self.upload_folder_branch.text().strip() or repo.get("default_branch", "main")
        excluded_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
        excluded_names = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
        candidates = []
        for root, dirs, names in os.walk(local_path):
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            for name in names:
                file_path = Path(root) / name
                if name.lower() not in excluded_names and file_path.suffix.lower() not in {".pem", ".key", ".p12", ".pfx"}:
                    try:
                        if file_path.stat().st_size <= 10 * 1024 * 1024:
                            candidates.append(file_path)
                    except OSError:
                        pass
        if len(candidates) > 100:
            QMessageBox.warning(self, "Folder too large", f"The GitHub uploader supports up to 100 files per folder commit. This folder has {len(candidates)} eligible files.")
            return
        answer = QMessageBox.warning(self, "Confirm folder upload",
            f"Upload {len(candidates)} eligible files from:\n{local_path}\n\nTo repository:\n{repo.get('full_name')}\nBranch: {branch}\nRemote root: {remote_root or '/'}\n\nSecret-looking files, build folders and files over 10 MB are excluded. Review your project before continuing.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        owner, name = repo["full_name"].split("/", 1)
        self._run_github("upload_folder", owner=owner, repo=name, local_path=str(local_path),
                         branch=branch, remote_root=remote_root,
                         message=self.upload_folder_commit.text().strip())

    def download_selected_repo(self):
        if not self._require_plus("Repository ZIP downloads"):
            return
        current = self.repo_list.currentItem()
        if not current:
            QMessageBox.information(self, "Select repository", "Select a GitHub repository first.")
            return
        repo = current.data(Qt.ItemDataRole.UserRole)
        dest = QFileDialog.getExistingDirectory(self, "Choose destination parent folder", self.current_project or str(Path.home()))
        if not dest:
            return
        target = Path(dest) / repo.get("name", "github-project")
        if target.exists() and any(target.iterdir()):
            QMessageBox.warning(self, "Destination not empty", f"Destination already exists and is not empty:\n{target}")
            return
        owner, name = repo["full_name"].split("/", 1)
        self._run_github("download_repo_zip", owner=owner, repo=name,
                         branch=repo.get("default_branch", "main"), destination=str(target))

    def upload_file(self):
        current = self.repo_list.currentItem()
        if not current:
            QMessageBox.warning(self, "Select repository", "Select a repository first.")
            return
        repo = current.data(Qt.ItemDataRole.UserRole)
        local_path = self.upload_local_path.text().strip()
        remote_path = self.upload_remote_path.text().strip()
        if not local_path or not Path(local_path).is_file():
            QMessageBox.warning(self, "Choose file", "Choose an existing local file.")
            return
        if not remote_path or remote_path.startswith("/") or ".." in Path(remote_path).parts:
            QMessageBox.warning(self, "Invalid destination", "Enter a safe repository-relative path such as src/main.py.")
            return
        if Path(local_path).name.lower() in {".env", "credentials.json", "id_rsa", "id_ed25519"}:
            answer = QMessageBox.warning(self, "Potentially sensitive file",
                "This filename may contain secrets. Are you absolutely sure you want to upload it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        answer = QMessageBox.question(self, "Confirm upload",
            f"Upload this local file?\n\n{local_path}\n\nTo:\n{repo.get('full_name')}/{remote_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        owner, name = repo["full_name"].split("/", 1)
        self._run_github("upload", owner=owner, repo=name, repo_path=remote_path,
                         local_path=local_path, branch=self.upload_branch.text().strip(),
                         message=self.upload_commit.text().strip())

    def open_lesson(self, title):
        lesson = next((x for x in LESSONS if x.title == title), None)
        if not lesson:
            return
        dialog = LessonDialog(lesson, title in self.completed_lessons, self)
        dialog.completed.connect(self.lesson_completed)
        dialog.exec()
        self._refresh_learning_stats()
        self._refresh_achievements()
        self._refresh_lesson_list()

    def open_selected_lesson(self):
        item = self.lesson_list.currentItem()
        if item:
            self.open_lesson(item.data(Qt.ItemDataRole.UserRole))

    def review_completed(self):
        done = [x for x in LESSONS if x.title in self.completed_lessons]
        if not done:
            QMessageBox.information(self, "Review", "Complete a lesson first, and it will appear here.")
            return
        menu, ok = QInputDialog.getItem(self, "Review completed lesson", "Choose lesson:", [x.title for x in done], 0, False)
        if ok and menu:
            self.open_lesson(menu)

    def lesson_completed(self, title, xp):
        if title not in self.completed_lessons:
            self.completed_lessons.add(title)
            self.xp += xp
            self.settings.setValue("learning/completed", sorted(self.completed_lessons))
            self.settings.setValue("learning/xp", self.xp)
            self._refresh_learning_stats()
            self._refresh_lesson_list()
            self._refresh_achievements()
            self.statusBar().showMessage(f"Lesson completed: +{xp} XP", 5000)

    def _refresh_learning_stats(self):
        if hasattr(self, "learning_xp_label"):
            self.learning_xp_label.setText(f"⭐ {self.xp} XP")
            self.learning_done_label.setText(f"✓ {len(self.completed_lessons)} lessons completed")
            self.card_xp.setText(str(self.xp))
            self.card_lessons.setText(str(len(self.completed_lessons)))

    def _refresh_lesson_list(self):
        if not hasattr(self, "lesson_list"):
            return
        for i in range(self.lesson_list.count()):
            item = self.lesson_list.item(i)
            title = item.data(Qt.ItemDataRole.UserRole)
            lesson = next((x for x in LESSONS if x.title == title), None)
            if lesson:
                item.setText(f"{'✓ ' if title in self.completed_lessons else '◇ '}{lesson.title}   ·   {lesson.level}   ·   {lesson.xp} XP")

    def _refresh_achievements(self):
        if not hasattr(self, "achievement_list"):
            return
        self.achievement_list.clear()
        achievements = [
            ("First Steps", len(self.completed_lessons) >= 1, "Complete your first lesson"),
            ("Curious Coder", len(self.completed_lessons) >= 3, "Complete 3 lessons"),
            ("Learning Explorer", len(self.completed_lessons) >= 5, "Complete 5 lessons"),
            ("XP Collector", self.xp >= 100, "Earn at least 100 XP"),
            ("Dedicated Learner", len(self.completed_lessons) >= 8, "Complete 8 bundled lessons"),
            ("GitHub Connected", bool(self.github_user), "Connect a GitHub account"),
            ("Project Opener", bool(self.current_project), "Open a local project folder"),
            ("Code Editor", any(isinstance(self.editor_tabs.widget(i), CodeEditor) and self.editor_tabs.widget(i).document().toPlainText() for i in range(self.editor_tabs.count())), "Write or open code")
        ]
        for title, unlocked, description in achievements:
            self.achievement_list.addItem(f"{'🏆' if unlocked else '🔒'} {title} — {description}")

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for i in range(self.editor_tabs.count()):
                editor = self.editor_tabs.widget(i)
                if isinstance(editor, CodeEditor):
                    editor.setFont(QFont("Consolas", int(self.settings.value("editor/font_size", 11))))
                    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if self.settings.value("editor/wrap", False, type=bool) else QPlainTextEdit.LineWrapMode.NoWrap)
            if not self.settings.value("github/save_token", True, type=bool):
                self._store_keyring_token("")
            QMessageBox.information(self, "Settings saved", "Settings saved.")

    def export_progress(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export learning progress", str(Path.home() / "codebox-progress.json"), "JSON files (*.json)")
        if not path:
            return
        data = {"app": APP_NAME, "xp": self.xp, "completed_lessons": sorted(self.completed_lessons)}
        try:
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            QMessageBox.information(self, "Export complete", f"Progress exported to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def reset_progress(self):
        answer = QMessageBox.warning(self, "Reset progress", "This permanently resets local XP and lesson completion. Continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.xp = 0
        self.completed_lessons.clear()
        self.settings.setValue("learning/completed", [])
        self.settings.setValue("learning/xp", 0)
        self._refresh_learning_stats()
        self._refresh_lesson_list()
        self._refresh_achievements()

    def closeEvent(self, event):
        modified = []
        for i in range(self.editor_tabs.count()):
            ed = self.editor_tabs.widget(i)
            if isinstance(ed, CodeEditor) and ed.document().isModified():
                modified.append(ed)
        if modified:
            answer = QMessageBox.question(self, "Unsaved files", "Some tabs have unsaved changes. Close anyway?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        try:
            token = self.auth_session.get("token")
            if token and requests is not None:
                requests.post(self.auth_api_base + "/api/logout", headers={"Authorization": "Bearer " + token}, timeout=2)
        except Exception:
            pass
        event.accept()


class DesktopOAuthWorker(QThread):
    """Desktop OAuth hand-off via a one-time code on loopback; never embeds provider secrets."""
    done = Signal(object, str)
    status = Signal(str)

    def __init__(self, provider, api_base, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.api_base = api_base.rstrip("/")

    def run(self):
        if requests is None:
            self.done.emit(None, "Install requests first: py -m pip install requests")
            return
        result = {"code": None}
        event = threading.Event()
        local_state = secrets.token_urlsafe(16)
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self_inner):
                    parsed = urllib.parse.urlparse(self_inner.path)
                    query = urllib.parse.parse_qs(parsed.query)
                    code = (query.get("code") or [None])[0]
                    if parsed.path == "/oauth/callback" and code:
                        result["code"] = code
                        body = b"CodeBox sign-in received. You can close this browser tab and return to CodeBox."
                        self_inner.send_response(200)
                        self_inner.send_header("Content-Type", "text/plain; charset=utf-8")
                        self_inner.send_header("Content-Length", str(len(body)))
                        self_inner.end_headers()
                        self_inner.wfile.write(body)
                        event.set()
                    else:
                        self_inner.send_error(400, "Invalid CodeBox callback")
                def log_message(self_inner, *_args):
                    return
            server = HTTPServer(("127.0.0.1", 8769), Handler)
            server.timeout = 1
            def serve():
                deadline = time.time() + 240
                while not event.is_set() and time.time() < deadline:
                    server.handle_request()
                server.server_close()
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            redirect = "http://127.0.0.1:8769/oauth/callback"
            url = self.api_base + "/auth/" + self.provider + "/start?client=desktop&redirect_uri=" + urllib.parse.quote(redirect, safe="")
            self.status.emit("Opening browser for " + self.provider.title() + " sign-in…")
            webbrowser.open(url)
            if not event.wait(240):
                raise RuntimeError("Sign-in timed out. Check the browser and provider OAuth configuration.")
            response = requests.post(self.api_base + "/api/auth/exchange-code", json={"code": result["code"]}, timeout=15)
            data = response.json()
            if not response.ok or not data.get("token"):
                raise RuntimeError(data.get("error", "Could not exchange the sign-in code."))
            self.done.emit(data, "")
        except Exception as exc:
            self.done.emit(None, str(exc))


class AccountGateDialog(QDialog):
    """Login-first gate shared with the CodeBox web account service."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in · CodeBox Nexus Studio")
        self.setMinimumWidth(540)
        self.auth_result = None
        self.oauth_worker = None
        settings = QSettings(ORG_NAME, APP_NAME)
        self.api_url = QLineEdit(os.environ.get("CODEBOX_API_URL", settings.value("auth/api_url", "http://127.0.0.1:8765")))
        self.email = QLineEdit()
        self.email.setPlaceholderText("you@example.com")
        self.password = QLineEdit()
        self.password.setPlaceholderText("At least 10 characters for new accounts")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.code = QLineEdit()
        self.code.setPlaceholderText("6-digit email code")
        self.code.setMaxLength(6)
        self.status = QLabel("Sign in is required before the workspace opens. Start CodeBox_Server.py first.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#a7adc6; padding:5px")

        root = QVBoxLayout(self)
        logo = LogoWidget()
        root.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        headline = QLabel("<h2>Welcome to CodeBox</h2><p>One account for the website and desktop app.</p>")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(headline)
        form = QFormLayout()
        form.addRow("API server", self.api_url)
        form.addRow("Email", self.email)
        form.addRow("Password", self.password)
        form.addRow("Email code", self.code)
        root.addLayout(form)
        row = QHBoxLayout()
        for label, handler in [("Sign In", self._login), ("Create Account", self._register)]:
            btn = QPushButton(label)
            btn.setObjectName("Primary" if label == "Sign In" else "")
            btn.clicked.connect(handler)
            row.addWidget(btn)
        root.addLayout(row)
        row2 = QHBoxLayout()
        send = QPushButton("Send Email Code")
        send.clicked.connect(self._send_code)
        verify = QPushButton("Sign In with Code")
        verify.clicked.connect(self._verify_code)
        row2.addWidget(send); row2.addWidget(verify)
        root.addLayout(row2)
        row3 = QHBoxLayout()
        gh = QPushButton("Continue with GitHub")
        gh.clicked.connect(lambda: self._oauth("github"))
        google = QPushButton("Continue with Google")
        google.clicked.connect(lambda: self._oauth("google"))
        row3.addWidget(gh); row3.addWidget(google)
        root.addLayout(row3)
        root.addWidget(self.status)
        quit_btn = QPushButton("Exit")
        quit_btn.clicked.connect(self.reject)
        root.addWidget(quit_btn)
        self.setStyleSheet("QDialog{background:#10111b;color:#eef0ff} QLabel{color:#e8e9f3} QLineEdit{background:#151725;border:1px solid #34374f;border-radius:7px;padding:8px;color:#fff} QPushButton{background:#272a40;border:1px solid #393d5a;border-radius:8px;padding:8px 10px;color:#fff} QPushButton#Primary{background:#7048e8;font-weight:bold}")

    def _base(self):
        base = self.api_url.text().strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            raise ValueError("API server must start with http:// or https://")
        QSettings(ORG_NAME, APP_NAME).setValue("auth/api_url", base)
        return base

    def _api(self, route, body):
        if requests is None:
            raise RuntimeError("The requests package is missing. Install with: py -m pip install requests")
        response = requests.post(self._base() + route, json=body, timeout=15)
        try: data = response.json()
        except Exception: data = {}
        if not response.ok:
            raise RuntimeError(data.get("error", f"Server returned HTTP {response.status_code}"))
        return data

    def _finish(self, data, provider="CodeBox Account"):
        token = data.get("token")
        user = data.get("user") or {}
        if not token:
            raise RuntimeError("The server did not return a session token.")
        self.auth_result = {
            "token": token,
            "email": user.get("email") or self.email.text().strip(),
            "username": user.get("username") or user.get("login") or user.get("name") or self.email.text().strip(),
            "plan": (user.get("plan") or data.get("plan") or "free").lower(),
            "provider": provider,
            "api_base": self._base()
        }
        self.accept()

    def _login(self):
        try:
            self.status.setText("Signing in…")
            self._finish(self._api("/api/login", {"email": self.email.text().strip(), "password": self.password.text()}), "Email & password")
        except Exception as exc: self.status.setText("Sign-in failed: " + str(exc))

    def _register(self):
        try:
            self.status.setText("Creating account…")
            self._finish(self._api("/api/register", {"email": self.email.text().strip(), "password": self.password.text()}), "Email & password")
        except Exception as exc: self.status.setText("Account creation failed: " + str(exc))

    def _send_code(self):
        try:
            data = self._api("/api/auth/send-code", {"email": self.email.text().strip()})
            self.status.setText(data.get("message", "If email delivery is configured, a code has been sent."))
        except Exception as exc: self.status.setText("Email code: " + str(exc))

    def _verify_code(self):
        try:
            data = self._api("/api/auth/verify-code", {"email": self.email.text().strip(), "code": self.code.text().strip()})
            self._finish(data, "Email verification code")
        except Exception as exc: self.status.setText("Code sign-in failed: " + str(exc))

    def _oauth(self, provider):
        try:
            self._base()
            self.status.setText("Opening provider sign-in in your browser…")
            self.oauth_worker = DesktopOAuthWorker(provider, self._base(), self)
            self.oauth_worker.status.connect(self.status.setText)
            self.oauth_worker.done.connect(lambda data, err, p=provider: self._oauth_done(data, err, p))
            self.oauth_worker.start()
        except Exception as exc: self.status.setText(str(exc))

    def _oauth_done(self, data, error, provider):
        if error:
            self.status.setText("OAuth failed: " + error)
            return
        try: self._finish(data, provider.title())
        except Exception as exc: self.status.setText(str(exc))


def main():
    global AUTH_SESSION, AUTH_API_BASE
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    gate = AccountGateDialog()
    if gate.exec() != QDialog.DialogCode.Accepted or not gate.auth_result:
        return
    AUTH_SESSION = dict(gate.auth_result)
    AUTH_API_BASE = AUTH_SESSION.get("api_base", AUTH_API_BASE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

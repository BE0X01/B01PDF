"""B01PDF: local-only, minimal desktop PDF viewer."""
import hashlib
import os
import json
import sys
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageFilter
from shiboken6 import delete as delete_qobject
from PySide6.QtCore import Qt, QSize, QRect, QSettings, QTimer, Signal, QEvent
from PySide6.QtGui import QFont, QAction, QIcon, QImage, QPixmap, QPainter, QColor, QKeySequence
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QScrollArea, QSplitter, QToolBar, QToolButton, QSizePolicy,
    QPushButton, QLabel, QComboBox, QSpinBox, QFileDialog, QMessageBox,
    QDialog, QHBoxLayout, QVBoxLayout, QCheckBox, QDialogButtonBox, QInputDialog, QLineEdit, QKeySequenceEdit, QFormLayout,
)

from updates import VERSION, UpdateJob, newer_release
from settings_store import open_settings


def configure_application_font(application):
    application.setFont(QFont("Malgun Gothic", 10))


def filtered_image(image, mode):
    if mode != "sharp":
        return image
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    pil = Image.frombytes("RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits()),
                          "raw", "RGBA", rgba.bytesPerLine())
    result = pil.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=3))
    data = result.tobytes()
    return QImage(data, result.width, result.height, result.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


class ImageCache:
    """Bounded in-memory render cache; never renders the whole PDF eagerly."""
    def __init__(self, document, limit=96 * 1024 * 1024):
        self.document = document
        self.limit = limit
        self.images = OrderedDict()
        self.bytes = 0

    def clear(self):
        self.images.clear()
        self.bytes = 0

    def get(self, page, size, mode="original"):
        key = (page, size.width(), size.height(), mode)
        if key in self.images:
            self.images.move_to_end(key)
            return self.images[key]
        image = filtered_image(self.document.render(page, size), mode)
        if image.isNull():
            return image
        cost = image.sizeInBytes()
        while self.images and self.bytes + cost > self.limit:
            _, old = self.images.popitem(last=False)
            self.bytes -= old.sizeInBytes()
        if cost <= self.limit:
            self.images[key] = image
            self.bytes += cost
        return image


class Pages(QWidget):
    pageChanged = Signal(int)

    def __init__(self, window, thumbnails=False):
        super().__init__()
        self.window = window
        self.thumbnails = thumbnails
        self.rectangles = []
        self.setAutoFillBackground(True)
        self.apply_theme()

    def apply_theme(self):
        dark = getattr(self.window, "dark_mode", False)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(
            ("#252731" if self.thumbnails else "#191b22") if dark else
            ("#e9e9ed" if self.thumbnails else "#d9dbe1")))
        self.setPalette(palette)
        self.update()

    def layout_pages(self):
        w = self.window
        count = w.document.pageCount()
        if not count:
            self.rectangles = []
            self.resize(max(1, self.parent().width()), max(1, self.parent().height()))
            self.update()
            return
        viewport = self.parent()
        available_w, available_h = max(100, viewport.width()), max(100, viewport.height())
        if self.thumbnails:
            rows = [[p] for p in range(count)]
            scale = max(20, available_w - 40) / max(w.document.pagePointSize(p).width() for p in range(count))
        else:
            if w.view_mode == "scroll":
                rows = [[p] for p in range(count)]
            elif w.view_mode == "two":
                first = (w.page // 2) * 2
                rows = [list(range(first, min(first + 2, count)))]
            else:
                rows = [[w.page]]
            scale = w.zoom / 100 * 96 / 72
            if w.fit != "manual":
                fit_rows = rows if w.view_mode != "scroll" else [[w.page]]
                width = max(sum(w.document.pagePointSize(p).width() for p in row)
                            for row in fit_rows)
                gap = 18 if w.view_mode == "two" and len(rows[0]) == 2 else 0
                scale = max(.05, (available_w - 40 - gap) / width)
                if w.fit == "page":
                    height = max(w.document.pagePointSize(p).height() for row in fit_rows for p in row)
                    scale = min(scale, max(.05, (available_h - 40) / height))
                w.show_zoom(scale * 72 / 96 * 100)
        row_sizes = []
        for row in rows:
            sizes = [(p, max(1, round(w.document.pagePointSize(p).width() * scale)),
                      max(1, round(w.document.pagePointSize(p).height() * scale))) for p in row]
            row_sizes.append(sizes)
        content_width = max(available_w, max(sum(s[1] for s in row) + 18 * (len(row) - 1)
                                           for row in row_sizes) + 40)
        y = 20
        self.rectangles = []
        for row in row_sizes:
            row_width = sum(s[1] for s in row) + 18 * (len(row) - 1)
            x = (content_width - row_width) // 2
            for page, width, height in row:
                self.rectangles.append((page, QRect(x, y, width, height)))
                x += width + 18
            y += max(s[2] for s in row) + (34 if self.thumbnails else 20)
        self.resize(content_width, max(available_h, y))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w = self.window
        for page, rect in self.rectangles:
            if not rect.adjusted(-5, -5, 5, 24).intersects(event.rect()):
                continue
            painter.fillRect(rect.adjusted(-1, -1, 1, 1), QColor("#131314"))
            painter.fillRect(rect, Qt.GlobalColor.white)
            ratio = self.devicePixelRatioF()
            factor = 1
            # Cap a render to 12 megapixels to bound individual allocations.
            rw, rh = max(1, int(rect.width() * ratio * factor)), max(1, int(rect.height() * ratio * factor))
            cap = min(1.0, (12_000_000 / (rw * rh)) ** .5)
            image = w.cache.get(page, QSize(max(1, int(rw * cap)), max(1, int(rh * cap))),
                                "original" if self.thumbnails else w.filter_mode)
            if not image.isNull():
                painter.drawImage(rect, image)
            if self.thumbnails:
                if page == w.page:
                    painter.setPen(QColor("#5468e7"))
                    painter.drawRect(rect.adjusted(-3, -3, 3, 3))
                painter.setPen(QColor("#c9ccda" if w.dark_mode else "#444653"))
                painter.drawText(QRect(rect.x(), rect.bottom() + 6, rect.width(), 20),
                                 Qt.AlignmentFlag.AlignCenter, str(page + 1))

    def mousePressEvent(self, event):
        if not self.thumbnails and event.button() == Qt.MouseButton.LeftButton:
            self.window.viewer.begin_pan(event.globalPosition())
            event.accept()
            return
        if self.thumbnails:
            for page, rect in self.rectangles:
                if rect.adjusted(-5, -5, 5, 24).contains(event.position().toPoint()):
                    self.window.go_to(page)
                    break
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.thumbnails and self.window.viewer.pan_origin is not None:
            self.window.viewer.move_pan(event.globalPosition())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.thumbnails and event.button() == Qt.MouseButton.LeftButton:
            self.window.viewer.end_pan()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class Viewer(QScrollArea):
    def __init__(self, window, thumbnails=False):
        super().__init__()
        self.window = window
        self.thumbnails = thumbnails
        self.setWidgetResizable(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.wheel_remainder = 0
        self.pan_origin = None
        if thumbnails:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.pages = Pages(window, thumbnails)
        self.setWidget(self.pages)
        if not thumbnails:
            self.pages.setCursor(Qt.CursorShape.OpenHandCursor)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        self.verticalScrollBar().valueChanged.connect(self.scrolled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self.window, "viewer"):
            self.window.relayout(preserve=True)

    def scrolled(self):
        w = self.window
        if self.thumbnails or w.relayouting or w.view_mode != "scroll":
            return
        top = self.verticalScrollBar().value()
        for page, rect in self.pages.rectangles:
            if rect.bottom() >= top + 24:
                w.set_current_page(page)
                break

    def begin_pan(self, position):
        self.pan_origin = position
        self.pan_scroll = (self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        self.pages.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        self.setFocus()

    def move_pan(self, position):
        if self.pan_origin is None:
            return
        delta = position - self.pan_origin
        self.horizontalScrollBar().setValue(round(self.pan_scroll[0] - delta.x()))
        self.verticalScrollBar().setValue(round(self.pan_scroll[1] - delta.y()))

    def end_pan(self):
        self.pan_origin = None
        self.pages.setCursor(Qt.CursorShape.OpenHandCursor)
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event):
        if self.thumbnails:
            super().wheelEvent(event)
            return
        angle = event.angleDelta().y() or event.angleDelta().x()
        pixels = event.pixelDelta().y() or event.pixelDelta().x()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if angle or pixels:
                self.window.set_zoom(self.window.zoom + (10 if (angle or pixels) > 0 else -10))
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            bar = self.horizontalScrollBar()
            distance = pixels if pixels else angle / 120 * bar.singleStep() * 3
            bar.setValue(round(bar.value() - distance))
            self.wheel_remainder = 0
        elif self.window.view_mode == "scroll":
            super().wheelEvent(event)
            return
        elif angle or pixels:
            bar = self.verticalScrollBar()
            direction = -1 if (angle or pixels) > 0 else 1
            at_edge = bar.value() <= bar.minimum() if direction < 0 else bar.value() >= bar.maximum()
            if not at_edge:
                distance = pixels if pixels else angle / 120 * bar.singleStep() * 3
                bar.setValue(round(bar.value() - distance))
                self.wheel_remainder = 0
            else:
                # A full wheel step at the edge changes the page, without skipping its bottom.
                delta = angle if angle else pixels * 3
                if self.wheel_remainder * delta < 0:
                    self.wheel_remainder = 0
                self.wheel_remainder += delta
                if abs(self.wheel_remainder) >= 120:
                    old_page = self.window.page
                    self.window.turn_page(direction)
                    self.wheel_remainder = 0
                    if self.window.page != old_page and direction < 0:
                        bar.setValue(bar.maximum())
        event.accept()

    def keyPressEvent(self, event):
        if self.window.navigate_key(event.key()):
            event.accept()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        configure_application_font(QApplication.instance())
        self.settings = settings if settings is not None else open_settings()
        self.document = QPdfDocument(self)
        self.cache = ImageCache(self.document)
        self.path = None
        self.page = 0
        self.zoom = max(10, min(400, self.settings.value("view/zoom", 100, type=float)))
        self.fit = self.settings.value("view/fit", "manual")
        if self.fit not in ("manual", "width", "page"):
            self.fit = "manual"
        self.view_mode = self.settings.value("view/mode", "single")
        if self.view_mode not in ("single", "two", "scroll"):
            self.view_mode = "single"
        self.filter_mode = self.settings.value("view/filter", "original")
        if self.filter_mode not in ("original", "sharp"):
            self.filter_mode = "original"
        self.dark_mode = self.settings.value("view/dark", False, type=bool)
        self.update_job = None
        self._settings_saved = False
        self.relayouting = False
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets" / "B01PDF.ico")))
        self.setWindowTitle("B01PDF")
        self.resize(1120, 800)
        self.setMinimumSize(800, 480)
        self.setAcceptDrops(True)
        self.create_toolbar()
        self.splitter = QSplitter()
        self.sidebar = Viewer(self, True)
        self.sidebar.setMinimumWidth(160)
        self.sidebar.setMaximumWidth(max(160, min(220, self.width() // 5)))
        self.viewer = Viewer(self)
        self.viewer.setMinimumWidth(200)
        self.splitter.addWidget(self.sidebar)
        self.splitter.setCollapsible(0, False)
        self.splitter.addWidget(self.viewer)
        self.splitter.setSizes([165, 955])
        self.setCentralWidget(self.splitter)
        self.sidebar.setVisible(self.settings.value("view/sidebar", True, type=bool))
        self.apply_theme(self.dark_mode)
        self.mode_input.setCurrentIndex(["single", "two", "scroll"].index(self.view_mode))
        self.viewer.viewport().installEventFilter(self)
        self.viewer.pages.installEventFilter(self)
        self.sidebar.viewport().installEventFilter(self)
        self.sidebar.pages.installEventFilter(self)
        self.statusBar().showMessage("Open a PDF or drag it into this window")
        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_position)
        self.viewer.verticalScrollBar().valueChanged.connect(lambda: self.save_timer.start())
        self.viewer.horizontalScrollBar().valueChanged.connect(lambda: self.save_timer.start())

    def create_toolbar(self):
        bar = QToolBar("View")
        self.toolbar = bar
        bar.setMovable(False)
        bar.setIconSize(QSize(22, 22))
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        def button(text, callback, shortcut=None):
            action = QAction(text, self)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            bar.addAction(action)
            return action
        self.shortcut_actions = {}
        self.shortcut_defaults = {}
        self.sidebar_action = QAction("Sidebar", self)
        self.sidebar_action.setCheckable(True)
        self.sidebar_action.setChecked(self.settings.value("view/sidebar", True, type=bool))
        self.sidebar_action.setToolTip("Toggle sidebar (F9)")
        self.sidebar_action.toggled.connect(self.toggle_sidebar)
        bar.addAction(self.sidebar_action)
        self.open_action = button("Open", self.choose_file)
        self.open_action.setToolTip("Open PDF (Ctrl+O)")
        self.register_shortcut("Open", self.open_action, "Ctrl+O")
        bar.addSeparator()
        button("‹", lambda: self.go_to(self.page - (2 if self.view_mode == "two" else 1)), "PgUp")
        self.page_input = QSpinBox()
        self.page_input.setRange(1, 1)
        self.page_input.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.page_input.setFixedWidth(55)
        self.page_input.setToolTip("Page number")
        self.page_input.editingFinished.connect(lambda: self.go_to(self.page_input.value() - 1))
        bar.addWidget(self.page_input)
        self.page_total = QLabel("/ 0")
        bar.addWidget(self.page_total)
        button("›", lambda: self.go_to(self.page + (2 if self.view_mode == "two" else 1)), "PgDown")
        bar.addSeparator()
        self.register_shortcut("Zoom Out", button("−", lambda: self.step_zoom(-1)), "Ctrl+-")
        self.zoom_input = QSpinBox()
        self.zoom_input.setRange(10, 400)
        self.zoom_input.setSuffix("%")
        self.zoom_input.setValue(round(self.zoom))
        self.zoom_input.setFixedWidth(76)
        self.zoom_input.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.zoom_input.editingFinished.connect(lambda: self.set_zoom(self.zoom_input.value()))
        bar.addWidget(self.zoom_input)
        self.register_shortcut("Zoom In", button("+", lambda: self.step_zoom(1)), "Ctrl++")
        self.register_shortcut("100%", button("100%", lambda: self.set_zoom(100)), "Ctrl+1")
        self.fit_width_action = button("Fit Width", lambda: self.set_fit("width"))
        self.fit_page_action = button("Fit Page", lambda: self.set_fit("page"))
        self.register_shortcut("Fit Width", self.fit_width_action, "Ctrl+9")
        self.register_shortcut("Fit Page", self.fit_page_action, "Ctrl+0")
        self.fit_width_action.setCheckable(True)
        self.fit_page_action.setCheckable(True)
        self.sync_fit_actions()
        bar.addSeparator()
        self.mode_input = QComboBox()
        self.mode_input.addItems(["1 Page", "2 Pages", "Scroll"])
        self.mode_input.currentIndexChanged.connect(self.change_mode)
        bar.addWidget(self.mode_input)
        self.register_shortcut("Settings", button("Settings", self.show_settings), "Ctrl+,")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.theme_action = QAction("Dark" if self.dark_mode else "Light", self)
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(self.dark_mode)
        self.theme_action.toggled.connect(self.apply_theme)
        self.theme_button = QToolButton()
        self.theme_button.setIconSize(QSize(22, 22))
        self.theme_button.setDefaultAction(self.theme_action)
        toolbar_container = QWidget()
        toolbar_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar_row = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_row)
        toolbar_layout.setContentsMargins(0, 0, 6, 0)
        toolbar_layout.setSpacing(6)
        toolbar_layout.addWidget(bar, 1)
        toolbar_layout.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.toolbar_divider = QWidget()
        self.toolbar_divider.setObjectName("toolbarDivider")
        self.toolbar_divider.setFixedHeight(1)
        container_layout = QVBoxLayout(toolbar_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(toolbar_row)
        container_layout.addWidget(self.toolbar_divider)
        self.toolbar_shell = QToolBar("Menu")
        self.toolbar_shell.setObjectName("toolbarShell")
        self.toolbar_shell.setMovable(False)
        self.toolbar_shell.addWidget(toolbar_container)
        self.addToolBar(self.toolbar_shell)
        self.register_shortcut("Sidebar", self.sidebar_action, "F9")
        for name, default, callback in [
            ("200%", "Ctrl+2", lambda: self.set_zoom(200)),
            ("300%", "Ctrl+3", lambda: self.set_zoom(300)),
            ("50%", "Ctrl+`", lambda: self.set_zoom(50)),
            ("1 Page", "Alt+1", lambda: self.mode_input.setCurrentIndex(0)),
            ("2 Pages", "Alt+2", lambda: self.mode_input.setCurrentIndex(1)),
            ("Scroll", "Alt+3", lambda: self.mode_input.setCurrentIndex(2)),
            ("Quit", "Ctrl+Q", self.confirm_quit),
        ]:
            action = QAction(name, self)
            action.triggered.connect(callback)
            self.addAction(action)
            self.register_shortcut(name, action, default)
        self.apply_shortcuts()

    def register_shortcut(self, name, action, default):
        self.shortcut_actions[name] = action
        self.shortcut_defaults[name] = default

    def apply_shortcuts(self):
        for name, action in self.shortcut_actions.items():
            value = self.settings.value("shortcuts/" + name, self.shortcut_defaults[name])
            sequences = [QKeySequence(value)] if value else []
            if name == "Zoom In" and value == "Ctrl++":
                sequences.append(QKeySequence("Ctrl+="))
            action.setShortcuts(sequences)

    def confirm_quit(self):
        reply = QMessageBox.question(self, "Quit B01PDF", "Are you sure you want to quit the application?",
                                     QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Ok:
            self.close()

    def step_zoom(self, direction):
        levels = (10, 25, 33, 50, 75, 100, 150, 200, 300)
        candidates = [level for level in levels if level > self.zoom + .001] if direction > 0 else [level for level in levels if level < self.zoom - .001]
        if candidates:
            self.set_zoom(min(candidates) if direction > 0 else max(candidates))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self.sidebar.setMaximumWidth(max(160, min(220, self.width() // 5)))

    def sync_fit_actions(self):
        self.fit_width_action.setChecked(self.fit == "width")
        self.fit_page_action.setChecked(self.fit == "page")

    def save_preferences(self):
        if not hasattr(self, "sidebar"):
            return
        for key, value in {"zoom": self.zoom, "fit": self.fit, "mode": self.view_mode,
                           "filter": self.filter_mode, "dark": self.dark_mode,
                           "sidebar": self.sidebar_action.isChecked()}.items():
            self.settings.setValue("view/" + key, value)

    def toggle_sidebar(self, visible):
        if hasattr(self, "sidebar"):
            self.sidebar.setVisible(visible)
            self.relayout(preserve=True)
            self.save_preferences()

    def refresh_toolbar_icons(self):
        """Render bundled Reicon SVGs at high DPI with explicit theme colors."""
        foreground = "#e1e3ee" if self.dark_mode else "#242632"
        def icon(name, checkable=False):
            result = QIcon()
            for state in (QIcon.State.Off, QIcon.State.On):
                weight = "filled" if name == "sidebar2" and state == QIcon.State.On else "outline"
                source = (Path(__file__).resolve().parent / "assets" / "icons" / f"{name}-{weight}.svg").read_text()
                for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected, QIcon.Mode.Disabled):
                    color = "#8b8e99" if mode == QIcon.Mode.Disabled else ("#ffffff" if checkable and state == QIcon.State.On else foreground)
                    svg = source.replace("currentColor", color).replace("var(--ri-primary)", color).replace("var(--ri-secondary)", color)
                    for scale in (1, 2, 3):
                        pixmap = QPixmap(22 * scale, 22 * scale)
                        pixmap.fill(Qt.GlobalColor.transparent)
                        painter = QPainter(pixmap)
                        QSvgRenderer(svg.encode()).render(painter)
                        painter.end()
                        pixmap.setDevicePixelRatio(scale)
                        result.addPixmap(pixmap, mode, state)
            return result
        for action, name, checkable in ((self.sidebar_action, "sidebar2", True),
                                       (self.open_action, "folder", False),
                                       (self.theme_action, "moon" if self.dark_mode else "sun", True)):
            action.setIcon(icon(name, checkable))
            button = self.theme_button if action is self.theme_action else self.toolbar.widgetForAction(action)
            button.setObjectName("iconButton")
            button.setFixedSize(32, 32)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setAccessibleName(action.text())

    def apply_theme(self, dark):
        self.dark_mode = dark
        self.theme_action.blockSignals(True)
        self.theme_action.setChecked(dark)
        self.theme_action.blockSignals(False)
        self.theme_action.setText("Dark" if dark else "Light")
        self.theme_action.setToolTip("Switch to light theme" if dark else "Switch to dark theme")
        self.refresh_toolbar_icons()
        if not hasattr(self, "viewer"):
            return
        background, foreground, input_bg, border = (("#252731", "#e1e3ee", "#323540", "#444857")
                                                    if dark else ("#f6f6f8", "#242632", "#ffffff", "#d2d4dc"))
        self.setStyleSheet(f"QMainWindow, QDialog, QToolBar, QStatusBar {{ background: {background}; color: {foreground}; }}"
                           f"QLabel, QCheckBox, QToolButton {{ color: {foreground}; }}"
                           f"QToolBar {{ spacing: 8px; padding: 6px; border: none; }}"
                           f"QToolButton {{ background: transparent; padding: 3px; border: none; border-radius: 5px; }}"
                           f"QToolBar#toolbarShell {{ padding: 0px; spacing: 0px; border: none; }}"
                           f"QWidget#toolbarDivider {{ background: {border}; }}"
                           f"QToolBar::separator {{ background: {'#3b3e48' if dark else '#b8bbc3'}; width: 1px; margin-top: 8px; margin-bottom: 8px; }}"
                           f"QToolButton#iconButton {{ padding: 0px; margin: 0px; }}"
                           f"QToolButton:checked {{ background: #5468e7; color: white; border-radius: 3px; }}"
                           f"QToolButton:hover {{ background: {input_bg}; }}"
                           f"QToolButton:checked:hover {{ background: #687bed; color: white; }}"
                           f"QComboBox, QSpinBox, QLineEdit, QKeySequenceEdit, QPushButton {{ background: {input_bg}; color: {foreground}; padding: 4px; }}"
                           f"QWidget#shortcutContainer {{ background: {background}; color: {foreground}; }}"
                           f"QAbstractItemView {{ background: {input_bg}; color: {foreground}; selection-background-color: #5468e7; }}"
                           f"QSplitter::handle {{ background: {border}; }}"
                           f"QScrollArea {{ background: {background}; }}"
                           f"QScrollBar {{ background: transparent; border: none; }}"
                           f"QScrollBar:vertical {{ width: 10px; margin: 2px; }}"
                           f"QScrollBar:horizontal {{ height: 10px; margin: 2px; }}"
                           f"QScrollBar::handle {{ background: {'#666b7b' if dark else '#b0b4c0'}; border-radius: 3px; }}"
                           f"QScrollBar::handle:vertical {{ min-height: 28px; }}"
                           f"QScrollBar::handle:horizontal {{ min-width: 28px; }}"
                           f"QScrollBar::handle:hover {{ background: {'#9399ac' if dark else '#858b9d'}; }}"
                           f"QScrollBar::handle:pressed {{ background: #5468e7; }}"
                           f"QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; border: none; background: transparent; }}"
                           f"QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}"
                           f"QAbstractScrollArea::corner {{ background: transparent; }}")
        self.viewer.pages.apply_theme()
        self.sidebar.pages.apply_theme()
        self.save_preferences()

    def turn_page(self, direction):
        target = max(0, min(self.document.pageCount() - 1, self.page + direction * (2 if self.view_mode == "two" else 1)))
        if target != self.page:
            self.go_to(target)

    def navigate_key(self, key):
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self.turn_page(1)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self.turn_page(-1)
        elif key == Qt.Key.Key_Home:
            self.go_to(0)
        elif key == Qt.Key.Key_End:
            self.go_to(self.document.pageCount() - 1)
        else:
            return False
        return True

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Type.MouseButtonDblClick
                and event.button() == Qt.MouseButton.LeftButton
                and watched in (self.viewer.viewport(), self.viewer.pages,
                                self.sidebar.viewport(), self.sidebar.pages)
                and self.document.pageCount() == 0):
            self.viewer.end_pan()
            self.choose_file()
            return True
        if watched is self.viewer.viewport():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.viewer.begin_pan(event.globalPosition())
                return True
            if event.type() == QEvent.Type.MouseMove and self.viewer.pan_origin is not None:
                self.viewer.move_pan(event.globalPosition())
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self.viewer.end_pan()
                return True
        if event.type() == QEvent.Type.KeyPress and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            if self.navigate_key(event.key()):
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if self.navigate_key(event.key()):
            event.accept()
        else:
            super().keyPressEvent(event)

    def check_updates(self):
        if self.update_job and self.update_job.running:
            self.statusBar().showMessage("An update request is already running")
            return
        self.statusBar().showMessage("Checking GitHub for updates...")
        self.update_job = UpdateJob(parent=self)
        self.update_job.result.connect(self.update_available)
        self.update_job.failed.connect(self.update_failed)
        self.update_job.start()

    def update_failed(self, message):
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "Updates", message)

    def update_available(self, release):
        try:
            if not newer_release(release):
                self.statusBar().showMessage(f"B01PDF {VERSION} is up to date")
                QMessageBox.information(self, "Updates", f"B01PDF {VERSION} is up to date.")
                return
            from updates import installer_asset
            asset = installer_asset(release)
        except (ValueError, KeyError, TypeError) as error:
            self.update_failed(str(error))
            return
        reply = QMessageBox.question(self, "Update Available",
                                     f"B01PDF {release['tag_name']} is available.\nDownload and install it now?\nThe viewer will close when the installer starts.")
        if reply != QMessageBox.StandardButton.Yes:
            self.statusBar().showMessage("Update postponed")
            return
        self.update_job = UpdateJob(asset, parent=self)
        self.update_job.progress.connect(lambda percent: self.statusBar().showMessage(f"Downloading update... {percent}%"))
        self.update_job.result.connect(self.install_update)
        self.update_job.failed.connect(self.update_failed)
        self.update_job.start()

    def install_update(self, executable):
        if sys.platform != "win32":
            self.update_failed("Automatic installation is available on Windows only.")
            return
        try:
            # ShellExecute handles the UAC prompt for a Program Files installer.
            os.startfile(executable, "open", arguments="/CLOSEAPPLICATIONS /RESTARTAPPLICATIONS")
        except OSError as error:
            self.update_failed(f"Could not start the update installer: {error}")
            return
        self.close()
        QApplication.instance().quit()

    def remember(self):
        return self.settings.value("remember", True, type=bool)

    def position_key(self):
        return "positions/" + hashlib.sha256(str(self.path).encode("utf-8")).hexdigest()

    def save_position(self):
        if not self.path or not self.remember() or not self.document.pageCount():
            return
        rect = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
        offset = 0 if rect is None else (self.viewer.verticalScrollBar().value() - rect.top()) / rect.height()
        state = {"page": self.page, "offset": offset, "x": self.viewer.horizontalScrollBar().value()}
        self.settings.setValue(self.position_key(), json.dumps(state))

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF (*.pdf)", options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            self.open_file(path)

    def open_file(self, path):
        self.save_position()
        # Load separately so an invalid file doesn't destroy the current document.
        document = QPdfDocument(self)
        error = document.load(str(path))
        while error == QPdfDocument.Error.IncorrectPassword:
            password, ok = QInputDialog.getText(self, "Password Required", "Password", QLineEdit.EchoMode.Password)
            if not ok:
                document.deleteLater()
                return False
            document.setPassword(password)
            error = document.load(str(path))
        if error != QPdfDocument.Error.None_ or document.pageCount() == 0:
            QMessageBox.warning(self, "Open Failed", "Unable to open this PDF. Check the file format or whether the file is damaged.")
            document.deleteLater()
            return False
        self.save_timer.stop()
        old = self.document
        self.document = document
        self.cache.clear()
        self.cache.document = document
        old.close()
        delete_qobject(old)
        self.path = Path(path).resolve()
        self.page = 0
        state = {}
        if self.remember():
            try:
                state = json.loads(self.settings.value(self.position_key(), "{}"))
                self.page = max(0, min(document.pageCount() - 1, int(state.get("page", 0))))
            except (ValueError, TypeError, AttributeError):
                state = {}
        self.mode_input.blockSignals(True)
        self.mode_input.setCurrentIndex(["single", "two", "scroll"].index(self.view_mode))
        self.mode_input.blockSignals(False)
        self.page_input.setRange(1, document.pageCount())
        self.page_total.setText(f"/ {document.pageCount()}")
        self.setWindowTitle("B01PDF")
        self.relayout()
        self.go_to(self.page)
        self.restore_offset(state)
        self.statusBar().showMessage(str(self.path))
        self.viewer.setFocus()
        return True

    def restore_offset(self, state):
        rect = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
        if rect and state:
            try:
                offset = max(-1.0, min(1.0, float(state.get("offset", 0))))
                self.viewer.verticalScrollBar().setValue(round(rect.top() + offset * rect.height()))
                self.viewer.horizontalScrollBar().setValue(int(state.get("x", 0)))
            except (ValueError, TypeError):
                pass

    def show_zoom(self, value):
        self.zoom = value
        self.zoom_input.setValue(round(value))
        self.zoom_input.setToolTip(f"Current zoom: {value:.1f}%")

    def relayout(self, preserve=False):
        if self.relayouting:
            return
        self.relayouting = True
        rect = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
        offset = ((self.viewer.verticalScrollBar().value() - rect.top()) / rect.height()
                  if preserve and rect else 0)
        self.viewer.pages.layout_pages()
        self.sidebar.pages.layout_pages()
        if preserve:
            new = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
            if new:
                self.viewer.verticalScrollBar().setValue(round(new.top() + offset * new.height()))
        self.relayouting = False
        self.show_zoom(self.zoom)

    def set_current_page(self, page):
        self.page = page
        self.page_input.setValue(page + 1)
        self.sidebar.pages.update()
        if hasattr(self, "save_timer"):
            self.save_timer.start()

    def go_to(self, page):
        if not self.document.pageCount():
            return
        page = max(0, min(self.document.pageCount() - 1, page))
        self.set_current_page(page)
        if self.view_mode != "scroll" or self.fit != "manual":
            self.relayout()
        rect = next((r for p, r in self.viewer.pages.rectangles if p == page), None)
        if rect:
            self.viewer.verticalScrollBar().setValue(max(0, rect.top() - 20))
        thumb = self.sidebar.pages.rectangles[page][1]
        self.sidebar.ensureVisible(thumb.center().x(), thumb.center().y(), 0, thumb.height() // 2 + 12)

    def set_zoom(self, value):
        self.fit = "manual"
        self.sync_fit_actions()
        self.zoom = max(10, min(400, value))
        self.relayout(preserve=True)
        self.save_preferences()

    def set_fit(self, mode):
        self.fit = mode
        self.sync_fit_actions()
        self.relayout(preserve=True)
        self.save_preferences()

    def change_mode(self, index):
        self.view_mode = ["single", "two", "scroll"][index]
        self.relayout()
        self.go_to(self.page)
        self.save_preferences()
        self.viewer.setFocus()

    def change_filter(self, index):
        self.filter_mode = ["original", "sharp"][index]
        self.cache.clear()
        self.viewer.pages.update()
        self.save_preferences()

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        layout = QVBoxLayout(dialog)
        remember = QCheckBox("Remember last page position")
        remember.setChecked(self.remember())
        layout.addWidget(remember)
        layout.addWidget(QLabel("Restore the last page and scroll position when reopening a PDF."))
        layout.addWidget(QLabel("Image filter"))
        image_filter = QComboBox()
        image_filter.addItems(["Original", "Sharp"])
        image_filter.setCurrentIndex(["original", "sharp"].index(self.filter_mode))
        layout.addWidget(image_filter)
        layout.addWidget(QLabel(f"B01PDF {VERSION} — Updates"))
        update_button = QPushButton("Check for Updates")
        update_button.clicked.connect(self.check_updates)
        layout.addWidget(update_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(QLabel("Keyboard shortcuts"))
        shortcut_scroll = QScrollArea()
        shortcut_scroll.setWidgetResizable(True)
        shortcut_scroll.setMinimumHeight(230)
        shortcut_scroll.setMaximumHeight(280)
        shortcut_container = QWidget()
        shortcut_container.setObjectName("shortcutContainer")
        shortcut_form = QFormLayout(shortcut_container)
        editors = {}
        for name, action in self.shortcut_actions.items():
            editor = QKeySequenceEdit(action.shortcut())
            editor.setMaximumSequenceLength(1)
            editors[name] = editor
            shortcut_form.addRow(name, editor)
        shortcut_scroll.setWidget(shortcut_container)
        layout.addWidget(shortcut_scroll)
        reset = QPushButton("Restore Default Shortcuts")
        reset.clicked.connect(lambda: [editor.setKeySequence(QKeySequence(self.shortcut_defaults[name])) for name, editor in editors.items()])
        layout.addWidget(reset)
        layout.addWidget(QLabel("Click a shortcut field and press the new keys. Backspace clears it."))
        def accept_settings():
            used = {"PgUp": "Previous Page", "PgDown": "Next Page", "Up": "Previous Page", "Left": "Previous Page", "Down": "Next Page", "Right": "Next Page", "Home": "First Page", "End": "Last Page"}
            for name, editor in editors.items():
                key = editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                aliases = [key, "Ctrl+="] if name == "Zoom In" and key == "Ctrl++" else [key]
                for alias in aliases:
                    if alias and alias in used:
                        QMessageBox.warning(dialog, "Shortcut Conflict", f"{name} and {used[alias]} use the same shortcut: {alias}")
                        return
                    if alias:
                        used[alias] = name
            dialog.accept()
        buttons.accepted.connect(accept_settings)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for name, editor in editors.items():
                self.settings.setValue("shortcuts/" + name, editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText))
            self.apply_shortcuts()
            self.change_filter(image_filter.currentIndex())
            self.settings.setValue("remember", remember.isChecked())
            if not remember.isChecked():
                self.settings.remove("positions")
            else:
                self.save_position()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() and u.toLocalFile().lower().endswith(".pdf")
                                             for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.open_file(url.toLocalFile())
                event.acceptProposedAction()
                break

    def flush_settings_on_exit(self):
        if self._settings_saved:
            return
        self.save_timer.stop()
        self.save_position()
        self.save_preferences()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.sync()
        self._settings_saved = True
        if self.settings.status() != QSettings.Status.NoError:
            QMessageBox.warning(self, "Settings Error",
                                "Unable to save settings.ini. Check the file permissions and available disk space. "
                                "Changes from this session could not be saved.")

    def closeEvent(self, event):
        self.flush_settings_on_exit()
        self.cache.clear()
        self.document.close()
        delete_qobject(self.document)
        self.document = QPdfDocument(self)
        self.cache.document = self.document
        super().closeEvent(event)


def main():
    from updates import cleanup_old_updates
    import threading
    threading.Thread(target=cleanup_old_updates, daemon=True).start()
    app = QApplication(sys.argv)
    app.setApplicationName("B01PDF")
    app.setStyle("Fusion")
    configure_application_font(app)

    try:
        window = MainWindow()
    except OSError as error:
        QMessageBox.critical(None, "Settings Error", str(error))
        sys.exit(1)
    app.aboutToQuit.connect(window.flush_settings_on_exit)
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(500, app.quit)
    elif len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: window.open_file(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

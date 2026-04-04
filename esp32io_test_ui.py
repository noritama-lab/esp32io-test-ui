import math
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStatusBar, QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont
from pyside6stylekit import (
    Theme, IndusAlternateButton, IndusLamp,
    StyledButton, StyledLabel, StyledGroupBox, StyledSlider,
    StyledLineEdit,
    StyledComboBox, StyledProgressBar, StyledTextEdit, utils
)

from esp32_worker import ESP32Worker
from serial.tools import list_ports


ESP32_S3_LEDC_CLOCK_HZ = 40_000_000
ESP32_S3_LEDC_MAX_DIVIDER = 1024


class ESP32IOTestUI(QMainWindow):
    # UIスレッドからWorkerスレッドへ処理依頼するための中継シグナル
    _connect_requested = Signal(str)
    _disconnect_requested = Signal()
    _refresh_requested = Signal()
    _set_do_requested = Signal(int, int)
    _set_pwm_requested = Signal(int, int)
    _get_pwm_config_requested = Signal()
    _set_pwm_config_requested = Signal(int, int)
    def __init__(self):
        super().__init__()
        self._connected = False

        # テーマ設定
        self.theme_title = Theme(
            primary="blue", mode="dark", size="large",
            background="transparent", text_color="white"
        )
        self.theme_bgtrans = Theme(
            primary="blue", mode="dark", size="small",
            background="transparent", text_color="white"
        )
        self.theme_btn_lamp = Theme(
            primary="blue", mode="dark", size="small",
            text_color="white"
        )
        self.theme_input = Theme(
            primary="blue", mode="dark", size="small",
            background="#cccccc", text_color="black"
        )
        self.theme_btn_off = Theme(
            primary=utils.adjust_color(utils.normalize_color("blue"), 0.2), 
            mode="dark", size="small", text_color="white"
        )

        self.auto_refresh_timer = QTimer()
        self.auto_refresh_timer.timeout.connect(self.refresh_di_adc)

        self.setWindowTitle("ESP32IO Test UI")
        self.setGeometry(100, 100, 1000, 600)
        self.setMinimumSize(1000, 700)

        # UI コンポーネントの辞書
        self.dio_buttons = {}      # pin_id: IndusAlternateButton
        self.di_lamps = {}         # pin_id: IndusLamp
        self.adc_labels = {}       # pin_id: StyledLabel
        self.adc_bars = {}         # pin_id: StyledProgressBar
        self.pwm_sliders = {}      # pin_id: (StyledSlider, StyledLabel)

        # Worker スレッド設定
        self._worker = ESP32Worker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.start()

        # Worker → UI シグナル接続
        self._worker.connected.connect(self._on_connected)
        self._worker.connection_failed.connect(self._on_connection_failed)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.di_adc_updated.connect(self._on_di_adc_updated)
        self._worker.do_done.connect(self._on_do_done)
        self._worker.do_failed.connect(self._on_do_failed)
        self._worker.command_failed.connect(self._on_command_failed)
        self._worker.pwm_config_updated.connect(self._on_pwm_config_updated)
        self._worker.pwm_config_failed.connect(self._on_pwm_config_failed)

        # UI → Worker シグナル接続
        self._connect_requested.connect(self._worker.do_connect)
        self._disconnect_requested.connect(self._worker.do_disconnect)
        self._refresh_requested.connect(self._worker.do_refresh)
        self._set_do_requested.connect(self._worker.do_set_do)
        self._set_pwm_requested.connect(self._worker.do_set_pwm)
        self._get_pwm_config_requested.connect(self._worker.do_get_pwm_config)
        self._set_pwm_config_requested.connect(self._worker.do_set_pwm_config)

        self.setup_ui()

    def setup_ui(self):
        """UI コンポーネントを設定"""
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: #1f1f1f;")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_row1 = QHBoxLayout()
        main_row2 = QHBoxLayout()
        main_row3 = QHBoxLayout()

        title = StyledLabel("ESP32IO Test UI", theme=self.theme_title)
        main_layout.addWidget(title)

        main_row1.addWidget(self._create_connection_group())
        main_row1.addWidget(self._create_auto_refresh_group())
        main_row1.setStretch(0, 1)
        main_row1.setStretch(1, 1)

        main_row2.addWidget(self._create_di_group())
        main_row2.addWidget(self._create_do_group())
        main_row2.setStretch(0, 1)
        main_row2.setStretch(1, 1)

        main_row3.addWidget(self._create_adc_group())
        main_row3.addWidget(self._create_pwm_group())
        main_row3.addWidget(self._create_pwm_config_group())
        main_row3.setStretch(0, 1)
        main_row3.setStretch(1, 1)
        main_row3.setStretch(2, 1)

        log_group = self._create_log_group()


        # main_layoutへの追加
        main_layout.addLayout(main_row1)
        main_layout.addLayout(main_row2)
        main_layout.addLayout(main_row3)
        main_layout.addWidget(log_group)

        # ステータスバー
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("切断状態")

        # 初期状態：ボタン無効化
        self.set_buttons_enabled(False)

    def _create_connection_group(self):
        connection_group = StyledGroupBox("接続設定", theme=self.theme_bgtrans)
        conn_layout = QVBoxLayout()

        port_rayout = QHBoxLayout()
        port_rayout.addWidget(StyledLabel("COM ポート:", theme=self.theme_bgtrans))
        self.port_combo = StyledComboBox(self.theme_input, self.get_available_ports())
        self.port_combo.setMinimumWidth(140)
        port_rayout.addWidget(self.port_combo)

        self.refresh_ports_btn = StyledButton("再読込", theme=self.theme_btn_lamp)
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        port_rayout.addWidget(self.refresh_ports_btn)
        conn_layout.addLayout(port_rayout)

        button_rayout = QHBoxLayout()
        self.connect_btn = StyledButton("接続", theme=self.theme_btn_lamp)
        self.connect_btn.clicked.connect(self.connect_esp32)
        button_rayout.addWidget(self.connect_btn)

        self.disconnect_btn = StyledButton("切断", theme=self.theme_btn_lamp)
        self.disconnect_btn.clicked.connect(self.disconnect_esp32)
        self.disconnect_btn.setEnabled(False)
        button_rayout.addWidget(self.disconnect_btn)

        self.auto_refresh_btn = StyledButton("自動更新: OFF", theme=self.theme_btn_lamp)
        self.auto_refresh_btn.setCheckable(True)
        self.auto_refresh_btn.toggled.connect(self.toggle_auto_refresh)
        self.auto_refresh_btn.setEnabled(False)
        button_rayout.addWidget(self.auto_refresh_btn)
        conn_layout.addLayout(button_rayout)

        connection_group.setLayout(conn_layout)
        return connection_group

    def _create_auto_refresh_group(self):
        styled_group = StyledGroupBox("自動更新設定", theme=self.theme_bgtrans)
        styled_layout = QVBoxLayout()

        styled_layout.addWidget(StyledLabel("更新間隔 (50〜5000 ms)", theme=self.theme_bgtrans))
        self.refresh_interval_input = StyledLineEdit(
            "例: 500", self.theme_input,
            mode="numeric_range", min_val=50, max_val=5000
        )
        self.refresh_interval_input.setText("500")
        styled_layout.addWidget(self.refresh_interval_input)

        self.response_speed_label = StyledLabel("応答速度: -- ms", theme=self.theme_bgtrans)
        styled_layout.addWidget(self.response_speed_label)

        styled_group.setLayout(styled_layout)
        return styled_group

    def _create_di_group(self):
        di_group = StyledGroupBox("DIO 入力 (PIN 0~5)", theme=self.theme_bgtrans)
        di_layout = QHBoxLayout()
        for i in range(6):
            lamp = IndusLamp(f"PIN{i}", self.theme_btn_lamp, diameter=48, state=False)
            self.di_lamps[i] = lamp
            di_layout.addWidget(lamp)
        di_group.setLayout(di_layout)
        return di_group

    def _create_do_group(self):
        do_group = StyledGroupBox("DIO 出力 (PIN 0~5)", theme=self.theme_bgtrans)
        do_layout = QHBoxLayout()
        for i in range(6):
            btn = IndusAlternateButton(f"PIN{i}", self.theme_btn_lamp, diameter=48)
            # pin_id=i を使い、ループ後も各ボタンが正しいPINを参照するようにする
            btn.toggled.connect(lambda checked, pin_id=i: self.on_do_toggle(pin_id, checked))
            self.dio_buttons[i] = btn
            do_layout.addWidget(btn)
        do_group.setLayout(do_layout)
        return do_group

    def _create_adc_group(self):
        adc_group = StyledGroupBox("ADC 読み取り (PIN 0~1)", theme=self.theme_bgtrans)
        adc_layout = QHBoxLayout()
        for i in range(2):
            frame = QFrame()
            frame.setFrameStyle(QFrame.Box | QFrame.Raised)
            frame.setLineWidth(2)
            layout = QVBoxLayout()

            label = StyledLabel(f"PIN{i}", theme=self.theme_bgtrans)
            label.setAlignment(Qt.AlignCenter)
            label.setFont(QFont("Arial", 10, QFont.Bold))

            value = StyledLabel("0 / 4095", theme=self.theme_bgtrans)
            value.setAlignment(Qt.AlignCenter)
            value.setFont(QFont("Arial", 14, QFont.Bold))

            bar = StyledProgressBar(theme=self.theme_bgtrans, min_val=0, max_val=4095, value=0)

            layout.addWidget(label)
            layout.addWidget(value)
            layout.addWidget(bar)
            frame.setLayout(layout)

            self.adc_labels[i] = value
            self.adc_bars[i] = bar
            adc_layout.addWidget(frame)
        adc_group.setLayout(adc_layout)
        return adc_group

    def _create_pwm_group(self):
        pwm_group = StyledGroupBox("PWM 出力 (PIN 0~1)", theme=self.theme_bgtrans)
        pwm_layout = QHBoxLayout()
        for i in range(2):
            frame = QFrame()
            frame.setFrameStyle(QFrame.Box | QFrame.Raised)
            frame.setLineWidth(2)
            layout = QVBoxLayout()

            label = StyledLabel(f"PIN{i}", theme=self.theme_bgtrans)
            label.setAlignment(Qt.AlignCenter)
            label.setFont(QFont("Arial", 10, QFont.Bold))

            slider = StyledSlider(theme=self.theme_bgtrans, min_val=0, max_val=255, value=0)
            slider.valueChanged.connect(lambda value, pin_id=i: self.pwm_set(pin_id, value))

            value_label = StyledLabel("0 / 255", theme=self.theme_bgtrans)
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setFont(QFont("Arial", 12, QFont.Bold))
            value_label.setMinimumWidth(40)

            layout.addWidget(label)
            layout.addWidget(slider)
            layout.addWidget(value_label)
            frame.setLayout(layout)

            self.pwm_sliders[i] = (slider, value_label)
            pwm_layout.addWidget(frame)
        pwm_layout.setStretch(0, 1)
        pwm_layout.setStretch(1, 1)
        pwm_group.setLayout(pwm_layout)
        return pwm_group

    def _create_pwm_config_group(self):
        pwm_config_group = StyledGroupBox("PWM 設定", theme=self.theme_bgtrans)
        pwm_config_layout = QVBoxLayout()

        freq_layout = QHBoxLayout()
        freq_layout.addWidget(StyledLabel("周波数 (1~20000):", theme=self.theme_bgtrans))
        self.pwm_freq_input = StyledLineEdit(
            "1000", self.theme_input,
            mode="numeric_range", min_val=1, max_val=20000
        )
        self.pwm_freq_input.setText("1000")
        self.pwm_freq_input.textChanged.connect(self._update_pwm_constraint_hint)
        freq_layout.addWidget(self.pwm_freq_input)

        self.pwm_freq_label = StyledLabel("--", theme=self.theme_bgtrans)
        freq_layout.addWidget(self.pwm_freq_label)
        pwm_config_layout.addLayout(freq_layout)

        res_layout = QHBoxLayout()
        res_layout.addWidget(StyledLabel("解像度 (1~14):", theme=self.theme_bgtrans))
        self.pwm_res_input = StyledLineEdit(
            "8", self.theme_input,
            mode="numeric_range", min_val=1, max_val=14
        )
        self.pwm_res_input.setText("8")
        self.pwm_res_input.textChanged.connect(self._update_pwm_constraint_hint)
        res_layout.addWidget(self.pwm_res_input)

        self.pwm_res_label = StyledLabel("--", theme=self.theme_bgtrans)
        res_layout.addWidget(self.pwm_res_label)
        pwm_config_layout.addLayout(res_layout)

        self.pwm_constraint_label = StyledLabel("", theme=self.theme_bgtrans)
        self.pwm_constraint_label.setWordWrap(True)
        pwm_config_layout.addWidget(self.pwm_constraint_label)
        self._update_pwm_constraint_hint()

        button_layout = QHBoxLayout()
        self.pwm_config_read_btn = StyledButton("読込", theme=self.theme_btn_lamp)
        self.pwm_config_read_btn.clicked.connect(self.read_pwm_config)
        self.pwm_config_read_btn.setEnabled(False)
        button_layout.addWidget(self.pwm_config_read_btn)

        self.pwm_config_apply_btn = StyledButton("適用", theme=self.theme_btn_lamp)
        self.pwm_config_apply_btn.clicked.connect(self.apply_pwm_config)
        self.pwm_config_apply_btn.setEnabled(False)
        button_layout.addWidget(self.pwm_config_apply_btn)

        pwm_config_layout.addLayout(button_layout)
        pwm_config_group.setLayout(pwm_config_layout)
        return pwm_config_group

    def _create_log_group(self):
        log_group = StyledGroupBox("イベントログ", theme=self.theme_bgtrans)
        log_layout = QVBoxLayout()
        self.log_text = StyledTextEdit(
            self.theme_bgtrans,
            "UI を初期化しました。\n使える styled widget をすべて表示しています。"
        )
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(120)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        return log_group

    def append_log(self, message: str):
        """ログ表示を追加"""
        self.log_text.append(message)

    def get_refresh_interval(self) -> int:
        """入力値から更新間隔を決定"""
        interval = 500

        if self.refresh_interval_input.is_valid():
            self.refresh_interval_input.show_error("")
            try:
                interval = int(self.refresh_interval_input.value())
            except (TypeError, ValueError):
                interval = int(self.refresh_interval_input.text() or 500)
                return interval, False
        else:
            self.refresh_interval_input.show_error("50〜5000 の範囲で入力してください")
            return interval, False

        return interval, True

    def refresh_ports(self):
        """COM ポート一覧を再読込"""
        current_port = self.port_combo.currentText()
        ports = self.get_available_ports()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current_port in ports:
            self.port_combo.setCurrentText(current_port)
        self.connect_btn.setEnabled(bool(ports) and not self._connected)
        if not ports:
            self.append_log("利用可能な COM ポートが見つかりません。")
        self.append_log("COM ポート一覧を更新しました。")

    def get_available_ports(self):
        """利用可能な COM ポートを取得"""
        ports = [p.device for p in list_ports.comports()]
        return ports

    def connect_esp32(self):
        """ESP32 に接続"""
        port = self.port_combo.currentText()
        if not port:
            self.append_log("接続失敗: COM ポートが選択されていません。")
            QMessageBox.warning(self, "エラー", "利用可能な COM ポートがありません。")
            return
        self.connect_btn.setEnabled(False)
        self.refresh_ports_btn.setEnabled(False)
        self.port_combo.setEnabled(False)
        self.append_log(f"{port} に接続中...")
        self._connect_requested.emit(port)
        self.toggle_auto_refresh(False)

    def disconnect_esp32(self):
        """ESP32 から切断"""
        self.auto_refresh_timer.stop()
        self.auto_refresh_btn.blockSignals(True)
        self.auto_refresh_btn.setChecked(False)
        self.auto_refresh_btn.blockSignals(False)
        self.auto_refresh_btn.setText("自動更新: OFF")
        self.disconnect_btn.setEnabled(False)
        self._disconnect_requested.emit()

    def set_buttons_enabled(self, enabled: bool):
        """操作ボタンの有効/無効を設定"""
        for btn in self.dio_buttons.values():
            btn.setEnabled(enabled)
        for slider, _ in self.pwm_sliders.values():
            slider.setEnabled(enabled)
        self.pwm_config_read_btn.setEnabled(enabled)
        self.pwm_config_apply_btn.setEnabled(enabled)
        self.auto_refresh_btn.setEnabled(enabled)

    def on_do_toggle(self, pin_id: int, checked: bool = None):
        """DIO 出力ボタンがトグルされた"""
        if not self._connected:
            return
        if checked is None:
            checked = self.dio_buttons[pin_id].isChecked()
        value = 1 if checked else 0
        self._set_do_requested.emit(pin_id, value)

    def pwm_set(self, pin_id: int, value: int, emit: bool = True):
        """PWM の表示を更新し、必要なら送信する"""
        slider, value_label = self.pwm_sliders[pin_id]
        value_label.setText(f"{value} / {slider.maximum()}")
        if emit and self._connected:
            self._set_pwm_requested.emit(pin_id, value)

    def _minimum_pwm_freq_for_resolution(self, res: int) -> int:
        if res < 1:
            return 1
        return max(1, math.ceil(ESP32_S3_LEDC_CLOCK_HZ / (ESP32_S3_LEDC_MAX_DIVIDER * (1 << res))))

    def _minimum_pwm_resolution_for_frequency(self, freq: int) -> int:
        if freq < 1:
            return 15
        for res in range(1, 15):
            if freq >= self._minimum_pwm_freq_for_resolution(res):
                return res
        return 15

    def _update_pwm_constraint_hint(self):
        freq_text = self.pwm_freq_input.text().strip() if hasattr(self, "pwm_freq_input") else ""
        res_text = self.pwm_res_input.text().strip() if hasattr(self, "pwm_res_input") else ""

        try:
            freq = int(freq_text) if freq_text else 1000
        except ValueError:
            freq = 1000

        try:
            res = int(res_text) if res_text else 8
        except ValueError:
            res = 8

        min_freq = self._minimum_pwm_freq_for_resolution(res)
        min_res = self._minimum_pwm_resolution_for_frequency(freq)
        is_combo_valid = 1 <= res <= 14 and 1 <= freq <= 20000 and min_res <= 14 and freq >= min_freq

        if min_res > 14:
            text = (
                f"制約目安: {freq} Hz は低すぎます。"
                f"14 bit でも {self._minimum_pwm_freq_for_resolution(14)} Hz 以上が必要です。"
            )
        elif freq < min_freq:
            text = (
                f"制約目安: {res} bit では {min_freq} Hz 以上、"
                f"{freq} Hz を使うなら {min_res} bit 以上が必要です。"
            )
        else:
            text = f"制約目安: 現在の {freq} Hz / {res} bit は送信可能範囲です。"

        if hasattr(self, "pwm_constraint_label"):
            self.pwm_constraint_label.setText(text)
        if hasattr(self, "pwm_config_apply_btn"):
            self.pwm_config_apply_btn.setEnabled(self._connected and is_combo_valid)

    def _get_pwm_config_values(self):
        """PWM 設定入力を取得する"""
        if not (self.pwm_freq_input.is_valid() and self.pwm_res_input.is_valid()):
            QMessageBox.warning(self, "エラー", "周波数は 1～20000、解像度は 1～14 の範囲で入力してください")
            return None

        try:
            freq = int(self.pwm_freq_input.value())
            res = int(self.pwm_res_input.value())
        except (TypeError, ValueError):
            QMessageBox.warning(self, "エラー", "数値を正しく入力してください")
            return None

        self.pwm_freq_input.show_error("")
        self.pwm_res_input.show_error("")

        min_freq = self._minimum_pwm_freq_for_resolution(res)
        min_res = self._minimum_pwm_resolution_for_frequency(freq)

        if min_res > 14:
            message = (
                f"{freq} Hz はこの ESP32-S3 の PWM 制約では低すぎます。\n"
                f"少なくとも {self._minimum_pwm_freq_for_resolution(14)} Hz 以上にしてください。"
            )
            self.pwm_freq_input.show_error("周波数が低すぎます")
            QMessageBox.warning(self, "エラー", message)
            self._update_pwm_constraint_hint()
            return None

        if freq < min_freq:
            self.pwm_freq_input.show_error(f"{res} bit では {min_freq} Hz 以上")
            self.pwm_res_input.show_error(f"{freq} Hz なら {min_res} bit 以上")
            QMessageBox.warning(
                self,
                "エラー",
                f"{freq} Hz / {res} bit はこの ESP32-S3 では設定できません。\n"
                f"{res} bit を使うなら {min_freq} Hz 以上、"
                f"{freq} Hz を使うなら {min_res} bit 以上にしてください。",
            )
            self._update_pwm_constraint_hint()
            return None

        return freq, res

    def toggle_auto_refresh(self, checked: bool):
        """自動更新をトグル"""
        if checked:
            interval, success = self.get_refresh_interval()
            if success:
                self.auto_refresh_btn.setText(f"自動更新: ON")
                self.auto_refresh_btn.theme = self.theme_btn_lamp
                self.auto_refresh_btn.apply_style()
                self.auto_refresh_timer.start(interval)
                self.append_log(f"自動更新を開始しました ({interval} ms)。")
            else:
                self.auto_refresh_btn.setChecked(False)
        else:
            self.auto_refresh_btn.setText("自動更新: OFF")
            self.auto_refresh_btn.theme = self.theme_btn_off
            self.auto_refresh_btn.apply_style()
            self.auto_refresh_timer.stop()
            self.append_log("自動更新を停止しました。")

    def refresh_di_adc(self):
        """DIO入力と ADC を更新（Worker スレッドへ委譲）"""
        if not self._connected:
            return
        self._refresh_requested.emit()

    # --- Worker からのコールバック ---

    def _on_connected(self):
        self._connected = True
        port = self.port_combo.currentText()
        self.statusBar.showMessage(f"接続完了: {port}")
        self.append_log(f"{port} に接続しました。")
        self.response_speed_label.setText("応答速度: -- ms")
        self.set_buttons_enabled(True)
        self.disconnect_btn.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.refresh_ports_btn.setEnabled(False)
        # 接続直後に1回取得してUIを最新状態へ同期
        self._refresh_requested.emit()
        self._get_pwm_config_requested.emit()

    def _on_connection_failed(self, error: str):
        self.append_log(f"接続失敗: {error}")
        self.connect_btn.setEnabled(True)
        self.refresh_ports_btn.setEnabled(True)
        self.port_combo.setEnabled(True)
        QMessageBox.critical(self, "エラー", f"接続失敗: {error}")

    def _on_disconnected(self):
        self._connected = False
        self.statusBar.showMessage("切断状態")
        self.append_log("ESP32 から切断しました。")
        self.response_speed_label.setText("応答速度: -- ms")
        self.set_buttons_enabled(False)
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.refresh_ports_btn.setEnabled(True)

    def _on_di_adc_updated(self, di_values: list, adc_values: list, elapsed_ms: float):
        for pin_id, value in enumerate(di_values):
            self.di_lamps[pin_id].set_state(value)
        for pin_id, value in enumerate(adc_values):
            self.adc_labels[pin_id].setText(f"{value} / 4095")
            self.adc_bars[pin_id].setValue(value)
        self.response_speed_label.setText(f"応答速度: {elapsed_ms:.1f} ms")
        if self._connected:
            port = self.port_combo.currentText()
            self.statusBar.showMessage(f"接続中: {port} | 応答速度 {elapsed_ms:.1f} ms")

    def _on_do_done(self, pin_id: int, value: int):
        self.append_log(f"DO PIN{pin_id} -> {value}")

    def _on_do_failed(self, pin_id: int, error: str):
        self.append_log(f"set_do 失敗 (PIN{pin_id}): {error}")
        self.dio_buttons[pin_id].blockSignals(True)
        self.dio_buttons[pin_id].setChecked(not self.dio_buttons[pin_id].isChecked())
        self.dio_buttons[pin_id].blockSignals(False)
        QMessageBox.warning(self, "エラー", f"set_do 失敗: {error}")

    def _on_command_failed(self, error: str):
        self.append_log(error)

    def _on_pwm_config_updated(self, freq: int, res: int):
        """PWM 設定の表示とスライダー範囲を更新"""
        max_pwm_value = max((1 << res) - 1, 0)
        if res >= 14 and max_pwm_value > 0:
            max_pwm_value -= 1

        for pin_id, (slider, _) in self.pwm_sliders.items():
            old_max = max(slider.maximum(), 1)
            scaled_value = slider.value() * max_pwm_value // old_max

            slider.blockSignals(True)
            slider.setRange(0, max_pwm_value)
            slider.setValue(scaled_value)
            slider.blockSignals(False)

            self.pwm_set(pin_id, scaled_value)

        self.pwm_freq_label.setText(f"現在: {freq}")
        self.pwm_res_label.setText(f"現在: {res}")
        self.pwm_freq_input.setText(str(freq))
        self.pwm_res_input.setText(str(res))
        self._update_pwm_constraint_hint()
        self.append_log(f"PWM 設定: 周波数={freq} Hz, 解像度={res} bit (最大値={max_pwm_value})")

    def _on_pwm_config_failed(self, error: str):
        """PWM 設定変更が失敗しました"""
        self.append_log(error)
        QMessageBox.warning(self, "エラー", f"PWM設定エラー: {error}")

    def read_pwm_config(self):
        """PWM 設定を読み込む"""
        if not self._connected:
            return
        self.append_log("PWM 設定を読み込み中...")
        self._get_pwm_config_requested.emit()

    def apply_pwm_config(self):
        """PWM 設定を適用"""
        if not self._connected:
            return

        config = self._get_pwm_config_values()
        if not config:
            return

        freq, res = config
        self.append_log(f"PWM 設定を適用中... 周波数={freq}, 解像度={res}")
        self._set_pwm_config_requested.emit(freq, res)

    def closeEvent(self, event):
        # 停止要求 -> スレッド終了 -> 終了待ち の順で後始末する
        self.auto_refresh_timer.stop()
        self._disconnect_requested.emit()
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    ui = ESP32IOTestUI()
    ui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

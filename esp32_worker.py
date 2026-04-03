import time

from PySide6.QtCore import QObject, Signal, Slot

from esp32io import ESP32IO


class ESP32Worker(QObject):
    """ESP32IO通信をUIスレッド外で実行するWorker。"""
    connected = Signal()
    connection_failed = Signal(str)
    disconnected = Signal()
    di_adc_updated = Signal(list, list, float)
    do_done = Signal(int, int)
    do_failed = Signal(int, str)
    command_failed = Signal(str)
    pwm_config_updated = Signal(int, int)  # freq, res
    pwm_config_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.esp = None
        # 更新処理の多重実行を防ぐフラグ
        self._refreshing = False

    @Slot(str)
    def do_connect(self, port: str):
        """指定COMポートへ接続し、疎通確認(ping)まで行う。"""
        try:
            self.esp = ESP32IO(port, debug=False, recv_timeout=1.0)
            if not self.esp.ping():
                try:
                    self.esp.close()
                except Exception:
                    pass
                self.esp = None
                self.connection_failed.emit("ping 応答がありません")
                return
            self.connected.emit()
        except Exception as e:
            self.esp = None
            self.connection_failed.emit(str(e))

    @Slot()
    def do_disconnect(self):
        try:
            if self.esp:
                self.esp.close()
        except Exception:
            pass
        finally:
            self.esp = None
            self.disconnected.emit()

    @Slot()
    def do_refresh(self):
        """DI/ADCをまとめて読み取り、計測時間付きで通知する。"""
        if not self.esp or self._refreshing:
            return
        self._refreshing = True
        try:
            start = time.perf_counter()
            di_values = [self.esp.read_di(i) for i in range(6)]
            adc_values = [self.esp.read_adc(i) for i in range(2)]
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.di_adc_updated.emit(di_values, adc_values, elapsed_ms)
        except Exception as e:
            self.command_failed.emit(f"更新失敗: {str(e)}")
        finally:
            self._refreshing = False

    @Slot(int, int)
    def do_set_do(self, pin_id: int, value: int):
        if not self.esp:
            return
        try:
            self.esp.set_do(pin_id, value)
            self.do_done.emit(pin_id, value)
        except Exception as e:
            self.do_failed.emit(pin_id, str(e))

    @Slot(int, int)
    def do_set_pwm(self, pin_id: int, value: int):
        if not self.esp:
            return
        try:
            self.esp.set_pwm(pin_id, value)
        except Exception as e:
            self.command_failed.emit(f"set_pwm 失敗 (PIN{pin_id}): {str(e)}")

    @Slot()
    def do_get_pwm_config(self):
        """現在のPWM設定(周波数/解像度)を取得する。"""
        if not self.esp:
            return
        try:
            config = self.esp.get_pwm_config()
            freq = config.get("freq", 0)
            res = config.get("res", 0)
            self.pwm_config_updated.emit(freq, res)
        except Exception as e:
            self.pwm_config_failed.emit(f"PWM設定取得失敗: {str(e)}")

    @Slot(int, int)
    def do_set_pwm_config(self, freq: int, res: int):
        """PWM設定(周波数/解像度)を更新し、反映値を通知する。"""
        if not self.esp:
            return
        try:
            config = self.esp.set_pwm_config(freq, res)
            freq_result = config.get("freq", 0)
            res_result = config.get("res", 0)
            self.pwm_config_updated.emit(freq_result, res_result)
        except Exception as e:
            self.pwm_config_failed.emit(f"PWM設定変更失敗: {str(e)}")

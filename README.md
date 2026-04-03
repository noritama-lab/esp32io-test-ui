# esp32io-test-ui

ESP32IO のテストUIを分離して管理するための subtree リポジトリ。

A subtree repository to manage the ESP32IO test UI separately.

## Overview

このリポジトリは、ESP32IO デバイスの I/O 動作確認を GUI で行うためのテストツールです。

This repository provides a GUI test tool for validating ESP32IO device I/O behavior.

## Features

- COM ポートの選択と接続/切断
- DIO 入力の監視 (PIN 0-5)
- DIO 出力のトグル操作 (PIN 0-5)
- ADC 値の表示とプログレスバー表示 (PIN 0-1)
- PWM 出力のスライダー操作 (PIN 0-1)
- PWM 設定（周波数・解像度）の読み込みと変更 (周波数: 1-20000 Hz, 解像度: 1-16 bit)
- 自動更新間隔の設定とイベントログ表示

## Requirements

- Python 3.10+
- ESP32IO デバイス
- 依存ライブラリ:
	- PySide6
	- pyserial
	- pyside6stylekit
	- esp32io

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install PySide6 pyserial pyside6stylekit esp32io
```

## Run

```powershell
python esp32io_test_ui.py
```

## How To Use

1. COM ポートを選択して **接続** を押します。
2. 必要に応じて **自動更新** を ON にします。
3. DIO/ADC/PWM の各パネルで I/O を確認します。
4. PWM の周波数・解像度を設定する場合:
   - **PWM 設定** パネルで周波数（1-20000 Hz）と解像度（1-16 bit）を入力
   - **読込** ボタンで現在の設定値を取得
   - **適用** ボタンで新しい設定値を反映
5. PWM デューティ比はスライダーで設定（範囲は解像度に応じて 0〜$2^{res}-1$）
6. 終了時は **切断** してからウィンドウを閉じます。

## Files

- `esp32io_test_ui.py`: テストUI本体
- `esp32_worker.py`: ESP32IO 通信を担当する Worker（UIスレッド外で実行）

## Notes

- 接続先デバイスのファームウェア仕様に応じて、利用可能な機能は変わる場合があります。
- `esp32io` パッケージの API 変更がある場合は、UI 側の更新が必要です。

## License

This project is licensed under the MIT License. See `LICENSE` for details.

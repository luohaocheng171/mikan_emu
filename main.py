# -*- coding: utf-8 -*-
"""
随机启动插件
点一下按钮，随机抽一个游戏启动
"""
import random

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt


class RandomPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self._api = api
        self._current = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(30, 30, 30, 30)
        v.setSpacing(16)

        # 标题
        title = QLabel("🎲 随机启动")
        title.setObjectName("SectionTitle")
        v.addWidget(title)

        # 提示
        hint = QLabel("点下面的按钮，从游戏库里随机抽一个游戏直接启动。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        v.addWidget(hint)

        # 显示抽到的游戏
        self.lbl_result = QLabel("还没抽过")
        self.lbl_result.setAlignment(Qt.AlignCenter)
        self.lbl_result.setStyleSheet(
            "font-size:20px;font-weight:600;color:#0067c0;"
            "padding:30px;background:#f5f5f5;border-radius:8px;")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setMinimumHeight(120)
        v.addWidget(self.lbl_result)

        # 大按钮
        self.btn_roll = QPushButton("🎲 抽一个")
        self.btn_roll.setObjectName("PrimaryBtn")
        self.btn_roll.setMinimumHeight(50)
        self.btn_roll.setStyleSheet("font-size:16px;")
        self.btn_roll.clicked.connect(self._roll)
        v.addWidget(self.btn_roll)

        # 再启动一次
        self.btn_relaunch = QPushButton("🔁 再启动一次（同一个游戏）")
        self.btn_relaunch.setEnabled(False)
        self.btn_relaunch.clicked.connect(self._relaunch)
        v.addWidget(self.btn_relaunch)

        # 历史
        v.addWidget(QLabel("本次会话抽过的："))
        self.list_history = QListWidget()
        v.addWidget(self.list_history, 1)

    def _roll(self):
        games = self._api.get_games()
        if not games:
            self.lbl_result.setText("游戏库是空的，先导入几个游戏吧")
            return

        g = random.choice(games)
        self._current = g

        self.lbl_result.setText(
            f"<div style='font-size:14px;color:#767676;'>抽到的是</div>"
            f"<div style='font-size:22px;color:#0067c0;'>{g.name}</div>"
            f"<div style='font-size:13px;color:#767676;'>"
            f"{g.custom_platform or g.platform}</div>"
        )
        self.lbl_result.setTextFormat(Qt.RichText)
        self.btn_relaunch.setEnabled(True)

        item = QListWidgetItem(f"🎮 {g.name}   ({g.custom_platform or g.platform})")
        self.list_history.insertItem(0, item)

        # 直接启动
        self._api.launch_game(g)
        self._api.notify("随机启动", f"正在启动：{g.name}")

    def _relaunch(self):
        if not self._current:
            return
        self._api.launch_game(self._current)
        self._api.notify("随机启动", f"正在启动：{self._current.name}")


def register(api):
    """插件入口。程序加载时调用一次。"""
    api.add_page("随机启动", lambda: RandomPage(api), icon="🎲")
    api.log("随机启动插件已加载")
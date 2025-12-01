#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
驱动器图标管理器
"""

import sys
import os
import json
import datetime
import winreg
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLabel, QPushButton, QCheckBox, QFrame,
    QGraphicsDropShadowEffect, QSpacerItem, QSizePolicy,
    QProgressBar, QToolButton, QDialog,
    QListWidget, QListWidgetItem, QStackedWidget, QButtonGroup
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect,
    QThread, pyqtSignal, QParallelAnimationGroup, QSequentialAnimationGroup,
    QMargins, QPoint
)
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QBrush, QPen, QFont, QPalette, QIcon, QMouseEvent,
    QHoverEvent, QGuiApplication, QPixmap, QPainterPath
)

class DriveManagerCore:
    """驱动器管理核心逻辑"""

    def __init__(self):
        self.drives_data: Dict[str, Dict] = {}
        self.backup_registry_path = r"Software\DriveManager\Backups"
        self._ensure_backup_registry_path()

    def _ensure_backup_registry_path(self):
        """确保注册表备份路径存在"""
        try:
            # 创建备份注册表路径
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.backup_registry_path)
            key.Close()
            print(f"注册表备份路径已创建: {self.backup_registry_path}")
        except Exception as e:
            print(f"创建注册表备份路径失败: {e}")
            raise Exception(f"无法创建注册表备份路径 {self.backup_registry_path}: {str(e)}")

    def enum_namespace_drives(self) -> Dict[str, Dict]:
        """枚举命名空间下的驱动器"""
        drives = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r"Software\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace",
                              0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        drive_info = self.get_drive_info(subkey_name)
                        if drive_info:
                            drives[subkey_name] = drive_info
                        i += 1
                    except WindowsError:
                        break
        except WindowsError as e:
            if e.winerror == 2:
                pass
            else:
                raise
        return drives

    def get_drive_info(self, subkey_name: str) -> Optional[Dict]:
        """获取驱动器信息"""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\MyComputer\\NameSpace\\{subkey_name}",
                              0, winreg.KEY_READ) as subkey:
                try:
                    name, _ = winreg.QueryValueEx(subkey, "")
                except WindowsError:
                    name = subkey_name

                return {
                    'name': name,
                    'visible': True,
                    'original_visible': True
                }
        except WindowsError:
            return None

    def hide_drive(self, drive_key: str, drive_info: Dict) -> bool:
        """隐藏驱动器"""
        try:
            # 备份注册表数据到注册表
            backup_data = {}
            key_path = f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\MyComputer\\NameSpace\\{drive_key}"

            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as subkey:
                    i = 0
                    while True:
                        try:
                            name, value, reg_type = winreg.EnumValue(subkey, i)
                            backup_data[name] = {'value': value, 'type': reg_type}
                            i += 1
                        except WindowsError:
                            break
            except WindowsError:
                pass

            # 保存备份到注册表
            self._save_backup_to_registry(drive_key, drive_info.get('name', drive_key), backup_data)

            # 删除注册表项
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace",
                                  0, winreg.KEY_WRITE) as key:
                    winreg.DeleteKey(key, drive_key)
            except WindowsError as e:
                if e.winerror != 2:
                    raise

            drive_info['original_visible'] = False
            drive_info['has_backup'] = True
            return True

        except Exception as e:
            raise Exception(f"隐藏驱动器失败: {str(e)}")

    def _save_backup_to_registry(self, drive_key: str, drive_name: str, backup_data: Dict):
        """保存备份数据到注册表"""
        try:
            # 确保备份注册表路径存在
            self._ensure_backup_registry_path()

            backup_key_path = f"{self.backup_registry_path}\\{drive_key}"

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, backup_key_path) as backup_key:
                # 保存驱动器名称
                winreg.SetValueEx(backup_key, "name", 0, winreg.REG_SZ, drive_name)

                # 保存备份数据（JSON格式）
                import json
                backup_json = json.dumps(backup_data, ensure_ascii=False)
                winreg.SetValueEx(backup_key, "original_data", 0, winreg.REG_SZ, backup_json)

                # 保存备份时间
                import datetime
                backup_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                winreg.SetValueEx(backup_key, "backup_time", 0, winreg.REG_SZ, backup_time)

                # 设置备份标记
                winreg.SetValueEx(backup_key, "has_backup", 0, winreg.REG_DWORD, 1)

            # 验证备份是否成功创建
            verify_path = f"{self.backup_registry_path}\\{drive_key}"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, verify_path, 0, winreg.KEY_READ):
                    print(f"备份创建成功: {verify_path}")
            except WindowsError:
                raise Exception(f"备份验证失败，无法找到创建的备份路径: {verify_path}")

        except Exception as e:
            raise Exception(f"保存备份到注册表失败: {str(e)}")

    def _load_backup_from_registry(self, drive_key: str) -> Dict:
        """从注册表加载备份数据"""
        try:
            # 确保备份注册表路径存在
            self._ensure_backup_registry_path()

            backup_key_path = f"{self.backup_registry_path}\\{drive_key}"

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, backup_key_path, 0, winreg.KEY_READ) as backup_key:
                # 检查是否有备份标记
                try:
                    has_backup, _ = winreg.QueryValueEx(backup_key, "has_backup")
                    if not has_backup:
                        return None
                except WindowsError:
                    return None

                # 读取备份数据
                try:
                    backup_json, _ = winreg.QueryValueEx(backup_key, "original_data")
                    import json
                    return json.loads(backup_json)
                except WindowsError:
                    return None

        except WindowsError:
            return None
        except Exception as e:
            raise Exception(f"从注册表加载备份失败: {str(e)}")

    def _delete_backup_from_registry(self, drive_key: str):
        """从注册表删除备份"""
        try:
            # 确保备份注册表路径存在
            self._ensure_backup_registry_path()

            backup_key_path = f"{self.backup_registry_path}\\{drive_key}"

            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, backup_key_path)
            except WindowsError:
                pass  # 键不存在也视为成功

        except Exception as e:
            print(f"删除注册表备份失败: {str(e)}")

    def restore_drive(self, drive_key: str, drive_info: Dict) -> bool:
        """恢复驱动器"""
        try:
            # 从注册表读取备份数据
            backup_data = self._load_backup_from_registry(drive_key)

            if not backup_data:
                raise Exception("未找到备份数据")

            # 重新创建注册表项
            key_path = f"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\MyComputer\\NameSpace\\{drive_key}"

            try:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as subkey:
                    for name, data in backup_data.items():
                        winreg.SetValueEx(subkey, name, 0, data['type'], data['value'])
            except WindowsError as e:
                raise Exception(f"创建注册表项失败: {str(e)}")

            # 删除注册表中的备份
            self._delete_backup_from_registry(drive_key)

            drive_info['original_visible'] = True
            drive_info['has_backup'] = False
            return True

        except Exception as e:
            raise Exception(f"恢复驱动器失败: {str(e)}")

class MacOSTitleBar(QFrame):
    """macOS风格标题栏"""

    # 信号定义
    close_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    maximize_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.mouse_pressed = False
        self.mouse_pos = QPoint()
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border: none;
                border-bottom: 1px solid rgba(229, 229, 231, 0.5);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        # 窗口控制按钮
        # 关闭按钮
        self.close_btn = self.create_traffic_light("#ff5f57", "×")
        self.close_btn.clicked.connect(self.close_clicked)
        layout.addWidget(self.close_btn)

        layout.addSpacing(8)

        # 最小化按钮
        self.minimize_btn = self.create_traffic_light("#ffbd2e", "−")
        self.minimize_btn.clicked.connect(self.minimize_clicked)
        layout.addWidget(self.minimize_btn)

        layout.addSpacing(8)

        # 最大化按钮
        self.maximize_btn = self.create_traffic_light("#28ca42", "+")
        self.maximize_btn.clicked.connect(self.maximize_clicked)
        layout.addWidget(self.maximize_btn)

        # 弹性空间
        layout.addStretch()

        # 标题
        self.title_label = QLabel("驱动器图标管理器")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #333333;
                font-size: 14px;
                font-weight: 600;
                background: transparent;
            }
        """)
        self.title_label.setFont(QFont("Microsoft YaHei UI", 13, QFont.Weight.Medium))
        layout.addWidget(self.title_label)

        # 右侧弹性空间
        layout.addStretch()

    def create_traffic_light(self, color: str, symbol: str) -> QPushButton:
        """创建macOS风格交通灯按钮"""
        btn = QPushButton()
        btn.setFixedSize(12, 12)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: none;
                border-radius: 6px;
                color: rgba(0, 0, 0, 0.3);
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {color};
                border: 1px solid rgba(0, 0, 0, 0.2);
                color: rgba(0, 0, 0, 0.5);
            }}
            QPushButton:pressed {{
                background-color: {color};
                border: 1px solid rgba(0, 0, 0, 0.4);
            }}
        """)

        btn.setText(symbol)
        return btn

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = True
            self.mouse_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        self.mouse_pressed = False

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件"""
        if self.mouse_pressed and self.parent():
            parent_window = self.parent().window()
            if parent_window:
                new_pos = event.globalPosition().toPoint() - self.mouse_pos
                parent_window.move(parent_window.pos() + new_pos)
                self.mouse_pos = event.globalPosition().toPoint()

class MacOSDriveCard(QFrame):
    """macOS风格驱动器卡片"""

    # 信号定义
    toggled = pyqtSignal(str, bool)
    delete_requested = pyqtSignal(str)

    def __init__(self, drive_key: str, drive_info: Dict, parent=None):
        super().__init__(parent)
        self.drive_key = drive_key
        self.drive_info = drive_info
        self.is_hovered = False

        self.setFixedSize(500, 100)  # 从520增加到570，增加50px宽度
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.init_ui()
        self.setup_animations()

    def init_ui(self):
        """初始化UI"""
        self.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 16px;
                border: 1px solid #e9ecef;
            }
            QFrame:hover {
                background-color: #ffffff;
                border: 2px solid #007AFF;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)

        # 驱动器图标容器
        icon_container = QWidget()
        icon_container.setFixedSize(60, 60)
        icon_container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(0, 123, 255, 0.15),
                    stop:1 rgba(88, 86, 214, 0.15));
                border-radius: 16px;
                border: 1px solid rgba(0, 123, 255, 0.2);
            }
        """)

        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("color: #007AFF; font-size: 24px; background: transparent;")
        icon_label.setText("💾")
        icon_layout.addWidget(icon_label)

        layout.addWidget(icon_container)

        # 信息区域
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        # 驱动器名称
        name_label = QLabel(self.drive_info.get('name', '未知驱动器'))
        name_label.setStyleSheet("""
            QLabel {
                color: #212529;
                font-size: 16px;
                font-weight: 600;
                background: transparent;
            }
        """)
        name_label.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.Medium))
        info_layout.addWidget(name_label)

        # 驱动器ID
        id_text = self.drive_key[:30] + "..." if len(self.drive_key) > 30 else self.drive_key
        id_label = QLabel(f"ID: {id_text}")
        id_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-size: 13px;
                background: transparent;
            }
        """)
        id_label.setFont(QFont("Microsoft YaHei UI", 12))
        info_layout.addWidget(id_label)

        layout.addLayout(info_layout)

        # 弹性空间
        layout.addStretch()

        # 状态区域
        status_widget = QWidget()
        status_widget.setFixedSize(80, 40)

        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("启用" if self.drive_info.get('visible', True) else "禁用")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #34c759;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
        """ if self.drive_info.get('visible', True) else """
            QLabel {
                color: #ff3b30;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
        """)
        self.status_label.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Medium))
        status_layout.addWidget(self.status_label)

        layout.addWidget(status_widget)

        # macOS风格切换开关
        self.toggle_switch = MacOSToggleSwitch()
        self.toggle_switch.setChecked(self.drive_info.get('visible', True))
        self.toggle_switch.toggled.connect(self.on_toggled)
        layout.addWidget(self.toggle_switch)

        # 删除按钮
        self.delete_button = QPushButton("删除")
        self.delete_button.setFixedSize(60, 32)
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #ff3b30;
                border: none;
                border-radius: 6px;
                color: white;
                font-size: 12px;
                font-weight: 600;
                font-family: "Microsoft YaHei UI";
            }
            QPushButton:hover {
                background-color: #d70015;
            }
            QPushButton:pressed {
                background-color: #c70010;
            }
        """)
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self.on_delete_requested)
        layout.addWidget(self.delete_button)

        # 添加阴影效果
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(15)
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(3)
        self.shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(self.shadow)

    def setup_animations(self):
        """设置动画"""
        self.shadow_animation = QPropertyAnimation(self.shadow, b"blurRadius")
        self.shadow_animation.setDuration(150)
        self.shadow_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.shadow_offset_animation = QPropertyAnimation(self.shadow, b"yOffset")
        self.shadow_offset_animation.setDuration(150)
        self.shadow_offset_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.shadow_color_animation = QPropertyAnimation(self.shadow, b"color")
        self.shadow_color_animation.setDuration(150)
        self.shadow_color_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 组合动画组
        self.hover_animation_group = QParallelAnimationGroup()
        self.hover_animation_group.addAnimation(self.shadow_animation)
        self.hover_animation_group.addAnimation(self.shadow_offset_animation)

        self.position_animation = QPropertyAnimation(self, b"pos")
        self.position_animation.setDuration(150)
        self.position_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event):
        """鼠标进入事件"""
        self.is_hovered = True

        # 增强阴影效果
        self.shadow_animation.setStartValue(15)
        self.shadow_animation.setEndValue(25)

        # 增加Y偏移
        self.shadow_offset_animation.setStartValue(3)
        self.shadow_offset_animation.setEndValue(8)

        # 改变阴影颜色为蓝色
        self.shadow_color_animation.setStartValue(QColor(0, 0, 0, 20))
        self.shadow_color_animation.setEndValue(QColor(0, 123, 255, 40))

        # 轻微上移效果
        current_pos = self.pos()
        self.position_animation.setStartValue(current_pos)
        self.position_animation.setEndValue(current_pos + QPoint(0, -2))

        # 同时播放所有动画
        self.hover_animation_group.start()
        self.position_animation.start()

    def leaveEvent(self, event):
        """鼠标离开事件"""
        self.is_hovered = False

        # 恢复正常阴影
        self.shadow_animation.setStartValue(25)
        self.shadow_animation.setEndValue(15)

        # 恢复Y偏移
        self.shadow_offset_animation.setStartValue(8)
        self.shadow_offset_animation.setEndValue(3)

        # 恢复阴影颜色
        self.shadow_color_animation.setStartValue(QColor(0, 123, 255, 40))
        self.shadow_color_animation.setEndValue(QColor(0, 0, 0, 20))

        # 恢复位置
        current_pos = self.pos()
        self.position_animation.setStartValue(current_pos)
        self.position_animation.setEndValue(current_pos + QPoint(0, 2))

        # 同时播放所有动画
        self.hover_animation_group.start()
        self.position_animation.start()

    def on_toggled(self, checked: bool):
        """切换状态"""
        self.toggled.emit(self.drive_key, checked)
        # 更新状态标签
        self.status_label.setText("启用" if checked else "禁用")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #34c759;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
        """ if checked else """
            QLabel {
                color: #ff3b30;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
        """)

    def update_status(self, visible: bool):
        """更新状态"""
        self.toggle_switch.blockSignals(True)
        self.toggle_switch.setChecked(visible)
        self.toggle_switch.blockSignals(False)

    def on_delete_requested(self):
        """删除按钮点击处理"""
        # 显示确认对话框
        reply = MacOSMessageBox.show_question(
            self,
            "确认删除",
            f"确定要删除驱动器 \"{self.drive_info.get('name', self.drive_key)}\" 吗？\n\n此操作将永久删除该驱动器的所有备份和配置。"
        )

        if reply:
            self.delete_requested.emit(self.drive_key)

class MacOSToggleSwitch(QWidget):
    """macOS风格切换开关"""

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(51, 31)
        self.is_checked = True
        self.animation = QPropertyAnimation(self, b"")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def setChecked(self, checked: bool):
        """设置选中状态"""
        self.is_checked = checked
        self.update()

    def isChecked(self) -> bool:
        """获取选中状态"""
        return self.is_checked

    def paintEvent(self, event):
        """绘制开关"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景圆角矩形
        path = QPainterPath()
        path.addRoundedRect(1, 1, self.width() - 2, self.height() - 2, 15, 15)

        # 设置背景颜色
        if self.is_checked:
            # macOS绿色
            painter.fillPath(path, QColor(52, 199, 89))
        else:
            # macOS灰色
            painter.fillPath(path, QColor(142, 142, 147))

        # 滑块圆形
        slider_x = 25 if self.is_checked else 3
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.setPen(QPen(QColor(0, 0, 0, 15), 1))
        painter.drawEllipse(QRect(slider_x, 3, 25, 25))

        # 滑块内部阴影效果
        if self.is_checked:
            painter.setBrush(QBrush(QColor(52, 199, 89, 30)))
            painter.drawEllipse(QRect(slider_x + 2, 5, 21, 21))

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_checked = not self.is_checked
            self.update()
            self.toggled.emit(self.is_checked)

class MacOSMessageBox(QDialog):
    """自定义macOS风格提示框"""

    def __init__(self, parent=None, title="", message="", msg_type="info"):
        super().__init__(parent)
        self.title = title
        self.message = message
        self.msg_type = msg_type
        self.result = None

        self.init_ui()
        self.setup_animations()

    def init_ui(self):
        """初始化UI"""
        # 设置窗口属性 - 修复鼠标悬停问题
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(400, 200)
        # 移除透明背景，避免按钮渲染问题
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
        """)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建内容容器
        content_container = QFrame()
        content_container.setObjectName("content_container")
        content_container.setStyleSheet("""
            QFrame#content_container {
                background-color: white;
                border-radius: 12px;
                border: none;
            }
        """)

        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)

        # 标题栏区域
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        # 图标
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)

        if self.msg_type == "info":
            icon_text = "ℹ️"
            icon_color = "#007AFF"
        elif self.msg_type == "warning":
            icon_text = "⚠️"
            icon_color = "#FF9500"
        elif self.msg_type == "error":
            icon_text = "❌"
            icon_color = "#FF3B30"
        elif self.msg_type == "success":
            icon_text = "✅"
            icon_color = "#34C759"
        elif self.msg_type == "question":
            icon_text = "❓"
            icon_color = "#007AFF"
        else:
            icon_text = "ℹ️"
            icon_color = "#007AFF"

        icon_label.setText(icon_text)
        icon_label.setStyleSheet(f"""
            QLabel {{
                color: {icon_color};
                font-size: 20px;
                background: transparent;
            }}
        """)
        header_layout.addWidget(icon_label)

        header_layout.addSpacing(12)

        # 标题
        title_label = QLabel(self.title)
        title_label.setStyleSheet("""
            QLabel {
                color: #1d1d1f;
                font-size: 16px;
                font-weight: 600;
                background: transparent;
            }
        """)
        title_label.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.Medium))
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                color: #8e8e93;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: rgba(142, 142, 147, 0.1);
                color: #1d1d1f;
            }
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)

        content_layout.addLayout(header_layout)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.05);
                border: none;
                max-height: 1px;
            }
        """)
        content_layout.addWidget(separator)

        # 消息内容
        message_label = QLabel(self.message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        message_label.setStyleSheet("""
            QLabel {
                color: #3c3c43;
                font-size: 13px;
                line-height: 1.4;
                background: transparent;
                padding: 8px 0;
            }
        """)
        message_label.setFont(QFont("Microsoft YaHei UI", 12))
        content_layout.addWidget(message_label)

        content_layout.addStretch()

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)

        if self.msg_type == "question":
            # 问题类型显示"是"和"否"按钮
            no_btn = QPushButton("否")
            no_btn.setFixedSize(80, 32)
            no_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f0f0f0;
                    color: #333333;
                    border: 1px solid #d0d0d0;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                    border: 1px solid #b0b0b0;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
            """)
            no_btn.setFont(QFont("Microsoft YaHei UI", 12))
            no_btn.clicked.connect(self.reject)
            button_layout.addWidget(no_btn)

            button_layout.addStretch()

            yes_btn = QPushButton("是")
            yes_btn.setFixedSize(80, 32)
            yes_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {icon_color};
                    color: white;
                    border: 1px solid {icon_color};
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: #0056CC;
                    border: 1px solid #0056CC;
                }}
                QPushButton:pressed {{
                    background-color: #003D99;
                }}
            """)
            yes_btn.setFont(QFont("Microsoft YaHei UI", 12))
            yes_btn.clicked.connect(self.accept)
            button_layout.addWidget(yes_btn)
        else:
            # 其他类型只显示"确定"按钮
            ok_btn = QPushButton("确定")
            ok_btn.setFixedSize(80, 32)
            ok_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {icon_color};
                    color: white;
                    border: 1px solid {icon_color};
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: #0056CC;
                    border: 1px solid #0056CC;
                }}
                QPushButton:pressed {{
                    background-color: #003D99;
                }}
            """)
            ok_btn.setFont(QFont("Microsoft YaHei UI", 12))
            ok_btn.clicked.connect(self.accept)
            button_layout.addWidget(ok_btn)

            button_layout.addStretch()

        content_layout.addLayout(button_layout)

        layout.addWidget(content_container)

        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 30))
        content_container.setGraphicsEffect(shadow)

    def setup_animations(self):
        """设置动画"""
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(200)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)
        # 居中显示
        if self.parent():
            parent_rect = self.parent().geometry()
            self.move(
                parent_rect.x() + (parent_rect.width() - self.width()) // 2,
                parent_rect.y() + (parent_rect.height() - self.height()) // 2
            )
        else:
            screen = QGuiApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2
            )

        # 播放淡入动画
        self.fade_animation.start()

    @staticmethod
    def show_info(parent, title, message):
        """显示信息提示框"""
        dialog = MacOSMessageBox(parent, title, message, "info")
        MacOSMessageBox.center_dialog(dialog, parent)
        dialog.exec()
        return True

    @staticmethod
    def show_warning(parent, title, message):
        """显示警告提示框"""
        dialog = MacOSMessageBox(parent, title, message, "warning")
        MacOSMessageBox.center_dialog(dialog, parent)
        dialog.exec()
        return True

    @staticmethod
    def show_error(parent, title, message):
        """显示错误提示框"""
        dialog = MacOSMessageBox(parent, title, message, "error")
        MacOSMessageBox.center_dialog(dialog, parent)
        dialog.exec()
        return True

    @staticmethod
    def show_success(parent, title, message):
        """显示成功提示框"""
        dialog = MacOSMessageBox(parent, title, message, "success")
        MacOSMessageBox.center_dialog(dialog, parent)
        dialog.exec()
        return True

    def close_silently(self):
        """静默关闭对话框"""
        try:
            self.hide()
            # 使用QTimer延迟删除，确保操作完成
            QTimer.singleShot(100, self.deleteLater)
        except Exception:
            # 如果出现错误，强制删除
            try:
                self.deleteLater()
            except Exception:
                pass

    @staticmethod
    def center_dialog(dialog, parent):
        """居中显示对话框"""
        try:
            if parent and parent.isVisible():
                parent_rect = parent.geometry()
                dialog_size = dialog.size()

                # 计算居中位置
                x = parent_rect.x() + (parent_rect.width() - dialog_size.width()) // 2
                y = parent_rect.y() + (parent_rect.height() - dialog_size.height()) // 2

                # 确保对话框在屏幕范围内
                screen = QApplication.primaryScreen().geometry()
                if x < screen.left():
                    x = screen.left()
                elif x + dialog_size.width() > screen.right():
                    x = screen.right() - dialog_size.width()

                if y < screen.top():
                    y = screen.top()
                elif y + dialog_size.height() > screen.bottom():
                    y = screen.bottom() - dialog_size.height()

                dialog.move(x, y)
            else:
                # 如果没有父窗口或父窗口不可见，居中显示在主屏幕上
                screen = QApplication.primaryScreen().geometry()
                dialog_size = dialog.size()
                x = screen.x() + (screen.width() - dialog_size.width()) // 2
                y = screen.y() + (screen.height() - dialog_size.height()) // 2
                dialog.move(x, y)
        except Exception:
            pass

    @staticmethod
    def show_question(parent, title, message):
        """显示问题提示框"""
        dialog = MacOSMessageBox(parent, title, message, "question")
        MacOSMessageBox.center_dialog(dialog, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.core = DriveManagerCore()
        self.drive_cards: Dict[str, MacOSDriveCard] = {}

        # 设置无边框窗口，但保持背景
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        # 移除透明背景，使用白色背景

        self.init_ui()
        self.setup_animations()
        self.load_drives()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("驱动器图标管理器 - macOS风格")
        self.setMinimumSize(970, 700)

        # 设置窗口样式 - 白色背景，不透明
        self.setStyleSheet("""
            QMainWindow {
                background-color: white;
            }
            QWidget {
                background-color: white;
            }
        """)

        # 不设置透明背景，保持不透明

        # 创建中央窗口部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 主布局
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建标题栏
        self.title_bar = MacOSTitleBar(self)
        self.title_bar.close_clicked.connect(self.close)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.maximize_clicked.connect(self.toggle_maximize)
        main_layout.addWidget(self.title_bar)

        # 创建主内容区域
        self.create_main_content(main_layout)

    def resizeEvent(self, event):
        """窗口大小改变时重绘圆角 - 简化版本"""
        super().resizeEvent(event)

        # 不使用复杂掩码，保持窗口完全可见
        # 圆角效果通过CSS样式实现

    def create_main_content(self, layout):
        """创建主内容区域"""
        # 主内容容器
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: white;")

        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(60, 40, 60, 40)

        # 标题区域
        self.create_header(content_layout)

        # 驱动器列表区域
        self.create_drive_list(content_layout)

        # 操作按钮区域
        self.create_action_buttons(content_layout)

        layout.addWidget(content_widget)

    def create_header(self, layout):
        """创建标题区域"""
        header_widget = QWidget()
        header_widget.setFixedHeight(100)

        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 主标题
        title_label = QLabel("驱动器管理")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #1d1d1f;
                font-size: 36px;
                font-weight: 700;
                background: transparent;
            }
        """)
        title_label.setFont(QFont("Microsoft YaHei UI", 32, QFont.Weight.Bold))
        header_layout.addWidget(title_label)

        # 副标题
        subtitle_label = QLabel('管理"我的电脑"中的第三方软件驱动器图标')
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-size: 16px;
                font-weight: 400;
                background: transparent;
            }
        """)
        subtitle_label.setFont(QFont("Microsoft YaHei UI", 14))
        header_layout.addWidget(subtitle_label)

        # 统计信息
        self.stats_label = QLabel("共 0 个驱动器")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_label.setStyleSheet("""
            QLabel {
                color: #6c757d;
                font-size: 13px;
                font-weight: 500;
                background: transparent;
                margin-top: 8px;
                padding: 6px 16px;
                background-color: #f8f9fa;
                border-radius: 12px;
            }
        """)
        self.stats_label.setFont(QFont("Microsoft YaHei UI", 11))
        header_layout.addWidget(self.stats_label)

        layout.addWidget(header_widget)

    def create_drive_list(self, layout):
        """创建驱动器列表"""
        # 驱动器滚动区域 - 直接创建，避免嵌套布局问题
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 修复滚动条样式 - 使用更简洁的样式避免黑色长条
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 0px;
                border: none;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: transparent;
                border: none;
                width: 0px;
                min-height: 0px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::up-arrow:vertical,
            QScrollBar::down-arrow:vertical {
                border: none;
                background: none;
                width: 0px;
                height: 0px;
            }
        """)

        # 驱动器容器 - 居中对齐，增加最大宽度以显示完整内容
        self.drive_container = QWidget()
        self.drive_container.setMaximumWidth(550)  # 从500增加到550，增加50px宽度
        self.drive_container.setStyleSheet("background-color: transparent;")
        self.drive_layout = QVBoxLayout(self.drive_container)
        self.drive_layout.setContentsMargins(20, 20, 20, 20)  # 添加边距避免内容贴边
        self.drive_layout.setSpacing(20)
        self.drive_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 将驱动器容器设置为滚动区域的widget
        self.scroll_area.setWidget(self.drive_container)

        # 创建居中布局来包装滚动区域
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(self.scroll_area)
        center_layout.addStretch()

        # 将居中布局添加到主布局中
        layout.addLayout(center_layout)

        # 设置滚动条策略 - 仅在需要时显示，并且避免黑色长条
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def create_action_buttons(self, layout):
        """创建操作按钮"""
        button_container = QWidget()
        button_container.setFixedHeight(100)

        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 30, 0, 0)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 现代化按钮样式
        modern_button_style = """
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #0056CC;
            }
            QPushButton:pressed {
                background-color: #003D99;
            }
        """

        # 刷新按钮
        self.refresh_btn = QPushButton("🔄 刷新列表")
        self.refresh_btn.setStyleSheet(modern_button_style)
        self.refresh_btn.clicked.connect(self.refresh_drives)
        button_layout.addWidget(self.refresh_btn)

        button_layout.addSpacing(20)

        # 保存设置按钮
        self.save_btn = QPushButton("💾 保存设置")
        self.save_btn.setStyleSheet(modern_button_style.replace("#007AFF", "#34C759"))
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)

        button_layout.addSpacing(20)

        # 重启资源管理器按钮
        self.restart_btn = QPushButton("🔄 重启资源管理器")
        self.restart_btn.setStyleSheet(modern_button_style.replace("#007AFF", "#FF3B30"))
        self.restart_btn.clicked.connect(self.restart_explorer)
        button_layout.addWidget(self.restart_btn)

        layout.addWidget(button_container)

    def toggle_maximize(self):
        """切换最大化状态"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def setup_animations(self):
        """设置动画"""
        self.fade_in_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in_animation.setDuration(500)
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def load_drives(self):
        """加载驱动器列表"""
        try:
            # 清除现有卡片
            for card in self.drive_cards.values():
                card.deleteLater()
            self.drive_cards.clear()

            # 加载数据
            self.core.drives_data = self.core.enum_namespace_drives()

            # 检查备份文件
            self.check_backup_files()

            # 更新统计信息
            self.stats_label.setText(f"共 {len(self.core.drives_data)} 个驱动器")

            if not self.core.drives_data:
                # 显示空状态
                empty_widget = QWidget()
                empty_widget.setFixedSize(450, 120)
                empty_widget.setStyleSheet("""
                    QWidget {
                        background-color: rgba(255, 255, 255, 0.8);
                        border-radius: 16px;
                        border: 1px solid rgba(0, 0, 0, 0.1);
                    }
                """)

                empty_layout = QVBoxLayout(empty_widget)
                empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                empty_label = QLabel("未找到第三方软件驱动器")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_label.setStyleSheet("""
                    QLabel {
                        color: #86868b;
                        font-size: 16px;
                        font-weight: 500;
                        background: transparent;
                        padding: 20px;
                    }
                """)
                empty_layout.addWidget(empty_label)

                self.drive_layout.addWidget(empty_widget)
            else:
                # 创建驱动器卡片
                for drive_key, drive_info in self.core.drives_data.items():
                    card = MacOSDriveCard(drive_key, drive_info)
                    card.toggled.connect(self.on_drive_toggled)
                    card.delete_requested.connect(self.on_drive_delete_requested)
                    self.drive_layout.addWidget(card)
                    self.drive_cards[drive_key] = card

            # 显示窗口时播放淡入动画
            self.fade_in_animation.start()

        except Exception as e:
            MacOSMessageBox.show_error(self, "错误", f"加载驱动器列表失败: {str(e)}")

    def check_backup_files(self):
        """检查注册表中的备份"""
        try:
            # 确保备份注册表路径存在
            self.core._ensure_backup_registry_path()

            # 打开备份注册表路径
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.core.backup_registry_path, 0, winreg.KEY_READ) as backup_root:
                i = 0
                while True:
                    try:
                        drive_key = winreg.EnumKey(backup_root, i)
                        i += 1

                        # 读取备份信息
                        backup_info = self._load_backup_info(drive_key)
                        if not backup_info:
                            continue

                        # 检查是否在当前驱动器列表中
                        if drive_key not in self.core.drives_data:
                            self.core.drives_data[drive_key] = {
                                'name': backup_info['name'],
                                'visible': False,
                                'original_visible': False,
                                'has_backup': True,
                                'backup_time': backup_info['backup_time'],
                                'hidden': True
                            }
                        else:
                            # 更新现有驱动器的备份信息
                            self.core.drives_data[drive_key]['has_backup'] = True
                            self.core.drives_data[drive_key]['backup_time'] = backup_info['backup_time']

                    except WindowsError:
                        break
        except WindowsError:
            # 备份注册表路径不存在
            pass
        except Exception as e:
            print(f"检查备份时出错: {e}")

    def _load_backup_info(self, drive_key: str) -> Dict:
        """加载单个驱动器的备份信息"""
        try:
            # 确保备份注册表路径存在
            self.core._ensure_backup_registry_path()

            backup_key_path = f"{self.core.backup_registry_path}\\{drive_key}"

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, backup_key_path, 0, winreg.KEY_READ) as backup_key:
                # 检查是否有备份标记
                try:
                    has_backup, _ = winreg.QueryValueEx(backup_key, "has_backup")
                    if not has_backup:
                        return None
                except WindowsError:
                    return None

                # 读取备份信息
                backup_info = {}

                # 读取驱动器名称
                try:
                    name, _ = winreg.QueryValueEx(backup_key, "name")
                    backup_info['name'] = name
                except WindowsError:
                    backup_info['name'] = drive_key

                # 读取备份时间
                try:
                    backup_time, _ = winreg.QueryValueEx(backup_key, "backup_time")
                    backup_info['backup_time'] = backup_time
                except WindowsError:
                    backup_info['backup_time'] = "未知时间"

                return backup_info

        except WindowsError:
            return None
        except Exception as e:
            print(f"加载备份信息失败 {drive_key}: {e}")
            return None

    def on_drive_toggled(self, drive_key: str, visible: bool):
        """驱动器状态切换"""
        if drive_key in self.core.drives_data:
            self.core.drives_data[drive_key]['visible'] = visible

    def on_drive_delete_requested(self, drive_key: str):
        """驱动器删除请求处理"""
        try:
            # 首先确保驱动器当前是隐藏状态（如果显示的话）
            if drive_key in self.core.drives_data:
                drive_info = self.core.drives_data[drive_key]
                if drive_info.get('visible', True):
                    # 隐藏驱动器
                    self.core.hide_drive(drive_key, drive_info)
                    drive_info['visible'] = False

                # 删除备份数据
                self.core._delete_backup_from_registry(drive_key)

                # 从数据中移除
                del self.core.drives_data[drive_key]

                # 从界面中移除卡片
                if drive_key in self.drive_cards:
                    card = self.drive_cards[drive_key]
                    card.hide()
                    self.drive_layout.removeWidget(card)
                    card.deleteLater()
                    del self.drive_cards[drive_key]

                # 显示成功消息
                MacOSMessageBox.show_info(self, "删除成功", "驱动器已成功删除！")

                # 检查是否还有驱动器，如果没有则显示空状态
                if not self.core.drives_data:
                    self.refresh_drives()

        except Exception as e:
            MacOSMessageBox.show_error(self, "删除失败", f"删除驱动器时出错: {str(e)}")

    def refresh_drives(self):
        """刷新驱动器列表"""
        self.load_drives()

    def save_settings(self):
        """保存设置"""
        try:
            changes_count = 0
            error_messages = []

            for drive_key, drive_info in self.core.drives_data.items():
                should_show = drive_info.get('visible', True)
                currently_showing = drive_info.get('original_visible', True)

                if should_show != currently_showing:
                    try:
                        if should_show:
                            self.core.restore_drive(drive_key, drive_info)
                        else:
                            self.core.hide_drive(drive_key, drive_info)
                        changes_count += 1
                    except Exception as e:
                        error_messages.append(f"{drive_info.get('name', drive_key)}: {str(e)}")

            # 显示结果
            if error_messages:
                error_detail = "\n".join(error_messages)
                if changes_count > 0:
                    MacOSMessageBox.show_warning(self, "部分保存成功",
                        f"已成功修改 {changes_count} 个驱动器设置，但以下操作失败:\n\n{error_detail}")
                else:
                    MacOSMessageBox.show_error(self, "保存失败", f"所有操作都失败了:\n\n{error_detail}")
            else:
                if changes_count > 0:
                    MacOSMessageBox.show_success(self, "保存成功",
                        f"已成功修改 {changes_count} 个驱动器设置。\n\n请重启资源管理器以查看效果。")
                else:
                    MacOSMessageBox.show_info(self, "无需更改", "没有需要修改的设置。")

        except Exception as e:
            MacOSMessageBox.show_error(self, "保存失败", f"保存设置时出现严重错误: {str(e)}")

    def restart_explorer(self):
        """重启Windows资源管理器"""
        reply = MacOSMessageBox.show_question(self, "确认重启",
            "重启资源管理器将使更改立即生效。\n\n"
            "这会关闭所有打开的文件夹窗口。\n\n"
            "确定要继续吗？")

        if reply:
            # 先显示进度提示 - 窗口置顶但不模态
            progress_dialog = MacOSMessageBox(self, "正在重启",
                "正在重启Windows资源管理器，请稍候...\n\n"
                "桌面可能会短暂闪烁，这是正常现象。\n\n"
                "请不要关闭此窗口，等待操作完成。", "info")
            # 不设置模态，让窗口保持可见但允许用户操作
            progress_dialog.show()

            # 使用QTimer延迟执行，避免阻塞UI
            QTimer.singleShot(500, lambda: self._do_restart_explorer(progress_dialog))

    def _do_restart_explorer(self, progress_dialog):
        """实际执行重启资源管理器操作"""
        try:
            import subprocess
            import threading
            import time

            def restart_in_thread():
                try:
                    # 关闭Windows资源管理器
                    subprocess.run(['taskkill', '/f', '/im', 'explorer.exe'],
                                 capture_output=True, text=True, timeout=10)

                    # 等待explorer完全关闭
                    time.sleep(3)

                    # 重新启动explorer - 使用更可靠的方法
                    try:
                        subprocess.Popen(['explorer.exe'], shell=True)
                    except Exception as restart_e:
                        # 备用方法
                        subprocess.run(['start', 'explorer.exe'], shell=True, capture_output=True)

                    # 设置结果标志，让主线程知道操作完成
                    self._restart_success = True

                except subprocess.TimeoutExpired:
                    self._restart_success = False
                    self._restart_error = "操作超时，请手动重启计算机或重试。"
                except Exception as thread_e:
                    self._restart_success = False
                    self._restart_error = f"重启过程中出现错误: {str(thread_e)}"

            # 初始化状态变量
            self._restart_success = None
            self._restart_error = None

            # 在独立线程中执行重启操作
            thread = threading.Thread(target=restart_in_thread, daemon=True)
            thread.start()

            # 监控线程状态
            def check_restart_status():
                if self._restart_success is None:
                    # 还在进行中，继续检查
                    QTimer.singleShot(500, check_restart_status)
                else:
                    # 操作完成，关闭进度对话框
                    progress_dialog.close_silently()

                    # 延迟显示结果
                    QTimer.singleShot(500, lambda: self._show_restart_result())

            # 开始监控
            QTimer.singleShot(1000, check_restart_status)

        except Exception as e:
            progress_dialog.close_silently()
            MacOSMessageBox.show_error(self, "启动失败", f"无法启动重启操作: {str(e)}")

    def _show_restart_result(self):
        """显示重启结果"""
        if hasattr(self, '_restart_success') and self._restart_success:
            MacOSMessageBox.show_success(self, "重启成功",
                "资源管理器已重启，更改已生效。\n\n"
                "桌面的驱动器图标现在应该已更新。")
        elif hasattr(self, '_restart_error'):
            MacOSMessageBox.show_error(self, "重启失败", self._restart_error)
        else:
            MacOSMessageBox.show_error(self, "重启失败", "未知错误，请手动重启计算机。")

    def show_about(self):
        """显示关于对话框"""
        about_text = """驱动器图标管理器

作者：小笙睡不醒
版本：1.0.0 """

        MacOSMessageBox.show_info(self, "关于", about_text)

    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        # 居中显示窗口
        if self.parent() is None:
            screen = QGuiApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2
            )

def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置应用程序信息
    app.setApplicationName("驱动器图标管理器")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("小笙睡不醒")

    # 创建主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
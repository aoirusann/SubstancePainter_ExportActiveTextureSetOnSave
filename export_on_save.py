"""
Substance Painter Plugin: Export on Save
Automatically exports textures when saving project, with user-configurable settings.

Features:
- Toggle to enable/disable auto export
- Dropdown to select export preset
- Logging of export results
"""

import json
import os
from functools import partial
from typing import Dict, List, Optional
import PySide6.QtWidgets as QtWidgets
import PySide6.QtCore as QtCore
import PySide6.QtGui as QtGui

# Substance Painter imports
import _substance_painter.project as _sp_p
import substance_painter.event
import substance_painter.export
import substance_painter.logging
import substance_painter.ui
import substance_painter.project
import substance_painter.resource
import substance_painter.textureset
import substance_painter.js

# Plugin settings
PLUGIN_NAME = "Export on Save"
SETTINGS_FILE = "export_on_save_settings.json"

class ExportOnSaveWidget(QtWidgets.QWidget):
	"""主插件控制面板"""
	
	def __init__(self):
		super().__init__()
		self.setObjectName("ExportOnSaveWidget")
		self.setWindowTitle(PLUGIN_NAME)
		self.setWindowIcon(QtGui.QIcon())
		
		# 设置变量
		self.enabled = False
		
		self.load_settings()
		self.init_ui()
	
	def init_ui(self):
		"""初始化用户界面"""
		layout = QtWidgets.QVBoxLayout()
		layout.setSpacing(10)
		
		# 标题
		title_label = QtWidgets.QLabel(PLUGIN_NAME)
		title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
		layout.addWidget(title_label)
		
		# 启用/禁用开关
		self.enable_checkbox = QtWidgets.QCheckBox("启用保存时自动导出")
		self.enable_checkbox.setChecked(self.enabled)
		self.enable_checkbox.stateChanged.connect(self.on_enabled_changed)
		layout.addWidget(self.enable_checkbox)
		

		
		# 状态显示
		self.status_label = QtWidgets.QLabel("状态: 就绪")
		self.status_label.setStyleSheet("color: green;")
		layout.addWidget(self.status_label)
		
		# 控制按钮行
		button_row = QtWidgets.QHBoxLayout()
		
		# 测试按钮（用于调试）
		test_button = QtWidgets.QPushButton("手动导出测试")
		test_button.clicked.connect(self.manual_export_test)
		button_row.addWidget(test_button)
		

		
		# 调试信息按钮
		debug_button = QtWidgets.QPushButton("显示调试信息")
		debug_button.clicked.connect(self.show_debug_info)
		debug_button.setToolTip("显示当前激活纹理集的调试信息")
		button_row.addWidget(debug_button)
		
		layout.addLayout(button_row)
		
		# 说明文本
		help_text = QtWidgets.QLabel(
			"说明：启用后，每次保存项目时将自动使用当前项目的导出配置导出当前激活的纹理集。"
			"导出结果会显示在日志中。"
		)
		help_text.setWordWrap(True)
		help_text.setStyleSheet("color: gray; font-size: 11px;")
		layout.addWidget(help_text)
		
		layout.addStretch()
		self.setLayout(layout)
	

	def on_enabled_changed(self, state):
		"""启用状态改变时的回调"""
		print(f"===={type(state)}: {state}====")

		self.enabled = (QtCore.Qt.CheckState(state) == QtCore.Qt.CheckState.Checked)
		self.save_settings()
		
		status = "启用" if self.enabled else "禁用"
		self.status_label.setText(f"状态: 自动导出已{status}")
		self.status_label.setStyleSheet("color: green;" if self.enabled else "color: gray;")
		
		substance_painter.logging.info(f"[{PLUGIN_NAME}] 自动导出功能已{status}")
	




	
	def show_debug_info(self):
		"""显示调试信息"""
		try:
			substance_painter.logging.info(f"[{PLUGIN_NAME}] === 调试信息 ===")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] 启用状态: {self.enabled}")

			# 显示当前激活的纹理集信息
			try:
				active_stack = substance_painter.textureset.get_active_stack()
				active_texture_set = active_stack.material()
				active_texture_set_name = active_texture_set.name()

				substance_painter.logging.info(f"[{PLUGIN_NAME}] 当前激活的纹理集: '{active_texture_set_name}'")
				substance_painter.logging.info(f"[{PLUGIN_NAME}] 当前激活的栈: '{active_stack.name()}'")

			except Exception as e:
				substance_painter.logging.warning(f"[{PLUGIN_NAME}] 获取当前激活纹理集失败: {str(e)}")

			self.status_label.setText("状态: 调试信息已输出到日志")
			self.status_label.setStyleSheet("color: green;")

			substance_painter.logging.info(f"[{PLUGIN_NAME}] === 调试信息结束 ===")

		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] 显示调试信息失败: {str(e)}")
	
	def manual_export_test(self):
		"""手动导出测试"""
		try:
			# 添加调试信息
			active_stack = substance_painter.textureset.get_active_stack()
			active_texture_set = active_stack.material()
			active_texture_set_name = active_texture_set.name()

			substance_painter.logging.info(f"[{PLUGIN_NAME}] 调试信息：")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] - 当前激活的纹理集: '{active_texture_set_name}'")

		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] 获取当前激活纹理集失败: {str(e)}")
			self.status_label.setText(f"状态: 获取当前纹理集失败 - {str(e)}")
			self.status_label.setStyleSheet("color: red;")
			return

		if not substance_painter.project.is_open():
			self.status_label.setText("状态: 没有打开的项目")
			self.status_label.setStyleSheet("color: red;")
			return

		self.execute_export("手动导出测试")
	
	def execute_export(self, trigger_source="自动导出"):
		"""执行导出操作"""
		try:

			# 获取当前激活的纹理集
			try:
				active_stack = substance_painter.textureset.get_active_stack()
				active_texture_set = active_stack.material()
				active_texture_set_name = active_texture_set.name()

				if not active_texture_set_name:
					substance_painter.logging.warning(f"[{PLUGIN_NAME}] {trigger_source}: 当前激活的纹理集没有名称")
					self.status_label.setText("状态: 当前纹理集无名称")
					self.status_label.setStyleSheet("color: orange;")
					return

				# 构建导出列表，只包含当前激活的纹理集
				export_list = [{"rootPath": active_texture_set_name}]

				substance_painter.logging.info(f"[{PLUGIN_NAME}] {trigger_source}: 将导出当前激活的纹理集 '{active_texture_set_name}'")

			except Exception as e:
				substance_painter.logging.error(f"[{PLUGIN_NAME}] 获取当前激活纹理集时出错: {str(e)}")
				self.status_label.setText("状态: 获取当前纹理集失败")
				self.status_label.setStyleSheet("color: red;")
				return

			# 获取当前导出路径
			export_path = substance_painter.js.evaluate("alg.mapexport.exportPath()")

			# 获取当前导出设定
			export_fileFormat = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().fileFormat")
			export_padding = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().padding").lower()
			export_dilation = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().dilation")
			export_bitDepth = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().bitDepth")
			export_exportShaderParams = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().exportShaderParams")

			if export_padding == "infinite" or export_padding == "passthrough":
				export_dithering = False
			else:
				export_dithering = True


			# 获取当前导出预设
			export_preset = substance_painter.js.evaluate("alg.mapexport.getProjectExportPreset()")
			
			# 构建导出配置
			export_config = {
				"exportShaderParams": export_exportShaderParams,
				"defaultExportPreset": export_preset,
				"exportPath": export_path,
				"exportList": export_list,
				"exportParameters": [{
					"parameters": {
						"fileFormat": export_fileFormat,
						"bitDepth": str(export_bitDepth),
						"dithering": export_dithering,
						"paddingAlgorithm": export_padding,
						"dilationDistance": export_dilation,
					}
				}]
			}
			
			# 记录将要导出的纹理集
			texture_set_names = [item["rootPath"] for item in export_list]
			substance_painter.logging.info(
				f"[{PLUGIN_NAME}] {trigger_source}: 准备导出纹理集: {', '.join(texture_set_names)}"
			)
			
			self.status_label.setText("状态: 正在导出...")
			self.status_label.setStyleSheet("color: orange;")
			
			# 执行导出
			result = substance_painter.export.export_project_textures(export_config)

			if result.status == substance_painter.export.ExportStatus.Success:
				# 统计导出的文件数量
				file_count = sum(len(files) for files in result.textures.values())
				
				self.status_label.setText(f"状态: 导出成功 ({file_count} 个文件)")
				self.status_label.setStyleSheet("color: green;")
				
				substance_painter.logging.info(
					f"[{PLUGIN_NAME}] {trigger_source}完成: 成功导出 {file_count} 个贴图文件到 {export_path}"
				)
				
				# 详细记录导出的文件
				for (texture_set, stack), files in result.textures.items():
					substance_painter.logging.info(
						f"[{PLUGIN_NAME}] 贴图集 '{texture_set}' -> {len(files)} 个文件"
					)
				
			elif result.status == substance_painter.export.ExportStatus.Warning:
				self.status_label.setText("状态: 导出完成但有警告")
				self.status_label.setStyleSheet("color: orange;")
				substance_painter.logging.warning(
					f"[{PLUGIN_NAME}] {trigger_source}完成但有警告: {result.message}"
				)
				
			elif result.status == substance_painter.export.ExportStatus.Cancelled:
				self.status_label.setText("状态: 导出被取消")
				self.status_label.setStyleSheet("color: orange;")
				substance_painter.logging.info(
					f"[{PLUGIN_NAME}] {trigger_source}被用户取消"
				)
			
			else:
				self.status_label.setText(f"状态: 导出失败")
				self.status_label.setStyleSheet("color: red;")
				substance_painter.logging.error(
					f"[{PLUGIN_NAME}] {trigger_source}失败: {result.message}"
				)
				
		except Exception as e:
			self.status_label.setText(f"状态: 导出异常 - {str(e)}")
			self.status_label.setStyleSheet("color: red;")
			substance_painter.logging.error(f"[{PLUGIN_NAME}] {trigger_source}时发生异常: {str(e)}")
	
	def load_settings(self):
		"""加载设置"""
		try:
			settings_path = os.path.join(
				os.path.dirname(__file__),
				SETTINGS_FILE
			)

			if os.path.exists(settings_path):
				with open(settings_path, 'r', encoding='utf-8') as f:
					settings = json.load(f)

				self.enabled = settings.get('enabled', False)

		except Exception as e:
			substance_painter.logging.warning(f"[{PLUGIN_NAME}] 加载设置失败: {str(e)}")
	
	def save_settings(self):
		"""保存设置"""
		try:
			settings = {
				'enabled': self.enabled
			}

			settings_path = os.path.join(
				os.path.dirname(__file__),
				SETTINGS_FILE
			)

			with open(settings_path, 'w', encoding='utf-8') as f:
				json.dump(settings, f, indent=2, ensure_ascii=False)

		except Exception as e:
			substance_painter.logging.warning(f"[{PLUGIN_NAME}] 保存设置失败: {str(e)}")


# 全局变量
export_widget = None
dock_widget = None

def on_project_saved(event):
	"""项目保存事件处理器"""
	global export_widget
	
	if export_widget and export_widget.enabled:
		substance_painter.logging.info(f"[{PLUGIN_NAME}] 检测到项目保存，开始自动导出...")
		# About Unlock and Lock: sp will lock the project file during all the saving progress,
		#   which will block the access to the texture set,
		#   the only workaround is to unlock the project.
		# Ref: https://community.adobe.com/t5/substance-3d-painter-discussions/python-scripting-writing-project-metadata-when-saving-the-project/td-p/13114944
		_sp_p.do_action(_sp_p.Action.Unlock)
		export_widget.execute_export("保存后自动导出")
		_sp_p.do_action(_sp_p.Action.Lock)

def start_plugin():
	"""启动插件"""
	global export_widget, dock_widget
	
	try:
		# 创建插件UI
		export_widget = ExportOnSaveWidget()
		
		# 将UI添加为停靠窗口
		dock_widget = substance_painter.ui.add_dock_widget(export_widget)
		
		# 注册项目保存事件监听器
		substance_painter.event.DISPATCHER.connect(
			substance_painter.event.ProjectSaved,
			on_project_saved
		)
		
		substance_painter.logging.info(f"[{PLUGIN_NAME}] 插件启动成功")
		
	except Exception as e:
		substance_painter.logging.error(f"[{PLUGIN_NAME}] 插件启动失败: {str(e)}")

def close_plugin():
	"""关闭插件"""
	global export_widget, dock_widget
	
	try:
		# 断开事件监听器
		substance_painter.event.DISPATCHER.disconnect(
			substance_painter.event.ProjectSaved,
			on_project_saved
		)
		
		# 清理UI
		if dock_widget:
			substance_painter.ui.delete_ui_element(dock_widget)
			dock_widget = None
		
		if export_widget:
			export_widget = None
		
		substance_painter.logging.info(f"[{PLUGIN_NAME}] 插件已关闭")
		
	except Exception as e:
		substance_painter.logging.error(f"[{PLUGIN_NAME}] 关闭插件时发生错误: {str(e)}")

# 插件入口点
if __name__ == "__plugin__":
	start_plugin()

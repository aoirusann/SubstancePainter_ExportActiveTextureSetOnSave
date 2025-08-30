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
		
		# 设置变量 - 使用用户偏好的命名格式 A2B
		self.enabled = False
		self.selected_preset_url = ""
		self.preset_name2url: Dict[str, str] = {}  # preset name to URL mapping
		self.selected_texture_sets: Dict[str, bool] = {}  # texture set name to selection status
		self.texture_set_checkboxes: Dict[str, QtWidgets.QCheckBox] = {}  # texture set name to checkbox
		
		self.init_ui()
		self.load_settings()
		self.refresh_presets()
	
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
		
		# 预设选择组
		preset_group = QtWidgets.QGroupBox("导出预设")
		preset_layout = QtWidgets.QVBoxLayout()
		
		# 预设下拉框
		self.preset_combo = QtWidgets.QComboBox()
		self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
		preset_layout.addWidget(self.preset_combo)
		
		# 刷新按钮
		refresh_button = QtWidgets.QPushButton("刷新预设和纹理集")
		refresh_button.clicked.connect(self.refresh_presets)
		preset_layout.addWidget(refresh_button)
		
		preset_group.setLayout(preset_layout)
		layout.addWidget(preset_group)
		
		# 纹理集选择组
		textureset_group = QtWidgets.QGroupBox("选择纹理集")
		textureset_layout = QtWidgets.QVBoxLayout()
		
		# 全选/全不选按钮行
		button_row_layout = QtWidgets.QHBoxLayout()
		select_all_button = QtWidgets.QPushButton("全选")
		select_all_button.clicked.connect(self.select_all_texture_sets)
		select_none_button = QtWidgets.QPushButton("全不选")
		select_none_button.clicked.connect(self.select_none_texture_sets)
		button_row_layout.addWidget(select_all_button)
		button_row_layout.addWidget(select_none_button)
		button_row_layout.addStretch()
		textureset_layout.addLayout(button_row_layout)
		
		# 滚动区域用于纹理集列表
		scroll_area = QtWidgets.QScrollArea()
		scroll_area.setWidgetResizable(True)
		scroll_area.setMaximumHeight(150)
		
		self.texture_sets_widget = QtWidgets.QWidget()
		self.texture_sets_layout = QtWidgets.QVBoxLayout(self.texture_sets_widget)
		self.texture_sets_layout.setContentsMargins(5, 5, 5, 5)
		
		scroll_area.setWidget(self.texture_sets_widget)
		textureset_layout.addWidget(scroll_area)
		
		# 纹理集统计标签
		self.textureset_count_label = QtWidgets.QLabel("纹理集: 0 个 (0 个已选)")
		self.textureset_count_label.setStyleSheet("color: gray; font-size: 11px;")
		textureset_layout.addWidget(self.textureset_count_label)
		
		textureset_group.setLayout(textureset_layout)
		layout.addWidget(textureset_group)
		
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
		
		# 同步状态按钮
		sync_button = QtWidgets.QPushButton("同步状态")
		sync_button.clicked.connect(self.sync_ui_to_state)
		sync_button.setToolTip("如果界面显示与实际选择不一致，点击此按钮强制同步")
		button_row.addWidget(sync_button)
		
		# 调试信息按钮
		debug_button = QtWidgets.QPushButton("显示调试信息")
		debug_button.clicked.connect(self.show_debug_info)
		debug_button.setToolTip("显示当前纹理集选择状态的调试信息")
		button_row.addWidget(debug_button)
		
		layout.addLayout(button_row)
		
		# 说明文本
		help_text = QtWidgets.QLabel(
			"说明：启用后，每次保存项目时将自动使用选定的预设导出贴图。"
			"导出结果会显示在日志中。"
		)
		help_text.setWordWrap(True)
		help_text.setStyleSheet("color: gray; font-size: 11px;")
		layout.addWidget(help_text)
		
		layout.addStretch()
		self.setLayout(layout)
	
	def refresh_presets(self):
		"""刷新可用的导出预设列表"""
		try:
			self.preset_combo.clear()
			self.preset_name2url.clear()
			
			# 获取资源预设
			resource_presets = substance_painter.export.list_resource_export_presets()
			for preset in resource_presets:
				name = preset.resource_id.name
				url = preset.resource_id.url()
				self.preset_name2url[name] = url
				self.preset_combo.addItem(name)
			
			# 获取预定义预设
			predefined_presets = substance_painter.export.list_predefined_export_presets()
			for preset in predefined_presets:
				name = f"[预定义] {preset.name}"
				url = preset.url
				self.preset_name2url[name] = url
				self.preset_combo.addItem(name)
				
			# 恢复之前选择的预设
			if self.selected_preset_url:
				for name, url in self.preset_name2url.items():
					if url == self.selected_preset_url:
						self.preset_combo.setCurrentText(name)
						break
			
			self.status_label.setText(f"状态: 找到 {len(self.preset_name2url)} 个预设")
			
			# 同时刷新纹理集列表
			self.refresh_texture_sets()
			
		except Exception as e:
			self.status_label.setText(f"状态: 获取预设失败 - {str(e)}")
			self.status_label.setStyleSheet("color: red;")
			substance_painter.logging.error(f"[{PLUGIN_NAME}] 获取导出预设失败: {str(e)}")
	
	def on_enabled_changed(self, state):
		"""启用状态改变时的回调"""
		self.enabled = (state == QtCore.Qt.CheckState.Checked)
		self.save_settings()
		
		status = "启用" if self.enabled else "禁用"
		self.status_label.setText(f"状态: 自动导出已{status}")
		self.status_label.setStyleSheet("color: green;" if self.enabled else "color: gray;")
		
		substance_painter.logging.info(f"[{PLUGIN_NAME}] 自动导出功能已{status}")
	
	def on_preset_changed(self, preset_name):
		"""预设选择改变时的回调"""
		if preset_name and preset_name in self.preset_name2url:
			self.selected_preset_url = self.preset_name2url[preset_name]
			self.save_settings()
			substance_painter.logging.info(f"[{PLUGIN_NAME}] 选择导出预设: {preset_name}")
	
	def refresh_texture_sets(self):
		"""刷新纹理集列表"""
		try:
			# 清除现有的复选框
			for checkbox in self.texture_set_checkboxes.values():
				checkbox.setParent(None)
				checkbox.deleteLater()
			self.texture_set_checkboxes.clear()
			
			# 检查是否有项目打开
			if not substance_painter.project.is_open():
				self.textureset_count_label.setText("纹理集: 无项目 (请打开项目)")
				return
			
			# 获取所有纹理集
			all_texture_sets = substance_painter.textureset.all_texture_sets()
			
			if not all_texture_sets:
				self.textureset_count_label.setText("纹理集: 0 个 (项目中无纹理集)")
				return
			
			# 为每个纹理集创建复选框
			for texture_set in all_texture_sets:
				texture_set_name = texture_set.name()
				if not texture_set_name:
					continue
				
				checkbox = QtWidgets.QCheckBox(texture_set_name)
				
				# 恢复之前的选择状态，默认选中
				is_selected = self.selected_texture_sets.get(texture_set_name, True)
				checkbox.setChecked(is_selected)
				
				# 连接信号 - 使用 partial 避免 lambda 闭包问题
				checkbox.stateChanged.connect(
					partial(self.on_texture_set_selection_changed, texture_set_name)
				)
				
				# 添加到布局和字典
				self.texture_sets_layout.addWidget(checkbox)
				self.texture_set_checkboxes[texture_set_name] = checkbox
				self.selected_texture_sets[texture_set_name] = is_selected
			
			self.update_texture_sets_count()
			
		except Exception as e:
			self.textureset_count_label.setText(f"纹理集: 获取失败 - {str(e)}")
			substance_painter.logging.error(f"[{PLUGIN_NAME}] 获取纹理集失败: {str(e)}")
	
	def select_all_texture_sets(self):
		"""全选所有纹理集"""
		for checkbox in self.texture_set_checkboxes.values():
			checkbox.setChecked(True)
	
	def select_none_texture_sets(self):
		"""取消选择所有纹理集"""
		for checkbox in self.texture_set_checkboxes.values():
			checkbox.setChecked(False)
	
	def on_texture_set_selection_changed(self, texture_set_name, state):
		"""纹理集选择状态改变时的回调"""
		is_selected = (state == QtCore.Qt.CheckState.Checked)
		self.selected_texture_sets[texture_set_name] = is_selected
		self.update_texture_sets_count()
		self.save_settings()
	
	def update_texture_sets_count(self):
		"""更新纹理集统计显示"""
		total_count = len(self.texture_set_checkboxes)
		selected_count = sum(1 for selected in self.selected_texture_sets.values() if selected)
		
		self.textureset_count_label.setText(
			f"纹理集: {total_count} 个 ({selected_count} 个已选)"
		)
		
		# 根据选择状态改变颜色
		if selected_count == 0:
			self.textureset_count_label.setStyleSheet("color: red; font-size: 11px;")
		elif selected_count < total_count:
			self.textureset_count_label.setStyleSheet("color: orange; font-size: 11px;")
		else:
			self.textureset_count_label.setStyleSheet("color: green; font-size: 11px;")
	
	def sync_ui_to_state(self):
		"""同步界面复选框状态到内部状态"""
		try:
			changed_count = 0
			for name, checkbox in self.texture_set_checkboxes.items():
				is_checked = checkbox.isChecked()
				old_state = self.selected_texture_sets.get(name, None)
				
				if old_state != is_checked:
					changed_count += 1
					substance_painter.logging.info(f"[{PLUGIN_NAME}] 同步状态变更: {name} = {old_state} -> {is_checked}")
				
				self.selected_texture_sets[name] = is_checked
			
			if changed_count > 0:
				substance_painter.logging.info(f"[{PLUGIN_NAME}] 状态同步完成，更新了 {changed_count} 个纹理集的状态")
				self.status_label.setText(f"状态: 已同步 {changed_count} 个状态变更")
				self.status_label.setStyleSheet("color: blue;")
				
				# 保存同步后的状态
				self.save_settings()
			else:
				substance_painter.logging.info(f"[{PLUGIN_NAME}] 状态已同步，无需更新")
				self.status_label.setText("状态: 界面状态已同步")
				self.status_label.setStyleSheet("color: green;")
			
			# 更新统计显示
			self.update_texture_sets_count()

			__DEBUG = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().dilation")
			
		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] 同步界面状态失败: {str(e)}")
			self.status_label.setText(f"状态: 同步失败 - {str(e)}")
			self.status_label.setStyleSheet("color: red;")
	
	def show_debug_info(self):
		"""显示调试信息"""
		try:
			substance_painter.logging.info(f"[{PLUGIN_NAME}] === 调试信息 ===")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] 启用状态: {self.enabled}")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] 选择的预设: {self.selected_preset_url}")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] 内部纹理集状态: {self.selected_texture_sets}")
			
			ui_states = {}
			for name, checkbox in self.texture_set_checkboxes.items():
				ui_states[name] = checkbox.isChecked()
			substance_painter.logging.info(f"[{PLUGIN_NAME}] 界面复选框状态: {ui_states}")
			
			# 检查不一致的状态
			inconsistent = []
			for name in ui_states:
				if ui_states[name] != self.selected_texture_sets.get(name, False):
					inconsistent.append(name)
			
			if inconsistent:
				substance_painter.logging.warning(f"[{PLUGIN_NAME}] 发现不一致的状态: {inconsistent}")
				self.status_label.setText(f"状态: 发现 {len(inconsistent)} 个状态不一致")
				self.status_label.setStyleSheet("color: orange;")
			else:
				substance_painter.logging.info(f"[{PLUGIN_NAME}] 所有状态一致")
				self.status_label.setText("状态: 调试信息已输出到日志")
				self.status_label.setStyleSheet("color: green;")
			
			substance_painter.logging.info(f"[{PLUGIN_NAME}] === 调试信息结束 ===")
			
		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] 显示调试信息失败: {str(e)}")
	
	def manual_export_test(self):
		"""手动导出测试"""
		# 添加调试信息
		substance_painter.logging.info(f"[{PLUGIN_NAME}] 调试信息：")
		substance_painter.logging.info(f"[{PLUGIN_NAME}] - 当前纹理集选择状态: {self.selected_texture_sets}")
		substance_painter.logging.info(f"[{PLUGIN_NAME}] - 界面复选框状态: {[(name, cb.isChecked()) for name, cb in self.texture_set_checkboxes.items()]}")
		
		if not self.selected_preset_url:
			self.status_label.setText("状态: 请先选择导出预设")
			self.status_label.setStyleSheet("color: red;")
			return
		
		if not substance_painter.project.is_open():
			self.status_label.setText("状态: 没有打开的项目")
			self.status_label.setStyleSheet("color: red;")
			return
		
		# 在导出前同步界面状态到内部状态
		self.sync_ui_to_state()
		
		self.execute_export("手动导出测试")
	
	def execute_export(self, trigger_source="自动导出"):
		"""执行导出操作"""
		try:
			if not self.selected_preset_url:
				substance_painter.logging.warning(f"[{PLUGIN_NAME}] {trigger_source}: 没有选择导出预设")
				return
			
			# 获取选中的纹理集
			try:
				# 检查是否有选中的纹理集
				selected_texture_set_names = [
					name for name, selected in self.selected_texture_sets.items() if selected
				]
				
				if not selected_texture_set_names:
					substance_painter.logging.warning(f"[{PLUGIN_NAME}] {trigger_source}: 没有选择任何纹理集进行导出")
					self.status_label.setText("状态: 请选择要导出的纹理集")
					self.status_label.setStyleSheet("color: orange;")
					return
				
				# 验证选中的纹理集在项目中是否存在
				all_texture_sets = substance_painter.textureset.all_texture_sets()
				existing_texture_set_names = [ts.name() for ts in all_texture_sets if ts.name()]
				
				# 构建导出列表，只包含选中且存在的纹理集
				export_list = []
				for texture_set_name in selected_texture_set_names:
					if texture_set_name in existing_texture_set_names:
						export_list.append({"rootPath": texture_set_name})
					else:
						substance_painter.logging.warning(
							f"[{PLUGIN_NAME}] 纹理集 '{texture_set_name}' 在项目中不存在，已跳过"
						)
				
				if not export_list:
					substance_painter.logging.warning(f"[{PLUGIN_NAME}] {trigger_source}: 所选的纹理集都不存在")
					self.status_label.setText("状态: 所选纹理集不存在")
					self.status_label.setStyleSheet("color: orange;")
					return
					
			except Exception as e:
				substance_painter.logging.error(f"[{PLUGIN_NAME}] 获取纹理集时出错: {str(e)}")
				self.status_label.setText("状态: 获取纹理集失败")
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
				self.selected_preset_url = settings.get('selected_preset_url', '')
				self.selected_texture_sets = settings.get('selected_texture_sets', {})
				
		except Exception as e:
			substance_painter.logging.warning(f"[{PLUGIN_NAME}] 加载设置失败: {str(e)}")
	
	def save_settings(self):
		"""保存设置"""
		try:
			settings = {
				'enabled': self.enabled,
				'selected_preset_url': self.selected_preset_url,
				'selected_texture_sets': self.selected_texture_sets
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
		# 在自动导出前也同步界面状态
		export_widget.sync_ui_to_state()
		export_widget.execute_export("保存后自动导出")

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

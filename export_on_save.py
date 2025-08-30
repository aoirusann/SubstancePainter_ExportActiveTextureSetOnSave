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
	"""Main plugin control panel"""
	
	def __init__(self):
		super().__init__()
		self.setObjectName("ExportOnSaveWidget")
		self.setWindowTitle(PLUGIN_NAME)
		self.setWindowIcon(QtGui.QIcon())
		
		# Settings variables
		self.enabled = False
		
		self.load_settings()
		self.init_ui()
	
	def init_ui(self):
		"""Initialize user interface"""
		layout = QtWidgets.QVBoxLayout()
		layout.setSpacing(10)
		
		# Title
		title_label = QtWidgets.QLabel(PLUGIN_NAME)
		title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
		layout.addWidget(title_label)
		
		# Enable/Disable toggle
		self.enable_checkbox = QtWidgets.QCheckBox("Enable Auto Export on Save")
		self.enable_checkbox.setChecked(self.enabled)
		self.enable_checkbox.stateChanged.connect(self.on_enabled_changed)
		layout.addWidget(self.enable_checkbox)
		

		
		# Status display
		self.status_label = QtWidgets.QLabel("Status: Ready")
		self.status_label.setStyleSheet("color: green;")
		layout.addWidget(self.status_label)
		
		# Control button row
		button_row = QtWidgets.QHBoxLayout()
		
		# Test button (for debugging)
		test_button = QtWidgets.QPushButton("Manual Export Test")
		test_button.clicked.connect(self.manual_export_test)
		button_row.addWidget(test_button)
		

		
		# Debug info button
		debug_button = QtWidgets.QPushButton("Show Debug Info")
		debug_button.clicked.connect(self.show_debug_info)
		debug_button.setToolTip("Show debug information for currently active texture set")
		button_row.addWidget(debug_button)
		
		layout.addLayout(button_row)
		
		# Help text
		help_text = QtWidgets.QLabel(
			"Note: When enabled, the currently active texture set will be automatically exported using the current project's export configuration each time the project is saved. "
			"Export results will be displayed in the log."
		)
		help_text.setWordWrap(True)
		help_text.setStyleSheet("color: gray; font-size: 11px;")
		layout.addWidget(help_text)
		
		layout.addStretch()
		self.setLayout(layout)
	

	def on_enabled_changed(self, state):
		"""Callback when enabled state changes"""
		print(f"===={type(state)}: {state}====")

		self.enabled = (QtCore.Qt.CheckState(state) == QtCore.Qt.CheckState.Checked)
		self.save_settings()
		
		status = "Enabled" if self.enabled else "Disabled"
		self.status_label.setText(f"Status: Auto Export {status}")
		self.status_label.setStyleSheet("color: green;" if self.enabled else "color: gray;")
		
		substance_painter.logging.info(f"[{PLUGIN_NAME}] Auto export feature {status.lower()}")




	
	def show_debug_info(self):
		"""Show debug information"""
		try:
			substance_painter.logging.info(f"[{PLUGIN_NAME}] === Debug Info ===")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] Enabled state: {self.enabled}")

			# Show currently active texture set information
			try:
				active_stack = substance_painter.textureset.get_active_stack()
				active_texture_set = active_stack.material()
				active_texture_set_name = active_texture_set.name()

				substance_painter.logging.info(f"[{PLUGIN_NAME}] Currently active texture set: '{active_texture_set_name}'")
				substance_painter.logging.info(f"[{PLUGIN_NAME}] Currently active stack: '{active_stack.name()}'")

			except Exception as e:
				substance_painter.logging.warning(f"[{PLUGIN_NAME}] Failed to get currently active texture set: {str(e)}")

			self.status_label.setText("Status: Debug info output to log")
			self.status_label.setStyleSheet("color: green;")

			substance_painter.logging.info(f"[{PLUGIN_NAME}] === Debug Info End ===")

		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] Failed to show debug info: {str(e)}")
	
	def manual_export_test(self):
		"""Manual export test"""
		try:
			# Add debug info
			active_stack = substance_painter.textureset.get_active_stack()
			active_texture_set = active_stack.material()
			active_texture_set_name = active_texture_set.name()

			substance_painter.logging.info(f"[{PLUGIN_NAME}] Debug info:")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] - Currently active texture set: '{active_texture_set_name}'")

		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] Failed to get currently active texture set: {str(e)}")
			self.status_label.setText(f"Status: Failed to get current texture set - {str(e)}")
			self.status_label.setStyleSheet("color: red;")
			return

		if not substance_painter.project.is_open():
			self.status_label.setText("Status: No project open")
			self.status_label.setStyleSheet("color: red;")
			return

		self.execute_export("Manual Export Test")
	
	def execute_export(self, trigger_source="Auto Export"):
		"""Execute export operation"""
		try:

			# Get currently active texture set
			try:
				active_stack = substance_painter.textureset.get_active_stack()
				active_texture_set = active_stack.material()
				active_texture_set_name = active_texture_set.name()

				if not active_texture_set_name:
					substance_painter.logging.warning(f"[{PLUGIN_NAME}] {trigger_source}: Currently active texture set has no name")
					self.status_label.setText("Status: Current texture set has no name")
					self.status_label.setStyleSheet("color: orange;")
					return

				# Build export list, only including currently active texture set
				export_list = [{"rootPath": active_texture_set_name}]

				substance_painter.logging.info(f"[{PLUGIN_NAME}] {trigger_source}: Will export currently active texture set '{active_texture_set_name}'")

			except Exception as e:
				substance_painter.logging.error(f"[{PLUGIN_NAME}] Error getting currently active texture set: {str(e)}")
				self.status_label.setText("Status: Failed to get current texture set")
				self.status_label.setStyleSheet("color: red;")
				return

			# Get current export path
			export_path = substance_painter.js.evaluate("alg.mapexport.exportPath()")

			# Get current export settings
			export_fileFormat = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().fileFormat")
			export_padding = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().padding").lower()
			export_dilation = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().dilation")
			export_bitDepth = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().bitDepth")
			export_exportShaderParams = substance_painter.js.evaluate("alg.mapexport.getProjectExportOptions().exportShaderParams")

			if export_padding == "infinite" or export_padding == "passthrough":
				export_dithering = False
			else:
				export_dithering = True


			# Get current export preset
			export_preset = substance_painter.js.evaluate("alg.mapexport.getProjectExportPreset()")
			
			# Build export configuration
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
			
			# Record texture sets to be exported
			texture_set_names = [item["rootPath"] for item in export_list]
			substance_painter.logging.info(
				f"[{PLUGIN_NAME}] {trigger_source}: Preparing to export texture sets: {', '.join(texture_set_names)}"
			)
			
			self.status_label.setText("Status: Exporting...")
			self.status_label.setStyleSheet("color: orange;")
			
			# Execute export
			result = substance_painter.export.export_project_textures(export_config)

			if result.status == substance_painter.export.ExportStatus.Success:
				# Count exported files
				file_count = sum(len(files) for files in result.textures.values())
				
				self.status_label.setText(f"Status: Export successful ({file_count} files)")
				self.status_label.setStyleSheet("color: green;")
				
				substance_painter.logging.info(
					f"[{PLUGIN_NAME}] {trigger_source} completed: Successfully exported {file_count} texture files to {export_path}"
				)
				
				# Detailed record of exported files
				for (texture_set, stack), files in result.textures.items():
					substance_painter.logging.info(
						f"[{PLUGIN_NAME}] Texture set '{texture_set}' -> {len(files)} files"
					)
				
			elif result.status == substance_painter.export.ExportStatus.Warning:
				self.status_label.setText("Status: Export completed with warnings")
				self.status_label.setStyleSheet("color: orange;")
				substance_painter.logging.warning(
					f"[{PLUGIN_NAME}] {trigger_source} completed with warnings: {result.message}"
				)
				
			elif result.status == substance_painter.export.ExportStatus.Cancelled:
				self.status_label.setText("Status: Export cancelled")
				self.status_label.setStyleSheet("color: orange;")
				substance_painter.logging.info(
					f"[{PLUGIN_NAME}] {trigger_source} cancelled by user"
				)
			
			else:
				self.status_label.setText(f"Status: Export failed")
				self.status_label.setStyleSheet("color: red;")
				substance_painter.logging.error(
					f"[{PLUGIN_NAME}] {trigger_source} failed: {result.message}"
				)
				
		except Exception as e:
			self.status_label.setText(f"Status: Export exception - {str(e)}")
			self.status_label.setStyleSheet("color: red;")
			substance_painter.logging.error(f"[{PLUGIN_NAME}] Exception occurred during {trigger_source}: {str(e)}")
	
	def load_settings(self):
		"""Load settings"""
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
			substance_painter.logging.warning(f"[{PLUGIN_NAME}] Failed to load settings: {str(e)}")
	
	def save_settings(self):
		"""Save settings"""
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
			substance_painter.logging.warning(f"[{PLUGIN_NAME}] Failed to save settings: {str(e)}")


# Global variables
export_widget = None
dock_widget = None

def on_project_saved(event):
	"""Project saved event handler"""
	global export_widget
	
	if export_widget and export_widget.enabled:
		substance_painter.logging.info(f"[{PLUGIN_NAME}] Project save detected, starting auto export...")
		# About Unlock and Lock: sp will lock the project file during all the saving progress,
		#   which will block the access to the texture set,
		#   the only workaround is to unlock the project.
		# Ref: https://community.adobe.com/t5/substance-3d-painter-discussions/python-scripting-writing-project-metadata-when-saving-the-project/td-p/13114944
		with substance_painter.project._ActionLock():
			export_widget.execute_export("Auto Export After Save")

def start_plugin():
	"""Start plugin"""
	global export_widget, dock_widget
	
	try:
		# Create plugin UI
		export_widget = ExportOnSaveWidget()
		
		# Add UI as dock widget
		dock_widget = substance_painter.ui.add_dock_widget(export_widget)
		
		# Register project saved event listener
		substance_painter.event.DISPATCHER.connect(
			substance_painter.event.ProjectSaved,
			on_project_saved
		)
		
		substance_painter.logging.info(f"[{PLUGIN_NAME}] Plugin started successfully")
		
	except Exception as e:
		substance_painter.logging.error(f"[{PLUGIN_NAME}] Plugin startup failed: {str(e)}")

def close_plugin():
	"""Close plugin"""
	global export_widget, dock_widget
	
	try:
		# Disconnect event listener
		substance_painter.event.DISPATCHER.disconnect(
			substance_painter.event.ProjectSaved,
			on_project_saved
		)
		
		# Clean up UI
		if dock_widget:
			substance_painter.ui.delete_ui_element(dock_widget)
			dock_widget = None
		
		if export_widget:
			export_widget = None
		
		substance_painter.logging.info(f"[{PLUGIN_NAME}] Plugin closed")
		
	except Exception as e:
		substance_painter.logging.error(f"[{PLUGIN_NAME}] Error occurred while closing plugin: {str(e)}")
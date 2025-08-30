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
import _substance_painter.project
import _substance_painter.textureset
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

class _ActionUnlock():
	"""Action to unlock the project
	About Unlock and Lock: Substance Painter will lock the project file during all the saving progress,
	which will block the access to the texture set,
	the only workaround is to unlock the project.
	Ref: https://community.adobe.com/t5/substance-3d-painter-discussions/python-scripting-writing-project-metadata-when-saving-the-project/td-p/13114944
	"""
	def __enter__(self):
		_substance_painter.project.do_action(_substance_painter.project.Action.Unlock)
		return self
	
	def __exit__(self, err_type, err_value, traceback):
		_substance_painter.project.do_action(_substance_painter.project.Action.Lock)



class ExportOnSaveMenu(QtWidgets.QMenu):
	"""Main plugin menu control"""

	def __init__(self):
		super().__init__(PLUGIN_NAME)
		self.setObjectName("ExportOnSaveMenu")

		# Settings variables
		self.enabled = False

		self.load_settings()
		self.init_menu()

	def init_menu(self):
		"""Initialize menu structure"""

		# Enable/Disable toggle action
		self.enable_action = QtGui.QAction("Enable Auto Export on Save")
		self.enable_action.setCheckable(True)
		self.enable_action.setChecked(self.enabled)
		self.enable_action.triggered.connect(self.on_enabled_changed)
		self.addAction(self.enable_action)

		self.addSeparator()

		# Manual Export Test action
		self.test_action = QtGui.QAction("Manual Export Test")
		self.test_action.triggered.connect(self.manual_export_test)
		self.addAction(self.test_action)

		# Debug info action
		self.debug_action = QtGui.QAction("Show Debug Info")
		self.debug_action.setToolTip("Show debug information for currently active texture set")
		self.debug_action.triggered.connect(self.show_debug_info)
		self.addAction(self.debug_action)

		self.addSeparator()

		# Status display (as a disabled action to show status)
		self.status_action = QtGui.QAction("Status: Ready")
		self.status_action.setEnabled(False)
		self.addAction(self.status_action)
	

	def on_enabled_changed(self, checked):
		"""Callback when enabled state changes"""
		self.enabled = checked
		self.save_settings()

		status = "Enabled" if self.enabled else "Disabled"
		self.status_action.setText(f"Status: Auto Export {status}")

		substance_painter.logging.info(f"[{PLUGIN_NAME}] Auto export feature {status.lower()}")


	def show_debug_info(self):
		"""Show debug information"""
		try:
			substance_painter.logging.info(f"[{PLUGIN_NAME}] === Debug Info ===")
			substance_painter.logging.info(f"[{PLUGIN_NAME}] Enabled state: {self.enabled}")

			# Show currently build config
			export_config = self.build_export_config()
			substance_painter.logging.info(f"[{PLUGIN_NAME}] Build config: {json.dumps(export_config, indent=2, ensure_ascii=False)}")

			substance_painter.logging.info(f"[{PLUGIN_NAME}] === Debug Info End ===")

		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] Failed to show debug info: {str(e)}")
	
	def manual_export_test(self):
		"""Manual export test"""
		if not substance_painter.project.is_open():
			self.status_action.setText("Status: No project open")
			return

		substance_painter.logging.info(f"[{PLUGIN_NAME}] Manual export test started")
		self.execute_export()
		substance_painter.logging.info(f"[{PLUGIN_NAME}] Manual export test completed")


	def execute_export(self):
		"""Execute export operation"""
		try:
			# Make build config
			export_config = self.build_export_config()
			substance_painter.logging.info(f"[{PLUGIN_NAME}] Build config: {json.dumps(export_config, indent=2, ensure_ascii=False)}")

			self.status_action.setText("Status: Exporting...")
			
			# Record texture sets to be exported
			texture_set_names = [item["rootPath"] for item in export_config["exportList"]]
			substance_painter.logging.info(
				f"[{PLUGIN_NAME}] Preparing to export texture sets: {', '.join(texture_set_names)}"
			)
			
			# Execute export
			result = substance_painter.export.export_project_textures(export_config)

			if result.status == substance_painter.export.ExportStatus.Success:
				# Count exported files
				file_count = sum(len(files) for files in result.textures.values())

				self.status_action.setText(f"Status: Export successful ({file_count} files)")

				substance_painter.logging.info(
					f"[{PLUGIN_NAME}] Successfully exported {file_count} texture files to {export_config['exportPath']}"
				)

				# Detailed record of exported files
				for (texture_set, stack), files in result.textures.items():
					substance_painter.logging.info(
						f"[{PLUGIN_NAME}] Texture set '{texture_set}' -> {', '.join(files)}"
					)

			elif result.status == substance_painter.export.ExportStatus.Warning:
				self.status_action.setText("Status: Export completed with warnings")
				substance_painter.logging.warning(
					f"[{PLUGIN_NAME}] {result.message}"
				)

			elif result.status == substance_painter.export.ExportStatus.Cancelled:
				self.status_action.setText("Status: Export cancelled")
				substance_painter.logging.info(
					f"[{PLUGIN_NAME}] Export cancelled by user"
				)

			else:
				self.status_action.setText(f"Status: Export failed")
				substance_painter.logging.error(
					f"[{PLUGIN_NAME}] Export failed: {result.message}"
				)
				
		except Exception as e:
			self.status_action.setText(f"Status: Export exception - {str(e)}")
			substance_painter.logging.error(f"[{PLUGIN_NAME}] Exception occurred during export: {str(e)}")

	def build_export_config(self):
		try:
			# Get currently active texture set
			try:
				active_stack = substance_painter.textureset.get_active_stack()
				active_texture_set = active_stack.material()
				# TextureSet.name() will call deprecated method `_utility.make_callable()`, so we hack it
				# active_texture_set_name = active_texture_set.name()
				active_texture_set_name = _substance_painter.textureset.material_name(active_texture_set.material_id)

				if not active_texture_set_name:
					substance_painter.logging.warning(f"[{PLUGIN_NAME}] Currently active texture set has no name")
					self.status_action.setText("Status: Current texture set has no name")
					return

				# Build export list, only including currently active texture set
				export_list = [{"rootPath": active_texture_set_name}]

			except Exception as e:
				substance_painter.logging.error(f"[{PLUGIN_NAME}] Error getting currently active texture set: {str(e)}")
				self.status_action.setText("Status: Failed to get current texture set")
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
		except Exception as e:
			substance_painter.logging.error(f"[{PLUGIN_NAME}] Failed to build export config: {str(e)}")
			return
		return export_config
	
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
export_menu = None

def on_project_saved(event):
	"""Project saved event handler"""
	global export_menu

	if export_menu and export_menu.enabled:
		substance_painter.logging.info(f"[{PLUGIN_NAME}] Auto export started on project saved")
		with _ActionUnlock():
			export_menu.execute_export()
		substance_painter.logging.info(f"[{PLUGIN_NAME}] Auto export completed")

def start_plugin():
	"""Start plugin"""
	global export_menu

	try:
		# Create plugin menu
		export_menu = ExportOnSaveMenu()

		# Add menu to application
		substance_painter.ui.add_menu(export_menu)
		
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
	global export_menu

	try:
		# Disconnect event listener
		substance_painter.event.DISPATCHER.disconnect(
			substance_painter.event.ProjectSaved,
			on_project_saved
		)

		# Clean up menu
		if export_menu:
			substance_painter.ui.delete_ui_element(export_menu)
			export_menu = None

		substance_painter.logging.info(f"[{PLUGIN_NAME}] Plugin closed")

	except Exception as e:
		substance_painter.logging.error(f"[{PLUGIN_NAME}] Error occurred while closing plugin: {str(e)}")
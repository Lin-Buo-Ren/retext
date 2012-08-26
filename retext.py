#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: sw=8:ts=8:noexpandtab

# ReText
# Copyright 2011-2012 Dmitry Shachnev

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

import sys
import re
from subprocess import Popen, PIPE
from PyQt4.QtCore import *
from PyQt4.QtGui import *

app_name = "ReText"
app_version = "3.0.4"

def readFromSettings(settings, key, keytype):
	try:
		return settings.value(key, type=keytype)
	except TypeError:
		# For old PyQt versions
		if keytype == str:
			return settings.value(key).toString()
		elif keytype == int:
			result, ok = settings.value(key).toInt()
			if not ok:
				print('Warning: cannot covert settings value to int!')
			return result
		elif keytype == bool:
			return settings.value(key).toBool()

def readListFromSettings(settings, key):
	if not settings.contains(key):
		return []
	value = settings.value(key)
	try:
		return value.toStringList()
	except:
		# For Python 3
		if isinstance(value, str):
			return [value]
		else:
			return value

def writeListToSettings(settings, key, value):
	if len(value) > 1:
		settings.setValue(key, value)
	elif len(value) == 1:
		settings.setValue(key, value[0])
	else:
		settings.remove(key)

settings = QSettings('ReText project', 'ReText')

try:
	import markdown
except:
	use_md = False
else:
	use_md = True
	exts = []
	if settings.contains('mdExtensions'):
		for ext in readListFromSettings(settings, 'mdExtensions'):
			exts.append(str(ext))
		try:
			md = markdown.Markdown(exts)
		except ValueError:
			print('Warning: failed to load extensions!')
			md = markdown.Markdown()
	else:
		md = markdown.Markdown()

try:
	import gdata.docs.data
	import gdata.docs.client
	from gdata.data import MediaSource
except:
	use_gdocs = False
else:
	use_gdocs = True

try:
	import enchant
	enchant.Dict()
except:
	use_enchant = False
else:
	use_enchant = True

dictionary = None

try:
	from docutils.core import publish_parts
except:
	use_docutils = False
else:
	use_docutils = True

icon_path = "icons/"

PARSER_DOCUTILS, PARSER_MARKDOWN, PARSER_HTML, PARSER_NA = range(4)

if QFileInfo("wpgen/wpgen.py").isExecutable():
	try:
		wpgen = unicode(QFileInfo("wpgen/wpgen.py").canonicalFilePath(), 'utf-8')
	except:
		# For Python 3
		wpgen = QFileInfo("wpgen/wpgen.py").canonicalFilePath()
elif QFileInfo("/usr/bin/wpgen").isExecutable():
	wpgen = "/usr/bin/wpgen"
else:
	wpgen = None

monofont = QFont()
if settings.contains('editorFont'):
	monofont.setFamily(readFromSettings(settings, 'editorFont', str))
else:
	monofont.setFamily('monospace')
if settings.contains('editorFontSize'):
	monofont.setPointSize(readFromSettings(settings, 'editorFontSize', int))

try:
	from PyQt4.QtWebKit import QWebView, QWebSettings
except:
	webkit_available = False
else:
	webkit_available = True

class ReTextHighlighter(QSyntaxHighlighter):
	def highlightBlock(self, text):
		patterns = (
			('<[^<>@]*>', Qt.darkMagenta, QFont.Bold),         # HTML tags
			('&[^; ]*;', Qt.darkCyan, QFont.Bold),             # HTML symbols
			('"[^"<]*"(?=[^<]*>)', Qt.darkYellow, QFont.Bold), # Quoted strings inside tags
			('<!--[^<>]*-->', Qt.gray, QFont.Normal),          # HTML comments
			('(?<!\\*)\\*[^ \\*][^\\*]*\\*', None, QFont.Normal, True), # *Italics*
			('(?<!_|\\w)_[^_]+_(?!\\w)', None, QFont.Normal, True),     # _Italics_
			('(?<!\\*)\\*\\*((?!\\*\\*).)*\\*\\*', None, QFont.Bold), # **Bold**
			('(?<!_|\\w)__[^_]+__(?!\\w)', None, QFont.Bold),         # __Bold__
			('\\*{3,3}[^\\*]+\\*{3,3}', None, QFont.Bold, True), # ***BoldItalics***
			('___[^_]+___', None, QFont.Bold, True),           # ___BoldItalics___
			('^#.+', None, QFont.Black),                       # Headers
			('(?<=\\[)[^\\[\\]]*(?=\\])', Qt.blue, QFont.Normal), # Links and images
			('(?<=\\]\\()[^\\(\\)]*(?=\\))', None, QFont.Normal, True, True) # Link references
		)
		for pattern in patterns:
			charFormat = QTextCharFormat()
			charFormat.setFontWeight(pattern[2])
			if pattern[1] != None:
				charFormat.setForeground(pattern[1])
			if len(pattern) >= 4:
				charFormat.setFontItalic(pattern[3])
			if len(pattern) >= 5:
				charFormat.setFontUnderline(pattern[4])
			for match in re.finditer(pattern[0], text):
				self.setFormat(match.start(), match.end() - match.start(), charFormat)
		if dictionary:
			try:
				text = unicode(text)
			except:
				# Not necessary for Python 3
				pass
			charFormat = QTextCharFormat()
			charFormat.setUnderlineColor(Qt.red)
			charFormat.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
			for match in re.finditer('[^_\\W]+', text, flags=re.UNICODE):
				finalFormat = QTextCharFormat()
				finalFormat.merge(charFormat)
				finalFormat.merge(self.format(match.start()))
				if not dictionary.check(match.group(0)):
					self.setFormat(match.start(), match.end() - match.start(), finalFormat)

class LogPassDialog(QDialog):
	def __init__(self, defaultLogin="", defaultPass=""):
		QDialog.__init__(self)
		self.setWindowTitle(app_name)
		self.verticalLayout = QVBoxLayout(self)
		self.label = QLabel(self)
		self.label.setText(self.tr("Enter your Google account data"))
		self.verticalLayout.addWidget(self.label)
		self.loginEdit = QLineEdit(self)
		self.loginEdit.setText(defaultLogin)
		self.verticalLayout.addWidget(self.loginEdit)
		self.passEdit = QLineEdit(self)
		self.passEdit.setText(defaultPass)
		self.passEdit.setEchoMode(QLineEdit.Password)
		try:
			self.loginEdit.setPlaceholderText(self.tr("Username"))
			self.passEdit.setPlaceholderText(self.tr("Password"))
		except:
			pass
		self.verticalLayout.addWidget(self.passEdit)
		self.buttonBox = QDialogButtonBox(self)
		self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
		self.verticalLayout.addWidget(self.buttonBox)
		self.connect(self.buttonBox, SIGNAL("accepted()"), self.accept)
		self.connect(self.buttonBox, SIGNAL("rejected()"), self.reject)

class HtmlDialog(QDialog):
	def __init__(self, parent=None):
		QDialog.__init__(self, parent)
		self.resize(600, 500)
		self.verticalLayout = QVBoxLayout(self)
		self.textEdit = QTextEdit(self)
		self.textEdit.setReadOnly(True)
		self.textEdit.setFont(monofont)
		ReTextHighlighter(self.textEdit.document())
		self.verticalLayout.addWidget(self.textEdit)
		self.buttonBox = QDialogButtonBox(self)
		self.buttonBox.setStandardButtons(QDialogButtonBox.Close)
		self.connect(self.buttonBox, SIGNAL("clicked(QAbstractButton*)"), self.doClose)
		self.verticalLayout.addWidget(self.buttonBox)
	
	def doClose(self):
		self.close()

class ReTextWindow(QMainWindow):
	def __init__(self, parent=None):
		QMainWindow.__init__(self, parent)
		self.resize(800, 600)
		screen = QDesktopWidget().screenGeometry()
		size = self.geometry()
		self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
		if settings.contains('iconTheme'):
			QIcon.setThemeName(readFromSettings(settings, 'iconTheme', str))
		if QIcon.themeName() in ('', 'hicolor'):
			try:
				gconf = Popen(['gconftool-2', '--get', '/desktop/gnome/interface/icon_theme'],
				stdout=PIPE)
			except: pass
			else:
				iconTheme = gconf.stdout.read().rstrip()
				if iconTheme: QIcon.setThemeName(iconTheme.decode())
		if settings.contains('font'):
			self.font = QFont(readFromSettings(settings, 'font', str))
			if settings.contains('fontSize'):
				self.font.setPointSize(readFromSettings(settings, 'fontSize', int))
		else:
			self.font = None
		if QFile.exists(icon_path+'retext.png'):
			self.setWindowIcon(QIcon(icon_path+'retext.png'))
		else:
			self.setWindowIcon(QIcon.fromTheme('retext', QIcon.fromTheme('accessories-text-editor')))
		self.editBoxes = []
		self.previewBoxes = []
		self.highlighters = []
		self.fileNames = []
		self.apc = []
		self.alpc = []
		self.aptc = []
		self.gDocsEntries = []
		self.tabWidget = QTabWidget(self)
		self.tabWidget.setTabsClosable(True)
		self.setCentralWidget(self.tabWidget)
		self.connect(self.tabWidget, SIGNAL('currentChanged(int)'), self.changeIndex)
		self.connect(self.tabWidget, SIGNAL('tabCloseRequested(int)'), self.closeTab)
		self.toolBar = QToolBar(self.tr('File toolbar'), self)
		self.addToolBar(Qt.TopToolBarArea, self.toolBar)
		self.editBar = QToolBar(self.tr('Edit toolbar'), self)
		self.addToolBar(Qt.TopToolBarArea, self.editBar)
		self.searchBar = QToolBar(self.tr('Search toolbar'), self)
		self.addToolBar(Qt.BottomToolBarArea, self.searchBar)
		self.actionNew = self.act(self.tr('New'), icon='document-new', shct=QKeySequence.New, trig=self.createNew)
		self.actionNew.setPriority(QAction.LowPriority)
		self.actionOpen = self.act(self.tr('Open'), icon='document-open', shct=QKeySequence.Open, trig=self.openFile)
		self.actionOpen.setPriority(QAction.LowPriority)
		self.actionSave = self.act(self.tr('Save'), icon='document-save', shct=QKeySequence.Save, trig=self.saveFile)
		self.actionSave.setEnabled(False)
		self.actionSave.setPriority(QAction.LowPriority)
		self.actionSaveAs = self.act(self.tr('Save as'), icon='document-save-as', shct=QKeySequence.SaveAs, \
		trig=self.saveFileAs)
		self.actionPrint = self.act(self.tr('Print'), icon='document-print', shct=QKeySequence.Print, trig=self.printFile)
		self.actionPrint.setPriority(QAction.LowPriority)
		self.actionPrintPreview = self.act(self.tr('Print preview'), icon='document-print-preview', \
		trig=self.printPreview)
		self.actionViewHtml = self.act(self.tr('View HTML code'), icon='text-html', trig=self.viewHtml)
		self.actionChangeFont = self.act(self.tr('Change default font'), trig=self.changeFont)
		self.actionSearch = self.act(self.tr('Find text'), icon='edit-find', shct=QKeySequence.Find)
		self.actionSearch.setCheckable(True)
		self.connect(self.actionSearch, SIGNAL('triggered(bool)'), self.searchBar, SLOT('setVisible(bool)'))
		self.connect(self.searchBar, SIGNAL('visibilityChanged(bool)'), self.searchBarVisibilityChanged)
		self.actionPreview = self.act(self.tr('Preview'), shct=Qt.CTRL+Qt.Key_E, trigbool=self.preview)
		if QIcon.hasThemeIcon('document-preview'):
			self.actionPreview.setIcon(QIcon.fromTheme('document-preview'))
		elif QIcon.hasThemeIcon('preview-file'):
			self.actionPreview.setIcon(QIcon.fromTheme('preview-file'))
		elif QIcon.hasThemeIcon('x-office-document'):
			self.actionPreview.setIcon(QIcon.fromTheme('x-office-document'))
		else:
			self.actionPreview.setIcon(QIcon(icon_path+'document-preview.png'))
		self.actionLivePreview = self.act(self.tr('Live preview'), shct=Qt.CTRL+Qt.SHIFT+Qt.Key_E, \
		trigbool=self.enableLivePreview)
		self.actionFullScreen = self.act(self.tr('Fullscreen mode'), icon='view-fullscreen', shct=Qt.Key_F11, \
		trigbool=self.enableFullScreen)
		self.actionPerfectHtml = self.act('HTML', icon='text-html', trig=self.saveFilePerfect)
		self.actionPdf = self.act('PDF', icon='application-pdf', trig=self.savePdf)
		self.actionOdf = self.act('ODT', icon='x-office-document', trig=self.saveOdf)
		settings.beginGroup('Export')
		if settings.allKeys():
			self.actionOtherExport = self.act(self.tr('Other formats'), trig=self.otherExport)
			otherExport = True
		else:
			otherExport = False
		settings.endGroup()
		self.getExportExtensionsList()
		self.actionQuit = self.act(self.tr('Quit'), icon='application-exit', shct=QKeySequence.Quit)
		self.actionQuit.setMenuRole(QAction.QuitRole)
		self.connect(self.actionQuit, SIGNAL('triggered()'), self.close)
		self.actionUndo = self.act(self.tr('Undo'), icon='edit-undo', shct=QKeySequence.Undo, \
		trig=lambda: self.editBoxes[self.ind].undo())
		self.actionRedo = self.act(self.tr('Redo'), icon='edit-redo', shct=QKeySequence.Redo, \
		trig=lambda: self.editBoxes[self.ind].redo())
		self.actionCopy = self.act(self.tr('Copy'), icon='edit-copy', shct=QKeySequence.Copy, \
		trig=lambda: self.editBoxes[self.ind].copy())
		self.actionCut = self.act(self.tr('Cut'), icon='edit-cut', shct=QKeySequence.Cut, \
		trig=lambda: self.editBoxes[self.ind].cut())
		self.actionPaste = self.act(self.tr('Paste'), icon='edit-paste', shct=QKeySequence.Paste, \
		trig=lambda: self.editBoxes[self.ind].paste())
		self.actionUndo.setEnabled(False)
		self.actionRedo.setEnabled(False)
		self.actionCopy.setEnabled(False)
		self.actionCut.setEnabled(False)
		self.connect(qApp.clipboard(), SIGNAL('dataChanged()'), self.clipboardDataChanged)
		self.clipboardDataChanged()
		self.sc = False
		if use_enchant:
			self.actionEnableSC = self.act(self.tr('Enable'), trigbool=self.enableSC)
			self.actionSetLocale = self.act(self.tr('Set locale'), trig=self.changeLocale)
			if settings.contains('spellCheckLocale'):
				self.sl = str(readFromSettings(settings, 'spellCheckLocale', str))
			else:
				self.sl = None
			if settings.contains('spellCheck'):
				if readFromSettings(settings, 'spellCheck', bool):
					self.actionEnableSC.setChecked(True)
					self.enableSC(True)
		self.actionPlainText = self.act(self.tr('Plain text'), trigbool=self.enablePlainText)
		if webkit_available:
			self.actionWebKit = self.act(self.tr('Use WebKit renderer'), trigbool=self.enableWebKit)
			self.useWebKit = False
			if settings.contains('useWebKit'):
				if readFromSettings(settings, 'useWebKit', bool):
					self.useWebKit = True
					self.actionWebKit.setChecked(True)
		if wpgen:
			self.actionWpgen = self.act(self.tr('Generate webpages'), trig=self.startWpgen)
		self.actionShow = self.act(self.tr('Show'), icon='system-file-manager', trig=self.showInDir)
		self.actionFind = self.act(self.tr('Next'), icon='go-next', shct=QKeySequence.FindNext, trig=self.find)
		self.actionFindPrev = self.act(self.tr('Previous'), icon='go-previous', shct=QKeySequence.FindPrevious, \
		trig=lambda: self.find(back=True))
		self.actionHelp = self.act(self.tr('Get help online'), icon='help-contents', trig=self.openHelp)
		try:
			self.aboutWindowTitle = self.tr('About %s') % app_name
		except:
			# For Python 2
			self.aboutWindowTitle = self.tr('About %s').replace('%s', '%1').arg(app_name)
		self.actionAbout = self.act(self.aboutWindowTitle, icon='help-about', trig=self.aboutDialog)
		self.actionAbout.setMenuRole(QAction.AboutRole)
		self.actionAboutQt = self.act(self.tr('About Qt'))
		self.actionAboutQt.setMenuRole(QAction.AboutQtRole)
		self.connect(self.actionAboutQt, SIGNAL('triggered()'), qApp, SLOT('aboutQt()'))
		self.chooseGroup = QActionGroup(self)
		self.useDocUtils = False
		self.actionUseMarkdown = self.act('Markdown')
		self.actionUseMarkdown.setCheckable(True)
		self.actionUseReST = self.act('ReStructuredText')
		self.actionUseReST.setCheckable(True)
		if settings.contains('useReST'):
			if readFromSettings(settings, 'useReST', bool):
				if use_docutils:
					self.useDocUtils = True
				self.actionUseReST.setChecked(True)
			else:
				self.actionUseMarkdown.setChecked(True)
		else:
			self.actionUseMarkdown.setChecked(True)
		self.connect(self.actionUseReST, SIGNAL('toggled(bool)'), self.setDocUtilsDefault)
		self.chooseGroup.addAction(self.actionUseMarkdown)
		self.chooseGroup.addAction(self.actionUseReST)
		self.actionBold = self.act(self.tr('Bold'), shct=QKeySequence.Bold, trig=lambda: self.insertChars('**'))
		self.actionItalic = self.act(self.tr('Italic'), shct=QKeySequence.Italic, trig=lambda: self.insertChars('*'))
		self.actionUnderline = self.act(self.tr('Underline'), shct=QKeySequence.Underline, \
		trig=lambda: self.insertTag(9)) # <u>...</u>
		if use_gdocs:
			self.actionSaveGDocs = self.act(self.tr('Save to Google Docs'), trig=self.saveGDocs)
			self.actionSaveGDocs.setIcon(QIcon.fromTheme('web-browser', self.actIcon('intenret-web-browser')))
		self.usefulTags = ('big', 'center', 's', 'small', 'span', 'table', 'td', 'tr', 'u')
		self.usefulChars = ('deg', 'divide', 'hellip', 'laquo', 'larr', \
			'lsquo', 'mdash', 'middot', 'minus', 'nbsp', 'ndash', 'raquo', \
			'rarr', 'rsquo', 'times')
		self.tagsBox = QComboBox(self.editBar)
		self.tagsBox.addItem(self.tr('Tags'))
		self.tagsBox.addItems(self.usefulTags)
		self.connect(self.tagsBox, SIGNAL('activated(int)'), self.insertTag)
		self.symbolBox = QComboBox(self.editBar)
		self.symbolBox.addItem(self.tr('Symbols'))
		self.symbolBox.addItems(self.usefulChars)
		self.connect(self.symbolBox, SIGNAL('activated(int)'), self.insertSymbol)
		if settings.contains('styleSheet'):
			ssname = readFromSettings(settings, 'styleSheet', str)
			sheetfile = QFile(ssname)
			sheetfile.open(QIODevice.ReadOnly)
			self.ss = QTextStream(sheetfile).readAll()
			sheetfile.close()
			webkitsettings = QWebSettings.globalSettings()
			webkitsettings.setUserStyleSheetUrl(QUrl.fromLocalFile(ssname))
		else:
			self.ss = ''
		if use_md and 'codehilite' in exts:
			# Load CSS style for codehilite
			try:
				from pygments.formatters import HtmlFormatter
			except:
				pass
			else:
				self.ss += HtmlFormatter().get_style_defs('.codehilite')
		self.menubar = QMenuBar(self)
		self.menubar.setGeometry(QRect(0, 0, 800, 25))
		self.setMenuBar(self.menubar)
		self.menuFile = self.menubar.addMenu(self.tr('File'))
		self.menuEdit = self.menubar.addMenu(self.tr('Edit'))
		self.menuHelp = self.menubar.addMenu(self.tr('Help'))
		self.menuFile.addAction(self.actionNew)
		self.menuFile.addAction(self.actionOpen)
		self.menuRecentFiles = self.menuFile.addMenu(self.tr('Open recent'))
		self.connect(self.menuRecentFiles, SIGNAL('aboutToShow()'), self.updateRecentFiles)
		self.menuFile.addMenu(self.menuRecentFiles)
		self.menuDir = self.menuFile.addMenu(self.tr('Directory'))
		self.menuDir.addAction(self.actionShow)
		if wpgen:
			self.menuDir.addAction(self.actionWpgen)
		self.menuFile.addSeparator()
		self.menuFile.addAction(self.actionSave)
		self.menuFile.addAction(self.actionSaveAs)
		self.menuFile.addSeparator()
		self.menuExport = self.menuFile.addMenu(self.tr('Export'))
		self.menuExport.addAction(self.actionPerfectHtml)
		self.menuExport.addAction(self.actionOdf)
		self.menuExport.addAction(self.actionPdf)
		if self.extensionActions:
			self.menuExport.addSeparator()
			for action, mimetype in self.extensionActions:
				self.menuExport.addAction(action)
			self.connect(self.menuRecentFiles, SIGNAL('aboutToShow()'), self.updateExtensionsVisibility)
		if otherExport:
			self.menuExport.addAction(self.actionOtherExport)
		if use_gdocs:
			self.menuExport.addSeparator()
			self.menuExport.addAction(self.actionSaveGDocs)
		self.menuFile.addAction(self.actionPrint)
		self.menuFile.addAction(self.actionPrintPreview)
		self.menuFile.addSeparator()
		self.menuFile.addAction(self.actionQuit)
		self.menuEdit.addAction(self.actionUndo)
		self.menuEdit.addAction(self.actionRedo)
		self.menuEdit.addSeparator()
		self.menuEdit.addAction(self.actionCut)
		self.menuEdit.addAction(self.actionCopy)
		self.menuEdit.addAction(self.actionPaste)
		self.menuEdit.addSeparator()
		if use_enchant:
			self.menuSC = self.menuEdit.addMenu(self.tr('Spell check'))
			self.menuSC.addAction(self.actionEnableSC)
			self.menuSC.addAction(self.actionSetLocale)
		self.menuEdit.addAction(self.actionSearch)
		self.menuEdit.addAction(self.actionPlainText)
		self.menuEdit.addAction(self.actionChangeFont)
		self.menuEdit.addSeparator()
		if use_docutils and use_md:
			self.menuMode = self.menuEdit.addMenu(self.tr('Default editing mode'))
			self.menuMode.addAction(self.actionUseMarkdown)
			self.menuMode.addAction(self.actionUseReST)
		self.menuFormat = self.menuEdit.addMenu(self.tr('Formatting'))
		self.menuFormat.addAction(self.actionBold)
		self.menuFormat.addAction(self.actionItalic)
		self.menuFormat.addAction(self.actionUnderline)
		if webkit_available:
			self.menuEdit.addAction(self.actionWebKit)
		self.menuEdit.addSeparator()
		self.menuEdit.addAction(self.actionViewHtml)
		self.menuEdit.addAction(self.actionLivePreview)
		self.menuEdit.addAction(self.actionPreview)
		self.menuEdit.addSeparator()
		self.menuEdit.addAction(self.actionFullScreen)
		self.menuHelp.addAction(self.actionHelp)
		self.menuHelp.addSeparator()
		self.menuHelp.addAction(self.actionAbout)
		self.menuHelp.addAction(self.actionAboutQt)
		self.menubar.addMenu(self.menuFile)
		self.menubar.addMenu(self.menuEdit)
		self.menubar.addMenu(self.menuHelp)
		self.toolBar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
		self.toolBar.addAction(self.actionNew)
		self.toolBar.addSeparator()
		self.toolBar.addAction(self.actionOpen)
		self.toolBar.addAction(self.actionSave)
		self.toolBar.addAction(self.actionPrint)
		self.toolBar.addSeparator()
		self.toolBar.addAction(self.actionPreview)
		self.editBar.addAction(self.actionUndo)
		self.editBar.addAction(self.actionRedo)
		self.editBar.addSeparator()
		self.editBar.addAction(self.actionCut)
		self.editBar.addAction(self.actionCopy)
		self.editBar.addAction(self.actionPaste)
		self.editBar.addSeparator()
		self.editBar.addWidget(self.tagsBox)
		self.editBar.addWidget(self.symbolBox)
		self.searchEdit = QLineEdit(self.searchBar)
		try:
			self.searchEdit.setPlaceholderText(self.tr('Search'))
		except:
			pass
		self.connect(self.searchEdit, SIGNAL('returnPressed()'), self.find)
		self.csBox = QCheckBox(self.tr('Case sensitively'), self.searchBar)
		self.searchBar.addWidget(self.searchEdit)
		self.searchBar.addWidget(self.csBox)
		self.searchBar.addAction(self.actionFindPrev)
		self.searchBar.addAction(self.actionFind)
		self.searchBar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
		self.searchBar.setVisible(False)
		self.autoSave = False
		if settings.contains('autoSave'):
			if readFromSettings(settings, 'autoSave', bool):
				self.autoSave = True
				timer = QTimer(self)
				timer.start(60000)
				self.connect(timer, SIGNAL('timeout()'), self.saveAll)
		self.restorePreviewState = False
		self.livePreviewEnabled = False
		if settings.contains('restorePreviewState'):
			self.restorePreviewState = readFromSettings(settings, 'restorePreviewState', bool)
		if settings.contains('previewState'):
			self.livePreviewEnabled = readFromSettings(settings, 'previewState', bool)
		self.ind = 0
		self.tabWidget.addTab(self.createTab(""), self.tr('New document'))
		if not (use_md or use_docutils):
			QMessageBox.warning(self, app_name, self.tr('You have neither Markdown nor Docutils modules installed!') \
			+'<br>'+self.tr('Only HTML formatting will be available.'))
	
	def act(self, name, icon=None, trig=None, trigbool=None, shct=None):
		if icon:
			action = QAction(self.actIcon(icon), name, self)
		else:
			action = QAction(name, self)
		if trig:
			self.connect(action, SIGNAL('triggered()'), trig)
		elif trigbool:
			action.setCheckable(True)
			self.connect(action, SIGNAL('triggered(bool)'), trigbool)
		if shct:
			action.setShortcut(shct)
		return action
	
	def actIcon(self, name):
		return QIcon.fromTheme(name, QIcon(icon_path+name+'.png'))
	
	def printError(self, error):
		print('Exception occured while parsing document:')
		print(error)
	
	def getSplitter(self, index):
		splitter = QSplitter(Qt.Horizontal)
		# Give both boxes a minimum size so the minimumSizeHint will be
		# ignored when splitter.setSizes is called below
		for widget in self.editBoxes[index], self.previewBoxes[index]:
			widget.setMinimumWidth(125)
			splitter.addWidget(widget)
		splitter.setSizes((50, 50))
		splitter.setChildrenCollapsible(False)
		return splitter
	
	def createTab(self, fileName):
		self.previewBlocked = False
		self.editBoxes.append(QTextEdit())
		self.highlighters.append(ReTextHighlighter(self.editBoxes[-1].document()))
		if self.useWebKit:
			self.previewBoxes.append(QWebView())
		else:
			self.previewBoxes.append(QTextEdit())
			self.previewBoxes[-1].setReadOnly(True)
		self.previewBoxes[-1].setVisible(False)
		self.fileNames.append(fileName)
		liveMode = self.restorePreviewState and self.livePreviewEnabled
		self.apc.append(liveMode)
		self.alpc.append(liveMode)
		self.aptc.append(False)
		self.gDocsEntries.append(None)
		self.editBoxes[-1].setFont(monofont)
		self.editBoxes[-1].setAcceptRichText(False)
		self.connect(self.editBoxes[-1], SIGNAL('textChanged()'), self.updateLivePreviewBox)
		self.connect(self.editBoxes[-1], SIGNAL('undoAvailable(bool)'), self.actionUndo, SLOT('setEnabled(bool)'))
		self.connect(self.editBoxes[-1], SIGNAL('redoAvailable(bool)'), self.actionRedo, SLOT('setEnabled(bool)'))
		self.connect(self.editBoxes[-1], SIGNAL('copyAvailable(bool)'), self.enableCopy)
		self.connect(self.editBoxes[-1].document(), SIGNAL('modificationChanged(bool)'), self.modificationChanged)
		return self.getSplitter(-1)
	
	def closeTab(self, ind):
		if self.maybeSave(ind):
			if self.tabWidget.count() == 1:
				self.tabWidget.addTab(self.createTab(""), self.tr("New document"))
			del self.editBoxes[ind]
			del self.previewBoxes[ind]
			del self.highlighters[ind]
			del self.fileNames[ind]
			del self.apc[ind]
			del self.alpc[ind]
			del self.aptc[ind]
			del self.gDocsEntries[ind]
			self.tabWidget.removeTab(ind)
	
	def changeIndex(self, ind):
		if ind > -1:
			self.actionPlainText.setChecked(self.aptc[ind])
			self.enablePlainTextMain(self.aptc[ind])
			self.actionUndo.setEnabled(self.editBoxes[ind].document().isUndoAvailable())
			self.actionRedo.setEnabled(self.editBoxes[ind].document().isRedoAvailable())
			self.actionCopy.setEnabled(self.editBoxes[ind].textCursor().hasSelection())
			self.actionCut.setEnabled(self.editBoxes[ind].textCursor().hasSelection())
			self.actionPreview.setChecked(self.apc[ind])
			self.actionLivePreview.setChecked(self.alpc[ind])
			self.editBar.setDisabled(self.apc[ind])
		self.ind = ind
		if self.fileNames[ind]:
			self.setCurrentFile()
		else:
			try:
				self.setWindowTitle(self.tr('New document') + '[*] ' + QChar(0x2014) + ' ' + app_name)
			except:
				# For Python 3
				self.setWindowTitle(self.tr('New document') + '[*] \u2014 ' + app_name)
		self.modificationChanged(self.editBoxes[ind].document().isModified())
		self.livePreviewEnabled = self.alpc[ind]
		if self.alpc[ind]:
			self.enableLivePreview(True)
		self.editBoxes[self.ind].setFocus(Qt.OtherFocusReason)
	
	def changeFont(self):
		if not self.font:
			self.font = QFont()
		fd = QFontDialog.getFont(self.font, self)
		if fd[1]:
			self.font = QFont()
			self.font.setFamily(fd[0].family())
			settings.setValue('font', fd[0].family())
			self.font.setPointSize(fd[0].pointSize())
			settings.setValue('fontSize', fd[0].pointSize())
			self.updatePreviewBox()
	
	def preview(self, viewmode):
		self.apc[self.ind] = viewmode
		if self.actionLivePreview.isChecked():
			self.actionLivePreview.setChecked(False)
			return self.enableLivePreview(False)
		self.editBar.setDisabled(viewmode)
		self.editBoxes[self.ind].setVisible(not viewmode)
		self.previewBoxes[self.ind].setVisible(viewmode)
		if viewmode:
			self.updatePreviewBox()
	
	def enableLivePreview(self, livemode):
		self.livePreviewEnabled = livemode
		self.alpc[self.ind] = livemode
		self.apc[self.ind] = livemode
		self.actionPreview.setChecked(livemode)
		self.editBar.setEnabled(True)
		self.previewBoxes[self.ind].setVisible(livemode)
		self.editBoxes[self.ind].setVisible(True)
		if livemode:
			self.updatePreviewBox()
	
	def enableWebKit(self, enable):
		self.useWebKit = enable
		if enable:
			settings.setValue('useWebKit', True)
		else:
			settings.remove('useWebKit')
		oldind = self.ind
		self.tabWidget.clear()
		for self.ind in range(len(self.editBoxes)):
			if enable:
				self.previewBoxes[self.ind] = QWebView()
			else:
				self.previewBoxes[self.ind] = QTextEdit()
				self.previewBoxes[self.ind].setReadOnly(True)
			splitter = self.getSplitter(self.ind)
			self.tabWidget.addTab(splitter, self.getDocumentTitle(baseName=True))
			self.updatePreviewBox()
			self.previewBoxes[self.ind].setVisible(self.apc[self.ind])
		self.ind = oldind
		self.tabWidget.setCurrentIndex(self.ind)
	
	def enableCopy(self, copymode):
		self.actionCopy.setEnabled(copymode)
		self.actionCut.setEnabled(copymode)
	
	def enableFullScreen(self, yes):
		if yes:
			self.showFullScreen()
		else:
			self.showNormal()
	
	def keyPressEvent(self, e):
		v = not self.menubar.isVisible()
		if e.key() == Qt.Key_F12 and e.modifiers() & Qt.ShiftModifier:
			self.menubar.setVisible(v)
			self.toolBar.setVisible(v)
			self.editBar.setVisible(v)
		elif e.key() == Qt.Key_F11:
			if v:
				n = not self.actionFullScreen.isChecked()
				self.actionFullScreen.setChecked(n)
				self.enableFullScreen(n)
	
	def enableSC(self, yes):
		global dictionary
		if yes:
			if self.sl:
				try:
					dictionary = enchant.Dict(self.sl)
				except Exception as e:
					QMessageBox.warning(self, app_name, str(e))
					dictionary = enchant.Dict()
			else:
				dictionary = enchant.Dict()
			settings.setValue('spellCheck', True)
		else:
			dictionary = None
			settings.remove('spellCheck')
		for highlighter in self.highlighters:
			highlighter.rehighlight()
	
	def changeLocale(self):
		if self.sl == None:
			text = ""
		else:
			text = self.sl
		sl, ok = QInputDialog.getText(self, app_name, self.tr('Enter locale name (example: en_US)'), QLineEdit.Normal, text)
		if ok and sl:
			try:
				sl = str(sl)
			except:
				pass
			else:
				self.sl = sl
				self.enableSC(self.actionEnableSC.isChecked())
		elif not sl:
			self.sl = None
			self.enableSC(self.actionEnableSC.isChecked())
	
	def searchBarVisibilityChanged(self, visible):
		self.actionSearch.setChecked(visible)
		if visible:
			self.searchEdit.setFocus(Qt.ShortcutFocusReason)
	
	def find(self, back=False):
		flags = 0
		if back:
			flags = QTextDocument.FindBackward
		if self.csBox.isChecked():
			flags = flags | QTextDocument.FindCaseSensitively
		text = self.searchEdit.text()
		if not self.findMain(text, flags):
			if text in self.editBoxes[self.ind].toPlainText():
				cursor = self.editBoxes[self.ind].textCursor()
				if back:
					cursor.movePosition(QTextCursor.End)
				else:
					cursor.movePosition(QTextCursor.Start)
				self.editBoxes[self.ind].setTextCursor(cursor)
				self.findMain(text, flags)
	
	def findMain(self, text, flags):
		if flags:
			return self.editBoxes[self.ind].find(text, flags)
		else:
			return self.editBoxes[self.ind].find(text)
	
	def updatePreviewBox(self):
		self.previewBlocked = False
		pb = self.previewBoxes[self.ind]
		textedit = isinstance(pb, QTextEdit)
		if self.ss and textedit:
			pb.document().setDefaultStyleSheet(self.ss)
		if self.aptc[self.ind]:
			if textedit:
				pb.setPlainText(self.editBoxes[self.ind].toPlainText())
			else:
				td = QTextDocument()
				td.setPlainText(self.editBoxes[self.ind].toPlainText())
				pb.setHtml(td.toHtml())
		else:
			try:
				pb.setHtml(self.parseText())
			except Exception as e:
				self.printError(e)
		if self.font and textedit:
			pb.document().setDefaultFont(self.font)
	
	def updateLivePreviewBox(self):
		if self.actionLivePreview.isChecked() and self.previewBlocked == False:
			self.previewBlocked = True
			QTimer.singleShot(1000, self.updatePreviewBox)
	
	def startWpgen(self):
		if self.fileNames[self.ind] == "":
			QMessageBox.warning(self, app_name, self.tr("Please, save the file somewhere."))
		elif wpgen:
			if not (QDir("html").exists() and QFile.exists("template.html")):
				Popen((wpgen, 'init')).wait()
			Popen([wpgen, 'updateall']).wait()
			msgBox = QMessageBox(QMessageBox.Information, app_name, \
			self.tr("Webpages saved in <code>html</code> directory."), QMessageBox.Ok)
			showButton = msgBox.addButton(self.tr("Show directory"), QMessageBox.AcceptRole)
			msgBox.exec_()
			if msgBox.clickedButton() == showButton:
				QDesktopServices.openUrl(QUrl.fromLocalFile(QDir('html').absolutePath()))
		else:
			QMessageBox.error(self, app_name, self.tr("Webpages generator is not installed!"))
	
	def showInDir(self):
		if self.fileNames[self.ind]:
			QDesktopServices.openUrl(QUrl.fromLocalFile(QFileInfo(self.fileNames[self.ind]).path()))
		else:
			QMessageBox.warning(self, app_name, self.tr("Please, save the file somewhere."))
	
	def setCurrentFile(self):
		self.setWindowTitle("")
		self.tabWidget.setTabText(self.ind, self.getDocumentTitle(baseName=True))
		self.setWindowFilePath(self.fileNames[self.ind])
		files = readListFromSettings(settings, "recentFileList")
		try:
			files.prepend(self.fileNames[self.ind])
			files.removeDuplicates()
		except:
			# For Python 3
			while self.fileNames[self.ind] in files:
				files.remove(self.fileNames[self.ind])
			files.insert(0, self.fileNames[self.ind])
		if len(files) > 10:
			del files[10:]
		writeListToSettings(settings, "recentFileList", files)
		QDir.setCurrent(QFileInfo(self.fileNames[self.ind]).dir().path())
	
	def createNew(self):
		self.tabWidget.addTab(self.createTab(""), self.tr("New document"))
		self.ind = self.tabWidget.count()-1
		self.tabWidget.setCurrentIndex(self.ind)
	
	def updateRecentFiles(self):
		self.menuRecentFiles.clear()
		self.recentFilesActions = []
		filesOld = readListFromSettings(settings, "recentFileList")
		files = []
		for f in filesOld:
			if QFile.exists(f):
				files.append(f)
				self.recentFilesActions.append(self.act(f, trig=self.openFunction(f)))
		writeListToSettings(settings, "recentFileList", files)
		for action in self.recentFilesActions:
			self.menuRecentFiles.addAction(action)
	
	def openFunction(self, fileName):
		return lambda: self.openFileWrapper(fileName)
	
	def extensionFuntion(self, data):
		return lambda: \
		self.runExtensionCommand(data['Exec'], data['FileFilter'], data['DefaultExtension'])
	
	def getExportExtensionsList(self):
		extensions = []
		for extsprefix in ('/usr', QDir.homePath()+'/.local'):
			extsdir = QDir(extsprefix+'/share/retext/export-extensions/')
			if extsdir.exists():
				for fileInfo in extsdir.entryInfoList(['*.desktop', '*.ini'], QDir.Files | QDir.Readable):
					extensions.append(self.readExtension(fileInfo.filePath()))
		locale = QLocale.system().name()
		self.extensionActions = []
		for extension in extensions:
			try:
				if ('Name[%s]' % locale) in extension:
					name = extension['Name[%s]' % locale]
				elif ('Name[%s]' % locale.split('_')[0]) in extension:
					name = extension['Name[%s]' % locale.split('_')[0]]
				else:
					name = extension['Name']
				data = {}
				for prop in ('FileFilter', 'DefaultExtension', 'Exec'):
					if 'X-ReText-'+prop in extension:
						data[prop] = extension['X-ReText-'+prop]
					elif prop in extension:
						data[prop] = extension[prop]
					else:
						data[prop] = ''
				action = self.act(name, trig=self.extensionFuntion(data))
				if 'Icon' in extension:
					action.setIcon(self.actIcon(extension['Icon']))
				mimetype = extension['MimeType'] if 'MimeType' in extension else None
			except KeyError:
				print('Failed to parse extension: Name is required')
			else:
				self.extensionActions.append((action, mimetype))
	
	def updateExtensionsVisibility(self):
		for action in self.extensionActions:
			if self.actionPlainText.isChecked():
				action[0].setEnabled(False)
				continue
			mimetype = action[1]
			if mimetype == None:
				enabled = True
			elif self.getParser() == PARSER_MARKDOWN:
				enabled = (mimetype in ("text/x-retext-markdown", "text/x-markdown"))
			elif self.getParser() == PARSER_DOCUTILS:
				enabled = (mimetype in ("text/x-retext-rst", "text/x-rst"))
			elif self.getParser() == PARSER_HTML:
				enabled = (mimetype == "text/html")
			else:
				enabled = False
			action[0].setEnabled(enabled)
	
	def readExtension(self, fileName):
		extFile = QFile(fileName)
		extFile.open(QIODevice.ReadOnly)
		extension = {}
		stream = QTextStream(extFile)
		while not stream.atEnd():
			line = stream.readLine()
			try:
				line = unicode(line)
			except:
				# Not needed for Python 3
				pass
			if '=' in line:
				index = line.index('=')
				extension[line[:index].rstrip()] = line[index+1:].lstrip()
		extFile.close()
		return extension
	
	def openFile(self):
		fileNames = QFileDialog.getOpenFileNames(self, self.tr("Select one or several files to open"), "", \
		self.tr("Supported files")+" (*.re *.md *.markdown *.mdown *.mkd *.mkdn *.rst *.rest *.txt *.html *.htm);;"+self.tr("All files (*)"))
		for fileName in fileNames:
			self.openFileWrapper(fileName)
	
	def openFileWrapper(self, fileName):
		if not fileName:
			return
		fileName = QFileInfo(fileName).canonicalFilePath()
		exists = False
		for i in range(self.tabWidget.count()):
			if self.fileNames[i] == fileName:
				exists = True
				ex = i
		if exists:
			self.tabWidget.setCurrentIndex(ex)
		elif QFile.exists(fileName):
			if self.fileNames[self.ind] or self.editBoxes[self.ind].toPlainText() \
			or self.editBoxes[self.ind].document().isModified():
				self.tabWidget.addTab(self.createTab(""), "")
				self.ind = self.tabWidget.count()-1
				self.tabWidget.setCurrentIndex(self.ind)
			self.fileNames[self.ind] = fileName
			self.openFileMain()
	
	def openFileMain(self):
		openfile = QFile(self.fileNames[self.ind])
		openfile.open(QIODevice.ReadOnly)
		html = QTextStream(openfile).readAll()
		openfile.close()
		self.editBoxes[self.ind].setPlainText(html)
		suffix = QFileInfo(self.fileNames[self.ind]).suffix()
		pt = suffix not in ('re', 'md', 'markdown', 'mdown', 'mkd', 'mkdn', 'rst', 'rest', 'html', 'htm')
		if settings.contains('autoPlainText'):
			if not readFromSettings(settings, 'autoPlainText', bool):
				pt = False
		self.actionPlainText.setChecked(pt)
		self.enablePlainText(pt)
		self.setCurrentFile()
		self.setWindowModified(False)
	
	def saveFile(self):
		self.saveFileMain(dlg=False)
	
	def saveFileAs(self):
		self.saveFileMain(dlg=True)
	
	def saveAll(self):
		oldind = self.ind
		for self.ind in range(self.tabWidget.count()):
			if self.fileNames[self.ind] and QFileInfo(self.fileNames[self.ind]).isWritable():
				self.saveFileWrapper(self.fileNames[self.ind])
				self.editBoxes[self.ind].document().setModified(False)
		self.ind = oldind
	
	def saveFileMain(self, dlg):
		if (not self.fileNames[self.ind]) or dlg:
			if self.actionPlainText.isChecked():
				defaultExt = self.tr("Plain text (*.txt)")
				ext = ".txt"
			elif self.getParser() == PARSER_DOCUTILS:
				defaultExt = self.tr("ReStructuredText files")+" (*.rest *.rst *.txt)"
				ext = ".rst"
			elif self.getParser() == PARSER_HTML:
				defaultExt = self.tr("HTML files")+" (*.html *.htm)"
				ext = ".html"
			else:
				defaultExt = self.tr("Markdown files")+" (*.re *.md *.markdown *.mdown *.mkd *.mkdn *.txt)"
				ext = ".mkd"
				if settings.contains('defaultExt'):
					ext = readFromSettings(settings, 'defaultExt', str)
			newFileName = QFileDialog.getSaveFileName(self, self.tr("Save file"), "", defaultExt)
			if newFileName:
				if not QFileInfo(newFileName).suffix():
					newFileName += ext
				self.fileNames[self.ind] = newFileName
		if self.fileNames[self.ind]:
			result = self.saveFileWrapper(self.fileNames[self.ind])
			if result:
				self.setCurrentFile()
				self.editBoxes[self.ind].document().setModified(False)
				self.setWindowModified(False)
			else:
				QMessageBox.warning(self, app_name, self.tr("Cannot save to file because it is read-only!"))
	
	def saveFileWrapper(self, fn):
		savefile = QFile(fn)
		result = savefile.open(QIODevice.WriteOnly)
		if result:
			savestream = QTextStream(savefile)
			savestream << self.editBoxes[self.ind].toPlainText()
			savefile.close()
		return result
	
	def saveHtml(self, fileName):
		if not QFileInfo(fileName).suffix():
			fileName += ".html"
		try:
			text = self.parseText()
		except Exception as e:
			return self.printError(e)
		htmlFile = QFile(fileName)
		htmlFile.open(QIODevice.WriteOnly)
		html = QTextStream(htmlFile)
		if self.getParser() == PARSER_HTML:
			html << text << "\n"
			htmlFile.close()
			return
		html << '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">\n'
		html << '<html>\n<head>\n'
		html << '  <meta http-equiv="content-type" content="text/html; charset=utf-8">\n'
		html << '  <meta name="generator" content="%s %s">\n' % (app_name, app_version)
		html << '  <title>' + self.getDocumentTitle() + '</title>\n'
		html << '</head>\n<body>\n'
		html << text
		html << '\n</body>\n</html>\n'
		htmlFile.close()
	
	def textDocument(self):
		if not self.actionPlainText.isChecked():
			text = self.parseText()
		td = QTextDocument()
		td.setMetaInformation(QTextDocument.DocumentTitle, self.getDocumentTitle())
		if self.ss:
			td.setDefaultStyleSheet(self.ss)
		if self.actionPlainText.isChecked():
			td.setPlainText(self.editBoxes[self.ind].toPlainText())
		else:
			td.setHtml('<html><body>'+text+'</body></html>')
		if self.font:
			td.setDefaultFont(self.font)
		return td
	
	def saveOdf(self):
		try:
			document = self.textDocument()
		except Exception as e:
			self.printError(e)
			return
		fileName = QFileDialog.getSaveFileName(self, self.tr("Export document to ODT"), "", self.tr("OpenDocument text files (*.odt)"))
		if not QFileInfo(fileName).suffix():
			fileName += ".odt"
		writer = QTextDocumentWriter(fileName)
		writer.setFormat("odf")
		writer.write(document)
	
	def saveFilePerfect(self):
		fileName = None
		fileName = QFileDialog.getSaveFileName(self, self.tr("Save file"), "", self.tr("HTML files (*.html *.htm)"))
		if fileName:
			self.saveHtml(fileName)
	
	def getDocumentForPrint(self):
		if self.useWebKit:
			return self.previewBoxes[self.ind]
		try:
			return self.textDocument()
		except Exception as e:
			self.printError(e)
			return None
	
	def standardPrinter(self):
		printer = QPrinter(QPrinter.HighResolution)
		printer.setDocName(self.getDocumentTitle())
		printer.setCreator(app_name+" "+app_version)
		return printer
	
	def savePdf(self):
		document = self.getDocumentForPrint()
		if document == None:
			return
		fileName = QFileDialog.getSaveFileName(self, self.tr("Export document to PDF"), "", self.tr("PDF files (*.pdf)"))
		if fileName:
			if not QFileInfo(fileName).suffix():
				fileName += ".pdf"
			printer = self.standardPrinter()
			printer.setOutputFormat(QPrinter.PdfFormat)
			printer.setOutputFileName(fileName)
			document.print_(printer)
	
	def printFile(self):
		document = self.getDocumentForPrint()
		if document == None:
			return
		printer = self.standardPrinter()
		dlg = QPrintDialog(printer, self)
		dlg.setWindowTitle(self.tr("Print document"))
		if (dlg.exec_() == QDialog.Accepted):
			document.print_(printer)
	
	def printPreview(self):
		document = self.getDocumentForPrint()
		if document == None:
			return
		printer = self.standardPrinter()
		preview = QPrintPreviewDialog(printer, self)
		self.connect(preview, SIGNAL("paintRequested(QPrinter*)"), document.print_)
		preview.exec_()
	
	def runExtensionCommand(self, command, filefilter='', defaultext=''):
		of = ('%of' in command)
		html = ('%html' in command)
		if of:
			if defaultext and not filefilter:
				filefilter = '*'+defaultext
			fileName = QFileDialog.getSaveFileName(self, self.tr('Export document'), '', filefilter)
			if not fileName:
				return
			if defaultext and not QFileInfo(fileName).suffix():
				fileName += defaultext
		if html:
			tmpname = '.retext-temp.html'
			self.saveHtml(tmpname)
		else:
			tmpname = '.retext-temp.rst' if self.getParser() == PARSER_DOCUTILS else '.retext-temp.mkd'
			self.saveFileWrapper(tmpname)
		command = command.replace('%of', 'out'+defaultext)
		command = command.replace('%html' if html else '%if', tmpname)
		args = str(command).split()
		try:
			Popen(args).wait()
		except Exception as error:
			errorstr = str(error)
			try:
				errorstr = QString.fromUtf8(errorstr)
			except:
				# Not needed for Python 3
				pass
			QMessageBox.warning(self, app_name, self.tr('Failed to execute the command:') + '\n' + errorstr)
		QFile(tmpname).remove()
		if of:
			QFile('out'+defaultext).rename(fileName)
	
	def otherExport(self):
		if self.actionPlainText.isChecked():
			return QMessageBox.warning(self, app_name, self.tr('This function is not available in Plain text mode!'))
		settings.beginGroup('Export')
		types = settings.allKeys()
		item, ok = QInputDialog.getItem(self, app_name, self.tr('Select type'), types, 0, False)
		if not ok:
			return settings.endGroup()
		command = readFromSettings(settings, item, str)
		settings.endGroup()
		self.runExtensionCommand(command, defaultext='.'+item)
	
	def getDocumentTitle(self, baseName=False):
		"""Ensure that parseText() is called before this function!
		If 'baseName' is set to True, file basename will be used."""
		realTitle = ''
		try:
			text = unicode(self.editBoxes[self.ind].toPlainText())
		except:
			# For Python 3
			text = self.editBoxes[self.ind].toPlainText()
		if not self.actionPlainText.isChecked():
			parser = self.getParser()
			if parser == PARSER_DOCUTILS:
				realTitle = publish_parts(text, writer_name='html')['title']
			elif parser == PARSER_MARKDOWN:
				try:
					realTitle = str.join(' ', md.Meta['title'])
				except:
					# Meta extension not installed
					pass
		if realTitle and not baseName:
			return realTitle
		elif self.fileNames[self.ind]:
			fileinfo = QFileInfo(self.fileNames[self.ind])
			basename = fileinfo.completeBaseName()
			return (basename if basename else fileinfo.fileName())
		else:
			return self.tr("New document")
	
	def saveGDocs(self):
		login = passwd = ''
		if settings.contains('GDocsLogin') and settings.contains('GDocsPasswd'):
			login = readFromSettings(settings, 'GDocsLogin', str)
			passwd = readFromSettings(settings, 'GDocsPasswd', str)
		if self.gDocsEntries[self.ind] == None:
			loginDialog = LogPassDialog(login, passwd)
			if loginDialog.exec_() == QDialog.Accepted:
				login = loginDialog.loginEdit.text()
				passwd = loginDialog.passEdit.text()
			else:
				return
		if self.actionPlainText.isChecked():
			tempFile = '.retext-temp.txt'
			contentType = 'text/plain'
			self.saveFileWrapper(tempFile)
		else:
			tempFile = '.retext-temp.html'
			contentType = 'text/html'
			self.saveHtml(tempFile)
		gdClient = gdata.docs.client.DocsClient(source=app_name)
		gdClient.ssl = True
		try:
			try:
				gdClient.ClientLogin(unicode(login), unicode(passwd), gdClient.source)
			except NameError:
				# For Python 3
				gdClient.ClientLogin(login, passwd, gdClient.source)
		except gdata.client.BadAuthentication:
			QFile(tempFile).remove()
			return QMessageBox.warning(self, app_name, self.tr("Incorrect user name or password!"))
		except:
			QFile(tempFile).remove()
			return QMessageBox.warning(self, app_name, \
			self.tr("Authentification failed, please check your internet connection!"))
		settings.setValue("GDocsLogin", login)
		settings.setValue("GDocsPasswd", passwd)
		try:
			title = unicode(self.getDocumentTitle())
		except:
			# For Python 3
			title = self.getDocumentTitle()
		ms = MediaSource(file_path=tempFile, content_type=contentType)
		entry = self.gDocsEntries[self.ind]
		if entry:
			entry.title.text = title
			entry = gdClient.Update(entry, media_source=ms, force=True)
		else:
			try:
				resource = gdata.docs.data.Resource(title=title)
				entry = gdClient.CreateResource(resource, media=ms)
			except AttributeError:
				# For old gdata versions
				entry = gdClient.Upload(ms, title)
		QDesktopServices.openUrl(QUrl(entry.GetAlternateLink().href))
		self.gDocsEntries[self.ind] = entry
		QFile(tempFile).remove()
	
	def autoSaveActive(self):
		return self.autoSave and self.fileNames[self.ind] and \
		QFileInfo(self.fileNames[self.ind]).isWritable()
	
	def modificationChanged(self, changed):
		if self.autoSaveActive():
			changed = False
		self.actionSave.setEnabled(changed)
		self.setWindowModified(changed)
	
	def clipboardDataChanged(self):
		self.actionPaste.setEnabled(qApp.clipboard().mimeData().hasText())
	
	def insertChars(self, chars):
		tc = self.editBoxes[self.ind].textCursor()
		if tc.hasSelection():
			tc.insertText(chars+tc.selectedText()+chars)
		else:
			tc.insertText(chars)
	
	def insertTag(self, num):
		if num:
			ut = self.usefulTags[num-1]
			hc = not ut in ('td', 'tr')
			arg = ''
			if ut == 'span':
				arg = ' style=""'
			tc = self.editBoxes[self.ind].textCursor()
			if hc:
				toinsert = '<'+ut+arg+'>'+tc.selectedText()+'</'+ut+'>'
				tc.insertText(toinsert)
			else:
				tc.insertText('<'+ut+arg+'>'+tc.selectedText())
		self.tagsBox.setCurrentIndex(0)
	
	def insertSymbol(self, num):
		if num:
			self.editBoxes[self.ind].insertPlainText('&'+self.usefulChars[num-1]+';')
		self.symbolBox.setCurrentIndex(0)
	
	def maybeSave(self, ind):
		if self.autoSaveActive():
			self.saveFileWrapper(self.fileNames[self.ind])
			return True
		if not self.editBoxes[ind].document().isModified():
			return True
		self.tabWidget.setCurrentIndex(ind)
		ret = QMessageBox.warning(self, app_name, self.tr("The document has been modified.\nDo you want to save your changes?"), \
		QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
		if ret == QMessageBox.Save:
			self.saveFileMain(False)
			return True
		elif ret == QMessageBox.Cancel:
			return False
		return True
	
	def closeEvent(self, closeevent):
		for self.ind in range(self.tabWidget.count()):
			if not self.maybeSave(self.ind):
				return closeevent.ignore()
		if self.restorePreviewState:
			if self.livePreviewEnabled:
				settings.setValue('previewState', True)
			else:
				settings.remove('previewState')
		closeevent.accept()
	
	def viewHtml(self):
		HtmlDlg = HtmlDialog(self)
		try:
			HtmlDlg.textEdit.setPlainText(self.parseText())
		except Exception as e:
			self.printError(e)
			return
		winTitle = self.tr('New document')
		if self.fileNames[self.ind]:
			winTitle = QFileInfo(self.fileNames[self.ind]).fileName()
		try:
			HtmlDlg.setWindowTitle(winTitle+" ("+self.tr("HTML code")+") "+QChar(0x2014)+" "+app_name)
		except:
			# For Python 3
			HtmlDlg.setWindowTitle(winTitle+" ("+self.tr("HTML code")+") \u2014 "+app_name)
		HtmlDlg.show()
		HtmlDlg.raise_()
		HtmlDlg.activateWindow()
	
	def openHelp(self):
		QDesktopServices.openUrl(QUrl('http://sourceforge.net/p/retext/home/Help and Support'))
	
	def aboutDialog(self):
		QMessageBox.about(self, self.aboutWindowTitle, \
		'<p><b>'+app_name+' '+app_version+'</b><br>'+self.tr('Simple but powerful editor for Markdown and ReStructuredText') \
		+'</p><p>'+self.tr('Author: Dmitry Shachnev, 2011') \
		+'<br><a href="http://sourceforge.net/p/retext/">'+self.tr('Website') \
		+'</a> | <a href="http://daringfireball.net/projects/markdown/syntax">'+self.tr('Markdown syntax') \
		+'</a> | <a href="http://docutils.sourceforge.net/docs/user/rst/quickref.html">' \
		+self.tr('ReST syntax')+'</a></p>')
	
	def enablePlainText(self, value):
		self.aptc[self.ind] = value
		self.enablePlainTextMain(value)
		self.updatePreviewBox()
	
	def enablePlainTextMain(self, value):
		self.actionPerfectHtml.setDisabled(value)
		self.actionViewHtml.setDisabled(value)
		self.tagsBox.setDisabled(value)
		self.symbolBox.setDisabled(value)
	
	def setDocUtilsDefault(self, yes):
		self.useDocUtils = yes
		if yes:
			settings.setValue('useReST', True)
		else:
			settings.remove('useReST')
		self.updatePreviewBox()
	
	def getParser(self):
		if self.fileNames[self.ind]:
			suffix = QFileInfo(self.fileNames[self.ind]).suffix()
			if suffix in ('md', 'markdown', 'mdown', 'mkd', 'mkdn', 're'):
				return PARSER_MARKDOWN if use_md else PARSER_NA
			elif suffix in ('rest', 'rst'):
				return PARSER_DOCUTILS if use_docutils else PARSER_NA
			elif suffix in ('html', 'htm'):
				return PARSER_HTML
		if not (use_docutils or use_md):
			return PARSER_HTML
		elif use_docutils and (self.useDocUtils or not use_md):
			return PARSER_DOCUTILS
		else:
			return PARSER_MARKDOWN
	
	def parseText(self):
		try:
			htmltext = unicode(self.editBoxes[self.ind].toPlainText())
		except:
			# For Python 3
			htmltext = self.editBoxes[self.ind].toPlainText()
		# WpGen directives
		htmltext = htmltext.replace('%HTMLDIR%', 'html')
		htmltext = htmltext.replace('%\\', '%')
		parser = self.getParser()
		if parser == PARSER_HTML:
			return htmltext
		elif parser == PARSER_DOCUTILS:
			return publish_parts(htmltext, writer_name='html')['body']
		elif parser == PARSER_MARKDOWN:
			md.reset()
			return md.convert(htmltext)
		else:
			return '<p style="color: red">'\
			+self.tr('Could not parse file contents, check if you have the necessary module installed!')+'</p>'

def main(fileNames):
	app = QApplication(sys.argv)
	app.setOrganizationName("ReText project")
	app.setApplicationName("ReText")
	RtTranslator = QTranslator()
	if not RtTranslator.load("retext_"+QLocale.system().name(), "locale"):
		if not RtTranslator.load("retext_"+QLocale.system().name(), "/usr/share/retext/locale"):
			RtTranslator.load("retext_"+QLocale.system().name(), "/usr/lib/retext")
	QtTranslator = QTranslator()
	QtTranslator.load("qt_"+QLocale.system().name(), QLibraryInfo.location(QLibraryInfo.TranslationsPath))
	app.installTranslator(RtTranslator)
	app.installTranslator(QtTranslator)
	if settings.contains('appStyleSheet'):
		stylename = readFromSettings(settings, 'appStyleSheet', str)
		sheetfile = QFile(stylename)
		sheetfile.open(QIODevice.ReadOnly)
		app.setStyleSheet(QTextStream(sheetfile).readAll())
		sheetfile.close()
	window = ReTextWindow()
	for fileName in fileNames:
		try:
			fileName = QString.fromUtf8(fileName)
		except:
			# Not needed for Python 3
			pass
		if QFile.exists(fileName):
			window.openFileWrapper(fileName)
	window.show()
	sys.exit(app.exec_())

if __name__ == '__main__':
	if len(sys.argv) > 1:
		main(sys.argv[1:])
	else:
		main("")

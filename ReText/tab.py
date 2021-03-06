# This file is part of ReText
# Copyright: 2015 Dmitry Shachnev
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from markups.common import MODULE_HOME_PAGE

from ReText import app_version, enchant, enchant_available, globalSettings
from ReText.editor import ReTextEdit
from ReText.highlighter import ReTextHighlighter

try:
	from ReText.fakevimeditor import ReTextFakeVimHandler
except ImportError:
	ReTextFakeVimHandler = None

from PyQt5.QtCore import Qt, QFile, QFileInfo, QObject, QTextStream, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QTextBrowser, QTextEdit, QSplitter
from PyQt5.QtWebKit import QWebSettings
from PyQt5.QtWebKitWidgets import QWebPage, QWebView

PreviewDisabled, PreviewLive, PreviewNormal = range(3)

class ReTextTab(QObject):
	def __init__(self, parent, fileName, previewState=PreviewDisabled):
		QObject.__init__(self, parent)
		self.p = parent
		self.fileName = fileName
		self.editBox = ReTextEdit(self)
		self.previewBox = self.createPreviewBox()
		self.markup = parent.getMarkup(fileName)
		self.previewState = previewState
		self.previewBlocked = False

		textDocument = self.editBox.document()
		self.highlighter = ReTextHighlighter(textDocument)
		if enchant_available and parent.actionEnableSC.isChecked():
			self.highlighter.dictionary = enchant.Dict(parent.sl)
			self.highlighter.rehighlight()
		self.highlighter.docType = self.markup.name

		self.editBox.textChanged.connect(self.updateLivePreviewBox)
		self.editBox.undoAvailable.connect(parent.actionUndo.setEnabled)
		self.editBox.redoAvailable.connect(parent.actionRedo.setEnabled)
		self.editBox.copyAvailable.connect(parent.actionCopy.setEnabled)
		textDocument.modificationChanged.connect(parent.modificationChanged)

		self.updateBoxesVisibility()

	def createWebView(self):
		webView = QWebView()
		if not globalSettings.handleWebLinks:
			webView.page().setLinkDelegationPolicy(QWebPage.DelegateExternalLinks)
			webView.page().linkClicked.connect(QDesktopServices.openUrl)
		settings = webView.settings()
		settings.setAttribute(QWebSettings.LocalContentCanAccessFileUrls, False)
		settings.setDefaultTextEncoding('utf-8')
		return webView

	def createPreviewBox(self):
		if globalSettings.useWebKit:
			return self.createWebView()
		browser = QTextBrowser()
		# TODO: honor globalSettings.handleWebLinks?
		browser.setOpenExternalLinks(True)
		return browser

	def getSplitter(self):
		splitter = QSplitter(Qt.Horizontal)
		# Give both boxes a minimum size so the minimumSizeHint will be
		# ignored when splitter.setSizes is called below
		for widget in self.editBox, self.previewBox:
			widget.setMinimumWidth(125)
			splitter.addWidget(widget)
		splitter.setSizes((50, 50))
		splitter.setChildrenCollapsible(False)
		splitter.tab = self
		return splitter

	def getDocumentTitle(self, baseName=False):
		if self.markup and not baseName:
			text = self.editBox.toPlainText()
			try:
				return self.markup.get_document_title(text)
			except Exception:
				self.p.printError()
		if self.fileName:
			fileinfo = QFileInfo(self.fileName)
			basename = fileinfo.completeBaseName()
			return (basename if basename else fileinfo.fileName())
		return self.tr("New document")

	def getHtml(self, includeStyleSheet=True, includeTitle=True,
	            includeMeta=False, webenv=False):
		if self.markup is None:
			markupClass = self.p.getMarkupClass(self.fileName)
			errMsg = self.tr('Could not parse file contents, check if '
			                 'you have the <a href="%s">necessary module</a> '
			                 'installed!')
			try:
				errMsg %= markupClass.attributes[MODULE_HOME_PAGE]
			except (AttributeError, KeyError):
				# Remove the link if markupClass doesn't have the needed attribute
				errMsg = errMsg.replace('<a href="%s">', '').replace('</a>', '')
			return '<p style="color: red">%s</p>' % errMsg
		text = self.editBox.toPlainText()
		headers = ''
		if includeStyleSheet:
			headers += '<style type="text/css">\n' + self.p.ss + '</style>\n'
		cssFileName = self.getDocumentTitle(baseName=True) + '.css'
		if QFile(cssFileName).exists():
			headers += ('<link rel="stylesheet" type="text/css" href="%s">\n'
			% cssFileName)
		if includeMeta:
			headers += ('<meta name="generator" content="ReText %s">\n'
			% app_version)
		fallbackTitle = self.getDocumentTitle() if includeTitle else ''
		return self.markup.get_whole_html(text,
			custom_headers=headers, include_stylesheet=includeStyleSheet,
			fallback_title=fallbackTitle, webenv=webenv)

	def updatePreviewBox(self):
		self.previewBlocked = False
		if isinstance(self.previewBox, QTextEdit):
			scrollbar = self.previewBox.verticalScrollBar()
			disttobottom = scrollbar.maximum() - scrollbar.value()
		else:
			frame = self.previewBox.page().mainFrame()
			scrollpos = frame.scrollPosition()
		try:
			html = self.getHtml()
		except Exception:
			return self.p.printError()
		if isinstance(self.previewBox, QTextEdit):
			self.previewBox.setHtml(html)
			self.previewBox.document().setDefaultFont(globalSettings.font)
			scrollbar.setValue(scrollbar.maximum() - disttobottom)
		else:
			settings = self.previewBox.settings()
			settings.setFontFamily(QWebSettings.StandardFont,
			                       globalSettings.font.family())
			settings.setFontSize(QWebSettings.DefaultFontSize,
			                     globalSettings.font.pointSize())
			self.previewBox.setHtml(html, QUrl.fromLocalFile(self.fileName))
			frame.setScrollPosition(scrollpos)

	def updateLivePreviewBox(self):
		if self.previewState == PreviewLive and not self.previewBlocked:
			self.previewBlocked = True
			QTimer.singleShot(1000, self.updatePreviewBox)

	def updateBoxesVisibility(self):
		self.editBox.setVisible(self.previewState < PreviewNormal)
		self.previewBox.setVisible(self.previewState > PreviewDisabled)

	def saveTextToFile(self, fileName=None, addToWatcher=True):
		if fileName is None:
			fileName = self.fileName
		self.p.fileSystemWatcher.removePath(fileName)
		savefile = QFile(fileName)
		result = savefile.open(QFile.WriteOnly)
		if result:
			savestream = QTextStream(savefile)
			if globalSettings.defaultCodec:
				savestream.setCodec(globalSettings.defaultCodec)
			savestream << self.editBox.toPlainText()
			savefile.close()
		if result and addToWatcher:
			self.p.fileSystemWatcher.addPath(fileName)
		return result

	def installFakeVimHandler(self):
		if ReTextFakeVimHandler:
			fakeVimEditor = ReTextFakeVimHandler(self.editBox, self)
			fakeVimEditor.setSaveAction(self.actionSave)
			fakeVimEditor.setQuitAction(self.actionQuit)
			# TODO: action is bool, really call remove?
			self.p.actionFakeVimMode.triggered.connect(fakeVimEditor.remove)

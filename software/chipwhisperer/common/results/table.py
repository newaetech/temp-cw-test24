#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2016, NewAE Technology Inc
# All rights reserved.
#
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.assembla.com/spaces/chipwhisperer
#
#    This file is part of chipwhisperer.
#
#    chipwhisperer is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    chipwhisperer is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with chipwhisperer.  If not, see <http://www.gnu.org/licenses/>.
#=================================================

from PySide.QtCore import *
from PySide.QtGui import *
from ._base import ResultsWidgetBase
from chipwhisperer.analyzer.attacks._base import ActiveAttackObserver


class ResultsTable(QTableWidget, ResultsWidgetBase, ActiveAttackObserver):
    _name = 'Results Table'
    _description = "Show all guesses based on sorting output of attack"

    def __init__(self, parentParam=None, name=None, useAbs=True):
        ResultsWidgetBase.__init__(self, parentParam, name)
        QTableWidget.__init__(self)

        self.params.addChildren([
            {'name':'Use Absolute Value for Rank', 'type':'list',
            'values':{"Default":lambda: self._analysisSource.getAbsoluteMode(), "True":True, "False":False},
            'value':"Default", 'set':self.setAbsoluteMode},
            {'name':'Use single point for Rank', 'type':'bool', 'value':False, 'set':self.setSingleMode},
            {'name':'Update Mode', 'key':'updateMode', 'type':'list', 'values':{'Entire Table (Slow)':'all', 'PGE Only (faster)':'pge'}, 'set':self.setUpdateMode},
        ])

        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.horizontalHeader().setMinimumSectionSize(51)
        self.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.useAbs = useAbs
        self.useSingle = False
        self.updateMode = self.findParam('updateMode').value()
        ActiveAttackObserver.__init__(self)

    def init(self):
        # Resize the table according to the attack model (number of subkeys and permutations) if needed
        ActiveAttackObserver.init(self)

        if self.numPerms + 1 != self.rowCount() or self.numKeys != self.columnCount():
            self.setRowCount(1 + self.numPerms)
            self.setColumnCount(self.numKeys)
            for x in range(0, self.numKeys):
                self.setHorizontalHeaderItem(x, QTableWidgetItem("%d" % x))
                cell = QTableWidgetItem("-")
                cell.setFlags(cell.flags() ^ Qt.ItemIsEditable)
                cell.setTextAlignment(Qt.AlignCenter)
                cell.setBackground(QBrush(QColor(253, 255, 205)))
                self.setItem(0, x, cell)
                for y in range(1, self.numPerms+1):
                    cell = QTableWidgetItem(" \n ")
                    cell.setFlags(cell.flags() ^ Qt.ItemIsEditable)
                    cell.setTextAlignment(Qt.AlignCenter)
                    self.setItem(y, x, cell)

            self.resizeRowsToContents()
            self.setVerticalHeaderItem(0, QTableWidgetItem("PGE"))
            for y in range(1, self.numPerms+1):
                self.setVerticalHeaderItem(y, QTableWidgetItem("%d" % (y-1)))

    def clearTableContents(self):
        for x in range(0, self.columnCount()):
            self.item(0, x).setText("-")
            for y in range(1, self.rowCount()):
                self.item(y, x).setText("")

    def setUpdateMode(self, mode):
        """Set if we update entire table or just PGE on every statistics update"""
        self.updateMode = mode

    def setAbsoluteMode(self, enabled):
        """If absolute mode is enabled, table is sorted based on absolute value of statistic"""
        self.useAbs = enabled

    def setSingleMode(self, enabled):
        """Single mode uses the same point across all traces, not useful normally"""
        self.useSingle = enabled

    def updateTable(self, everything=False):
        """Re-sort data and redraw the table. If update-mode is 'pge' we only redraw entire table
        when  everything=True (analysis is completed)."""
        if not self._analysisSource:
            return

        self.init()
        attackStats = self._analysisSource.getStatistics()
        attackStats.setKnownkey(self._analysisSource.knownKey())
        attackStats.findMaximums(useAbsolute=self.useAbs)
        highlights = self.highlightedKey()

        for bnum in range(0, self.numKeys):
            highlightValue = highlights[bnum] if highlights is not None and bnum < len(highlights) else None
            if bnum in self._analysisSource.bytesEnabled() and attackStats.maxValid[bnum]:
                self.setColumnHidden(bnum, False)
                maxes = attackStats.maxes[bnum]

                self.item(0, bnum).setText("%d" % attackStats.pge[bnum])
                if everything:
                    for j in range(0, self.numPerms):
                        cell = self.item(j+1, bnum)
                        cell.setText("%02X\n%.4f" % (maxes[j]['hyp'], maxes[j]['value']))
                        if maxes[j]['hyp'] == highlightValue:
                            cell.setForeground(QBrush(Qt.red))
                        else:
                            cell.setForeground(QBrush(Qt.black))
            else:
                self.setColumnHidden(bnum, True)
        self.setVisible(True)

    def analysisStarted(self):
        self.clearTableContents()

    def analysisUpdated(self):
        self.updateTable(everything=(self.updateMode == 'all'))

    def processAnalysis(self):
        self.updateTable(everything=True)

from burp import IBurpExtender, IContextMenuFactory, ITab, IContextMenuInvocation
from javax.swing import JMenuItem, JPanel, JScrollPane, JTable, JTabbedPane, JPopupMenu, JTextArea, JFrame, JOptionPane, JButton, JLabel, JCheckBox, TransferHandler, JFileChooser
from javax.swing.table import DefaultTableModel
from javax.swing import DropMode
from java.awt import BorderLayout, FlowLayout, Toolkit
from java.awt.event import MouseAdapter, KeyAdapter, KeyEvent
from java.awt.datatransfer import DataFlavor, Transferable, StringSelection
from java.util import ArrayList
import json, re
from java.nio.file import Files, Paths
from java.lang import String
from java.io import FileWriter

# Transfer handler for drag-and-drop row reordering
class TableRowTransferHandler(TransferHandler):
    def __init__(self, table):
        super(TableRowTransferHandler, self).__init__()
        self.table = table
        self.flavor = DataFlavor(
            "application/x-java-jvm-local-objectref;class=java.lang.Integer", None
        )

    def createTransferable(self, comp):
        return TransferableRow(comp.getSelectedRow())

    def getSourceActions(self, comp):
        return TransferHandler.MOVE

    def canImport(self, support):
        return support.isDrop() and support.isDataFlavorSupported(self.flavor)

    def importData(self, support):
        if not self.canImport(support):
            return False
        table = support.getComponent()
        toRow = support.getDropLocation().getRow()
        fromRow = support.getTransferable().getTransferData(self.flavor)
        model = table.getModel()
        rowData = [model.getValueAt(fromRow, c) for c in range(model.getColumnCount())]
        model.removeRow(fromRow)
        if toRow > fromRow:
            toRow -= 1
        model.insertRow(toRow, rowData)
        return True

class TransferableRow(Transferable):
    def __init__(self, rowIndex):
        self.rowIndex = rowIndex
    def getTransferDataFlavors(self):
        return [DataFlavor("application/x-java-jvm-local-objectref;class=java.lang.Integer", None)]
    def isDataFlavorSupported(self, flavor):
        return True
    def getTransferData(self, flavor):
        return self.rowIndex

class BurpExtender(IBurpExtender, IContextMenuFactory, ITab):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        callbacks.setExtensionName("ParamOrganizer")
        self.mainPanel = JPanel(BorderLayout())
        self.tabbedPane = JTabbedPane()
        self.mainPanel.add(self.tabbedPane, BorderLayout.CENTER)
        # records: uid -> {model, table, custom entries}
        self.records = {}
        callbacks.registerContextMenuFactory(self)
        callbacks.addSuiteTab(self)

    # ITab
    def getTabCaption(self):
        return "ParamOrganizer"

    def getUiComponent(self):
        return self.mainPanel

    # Context menu
    def createMenuItems(self, invocation):
        menu = ArrayList()
        msgs = invocation.getSelectedMessages()
        if not msgs:
            return menu
        msg = msgs[0]
        menu.add(JMenuItem("Just Request", actionPerformed=lambda e,inv=invocation: self.onMenuClick(inv, 'req')))
        if msg.getResponse() is not None:
            menu.add(JMenuItem("Just Response", actionPerformed=lambda e,inv=invocation: self.onMenuClick(inv, 'resp')))
            menu.add(JMenuItem("Request with Response", actionPerformed=lambda e,inv=invocation: self.onMenuClick(inv, 'both')))
        return menu

    def onMenuClick(self, invocation, mode):
        msgs = invocation.getSelectedMessages()
        if not msgs:
            return
        msg = msgs[0]
        helpers = self._callbacks.getHelpers()

        # extract params
        req_bytes = msg.getRequest()
        params_req = {}
        self.extract_params(helpers, req_bytes, True, params_req)
        resp_bytes = msg.getResponse()
        params_resp = {}
        if resp_bytes:
            self.extract_params(helpers, resp_bytes, False, params_resp)

        # combine
        combined = {}
        if mode in ('req','both'):
            for k,v in params_req.items(): combined.setdefault(k, []).append((v,'req'))
        if mode in ('resp','both'):
            for k,v in params_resp.items(): combined.setdefault(k, []).append((v,'resp'))
        if not combined:
            return

        # choose unique key
        keys = sorted(combined.keys()) + ['Custom']
        sel = JOptionPane.showInputDialog(None, "Select unique key:", "Unique Key",
                                         JOptionPane.QUESTION_MESSAGE, None, keys, keys[0])
        if not sel:
            return
        if sel == 'Custom' or sel not in combined:
            sel = JOptionPane.showInputDialog(None, "Enter custom key:", "Custom Key", JOptionPane.QUESTION_MESSAGE)
            if not sel: return
            sel_val = JOptionPane.showInputDialog(None, "Enter value for %s:" % sel, "Custom Value", JOptionPane.QUESTION_MESSAGE)
            if sel_val is None: return
        else:
            sel_val = combined[sel][0][0]
        uid = "%s:%s" % (sel, sel_val)

        # base entries
        base_entries = [(k,v,src) for k, lst in combined.items() for v,src in lst]

        # if existing
        if uid in self.records:
            rec = self.records[uid]
            model = rec['model']
            table = rec['table']
            custom = rec['custom']
            all_entries = base_entries + custom
            model.setRowCount(len(all_entries))
            for i,(p,v,s) in enumerate(all_entries):
                model.setValueAt(p, i, 0)
                model.setValueAt("%s (%s)" % (v, s), i, 1)
                model.setValueAt(s, i, 2)
            idx = self.tabbedPane.indexOfTab(uid)
            self.tabbedPane.setSelectedIndex(idx)
            return

        # new tab
        model = DefaultTableModel(len(base_entries), 3)
        model.setColumnIdentifiers(["Parameter","Value","Source"])
        table = JTable(model)
        table.setName(uid)  # tag table with unique id
        table.setDragEnabled(True)
        table.setDropMode(DropMode.INSERT_ROWS)
        table.setTransferHandler(TableRowTransferHandler(table))
        for i,(p,v,s) in enumerate(base_entries):
            model.setValueAt(p, i, 0)
            model.setValueAt("%s (%s)" % (v, s), i, 1)
            model.setValueAt(s, i, 2)
        table.getColumnModel().removeColumn(table.getColumnModel().getColumn(2))

        # controls
        cb_full = JCheckBox("Show full path"); cb_full.setSelected(True)
        cb_hide = JCheckBox("Hide source suffix"); cb_hide.setSelected(False)
        btn_copy_p = JButton("Copy Parameters")
        btn_copy_v = JButton("Copy Values")
        btn_add = JButton("Add Entry")
        btn_export = JButton("Export JSON")
        btn_import = JButton("Import JSON")

        def copy_col(ci):
            txt = [str(model.getValueAt(r,ci)) for r in range(model.getRowCount())]
            sel_clip = StringSelection('\n'.join(txt))
            Toolkit.getDefaultToolkit().getSystemClipboard().setContents(sel_clip, None)
        btn_copy_p.addActionListener(lambda e: copy_col(0))
        btn_copy_v.addActionListener(lambda e: copy_col(1))

        def on_add(e):
            key = JOptionPane.showInputDialog(None, "Enter Parameter:", "Add Entry", JOptionPane.QUESTION_MESSAGE)
            if not key:
                return
            val = JOptionPane.showInputDialog(None, "Enter Value for %s:" % key, "Add Entry", JOptionPane.QUESTION_MESSAGE)
            if val is None:
                return
            src = JOptionPane.showInputDialog(None, "Select source:", "Add Entry",
                                             JOptionPane.QUESTION_MESSAGE, None, ['req','resp'], 'req')
            if not src:
                return
            rec = self.records.get(uid, {'model': model, 'table': table, 'custom': []})
            rec['custom'].append((key, val, src))
            model.addRow([key, "%s (%s)" % (val, src), src])
        btn_add.addActionListener(on_add)

        # JSON export
        def on_export(e):
            chooser = JFileChooser()
            chooser.setDialogTitle("Save JSON")
            if chooser.showSaveDialog(None) == JFileChooser.APPROVE_OPTION:
                f = chooser.getSelectedFile()
                rows = []
                for i in range(model.getRowCount()):
                    rows.append({
                        "Parameter": model.getValueAt(i,0),
                        "Value": model.getValueAt(i,1).split(' ')[0],
                        "Source": model.getValueAt(i,2)
                    })
                fw = FileWriter(f.getAbsolutePath())
                fw.write(json.dumps(rows, indent=2))
                fw.close()
        btn_export.addActionListener(on_export)

        # JSON import
        def on_import(e):
            chooser = JFileChooser()
            chooser.setDialogTitle("Open JSON")
            if chooser.showOpenDialog(None) == JFileChooser.APPROVE_OPTION:
                f = chooser.getSelectedFile()
                # read raw bytes and convert to string
                content_bytes = Files.readAllBytes(Paths.get(f.getAbsolutePath()))
                content = String(content_bytes, "UTF-8")
                # convert java.lang.String to Python str
                content = content.toString()
                items = json.loads(content)
                model.setRowCount(0)
                rec = self.records.get(uid)
                rec['custom'] = []
                for it in items:
                    p = it["Parameter"]
                    v = it["Value"]
                    s = it["Source"]
                    model.addRow([p, "%s (%s)" % (v, s), s])
                    rec['custom'].append((p, v, s))
        btn_import.addActionListener(on_import)

        def toggle_full(e):
            show = cb_full.isSelected()
            for i,(p,v,s) in enumerate(base_entries + self.records.get(uid, {'custom':[]})['custom']):
                model.setValueAt(p if show else p.split('.')[-1], i, 0)
        cb_full.addActionListener(toggle_full)

        def toggle_hide(e):
            hide = cb_hide.isSelected()
            for i,(p,v,s) in enumerate(base_entries + self.records.get(uid, {'custom':[]})['custom']):
                model.setValueAt(v if hide else "%s (%s)" % (v, s), i, 1)
        cb_hide.addActionListener(toggle_hide)

        panel = JPanel(BorderLayout())
        top = JPanel(FlowLayout(FlowLayout.LEFT))
        for comp in (cb_full, cb_hide, btn_copy_p, btn_copy_v, btn_add, btn_export, btn_import):
            top.add(comp)
        panel.add(top, BorderLayout.NORTH)
        panel.add(JScrollPane(table), BorderLayout.CENTER)

        # context-menu popup
        self.attach_popup(table, req_bytes, resp_bytes, helpers)

        # add tab
        self.tabbedPane.addTab(uid, panel)
        idx = self.tabbedPane.getTabCount() - 1
        self.tabbedPane.setSelectedIndex(idx)
        # close button
        hdr = JPanel(FlowLayout(FlowLayout.LEFT,0,0))
        lbl = JLabel(uid)
        close_btn = JButton('x')
        close_btn.setBorder(None); close_btn.setContentAreaFilled(False); close_btn.setFocusPainted(False)
        close_btn.addActionListener(lambda e,ix=idx,k=uid: self.tabbedPane.removeTabAt(ix) or self.records.pop(k,None))
        hdr.add(lbl); hdr.add(close_btn)
        self.tabbedPane.setTabComponentAt(idx, hdr)

        # store record
        self.records[uid] = {'model': model, 'table': table, 'custom': []}

    def extract_params(self, helpers, msg_bytes, is_req, out_map):
        try:
            info = helpers.analyzeRequest(msg_bytes) if is_req else helpers.analyzeResponse(msg_bytes)
            body = msg_bytes[info.getBodyOffset():].tostring()
            headers = info.getHeaders()
            if any('application/json' in h.lower() for h in headers):
                data = json.loads(body)
                self.flatten_json("", data, out_map)
            else:
                for part in body.split("&"):
                    if "=" in part:
                        k,v = part.split("=",1)
                        out_map[k] = v
        except Exception as e:
            self._callbacks.printError("Parse error: %s" % e)

    def attach_popup(self, table, req_bytes, resp_bytes, helpers):
        ext = self  # reference for inner listeners

        popup = JPopupMenu()
        item = JMenuItem("Show in Message")
        popup.add(item)
        def on_show(evt):
            row = table.getSelectedRow()
            if row < 0: return
            key = table.getModel().getValueAt(row, 0)
            val = table.getModel().getValueAt(row, 1).split(' ')[0]
            src = table.getModel().getValueAt(row, 2)
            raw = resp_bytes if src=='resp' and resp_bytes else req_bytes
            analyzed = helpers.analyzeResponse(resp_bytes) if src=='resp' and resp_bytes else helpers.analyzeRequest(req_bytes)
            text = helpers.bytesToString(raw)
            body = text[analyzed.getBodyOffset():]
            headers = analyzed.getHeaders()
            if any('application/json' in h.lower() for h in headers):
                pat = r'"%s"\s*:\s*"%s"' % (re.escape(key), re.escape(val))
                m = re.search(pat, body)
                if m: start,end = m.span()
                else: start = body.find(val); end = start + len(val)
            else:
                pat = "%s=%s" % (key, val)
                start = body.find(pat); end = start + len(pat) if start>=0 else -1
            ta = JTextArea(body, 20, 80)
            if start>=0:
                ta.select(start, end)
                ta.requestFocus()
            fr = JFrame(("Response" if src=='resp' else "Request") + " - " + key)
            fr.setLayout(BorderLayout())
            fr.add(JScrollPane(ta), BorderLayout.CENTER)
            fr.setSize(700, 500)
            fr.setVisible(True)
        item.addActionListener(on_show)
        # Add delete option for selected entries
        delete_item = JMenuItem("Delete Entry(s)")
        popup.add(delete_item)
        def on_delete(evt):
            uid = table.getName()
            rec = self.records.get(uid)
            if not rec: return
            model = rec['model']
            custom = rec['custom']
            rows = table.getSelectedRows()
            # remove from bottom to top
            for row in sorted(rows, reverse=True):
                key = model.getValueAt(row, 0)
                val = model.getValueAt(row, 1).split(' ')[0]
                src = model.getValueAt(row, 2)
                entry = (key, val, src)
                if entry in custom:
                    custom.remove(entry)
                model.removeRow(row)
        delete_item.addActionListener(on_delete)
        def maybe_show(e):
            if e.isPopupTrigger():
                pt = e.getPoint(); r = table.rowAtPoint(pt)
                if r>=0:
                    table.setRowSelectionInterval(r, r)
                    popup.show(table, pt.x, pt.y)
        class PopupListener(MouseAdapter):
            def mousePressed(self, e): maybe_show(e)
            def mouseReleased(self, e): maybe_show(e)
        table.addMouseListener(PopupListener())
        # Add Delete key shortcut to remove selected entries
        class DeleteKeyListener(KeyAdapter):
            def keyPressed(self, e):
                if e.getKeyCode() == KeyEvent.VK_DELETE:
                    uid = table.getName()
                    rec = ext.records.get(uid)
                    if not rec: return
                    model = rec['model']
                    custom = rec['custom']
                    rows = table.getSelectedRows()
                    for row in sorted(rows, reverse=True):
                        key = model.getValueAt(row, 0)
                        val = model.getValueAt(row, 1).split(' ')[0]
                        src = model.getValueAt(row, 2)
                        entry = (key, val, src)
                        if entry in custom:
                            custom.remove(entry)
                        model.removeRow(row)
        table.setFocusable(True)
        table.requestFocusInWindow()
        table.addKeyListener(DeleteKeyListener())

    def flatten_json(self, prefix, obj, out_map):
        if isinstance(obj, dict):
            for k,v in obj.items():
                new_key = "%s.%s" % (prefix, k) if prefix else k
                self.flatten_json(new_key, v, out_map)
        elif isinstance(obj, list):
            for i,v in enumerate(obj):
                new_key = "%s[%d]" % (prefix, i)
                self.flatten_json(new_key, v, out_map)
        else:
            out_map[prefix] = obj

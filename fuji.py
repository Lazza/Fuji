import string
import sys
import threading
from pathlib import Path

import wx

from acquisition.abstract import AcquisitionMethod, Parameters
from acquisition.asr import AsrMethod
from acquisition.rsync import RsyncMethod

METHODS = [AsrMethod(), RsyncMethod()]
PARAMS = Parameters()

INPUT_WINDOW: "InputWindow"
OVERVIEW_WINDOW: "OverviewWindow"
PROCESSING_WINDOW: "ProcessingWindow"


class RedirectText(object):
    def __init__(self, control: wx.TextCtrl):
        self.out = control

    def write(self, value):
        wx.CallAfter(self.out.AppendText, value)


class InputWindow(wx.Frame):
    method: AcquisitionMethod

    def __init__(self):
        super().__init__(
            parent=None,
            title="Fuji - Forensic Unattended Juicy Imaging",
            size=(600, 400),
        )
        panel = wx.Panel(self)

        # Components
        title = wx.StaticText(panel, label="Fuji")
        title_font = wx.Font(
            36, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_HEAVY
        )
        title.SetFont(title_font)
        desc = wx.StaticText(panel, label="Forensic Unattended Juicy Imaging")

        case_label = wx.StaticText(panel, label="Case name:")
        self.case_text = wx.TextCtrl(panel, value=PARAMS.case)
        examiner_label = wx.StaticText(panel, label="Examiner:")
        self.examiner_text = wx.TextCtrl(panel, value=PARAMS.examiner)
        notes_label = wx.StaticText(panel, label="Notes:")
        self.notes_text = wx.TextCtrl(panel, value=PARAMS.notes)

        output_label = wx.StaticText(panel, label="Image name:")
        self.output_text = wx.TextCtrl(panel, value=PARAMS.image_name)
        self.output_text.Bind(wx.EVT_CHAR, self._validate_image_name)
        source_label = wx.StaticText(panel, label="Source:")
        self.source_picker = wx.DirPickerCtrl(panel, path="/")
        tmp_label = wx.StaticText(panel, label="Temporary image location:")
        self.tmp_picker = wx.DirPickerCtrl(panel, path="/Volumes/Fuji")
        destination_label = wx.StaticText(panel, label="DMG destination:")
        self.destination_picker = wx.DirPickerCtrl(panel, path="/Volumes/Fuji")
        method_label = wx.StaticText(panel, label="Acquisition method:")
        self.method_choice = wx.Choice(panel, choices=[m.name for m in METHODS])
        self.method_choice.SetSelection(0)

        # Prepare method descriptions
        self.description_texts = []
        for method in METHODS:
            description_label = f"<b>{method.name}:</b> {method.description}"
            description_text = wx.StaticText(panel)
            description_text.SetLabelMarkup(description_label)
            self.description_texts.append(description_text)

        # Buttons
        continue_btn = wx.Button(panel, label="Continue")
        continue_btn.Bind(wx.EVT_BUTTON, self.on_continue)

        # Layout
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add(desc, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 5)
        vbox.Add((0, 20))

        # Create a FlexGridSizer for labels and text controls
        case_info = wx.FlexGridSizer(cols=2, hgap=10, vgap=10)
        case_info.Add(case_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        case_info.Add(self.case_text, 1, wx.EXPAND)
        case_info.Add(examiner_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        case_info.Add(self.examiner_text, 1, wx.EXPAND)
        case_info.Add(notes_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        case_info.Add(self.notes_text, 1, wx.EXPAND)
        case_info.AddGrowableCol(1, 1)

        vbox.Add(case_info, 0, wx.EXPAND | wx.ALL, 10)

        output_info = wx.FlexGridSizer(cols=2, hgap=10, vgap=10)
        output_info.Add(output_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.output_text, 1, wx.EXPAND)
        output_info.Add(source_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.source_picker, 1, wx.EXPAND)
        output_info.Add(tmp_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.tmp_picker, 1, wx.EXPAND)
        output_info.Add(destination_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.destination_picker, 1, wx.EXPAND)
        output_info.Add(method_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.method_choice, 1, wx.EXPAND)
        output_info.AddGrowableCol(1, 1)

        vbox.Add(output_info, 0, wx.EXPAND | wx.ALL, 10)

        for description_text in self.description_texts:
            vbox.Add(description_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        vbox.Add((0, 20))
        vbox.Add(continue_btn, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 20)
        panel.SetSizer(vbox)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel)
        self.SetSizerAndFit(sizer)

        # Bind close
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def _validate_image_name(self, event):
        key = event.GetKeyCode()
        valid_characters = "-_" + string.ascii_letters + string.digits

        if chr(key) in valid_characters:
            event.Skip()
            return
        else:
            return False

    def on_continue(self, event):
        PARAMS.case = self.case_text.Value
        PARAMS.examiner = self.examiner_text.Value
        PARAMS.notes = self.notes_text.Value
        PARAMS.image_name = self.output_text.Value
        PARAMS.source = Path(self.source_picker.GetPath())
        PARAMS.tmp = Path(self.tmp_picker.GetPath())
        PARAMS.destination = Path(self.destination_picker.GetPath())
        self.method = METHODS[self.method_choice.GetSelection()]

        self.Hide()
        OVERVIEW_WINDOW.update_overview()
        OVERVIEW_WINDOW.Show()

    def on_close(self, event):
        app: wx.App = wx.GetApp()
        app.ExitMainLoop()


class OverviewWindow(wx.Frame):
    def __init__(self):
        super().__init__(
            parent=None,
            title="Fuji - Overview",
            size=(600, 400),
        )
        panel = wx.Panel(self)

        # Components
        title = wx.StaticText(panel, label="Acquisition overview")
        title_font = wx.Font(
            18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD
        )
        title.SetFont(title_font)
        self.overview_text = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.VSCROLL
        )

        # Buttons
        back_btn = wx.Button(panel, label="Back")
        back_btn.Bind(wx.EVT_BUTTON, self.on_back)
        confirm_btn = wx.Button(panel, label="Confirm")
        confirm_btn.Bind(wx.EVT_BUTTON, self.on_confirm)

        # Layout
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add((0, 10))
        vbox.Add(self.overview_text, 1, wx.EXPAND | wx.ALL, 10)
        vbox.Add((0, 20))
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(back_btn, 0, wx.RIGHT, 10)
        hbox.Add(confirm_btn, 0)
        vbox.Add(hbox, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 20)

        panel.SetSizer(vbox)

        # Bind close
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def update_overview(self):
        overview = f"Case name: {PARAMS.case}\n"
        overview += f"Examiner: {PARAMS.examiner}\n"
        overview += f"Notes: {PARAMS.notes}\n"
        overview += f"Image name: {PARAMS.image_name}\n"
        overview += f"Source: {PARAMS.source}\n"
        overview += f"Temporary image location: {PARAMS.tmp}\n"
        overview += f"DMG destination: {PARAMS.destination}\n"
        overview += f"Acquisition method: {INPUT_WINDOW.method.name}\n"

        self.overview_text.SetValue(overview)

    def on_back(self, event):
        # Hide the overview window and show the input window again
        self.Hide()
        INPUT_WINDOW.Show()

    def on_confirm(self, event):
        # Start acquisition
        self.Hide()
        PROCESSING_WINDOW.activate()

    def on_close(self, event):
        self.on_back(event)


class ProcessingWindow(wx.Frame):
    def __init__(self):
        super().__init__(
            parent=None,
            title="Fuji - Acquisition",
            size=(800, 600),
        )
        self.panel = wx.Panel(self)

        # Components
        self.title = wx.StaticText(self.panel, label="Acquisition in progress")
        self.title_font = wx.Font(
            18, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD
        )
        self.title.SetFont(self.title_font)
        self.output_text = wx.TextCtrl(
            self.panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.VSCROLL
        )

        # Layout
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self.title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add(self.output_text, 1, wx.EXPAND | wx.ALL, 10)

        self.panel.SetSizer(vbox)

        # Bind close
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def activate(self):
        self.running = True

        # Reset initial status
        self.title.SetLabel("Acquisition in progress")
        self.title.SetForegroundColour(wx.NullColour)
        self.title.SetFont(self.title_font)
        self.output_text.SetValue("")

        self.Show()

        # Redirect sys.stdout to the custom file-like object
        redir = RedirectText(self.output_text)
        sys.stdout = redir
        sys.stderr = redir

        # Start acquisition process in a separate thread
        self.acquisition_thread = threading.Thread(target=self.execute_acquisition)
        self.acquisition_thread.start()

    def execute_acquisition(self):
        try:
            method = INPUT_WINDOW.method
            result = method.execute(PARAMS)

            # Process ended
            wx.CallAfter(self.set_completion_status, result.success)

        except Exception as e:
            # Acquisition failed
            wx.CallAfter(self.set_completion_status, False)
            wx.CallAfter(sys.stdout.write, f"Error: {str(e)}\n")

    def set_completion_status(self, success):
        if success:
            self.title.SetLabel("Acquisition completed")
            self.title.SetForegroundColour((20, 240, 20))
        else:
            self.title.SetLabel("Acquisition failed")
            self.title.SetForegroundColour((240, 20, 20))
        self.title.SetFont(self.title_font)
        self.running = False

    def on_close(self, event):
        if not self.running:
            self.Hide()
            INPUT_WINDOW.Show()


if __name__ == "__main__":
    app = wx.App()
    INPUT_WINDOW = InputWindow()
    OVERVIEW_WINDOW = OverviewWindow()
    PROCESSING_WINDOW = ProcessingWindow()

    INPUT_WINDOW.Show()
    app.MainLoop()
    app.Destroy()

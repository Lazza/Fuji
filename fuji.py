import string
import wx

from acquisition.abstract import Parameters
from acquisition.asr import AsrMethod
from acquisition.rsync import RsyncMethod

METHODS = [AsrMethod(), RsyncMethod()]
PARAMS = Parameters()


class InputWindow(wx.Frame):
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

        output_label = wx.StaticText(panel, label="Output name:")
        self.output_text = wx.TextCtrl(panel, value="FujiAcquisition")
        self.output_text.Bind(wx.EVT_CHAR, self._validate_image_name)
        source_label = wx.StaticText(panel, label="Source device:")
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

    def _validate_image_name(self, event):
        key = event.GetKeyCode()
        valid_characters = "-_" + string.ascii_letters + string.digits

        if chr(key) in valid_characters:
            event.Skip()
            return
        else:
            return False

    def on_continue(self, event):
        # Validate input and proceed to the next window
        pass


if __name__ == "__main__":
    app = wx.App()
    input_win = InputWindow()
    input_win.Show()
    app.MainLoop()

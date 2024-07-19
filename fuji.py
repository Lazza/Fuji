import os
import string
import subprocess
import sys
import threading
from pathlib import Path

import wx
import wx.lib.agw.hyperlink as hl

from acquisition.abstract import AcquisitionMethod, Parameters
from acquisition.asr import AsrMethod
from acquisition.rsync import RsyncMethod
from acquisition.sysdiagnose import SysdiagnoseMethod
from checks.folders import FoldersCheck
from checks.free_space import FreeSpaceCheck
from checks.network import NetworkCheck
from meta import AUTHOR, HOMEPAGE, VERSION
from shared.utils import lines_to_properties

METHODS = [AsrMethod(), RsyncMethod(), SysdiagnoseMethod()]
CHECKS = [FoldersCheck(), FreeSpaceCheck(), NetworkCheck()]
PARAMS = Parameters()

INPUT_WINDOW: "InputWindow"
OVERVIEW_WINDOW: "OverviewWindow"
PROCESSING_WINDOW: "ProcessingWindow"


class RedirectText(object):
    out: wx.TextCtrl
    max_lines = 500

    def __init__(self, control: wx.TextCtrl):
        self.out = control

    def write(self, value):
        wx.CallAfter(self.append_shrink, value)

    def append_shrink(self, value):
        self.out.AppendText(value)
        lines = self.out.GetNumberOfLines()
        if lines > self.max_lines:
            delta = lines - self.max_lines
            position = self.out.XYToPosition(0, delta - 1)
            self.out.Remove(0, position)
        self.out.ShowPosition(self.out.GetLastPosition())


class InputWindow(wx.Frame):
    method: AcquisitionMethod

    def __init__(self):
        super().__init__(
            parent=None,
            title="Fuji - Forensic Unattended Juicy Imaging",
            size=(600, 400),
            style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX),
        )
        self.EnableMaximizeButton(False)
        panel = wx.Panel(self)

        # Components
        title = wx.StaticText(panel, label="Fuji")
        title_font: wx.Font = title.GetFont()
        title_font.SetPointSize(36)
        title_font.SetWeight(wx.FONTWEIGHT_EXTRABOLD)
        title.SetFont(title_font)
        desc = wx.StaticText(panel, label="Forensic Unattended Juicy Imaging")
        desc_font: wx.Font = desc.GetFont()
        desc_font.SetPointSize(18)
        desc_font.SetWeight(wx.FONTWEIGHT_BOLD)
        desc.SetFont(desc_font)

        byline_text = wx.StaticText(panel, label=f"Version {VERSION} by {AUTHOR}")
        byline_link = hl.HyperLinkCtrl(panel, label=HOMEPAGE, URL=HOMEPAGE)
        accent = wx.Colour(181, 78, 78)
        byline_link.SetColours(accent, accent, accent)
        byline_link.SetBold(True)
        byline_link.UpdateLink()

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
        self.source_picker = wx.DirPickerCtrl(panel)
        self.source_picker.SetInitialDirectory("/")
        self.source_picker.SetPath(str(PARAMS.source))
        tmp_label = wx.StaticText(panel, label="Temp image location:")
        self.tmp_picker = wx.DirPickerCtrl(panel)
        self.tmp_picker.SetInitialDirectory("/Volumes")
        if os.path.isdir(PARAMS.tmp):
            self.tmp_picker.SetPath(str(PARAMS.tmp))
        destination_label = wx.StaticText(panel, label="DMG destination:")
        self.tmp_picker.Bind(wx.EVT_DIRPICKER_CHANGED, self._tmp_location_changed)
        self.destination_picker = wx.DirPickerCtrl(panel)
        self.destination_picker.SetInitialDirectory("/Volumes")
        if os.path.isdir(PARAMS.destination):
            self.destination_picker.SetPath(str(PARAMS.destination))
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

        # Sound checkbox
        self.sound_checkbox = wx.CheckBox(
            panel, label="Play loud sound when acquisition is completed"
        )
        self.sound_checkbox.SetValue(True)

        # Buttons
        continue_btn = wx.Button(panel, label="Continue")
        continue_btn.Bind(wx.EVT_BUTTON, self.on_continue)

        # Layout
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add(desc, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 5)
        vbox.Add((0, 10))

        vbox.Add(byline_text, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 0)
        vbox.Add(byline_link, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 5)
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
        vbox.Add(self.sound_checkbox, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 10)
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

    def _tmp_location_changed(self, event):
        temp_location = self.tmp_picker.GetPath()
        destination_location = self.destination_picker.GetPath()
        if not destination_location:
            self.destination_picker.SetPath(temp_location)

    def on_continue(self, event):
        PARAMS.case = self.case_text.Value
        PARAMS.examiner = self.examiner_text.Value
        PARAMS.notes = self.notes_text.Value
        PARAMS.image_name = self.output_text.Value
        PARAMS.source = Path(self.source_picker.GetPath().strip())
        PARAMS.tmp = Path(self.tmp_picker.GetPath().strip())
        PARAMS.destination = Path(self.destination_picker.GetPath().strip())
        PARAMS.sound = self.sound_checkbox.GetValue()
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
            size=(800, 400),
            style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX),
        )
        panel = wx.Panel(self)

        # Components
        title = wx.StaticText(panel, label="Acquisition overview")
        title_font: wx.Font = title.GetFont()
        title_font.SetPointSize(18)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)

        # Overview grid container of 2 columns
        self.overview_grid = wx.FlexGridSizer(cols=2, hgap=20, vgap=10)
        self.overview_grid.AddGrowableCol(1, 1)

        # Buttons
        back_btn = wx.Button(panel, label="Back")
        back_btn.Bind(wx.EVT_BUTTON, self.on_back)
        confirm_btn = wx.Button(panel, label="Confirm")
        confirm_btn.Bind(wx.EVT_BUTTON, self.on_confirm)

        # Layout
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add((0, 10))
        vbox.Add(self.overview_grid, 0, wx.EXPAND | wx.ALL, 10)
        vbox.Add((0, 20))
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(back_btn, 0, wx.RIGHT, 10)
        hbox.Add(confirm_btn, 0)
        vbox.Add(hbox, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 20)

        panel.SetSizer(vbox)
        self.panel = panel

        # Bind close
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def update_overview(self):
        # Clear the existing grid content
        self.overview_grid.Clear(True)

        data = {
            "Case name": PARAMS.case,
            "Examiner": PARAMS.examiner,
            "Notes": PARAMS.notes,
            "Image name": PARAMS.image_name,
            "Source": PARAMS.source,
            "Temp image location": PARAMS.tmp,
            "DMG destination": PARAMS.destination,
            "Acquisition method": INPUT_WINDOW.method.name,
            "Play sound": "Yes" if PARAMS.sound else "No",
        }

        max_text_width = 600

        # Insert rows into the grid
        for label, value in data.items():
            label_text = wx.StaticText(self.panel, label=label)
            label_text_font = label_text.GetFont()
            label_text_font.SetWeight(wx.FONTWEIGHT_BOLD)
            label_text.SetFont(label_text_font)
            value_text = wx.StaticText(
                self.panel,
                label=f"{value}",
                size=(max_text_width, -1),
            )
            value_text.Wrap(max_text_width)
            self.overview_grid.Add(label_text, 0, wx.ALIGN_LEFT | wx.ALIGN_TOP)
            self.overview_grid.Add(value_text, 1, wx.ALIGN_LEFT | wx.ALIGN_TOP)

        # Perform checks
        for check in CHECKS:
            result = check.execute(PARAMS)
            label_text = wx.StaticText(self.panel, label=check.name)
            label_text_font = label_text.GetFont()
            label_text_font.SetWeight(wx.FONTWEIGHT_BOLD)
            label_text.SetFont(label_text_font)
            if not result.passed:
                label_text.SetForegroundColour((240, 20, 20))
            value_text = wx.StaticText(
                self.panel,
                label=result.message,
                size=(max_text_width, -1),
            )
            value_text.Wrap(max_text_width)
            self.overview_grid.Add(label_text, 0, wx.ALIGN_LEFT | wx.ALIGN_TOP)
            self.overview_grid.Add(value_text, 1, wx.ALIGN_LEFT | wx.ALIGN_TOP)

        # Update the layout
        self.panel.Layout()
        self.panel.Fit()
        self.Fit()

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
        self.title_font: wx.Font = self.title.GetFont()
        self.title_font.SetPointSize(18)
        self.title_font.SetWeight(wx.FONTWEIGHT_BOLD)
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

            if PARAMS.sound:
                self.play_sound(result.success)

        except Exception as e:
            # Acquisition failed
            wx.CallAfter(self.set_completion_status, False)
            wx.CallAfter(sys.stdout.write, f"Error: {str(e)}\n")

    def play_sound(self, success: bool):
        MAX_VOLUME = 7

        volume_settings = subprocess.check_output(
            ["osascript", "-e", "get volume settings"], universal_newlines=True
        )
        volume_properties = lines_to_properties(volume_settings.split(","))
        try:
            current_volume = int(volume_properties.get("output volume"))
        except:
            # Keep reasonable volume
            current_volume = 50
        scaled = MAX_VOLUME * (current_volume / 100.0)
        rounded = round(scaled, 4)

        # Play the sound
        subprocess.call(["osascript", "-e", f"set Volume {MAX_VOLUME}"])
        sound = "Glass" if success else "Basso"
        subprocess.call(["afplay", f"/System/Library/Sounds/{sound}.aiff"])
        subprocess.call(["osascript", "-e", f"set Volume {rounded}"])

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
    # Try to find the serial number
    information = subprocess.check_output(
        ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], universal_newlines=True
    ).splitlines()
    for line in information:
        if "IOPlatformSerialNumber" in line:
            parts = line.split("=")
            serial_number = parts[1].strip(' "')
            PARAMS.image_name = f"{serial_number}_Acquisition"
            break

    app = wx.App()
    INPUT_WINDOW = InputWindow()
    OVERVIEW_WINDOW = OverviewWindow()
    PROCESSING_WINDOW = ProcessingWindow()

    INPUT_WINDOW.Show()
    app.MainLoop()
    app.Destroy()

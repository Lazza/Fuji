import os
import re
import string
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import humanize
import wx

from acquisition.abstract import AcquisitionMethod, Parameters
from acquisition.asr import AsrMethod
from acquisition.ditto import DittoMethod
from acquisition.rsync import RsyncMethod
from acquisition.sysdiagnose import SysdiagnoseMethod
from checks.abstract import Check
from checks.folders import FoldersCheck
from checks.free_space import FreeSpaceCheck
from checks.name import NameCheck
from checks.network import NetworkCheck
from checks.readonly import ReadOnlySourceCheck
from checks.running_apps import RunningAppsCheck
from meta import AUTHOR, HOMEPAGE, VERSION
from shared.environment import RECOVERY, AdaptiveHyperLinkCtrl, attempt_ramdisk
from shared.filevault import (
    EncryptedVolume,
    UnlockError,
    list_encrypted_volumes,
    unlock_volume_readonly,
)
from shared.utils import (
    ACCENT_COLOR,
    GREEN_COLOR,
    RED_COLOR,
    command_to_properties,
    dedent,
    lines_to_properties,
    set_font,
)

ALL_METHODS: List[AcquisitionMethod] = [
    DittoMethod(),
    RsyncMethod(),
    AsrMethod(),
    SysdiagnoseMethod(),
]
METHODS = [m for m in ALL_METHODS if m.available()]
ALL_CHECKS: List[Check] = [
    NameCheck(),
    FoldersCheck(),
    FreeSpaceCheck(),
    NetworkCheck(),
    ReadOnlySourceCheck(),
    RunningAppsCheck(),
]
CHECKS = [c for c in ALL_CHECKS if c.active()]
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


@dataclass
class DiskSpaceInfo:
    identifier: str = ""
    size: int = 0
    used_space: int = 0
    free_space: int = 0
    mount_point: str = ""


@dataclass
class DeviceInfo:
    indent: int = 0
    type: str = ""
    name: str = ""
    size: str = ""
    identifier: str = ""
    status: str = ""
    disk_space: Optional[DiskSpaceInfo] = None
    filevault_status: str = ""
    is_locked: bool = False


class DevicesWindow(wx.Frame):
    def _parse_stanza(
        self, stanza: str, mount_info: dict[str, DiskSpaceInfo]
    ) -> Iterable[DeviceInfo]:
        lines = stanza.splitlines()
        first, second = lines[:2]
        status = ""
        if "(" in first:
            status = first.split("(")[1].split(")")[0]
        pivot_1 = second.index(":") + 1
        pivot_2 = second.index(" NAME")
        pivot_3 = second.index(" SIZE")
        pivot_4 = second.index(" IDENTIFIER")

        is_disk = True
        for line in lines[2:]:
            type = line[pivot_1 + 1 : pivot_2].strip()
            name = line[pivot_2:pivot_3].strip()
            size = line[pivot_3 + 1 : pivot_4].strip()
            identifier = line[pivot_4:].strip()
            if not identifier:
                continue
            indent = identifier[4:].count("s")
            if identifier == "-":
                indent = 1
            device_info = DeviceInfo(
                indent=indent,
                type=type,
                name=name,
                size=size,
                identifier=identifier,
                status=status if is_disk else "",
                disk_space=mount_info.get(identifier),
            )

            is_disk = False
            yield device_info

    def __init__(self, parent):
        super().__init__(parent, title="Fuji - Drives and partitions")
        self.parent = parent
        panel = wx.Panel(self)
        self._panel = panel

        title = wx.StaticText(panel, label="List of drives and partitions")
        set_font(title, size=18, weight=wx.FONTWEIGHT_BOLD)

        devices_label = wx.StaticText(
            panel,
            label="The source can be set by double-clicking on a mounted partition",
        )

        self.list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.on_item_focused)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)

        # Add columns to the list control. "FileVault" is inserted between
        # "Device status" and "Mount point" so that lock state is visible in
        # the same row as the rest of the per-partition information.
        self._columns = [
            "Identifier",
            "Type",
            "Name",
            "Size",
            "Device status",
            "FileVault",
            "Mount point",
            "Used space",
        ]

        for index, col in enumerate(self._columns):
            self.list_ctrl.InsertColumn(index, col, width=-1)

        self.devices: List[DeviceInfo] = []
        self.selected_index = -1

        self._enumerate_devices()
        self._populate_list()

        # Compute a sensible minimum size based on the initial contents. This
        # is done only once; _populate_list resizes columns on every refresh
        # without altering the window minimum.
        padding = 10
        width = padding * 4
        height = padding * 4
        for index in range(len(self._columns)):
            width = width + self.list_ctrl.GetColumnWidth(index)
        for index in range(self.list_ctrl.ItemCount):
            rect: wx.Rect = self.list_ctrl.GetItemRect(index)
            height = height + rect.GetHeight()

        self.list_ctrl.SetMinSize(wx.Size(width, height))

        # Unlock button for FileVault-encrypted volumes. This is the only
        # affordance for bringing a locked APFS volume online; the existing
        # double-click flow intentionally refuses unmounted volumes.
        self.unlock_btn = wx.Button(panel, label="Unlock FileVault volume\u2026")
        self.unlock_btn.Bind(wx.EVT_BUTTON, self.on_unlock_filevault)
        self._refresh_unlock_button_state()

        # Add controls to the sizer
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add(devices_label, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 10)
        vbox.Add((0, 10))
        vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, border=10)
        vbox.Add(self.unlock_btn, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 10)
        panel.SetSizerAndFit(vbox)

        sizer = wx.GridSizer(1)
        sizer.Add(panel, 1, wx.EXPAND | wx.ALL)
        self.SetSizerAndFit(sizer)

        # The list control might become quite big, thus this line sets a
        # reasonable minimum so the window can be reduced
        self.SetMinSize(wx.Size(480, 240))

    def _back_to_selected(self):
        try:
            self.list_ctrl.Select(self.selected_index)
            self.list_ctrl.Focus(self.selected_index)
        except:
            pass

    def on_item_focused(self, event):
        index = event.GetIndex()
        device: DeviceInfo = self.devices[index]
        if device.disk_space and device.disk_space.mount_point:
            self.selected_index = event.GetIndex()
        elif device.is_locked:
            # Allow focusing locked FileVault volumes so the examiner can
            # highlight them and use "Unlock FileVault volume…" or
            # double-click to trigger the unlock dialog directly.
            self.selected_index = event.GetIndex()
        else:
            self._back_to_selected()

    def on_item_activated(self, event):
        index = event.GetIndex()
        device: DeviceInfo = self.devices[index]
        if device.disk_space and device.disk_space.mount_point:
            PARAMS.source = Path(device.disk_space.mount_point)
            self.parent.source_picker.SetPath(device.disk_space.mount_point)
            self.parent.source_picker.SetFocus()

            # Clean up event listeners and close
            self.list_ctrl.Unbind(
                wx.EVT_LIST_ITEM_FOCUSED, handler=self.on_item_focused
            )
            self.list_ctrl.Unbind(
                wx.EVT_LIST_ITEM_ACTIVATED, handler=self.on_item_activated
            )
            self.Close()
        elif device.is_locked:
            # Double-clicking a locked FileVault volume launches the unlock
            # dialog pre-aimed at that specific volume.
            self._run_unlock_dialog(preferred_identifier=device.identifier)
        else:
            self._back_to_selected()

    def _enumerate_devices(self) -> None:
        """Re-read disk state and rebuild ``self.devices``.

        Called on window creation and again after a successful FileVault
        unlock so the newly-mounted volume appears in the list.
        """
        mount_info: dict[str, DiskSpaceInfo] = {}
        df_lines = subprocess.check_output(
            ["df"], universal_newlines=True
        ).splitlines()
        for line in df_lines:
            if not line.startswith("/dev/disk"):
                continue
            identifier, size, used, free, _, _, _, _, mount_point = re.split(
                r"\s+", line, maxsplit=8
            )
            short_identifier: str = identifier[5:]
            mount_info[short_identifier] = DiskSpaceInfo(
                identifier=identifier,
                size=int(size) * 512,
                used_space=int(used) * 512,
                free_space=int(free) * 512,
                mount_point=mount_point,
            )

        self.devices = []
        diskutil_list = subprocess.check_output(
            ["diskutil", "list"], universal_newlines=True
        )
        stanzas = diskutil_list.strip().split("\n\n")
        for stanza in stanzas:
            self.devices.extend(self._parse_stanza(stanza, mount_info))

        # Overlay FileVault / encryption state from ``diskutil apfs list``.
        # If the lookup fails for any reason, the overlay is silently skipped
        # and the UI degrades to the pre-FileVault behaviour.
        try:
            encrypted_map = {
                v.identifier: v for v in list_encrypted_volumes()
            }
        except Exception:
            encrypted_map = {}

        for device in self.devices:
            enc = encrypted_map.get(device.identifier)
            if enc is not None:
                device.filevault_status = enc.display_status
                device.is_locked = enc.locked

    def _populate_list(self) -> None:
        """Fill the list control from ``self.devices``.

        Clears any existing rows first so this method can be used for the
        initial populate and for post-unlock refreshes.
        """
        self.list_ctrl.DeleteAllItems()
        self.selected_index = -1

        highlight = wx.Colour()
        highlight.SetRGBA(0x18808080)

        locked_colour = wx.Colour(181, 78, 78)  # matches ACCENT_COLOR

        for index, line in enumerate(self.devices):
            mount_point = ""
            size_str = line.size
            used_str = ""
            if line.type in ("APFS Volume", "APFS Snapshot"):
                used_str = size_str
                size_str = "^"
            disk_space = line.disk_space
            if disk_space:
                mount_point = disk_space.mount_point
                used_str = humanize.naturalsize(disk_space.used_space)

            index = self.list_ctrl.InsertItem(
                index, f"{'  ' * line.indent}{line.identifier}"
            )
            self.list_ctrl.SetItem(index, 1, line.type)
            self.list_ctrl.SetItem(index, 2, line.name)
            self.list_ctrl.SetItem(index, 3, size_str)
            self.list_ctrl.SetItem(index, 4, line.status)
            self.list_ctrl.SetItem(index, 5, line.filevault_status)
            self.list_ctrl.SetItem(index, 6, mount_point)
            self.list_ctrl.SetItem(index, 7, used_str)
            self.list_ctrl.SetItemData(index, index)
            if f"{PARAMS.source}" == mount_point:
                self.list_ctrl.Select(index)
                self.list_ctrl.Focus(index)
                self.selected_index = index
            if index % 2:
                self.list_ctrl.SetItemBackgroundColour(index, highlight)
            if line.is_locked:
                # Locked FileVault volumes stand out so the examiner knows
                # an unlock step is required before selection.
                self.list_ctrl.SetItemTextColour(index, locked_colour)
            elif not mount_point:
                self.list_ctrl.SetItemTextColour(index, (128, 128, 128))

        padding = 10
        for col_index in range(len(self._columns)):
            self.list_ctrl.SetColumnWidth(col_index, wx.LIST_AUTOSIZE)
            padded_width = self.list_ctrl.GetColumnWidth(col_index) + padding
            padded_width = max(padded_width, 100)
            if col_index == 2:
                padded_width = min(padded_width, 180)
            self.list_ctrl.SetColumnWidth(col_index, padded_width)

    def _refresh_unlock_button_state(self) -> None:
        """Enable the unlock button only when at least one volume is locked."""
        has_locked = any(d.is_locked for d in self.devices)
        self.unlock_btn.Enable(has_locked)
        if has_locked:
            self.unlock_btn.SetToolTip(
                "Unlock a FileVault-encrypted volume and mount it read-only"
            )
        else:
            self.unlock_btn.SetToolTip("No locked FileVault volumes detected")

    def _run_unlock_dialog(self, preferred_identifier: str = "") -> None:
        """Show the FileVault unlock dialog and process the result.

        If *preferred_identifier* is provided (e.g. from a double-click on a
        specific locked row), that volume is moved to the front of the choice
        list so it is pre-selected in the dialog. The examiner can still pick a
        different volume from the drop-down if needed.

        The unlocked volume is mounted read-only; the device list is then
        re-enumerated so the new mount point appears. The examiner still has to
        explicitly double-click the newly mounted volume to set it as the
        acquisition source, matching the existing UI contract.
        """
        # FileVaultUnlockDialog expects EncryptedVolume objects (which carry
        # .roles, .name, .is_user_data).  self.devices holds DeviceInfo objects
        # that only carry .is_locked as a flag — passing those caused an
        # AttributeError on .roles before the dialog could appear.
        try:
            locked = [v for v in list_encrypted_volumes() if v.locked]
        except Exception:
            locked = []

        if not locked:
            wx.MessageBox(
                "No locked FileVault volumes are currently visible.",
                "Nothing to unlock",
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        if preferred_identifier:
            # Move the preferred volume to the front so it is pre-selected.
            locked = sorted(
                locked, key=lambda v: v.identifier != preferred_identifier
            )

        dialog = FileVaultUnlockDialog(self, locked)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            identifier = dialog.get_identifier()
            password = dialog.get_password()
        finally:
            dialog.Destroy()

        if not identifier or password is None:
            return

        try:
            mount_point = unlock_volume_readonly(identifier, password)
        except UnlockError as exc:
            wx.MessageBox(
                f"{exc}",
                "Unlock failed",
                wx.OK | wx.ICON_ERROR,
            )
            return
        finally:
            # Drop our reference to the password as early as possible. Python
            # strings are immutable, so this does not zero memory, but it
            # does remove the only live reference from our side.
            password = None  # noqa: F841

        wx.MessageBox(
            f"Volume unlocked and mounted READ-ONLY at:\n\n{mount_point}\n\n"
            "Select it from the list to use it as the acquisition source.",
            "Unlock successful",
            wx.OK | wx.ICON_INFORMATION,
        )

        # Refresh the device list so the new mount appears.
        self._enumerate_devices()
        self._populate_list()
        self._refresh_unlock_button_state()

    def on_unlock_filevault(self, event):
        """Button handler: open the unlock dialog with no volume pre-selected."""
        self._run_unlock_dialog()


class FileVaultUnlockDialog(wx.Dialog):
    """Modal dialog: pick a locked volume, enter its FileVault password.

    The password field uses ``wx.TE_PASSWORD`` so characters are masked.
    A read-only notice is displayed prominently; this dialog has no option
    to choose a writable mount because the forensic contract forbids it.
    """

    def __init__(self, parent, locked_volumes: List[EncryptedVolume]):
        super().__init__(
            parent,
            title="Unlock FileVault volume",
            style=wx.DEFAULT_DIALOG_STYLE,
        )
        self._locked = locked_volumes

        panel = wx.Panel(self)

        intro = wx.StaticText(
            panel,
            label=(
                "The selected volume will be unlocked and mounted "
                "READ-ONLY.\nThe password is sent to diskutil via stdin "
                "and is never stored or logged."
            ),
        )

        volume_label = wx.StaticText(panel, label="Locked volume:")
        choices = [self._format_choice(v) for v in self._locked]
        self._choice = wx.Choice(panel, choices=choices)
        if choices:
            # Prefer the Data role volume if present, otherwise the first entry.
            default_index = next(
                (i for i, v in enumerate(self._locked) if v.is_user_data),
                0,
            )
            self._choice.SetSelection(default_index)

        password_label = wx.StaticText(panel, label="FileVault password:")
        self._password_text = wx.TextCtrl(
            panel, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER
        )
        self._password_text.Bind(wx.EVT_TEXT_ENTER, self._on_enter)

        ok_btn = wx.Button(panel, wx.ID_OK, label="Unlock")
        ok_btn.SetDefault()
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="Cancel")

        # Layout
        grid = wx.FlexGridSizer(cols=2, hgap=10, vgap=10)
        grid.AddGrowableCol(1, 1)
        grid.Add(volume_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._choice, 1, wx.EXPAND)
        grid.Add(password_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._password_text, 1, wx.EXPAND)

        btn_box = wx.BoxSizer(wx.HORIZONTAL)
        btn_box.Add(cancel_btn, 0, wx.RIGHT, 10)
        btn_box.Add(ok_btn, 0)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(intro, 0, wx.ALL, 15)
        vbox.Add(grid, 0, wx.EXPAND | wx.ALL, 15)
        vbox.Add(btn_box, 0, wx.ALIGN_RIGHT | wx.ALL, 15)

        panel.SetSizerAndFit(vbox)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(outer)
        self.Center()

        self._password_text.SetFocus()

    @staticmethod
    def _format_choice(v: EncryptedVolume) -> str:
        role = ", ".join(v.roles) if v.roles else "no role"
        name = v.name or "(unnamed)"
        return f"{v.identifier}  —  {name}  [{role}]"

    def _on_enter(self, event):
        # Enter in the password field submits the dialog.
        if self.IsModal():
            self.EndModal(wx.ID_OK)

    def get_identifier(self) -> str:
        index = self._choice.GetSelection()
        if index < 0 or index >= len(self._locked):
            return ""
        return self._locked[index].identifier

    def get_password(self) -> Optional[str]:
        return self._password_text.GetValue()


class InputWindow(wx.Frame):
    method: AcquisitionMethod
    devices_window: Optional["DevicesWindow"] = None
    description_labels: List[str] = []

    def __init__(self):
        super().__init__(
            parent=None,
            title="Fuji - Forensic Unattended Juicy Imaging",
            size=(540, 400),
            style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX),
        )
        self.EnableMaximizeButton(False)
        panel = wx.Panel(self)

        # Components
        title = wx.StaticText(panel, label="Fuji")
        set_font(title, size=36, weight=wx.FONTWEIGHT_EXTRABOLD)
        desc = wx.StaticText(panel, label="Forensic Unattended Juicy Imaging")
        set_font(desc, size=18, weight=wx.FONTWEIGHT_BOLD)

        byline_text = wx.StaticText(panel, label=f"Version {VERSION} by {AUTHOR}")
        byline_link = AdaptiveHyperLinkCtrl(panel, label=HOMEPAGE, URL=HOMEPAGE)
        accent = wx.Colour(*ACCENT_COLOR)
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
        source_label = wx.StaticText(panel, label="Source location:")
        self.source_picker = wx.DirPickerCtrl(panel)
        self.source_picker.SetInitialDirectory("/")
        self.source_picker.SetPath(str(PARAMS.source))
        # Add Devices button
        devices_button = wx.Button(panel, label="List of drives and partitions")
        devices_button.Bind(wx.EVT_BUTTON, self.on_open_devices)
        tmp_label = wx.StaticText(panel, label="Temporary files:")
        self.tmp_picker = wx.DirPickerCtrl(panel)
        self.tmp_picker.SetInitialDirectory("/Volumes")
        if os.path.isdir(PARAMS.tmp):
            self.tmp_picker.SetPath(str(PARAMS.tmp))
        destination_label = wx.StaticText(panel, label="Output destination:")
        self.destination_picker = wx.DirPickerCtrl(panel)
        self.destination_picker.SetInitialDirectory("/Volumes")
        self.destination_picker.Bind(
            wx.EVT_DIRPICKER_CHANGED, self.on_destination_changed
        )
        if os.path.isdir(PARAMS.destination):
            self.destination_picker.SetPath(str(PARAMS.destination))
        method_label = wx.StaticText(panel, label="Acquisition method:")
        self.method_choice = wx.Choice(panel, choices=[m.name for m in METHODS])
        self.method_choice.Bind(wx.EVT_CHOICE, self.on_method_changed)
        self.method_choice.SetSelection(0)

        # Prepare method descriptions
        for method in METHODS:
            description_label = f"<b>{method.name}:</b> {dedent(method.description)}"
            self.description_labels.append(description_label)

        # Sound checkbox
        self.sound_checkbox = wx.CheckBox(
            panel, label="Play loud sound when acquisition is completed"
        )
        self.sound_checkbox.SetValue(PARAMS.sound)

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
        output_info.Add((0, 0))
        output_info.Add(devices_button, 0, wx.EXPAND)
        output_info.Add(destination_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.destination_picker, 1, wx.EXPAND)
        output_info.Add(tmp_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.tmp_picker, 1, wx.EXPAND)
        output_info.Add(method_label, 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        output_info.Add(self.method_choice, 1, wx.EXPAND)
        output_info.AddGrowableCol(1, 1)

        vbox.Add(output_info, 0, wx.EXPAND | wx.ALL, 10)

        self.method_description = wx.StaticText(panel, style=wx.ALIGN_CENTRE_HORIZONTAL)
        vbox.Add(self.method_description, 0, wx.EXPAND | wx.BOTTOM, 10)
        self.describe_method(0)

        vbox.Add((0, 20))
        if not RECOVERY:
            vbox.Add(self.sound_checkbox, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 10)
        else:
            self.sound_checkbox.Hide()

        vbox.Add(continue_btn, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 20)

        vbox.SetMinSize(wx.Size(540, 0))
        panel.SetSizer(vbox)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel)
        self.SetSizerAndFit(sizer)
        self.Center()

        # Bind close and create a menu bar
        menu_bar = wx.MenuBar()
        self.SetMenuBar(menu_bar)
        self.Bind(wx.EVT_CLOSE, self.on_quit)

    def on_open_devices(self, event):
        if self.devices_window is not None:
            self.devices_window.Raise()
            return
        self.devices_window = DevicesWindow(self)
        self.devices_window.Show()
        self.devices_window.CenterOnParent()
        self.devices_window.Bind(wx.EVT_CLOSE, self.on_close_devices)

    def on_close_devices(self, event):
        if self.devices_window:
            self.devices_window.Destroy()
        self.devices_window = None

    def on_destination_changed(self, event):
        destination_location = self.destination_picker.GetPath()
        temp_location = self.tmp_picker.GetPath()
        if not temp_location:
            self.tmp_picker.SetPath(destination_location)

    def on_method_changed(self, event):
        method_index = self.method_choice.GetSelection()
        self.describe_method(method_index)

    def describe_method(self, index: int):
        if index < len(self.description_labels):
            self.method_description.SetLabelMarkup(self.description_labels[index])
        self.Layout()
        self.Fit()

    def _validate_image_name(self, event):
        key = event.GetKeyCode()
        valid_characters = "-_." + string.ascii_letters + string.digits

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

    def on_quit(self, event):
        if PROCESSING_WINDOW.running:
            wx.MessageBox(
                "Cannot quit while an acquisition is in progress.",
                "Acquisition in progress",
                wx.OK | wx.ICON_INFORMATION,
            )
        else:
            app = wx.GetApp()
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
        set_font(title, size=18, weight=wx.FONTWEIGHT_BOLD)

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
        self.Center()
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
            "Source location": PARAMS.source,
            "Output destination": PARAMS.destination,
            "Temporary files": PARAMS.tmp,
            "Acquisition method": INPUT_WINDOW.method.name,
        }
        if not RECOVERY:
            data["Play sound"] = "Yes" if PARAMS.sound else "No"

        max_text_width = 600

        # Insert rows into the grid
        for label, value in data.items():
            label_text = wx.StaticText(self.panel, label=label)
            set_font(label_text, weight=wx.FONTWEIGHT_BOLD)
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
            set_font(label_text, weight=wx.FONTWEIGHT_BOLD)
            if not result.passed:
                label_text.SetForegroundColour(RED_COLOR)
            else:
                label_text.SetForegroundColour(GREEN_COLOR)
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
    running = False

    def __init__(self):
        super().__init__(
            parent=None,
            title="Fuji - Acquisition",
            size=(800, 600),
        )
        self.panel = wx.Panel(self)

        # Components
        self.title = wx.StaticText(self.panel, label="Acquisition in progress")
        set_font(self.title, size=18, weight=wx.FONTWEIGHT_BOLD)
        self.output_text = wx.TextCtrl(
            self.panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.VSCROLL
        )

        # Layout
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(self.title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add((0, 10))
        vbox.Add(self.output_text, 1, wx.EXPAND | wx.ALL, 10)

        self.panel.SetSizer(vbox)
        self.Center()

        # Bind close
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def activate(self):
        self.running = True

        # Reset initial status
        self.title.SetLabel("Acquisition in progress")
        self.title.SetForegroundColour(wx.NullColour)
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
        current_volume = int(volume_properties.get("output volume", -1))
        if current_volume < 0:
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
            self.title.SetForegroundColour(GREEN_COLOR)
        else:
            self.title.SetLabel("Acquisition failed")
            self.title.SetForegroundColour(RED_COLOR)
        self.running = False

    def on_close(self, event):
        if not self.running:
            self.Hide()
            INPUT_WINDOW.Show()


if __name__ == "__main__":
    if RECOVERY:
        # Attempt to migrate to a RAM disk
        attempt_ramdisk()

    # Try to find the serial number
    information = command_to_properties(
        ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
        separator="=",
        strip_chars='"<> ',
    )
    if "IOPlatformSerialNumber" in information:
        serial_number = information["IOPlatformSerialNumber"]
        PARAMS.image_name = f"{serial_number}_Acquisition"

    app = wx.App()
    INPUT_WINDOW = InputWindow()
    OVERVIEW_WINDOW = OverviewWindow()
    PROCESSING_WINDOW = ProcessingWindow()

    INPUT_WINDOW.Show()
    app.MainLoop()
    app.Destroy()

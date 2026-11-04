from typing import List, Optional

import wx

from shared import filevault
from shared.utils import RED_COLOR, set_font


class UnlockDialog(wx.Dialog):
    """Dialog to unlock (FileVault) and mount a macOS data volume."""

    mount_point: str = ""

    def __init__(self, parent, volumes: List[filevault.DataVolume]):
        super().__init__(parent, title="Fuji - Unlock data volume")
        self.volumes = volumes
        self.users: List[filevault.CryptoUser] = []

        panel = wx.Panel(self)

        title = wx.StaticText(panel, label="Unlock data volume")
        set_font(title, size=18, weight=wx.FONTWEIGHT_BOLD)
        intro = wx.StaticText(
            panel,
            label=(
                "The macOS data volume is not mounted. A FileVault volume\n"
                "can be unlocked with a user password or the recovery key."
            ),
        )

        volume_label = wx.StaticText(panel, label="Volume:")
        self.volume_choice = wx.Choice(panel, choices=[v.label() for v in volumes])
        self.volume_choice.Bind(wx.EVT_CHOICE, self.on_volume_changed)

        user_label = wx.StaticText(panel, label="Unlock with:")
        self.user_choice = wx.Choice(panel)

        password_label = wx.StaticText(panel, label="Password / key:")
        self.password_text = wx.TextCtrl(
            panel, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER
        )
        self.password_text.Bind(wx.EVT_TEXT_ENTER, self.on_unlock)

        self.readonly_checkbox = wx.CheckBox(
            panel, label="Mount read-only (recommended for acquisition)"
        )
        self.readonly_checkbox.SetValue(True)

        self.status_text = wx.StaticText(panel, label="")
        self.status_text.SetForegroundColour(RED_COLOR)

        self.unlock_btn = wx.Button(panel, wx.ID_OK, label="Unlock")
        self.unlock_btn.Bind(wx.EVT_BUTTON, self.on_unlock)
        self.unlock_btn.SetDefault()
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="Cancel")

        # Layout
        grid = wx.FlexGridSizer(cols=2, hgap=10, vgap=10)
        grid.Add(volume_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.volume_choice, 1, wx.EXPAND)
        grid.Add(user_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.user_choice, 1, wx.EXPAND)
        grid.Add(password_label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.password_text, 1, wx.EXPAND)
        grid.AddGrowableCol(1, 1)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(cancel_btn, 0, wx.RIGHT, 10)
        buttons.Add(self.unlock_btn, 0)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 20)
        vbox.Add(intro, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 10)
        vbox.Add(grid, 0, wx.EXPAND | wx.ALL, 20)
        vbox.Add(self.readonly_checkbox, 0, wx.LEFT | wx.RIGHT, 20)
        vbox.Add(self.status_text, 0, wx.EXPAND | wx.ALL, 20)
        vbox.Add(buttons, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 20)
        vbox.SetMinSize(wx.Size(520, 0))
        panel.SetSizer(vbox)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(sizer)
        self.CenterOnParent()

        # Preselect the first locked volume, if any
        initial = next((i for i, v in enumerate(volumes) if v.locked), 0)
        self.volume_choice.SetSelection(initial)
        self._load_volume(initial)

    def _selected_volume(self) -> Optional[filevault.DataVolume]:
        index = self.volume_choice.GetSelection()
        if 0 <= index < len(self.volumes):
            return self.volumes[index]
        return None

    def _load_volume(self, index: int):
        volume = self.volumes[index]
        self.user_choice.Clear()
        self.status_text.SetLabel("")

        if volume.locked:
            with wx.BusyCursor():
                self.users = filevault.crypto_users(volume.identifier)
            self.user_choice.Append("Any user (try all)")
            for user in self.users:
                self.user_choice.Append(user.label())
            self.user_choice.SetSelection(0)
            self.unlock_btn.SetLabel("Unlock")
        else:
            self.users = []
            self.user_choice.Append("Not needed (volume is not locked)")
            self.user_choice.SetSelection(0)
            self.unlock_btn.SetLabel("Mount")

        self.user_choice.Enable(volume.locked)
        self.password_text.Enable(volume.locked)
        if volume.locked:
            self.password_text.SetFocus()
        self.Layout()

    def on_volume_changed(self, event):
        self._load_volume(self.volume_choice.GetSelection())

    def on_unlock(self, event):
        volume = self._selected_volume()
        if volume is None:
            return

        read_only = self.readonly_checkbox.GetValue()
        self.status_text.SetLabel("")

        with wx.BusyCursor():
            if volume.locked:
                passphrase = self.password_text.GetValue()
                if not passphrase:
                    self.status_text.SetLabel("Please enter a password or key.")
                    return
                user_index = self.user_choice.GetSelection() - 1
                user_uuid = (
                    self.users[user_index].uuid
                    if 0 <= user_index < len(self.users)
                    else None
                )
                ok, message, point = filevault.unlock(
                    volume, passphrase, user_uuid=user_uuid, read_only=read_only
                )
            else:
                ok, message, point = filevault.mount(volume, read_only=read_only)

        # Never keep the passphrase around longer than needed
        self.password_text.SetValue("")

        if ok:
            self.mount_point = point
            self.EndModal(wx.ID_OK)
        else:
            last_line = message.strip().splitlines()[-1] if message.strip() else ""
            self.status_text.SetLabel(f"Failed: {last_line}")
            self.status_text.Wrap(480)
            self.Fit()
            self.password_text.SetFocus()

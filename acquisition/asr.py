from acquisition.abstract import AcquisitionMethod, Parameters


class AsrMethod(AcquisitionMethod):
    name = "ASR"
    description = """Apple Software Restore logical acquisition.
    This is the recommended option, but it works only for volumes."""

    def execute(self, params: Parameters):
        pass

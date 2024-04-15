from acquisition.abstract import AcquisitionMethod, Parameters


class RsyncMethod(AcquisitionMethod):
    name = "Rsync"
    description = """Files and directories are copied using Rsync.
    This is slower but it can be used on any source directory. Errors are ignored."""

    def execute(self, params: Parameters) -> bool:
        pass

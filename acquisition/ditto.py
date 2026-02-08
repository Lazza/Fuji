from datetime import datetime

from acquisition.abstract import AcquisitionMethod, Parameters, Report


class DittoMethod(AcquisitionMethod):
    name = "Ditto"
    description = """Files and directories are copied using Ditto.
    This is a bit slow but it can be used on any source directory. Errors are ignored."""

    def execute(self, params: Parameters) -> Report:
        # Prepare report
        report = Report(params, self, start_time=datetime.now())
        report.path_details = self._gather_path_info(params.source)
        report.hardware_info = self._gather_hardware_info()

        temporary_image = self._create_temporary_image(report)
        if not temporary_image:
            return report

        print("\nDitto", params.source, "->", temporary_image.mount)
        source_str = f"{params.source}"
        if not source_str.endswith("/"):
            source_str = source_str + "/"
        command = ["ditto", "-X", "-V", source_str, temporary_image.mount]
        status = self._run_status(command)

        # We cannot rely on the exit code, because it will probably contain some
        # errors if a few files cannot be copied.
        if status != 0:
            print(f"Ditto terminated (with status {status})")
        else:
            print("Ditto terminated")

        return self._dmg_and_hash(report)

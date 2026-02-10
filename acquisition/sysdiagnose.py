import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import IO, Optional

from acquisition.abstract import (
    AcquisitionMethod,
    OutputFormat,
    Parameters,
    Report,
    SparseInfo,
)
from shared.environment import RECOVERY


class SysdiagnoseMethod(AcquisitionMethod):
    name = "Sysdiagnose"
    description = """System logs and configuration.
    This only acquires system data and unified logs (converted to SQLite)."""

    def available(self) -> bool:
        return not RECOVERY

    def _create_temporary_image(self, report: Report) -> Optional[SparseInfo]:
        # Temporary image is placed in the temporary directory
        base = report.parameters.tmp
        info = self._create_sparse_image(report, base=base, suffix="-temporary")
        self.temporary_image = info
        return info

    def _write_log_line(self, line: str, cursor: sqlite3.Cursor) -> None:
        data = json.loads(line)

        backtrace_frames = data.get("backtrace", {}).get("frames", [])
        cursor.execute(
            """
            INSERT INTO system_logs (
                timestamp, timezoneName, messageType, eventType, source, formatString, userID,
                activityIdentifier, subsystem, category, threadID, senderImageUUID, imageOffset,
                imageUUID, bootUUID, processImagePath, senderImagePath, machTimestamp, eventMessage,
                processImageUUID, traceID, processID, senderProgramCounter, parentActivityIdentifier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("timestamp"),
                data.get("timezoneName"),
                data.get("messageType"),
                data.get("eventType"),
                data.get("source"),
                data.get("formatString"),
                data.get("userID"),
                data.get("activityIdentifier"),
                data.get("subsystem"),
                data.get("category"),
                data.get("threadID"),
                data.get("senderImageUUID"),
                (
                    str(backtrace_frames[0].get("imageOffset"))
                    if len(backtrace_frames)
                    else None
                ),
                (
                    backtrace_frames[0].get("imageUUID")
                    if len(backtrace_frames)
                    else None
                ),
                data.get("bootUUID"),
                data.get("processImagePath"),
                data.get("senderImagePath"),
                str(data.get("machTimestamp")),
                data.get("eventMessage"),
                data.get("processImageUUID"),
                str(data.get("traceID")),
                str(data.get("processID")),
                str(data.get("senderProgramCounter")),
                data.get("parentActivityIdentifier"),
            ),
        )

    def _convert_logs(
        self, logarchive_path: Path, database_file: Path, buffer_size=1024000
    ) -> int:
        # Create the database
        connection = sqlite3.connect(f"{database_file}")
        cursor = connection.cursor()

        # Set PRAGMA journal_mode to WAL (faster)
        cursor.execute("PRAGMA journal_mode=WAL;")

        # Values marked with "*" are numbers, but we use TEXT because sometimes
        # they are too large to fit in a SQLite integer value
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                timestamp TEXT,
                timezoneName TEXT,
                messageType TEXT,
                eventType TEXT,
                source TEXT,
                formatString TEXT,
                userID INTEGER,
                activityIdentifier INTEGER,
                subsystem TEXT,
                category TEXT,
                threadID INTEGER,
                senderImageUUID TEXT,
                imageOffset TEXT, -- *
                imageUUID TEXT,
                bootUUID TEXT,
                processImagePath TEXT,
                senderImagePath TEXT,
                machTimestamp TEXT, -- *
                eventMessage TEXT,
                processImageUUID TEXT,
                traceID TEXT, -- *
                processID TEXT, -- *
                senderProgramCounter TEXT, -- *
                parentActivityIdentifier INTEGER
            )
            """
        )

        # Run log collect
        command = [
            "log",
            "show",
            "--info",
            "--debug",
            "--signpost",
            "--style",
            "ndjson",
            "--archive",
            f"{logarchive_path}",
        ]
        p = self._create_shell_process(command)
        stdout: IO[str] = p.stdout  # type: ignore

        while True:
            time.sleep(0.1)

            lines = stdout.readlines(buffer_size)
            for line in lines:
                self._write_log_line(line, cursor)
            print(".", end="")
            connection.commit()

            if p.poll() != None:
                lines = stdout.readlines()
                for line in lines:
                    self._write_log_line(line, cursor)
                print(".", end="")
                connection.commit()
                break

        print("\n\nCreating indexes...")
        for column in (
            "timestamp",
            "messageType",
            "eventType",
            "userID",
            "activityIdentifier",
            "processID",
            "parentActivityIdentifier",
        ):
            cursor.execute(f"CREATE INDEX idx_{column} ON system_logs({column});")

        connection.commit()
        connection.close()

        return p.returncode

    def execute(self, params: Parameters) -> Report:
        # Prepare report
        report = Report(params, self, start_time=datetime.now())
        report.path_details = self._gather_path_info(params.source)
        report.hardware_info = self._gather_hardware_info()
        # Write preliminary report
        self._write_report(report)

        temporary_image = self._create_temporary_image(report)
        if not temporary_image:
            return report

        sysdiagnose_destination = Path(temporary_image.mount)
        folder_name = "sysdiagnose_fuji"
        mount_point = self._find_mount_point(params.source)

        print("\nRunning sysdiagnose ->", sysdiagnose_destination)
        command = [
            "sysdiagnose",
            "-f",
            f"{sysdiagnose_destination}",
            "-A",
            f"{folder_name}",
            "-n",
            "-u",
            "-b",
            "-V",
            f"{mount_point}",
        ]
        status = self._run_status(command)

        if not status == 0:
            return report

        folder_path = sysdiagnose_destination / folder_name
        logarchive_path = folder_path / "system_logs.logarchive"
        database_file = sysdiagnose_destination / "system_logs.db"

        print("\nRunning log show on", logarchive_path)
        status = self._convert_logs(logarchive_path, database_file)

        if not status == 0:
            return report

        return self._pack_and_hash(report, format=OutputFormat.ZIP)

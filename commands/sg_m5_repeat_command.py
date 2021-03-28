#!/usr/bin/env python3

import click
from datetime import datetime, timedelta
from time import time, sleep, ctime
import logging
from pathlib import Path
import subprocess
import json

# Today's date and time
current_datetime = datetime.now()

# Prepare filepath to store logs
logs_file_path = Path.cwd().joinpath("logs", "m5-sequence-run")
# Create the folder to store logs
logs_file_path.mkdir(parents=True, exist_ok=True)

# Set the basic config for logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=f'{logs_file_path.as_posix()}/{current_datetime.strftime("%Y%m%d-%H%M%S")}.log',
)


@click.command()
@click.option("-time", "--total_time", help="Total time(in minutes) of the run", default=720, type=int)
@click.option("-sleep", "--sleep_time", help="Sleep time(in minutes) of the run", default=60, type=int)
def run(total_time, sleep_time):
    # Add total_time(minutes) to current time
    total_run_time = current_datetime + timedelta(minutes=total_time)
    sg_m5_repeat_path = Path.cwd().joinpath("examples", "sg_m5_repeat.py")

    print(f"This process is initiated at {ctime(time())}\n")

    logging.info(f"This process is initiated at {ctime(time())}")

    # Count to log how many times a full run executed.
    i = 1

    # Loop till the current time is less than or equal to total run time.
    while datetime.now() <= total_run_time:
        start_run = ctime(time())

        # Logging start of subprocess.
        print(
            "======================================\n"
            f"Run id: {i}\n"
            f"Subprocess started at {start_run}\n"
        )

        logging.info(json.dumps(
            {
                "run_id": i,
                "message": f"Subprocess started at {start_run}"
            }
        ))

        process = subprocess.run(
            ["python", sg_m5_repeat_path.as_posix()],
            capture_output=True,
            shell=True
        )

        """
        Subprocess run will return a returncode.
        0 - Successfully ran the subprocess
        1 - Failed subprocess
        """
        if process.returncode:
            process_error = process.stderr.decode("utf-8")

            print(process_error)
            logging.error(process_error)

            click.Abort()

        # Logging end of subprocess.
        end_run = ctime(time())
        print(
            f"Run id: {i}\n"
            f"Subprocess ended at {end_run}\n"
            "===================================="
        )

        logging.info(json.dumps(
            {
                "run_id": i,
                "message": f"Subprocess ended at {end_run}"
            }
        ))

        # Display the sleep status as a progressbar.
        with click.progressbar(range(sleep_time * 60), label="In Sleep") as progress:
            for _ in progress:
                sleep(1)

        # Increment the count
        i += 1


if __name__ == "__main__":
    run()

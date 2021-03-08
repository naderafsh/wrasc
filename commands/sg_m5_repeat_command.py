#!/usr/bin/env python3


import argparse
from datetime import datetime, timedelta
import time
import logging
from pathlib import Path
import subprocess


def run(data):
    """Repeat the following process for given interval:
    1. Run a python file.
    2. Go to sleep

    Args:
        data ([type]): Commandline arguments.

    Returns:
        None: It doesn't return anything.
    """
    total_time, sleep_time = data.total_time, data.sleep
    current_time = datetime.now()
    total_run_time = current_time + timedelta(hours=total_time)
    sg_m5_repeat_path = Path.cwd().joinpath('examples', 'sg_m5_repeat.py')

    # Prepare filepath to store logs
    logs_file_path = Path.cwd().joinpath(
        'logs',
        'm5-sequence-run'
    )
    # Create the folder to store logs
    logs_file_path.mkdir(parents=True, exist_ok=True)

    # Set the basic config for logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=f'{logs_file_path.as_posix()}/{current_time.strftime("%Y%m%d-%H%M%S")}.log'
    )

    while current_time <= total_run_time:
        '''
        Subprocess run will return a returncode.
        0 - Successfully ran the subprocess
        1 - Failed subprocess
        '''
        process = subprocess.run(
            ['python', sg_m5_repeat_path.as_posix()],
            capture_output=True
        )

        # Check whether the subprocess status
        if process.returncode:
            process_error = process.stderr.decode('utf-8')
            print(process_error)
            logging.error(process_error)
            break

        # Sleep for next iteration. Convert hours to seconds.
        time.sleep(sleep_time * 60 * 60)


def main():
    parser = argparse.ArgumentParser(description="""
                Run the Icing motors test.
                """)

    # Optional options
    parser.add_argument('-time', '--total_time', type=int,
                        help='Provide time in hours to run the process',
                        default='12')
    parser.add_argument('-sleep', '--sleep', type=int,
                        help='Provide time in hours to wait the process',
                        default='1')

    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        print(e)

    # Run the process
    run(args)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3


import argparse
from datetime import datetime, timedelta
from time import time, sleep, ctime
import logging
from pathlib import Path
import subprocess
import json


def convert_to_hrs(input_time):
    """Convert input which is less than 1hour into hours.
    Say we got 0.25 hours as input, first convert into a
    whole number, then divide by 60 to get into hours.

    Args:
        input_time (float): Input time

    Returns:
        float: converted time in hours
    """
    return ((input_time * 100) / 60) if input_time < 1 else input_time


def run(data):
    """Repeat the following process for given interval:
    1. Run a python file.
    2. Go to sleep

    Args:
        data (Namespace): Commandline arguments.

    Returns:
        None: It doesn't return anything.
    """
    total_time, sleep_time = (
        convert_to_hrs(data.total_time),
        convert_to_hrs(data.sleep)
    )
    current_datetime = datetime.now()
    total_run_time = current_datetime + timedelta(hours=total_time)
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
        filename=f'{logs_file_path.as_posix()}/{current_datetime.strftime("%Y%m%d-%H%M%S")}.log'
    )

    print(
        f'This process is initiated at {ctime(time())}\n'
    )

    logging.info(
        f'This process is initiated at {ctime(time())}'
    )

    # Count to log how many times a full run executed.
    i = 1
    while current_datetime <= total_run_time:
        '''
        Subprocess run will return a returncode.
        0 - Successfully ran the subprocess
        1 - Failed subprocess
        '''
        start_run = ctime(time())

        # Logging start of subprocess.
        print(
            '======================================\n'
            f'Run id: {i}\n'
            f'Subprocess started at {start_run}\n'
        )

        logging.info(json.dumps({
            'run_id': i,
            'message': f'Subprocess started at {start_run}'
        }))

        process = subprocess.run(
            ['python', sg_m5_repeat_path.as_posix()],
            capture_output=True,
            shell=True
        )

        # Check whether the subprocess status
        if process.returncode:
            process_error = process.stderr.decode('utf-8')
            print(process_error)
            logging.error(process_error)
            break

        # Logging end of subprocess.
        end_run = ctime(time())
        print(
            f'Run id: {i}\n'
            f'Subprocess ended at {end_run}\n'
            '===================================='
        )

        logging.info(json.dumps({
            'run_id': i,
            'message': f'Subprocess ended at {end_run}'
        }))

        # Sleep for next iteration. Convert hours to seconds.
        sleep(sleep_time * 60 * 60)

        # Increment the count
        i += 1


def main():
    parser = argparse.ArgumentParser(description="""
                Run the Icing motors test.
                """)

    # Optional options
    parser.add_argument('-time', '--total_time', type=float,
                        help='Provide time in hours to run the process. Default to 12hours.',
                        default='12')
    parser.add_argument('-sleep', '--sleep', type=float,
                        help='Provide time in hours to wait the process. Default to 1hour.',
                        default='1')

    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        print(e)

    # Run the process
    run(args)


if __name__ == '__main__':
    main()

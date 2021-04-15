from PBTools.pp_comm import PPComm  # ppmac communication through ssh with gpascii
import PBTools.gather as gather
import time


class gpcom_gather:
    """
    This class manages setting of gathered variables, start and stop gather.
    """

    def __init__(self):
        self.duration = 60  # maximum gather duration is seconds
        self.period = 5  # nb of servo_period between each acquisition

    def start_gather(self, addr, host):
        """
        start gather with addr variables list
        """
        self.addr = addr
        # estimate max duration is seconds

        # gather.gather_and_plot(self.comm.gpascii, self.addr, duration=duration, period=period, gather_file=self.ui.gatherFile.text() if self.ui.gatherFile.text()!='' else 'test.txt')
        # for gather
        # time.sleep(2)  # PVA connect to gather was not alwas succeding
        for comm_try_index in range(10):
            try:
                self.gather_comm = PPComm(host, fast_gather=False)
                print("gather connection succedded")
                servo_period = (
                    self.gather_comm.gpascii.servo_period
                )  # servo_period read from ppmac
                break
            except:
                print("Problem for gather connection")
                print(f"tried gather connection {comm_try_index + 1} times")
                return

        print("Servo period is %g (%g KHz)", servo_period, 1.0 / (servo_period * 1000))
        print(f"{time.time()} start gather()")

        total_samples = gather.setup_gather(
            self.gather_comm.gpascii,
            self.addr,
            duration=self.duration,
            period=self.period,
        )
        gather.gather_start(self.gather_comm.gpascii)

    def stop_gather(self):
        """
        instant stop of gather and return gathered data
        """
        data = gather.gather_stop(self.gather_comm.gpascii, self.addr)
        print(f"{time.time()} end gather")
        return data

    def write_gather_to_file(self, addr, data, file_name="test.gat"):
        """
        Write gathered data fo file
        """
        print(f"{time.time()} start write to file")
        gather.gather_data_to_file(file_name, addr, data)
        print(f"{time.time()} end writing to file")

    def plot_gather(self, addr, data):
        """
        Plot data with module mathplotlib
        """
        print(f"{time.time()} plot")
        gather.plot(addr, data)
        print(f"{time.time()} end plot")


class wrasc_ppcom(PPComm):
    def init(self, **kwargs):
        super().__init__(**kwargs)

    def validate_cmd(self, cmd):

        if cmd:
            return True, cmd
        else:
            return False, None

    def send_receive_raw(self, cmds: str = None, response_count=None, timeout=5):

        """
        this is a blocking receive,
        it wait for expected responses in rcv_buffer or timed out,
        then flushes out the in and out buffers and returns the 
        responses found. 
        Assuming responses are terminated by \006 \n as it is te case for 
        current version of ppmac

        (Zero timeout is changed to 30000 seconds for compatibility)

        No processing is done on the received data

        response_count = None : (ALL!) wait for number of responses to match the number 
        of commands (lines in cmds)
        response_count = 0 : don't wait. just return alk there is.
        response_count = n : wait for the lesser of n and than number of commands    
        """

        assert isinstance(self, PPComm)

        cmd_validated, cmds = self.validate_cmd(cmds)
        # TODO is cmds valid?
        if not cmd_validated:
            return [], False, "invalid command(s)"

        cmd_count = cmds.count("\n") + cmds.count("\r") + 1

        # send all commands
        for cmd in cmds.splitlines():
            self.gpascii.send_line(cmd)

        # if an n_responses of 'all' is supplied, then calcultate what it means
        if not response_count:
            # caller indicated ALL responses
            n_responses = cmd_count
        else:
            # caller indicated not to wait for responses.
            n_responses = max(response_count, cmd_count)

        # make sure it all gets sent before waiting for replies
        # ppmac -- self.stdin.flush()

        st_time = time.time()

        if timeout == 0:
            timeout = 30000

        timeout_time = time.time() + timeout

        # pull out data from the rcv_buffer as many responses there are 0x06

        ack_n = 0
        rcv_buffer = ""
        while ack_n < n_responses:

            rcv_buffer += next(self.gpascii.read_timeout())
            ack_pos = rcv_buffer.rfind("\006")
            ack_n = rcv_buffer.count("\006")
            if timeout != 0:
                if time.time() > timeout_time:
                    return []
            if ack_n < 1:
                time.sleep(0.0001)

        ack_pos = rcv_buffer.rfind("\006")

        response = rcv_buffer[0:ack_pos]

        ack_pos = ack_pos + 1  # increment past "\x06"

        if ack_pos > len(rcv_buffer):
            ack_pos = len(rcv_buffer)

        # \x06 is trailed by a \n is this a gpascii artifact?
        rcv_buffer = rcv_buffer[ack_pos + 1 :]

        cmd_val = cmd  #  self.queue_in.popleft()[:]
        # cmd_response = [self.queue_in[0], response]
        cmd_response = [cmd_val, response]

        # returns errors string if problem
        error_returned, error_msg = "", ""
        wasSuccessful = not error_returned

        # DONE: YES need success/fail return added
        return cmd_response, wasSuccessful, error_msg  # [cmd, response] pair


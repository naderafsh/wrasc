""" low-level ppmac class
for talking to the powerbrick directly via python"""

# from typing import List
import sys
import time
import select
from collections import deque
import paramiko  # ssh library
from ppmac.util import ClosingContextManager


class GpasciiClient(ClosingContextManager):
    """ Communicates with the powerPMAC Delta Tau via ssh."""

    # things that are in return from gpascii indicating something wrong
    error_list = ["MOTOR NOT ACTIVE", "ILLEGAL CMD",
                  "ILLEGAL PARAMETER", "NOT READY TO RUN",
                  "PROGRAM RUNNING", "OUT OF RANGE NUMBER"]

    def __init__(self, host, debug=False):
        # TODO: check valid host or host lookup
        self.host = host.strip(" ")
        self.debug = debug

        # gpascii_ack = "\x06\r\n"
        # gpascii_inp = 'Input\r\n'
        # ssh_prompt = "ppmac# "
        self.timeout = 5
        self.paramiko_session = None  # paramiko connection for send/receive.
        # gpascii_session = None
        self.connected = False
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.debug = debug

        self.rcv_buffer = ""

        # list of commands for which we are waiting for a reply.
        # The first element in the list is the next expected reply
        self.queue_in = deque([])

        # receive throughput stats
        self.time_sum = 0  # [ms]
        self.num_received = 0
        self.ave_time_per_cmd = 0  # [ms/cmd]

        # send throughput stats
        self.stime_sum = 0  # [ms]
        self.snum_received = 0
        self.save_time_per_cmd = 0  # [ms/cmd]

    def connect(self, username='root', password='deltatau'):
        """ssh to PowerBrick and run gpascii.
        returns True (success) if connected
        :param str username: default=root
        :raises SSHException:
            if unable to connect
        """
        success = False

        if self.host is None:
            return False

        self.d_print(f"Trying to connect to ppmac at {self.host} ..")
        try:
            self.paramiko_session = paramiko.SSHClient()
            self.paramiko_session.set_missing_host_key_policy(
                paramiko.AutoAddPolicy())
            self.paramiko_session.connect(self.host,
                                          username=username,
                                          password=password)
            # see also paramiko timeout=self.TIMEOUT)
            self.d_print("Success, connected.")
            success = True
        except paramiko.AuthenticationException:
            self.d_print("Authentication failed when connecting"
                         f"to {self.host}")
            sys.exit(1)

        # 8192 is paramiko default bufsize
        self.stdin, self.stdout, self.stderr = \
            self.paramiko_session.exec_command("gpascii -2", bufsize=8192)

        self.d_print("sent gpascii.")

        rcv_buffer = ""  # clear buffer for new connection.
        loop_time = time.time()
        # wait for the "Input\n" at the end of line when gpascii starts
        while rcv_buffer.find("Input\n") == -1:
            buffer_temp = self.nb_read()
            rcv_buffer += buffer_temp
            if time.time() - loop_time > 5: 
                raise TimeoutError(f"waiting for gpascii on ppmac at {self.host}")
        self.d_print(f"received: \"{rcv_buffer}\"")

        self.connected = True
        # TODO: check ppmac firmware version/CID

        return success

    def send_list(self, cmd_list):
        """ send a list of commands
        """
        for cmd in cmd_list:
            self.send(cmd)

    def send(self, command):
        """send command to brick.
        this is a non-blocking single command send,
        it data into the channel buffer and returns
        the expected response is queued, and must be retrieved FIFO style
        Because this is buffered, data may not actually be sent.
        If you want to make sure, you have to send flush() afte rthis.
        """
        # TODO: check blacklist,
        # TODO: prevent sending duplicate commands that might cause sync error
        # TODO: what if the connection was closed,
        #   or brick has crashed/turned off?
        # ie if receive back "ppmac#" then gpascii has closed..
        st_time = time.time()
        self.d_print(f"sending: {command}")
        # the following write is slow (~1ms) if not using buffered comms
        self.stdin.write(command + "\r\n")
        self.stime_sum += (time.time() - st_time)*1000
        self.snum_received += 1
        self.save_time_per_cmd = self.stime_sum/self.snum_received

        self.queue_in.append(command[:])

    # TODO: timeout that applies to individual receive.
    # TODO: version for just one token?
    def receive_dict(self, num_replies='all', wait=False, timeout=0):
        """ receive a list of responses, typically used with send_list.
        this is a non-blocking receive,
        and will return all available replies in a list
        if wait=True it will return at least one
        if num_replies is a number, it assumes wait=True, and it will wait until
        all received
        if num_replies=='all' and wait=false, it will get all available and
        return immediately.
        Note that because this returns a dict, any duplicate cmd key will be
        overwritten by the last value.
        """
        response_dict = {}
        if num_replies == 'all':
            response = self.receive(wait=wait, timeout=timeout)
            while response != []:
                response_dict[response[0]] = response[1]
                response = self.receive(wait=wait, timeout=timeout)
        elif isinstance(num_replies, int) and num_replies > 0:
            for _ in range(num_replies):
                response = self.receive(wait=True, timeout=timeout)
                # TODO: if this times out and returns empty,
                #   should it go to an error?
                response_dict[response[0]] = response[1]

        return response_dict

    # TODO: version for just one token?
    def receive(self, wait=False, timeout=0):
        """this is a non-blocking receive,
        it will fetch whatever is available from ssh into rcv_buffer,
        but only return one value terminated by \006
        timeout is not valid unless wait=True, a timeout=0 will wait forever"""

        st_time = time.time()

        if timeout != 0:
            timeout_time = time.time() + timeout

        # pull out data from the rcv_buffer until the next 0x06
        if wait:
            ack_pos = -1
            while ack_pos == -1:
                self.rcv_buffer += self.nb_read()
                ack_pos = self.rcv_buffer.find("\006")
                if timeout != 0:
                    if time.time() > timeout_time:
                        return []
                if ack_pos == -1:
                    time.sleep(0.0001)
        else:
            self.rcv_buffer += self.nb_read()
            ack_pos = self.rcv_buffer.find("\006")
            if ack_pos == -1:
                return []

        response = self.rcv_buffer[0:ack_pos]
        ack_pos = ack_pos + 1  # increment past "\x06"

        if ack_pos >= len(self.rcv_buffer):
            ack_pos = len(self.rcv_buffer)

        self.rcv_buffer = self.rcv_buffer[ack_pos + 1:]

        response = response.replace("\r", "")
        response = response.replace("\n", "")

        # as some responses do not include the command, we check and return the
        # variable that should match to this response

        # only going to check against the intended  command if there is an
        # equals sign, sometimes there is no command in the reply
        if response.find("=") != -1:
            cmd_val = self.queue_in.popleft()[:]
            # cmd_response = [self.queue_in[0], response.split("=")[1]]
            # intended_cmd = self.queue_in[0].lower()
            cmd_response = [cmd_val, response.split("=")[1]]
            intended_cmd = cmd_val.lower()
            cmd_received = response.split("=")[0].lower()
            # assert cmd_received == intended_cmd, \
            #     f"sync error, {response.split('=')[0]} != {self.queue_in[0]}"
            assert cmd_received == intended_cmd, \
                f"sync error, {response.split('=')[0]} != {cmd_val}"
            # if it gets out of sync then it should stop, TODO flush/reconnect
        else:
            cmd_val = self.queue_in.popleft()[:]
            # cmd_response = [self.queue_in[0], response]
            cmd_response = [cmd_val, response]

        # del self.queue_in[0]
        # self.queue_in.popleft()

        error = self.stderr_error()  # returns errors string if problem
        if error is not False:
            success = 0

        self.time_sum += (time.time() - st_time)*1000
        self.num_received += 1
        self.ave_time_per_cmd = self.time_sum/self.num_received

        # TODO: need success/fail return?
        return cmd_response  # [cmd, response] pair

    def validate_cmd(self, cmd):

        if cmd:
            return True, cmd
        else:
            return False, None

    def send_receive_raw(self, cmds=None, response_count=None, timeout=5):

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

        cmd_validated, cmds = self.validate_cmd(cmds)
        # TODO is cmd valid?
        if not cmd_validated:
            return []

        cmd_count = cmds.count("\n") + cmds.count("\r") + 1

        self.send(cmds)

        # if an n_responses of 'all' is supplied, then calcultate what it means
        if not response_count:
            # caller indicated ALL responses
            n_responses = cmd_count
        else:
            # caller indicated not to wait for responses.
            n_responses = max(response_count, cmd_count) 

        # make sure it all gets sent before waiting for replies
        self.stdin.flush()

        st_time = time.time()

        if timeout == 0:
            timeout = 30000

        timeout_time = time.time() + timeout

        # pull out data from the rcv_buffer as many responses there are 0x06

        ack_n = 0
        while ack_n < n_responses:
            self.rcv_buffer += self.nb_read()
            ack_pos = self.rcv_buffer.rfind("\006")
            ack_n = self.rcv_buffer.count("\006")
            if timeout != 0:
                if time.time() > timeout_time:
                    return []
            if ack_n < 1:
                time.sleep(0.0001)

        ack_pos = self.rcv_buffer.rfind("\006")

        response = self.rcv_buffer[0:ack_pos]

        ack_pos = ack_pos + 1  # increment past "\x06"

        if ack_pos > len(self.rcv_buffer):
            ack_pos = len(self.rcv_buffer)

        # \x06 is trailed by a \n is this a gpascii artifact? 
        self.rcv_buffer = self.rcv_buffer[ack_pos + 1:]

        cmd_val = self.queue_in.popleft()[:]
        # cmd_response = [self.queue_in[0], response]
        cmd_response = [cmd_val, response]

        # returns errors string if problem
        error_returned, error_msg = self.stderr_error()  
        wasSuccessful = (not error_returned)

        self.time_sum += (time.time() - st_time)*1000
        self.num_received += 1
        self.ave_time_per_cmd = self.time_sum/self.num_received

        # DONE: YES need success/fail return added
        return cmd_response, wasSuccessful, error_msg  # [cmd, response] pair

    def clear_stats(self):
        """ clear the received statistics"""
        self.time_sum = 0
        self.num_received = 0
        self.ave_time_per_cmd = 0

    def stderr_error(self):
        """note that errors come back on stderr,
        check for indications of errors in commands"""
        # TODO add a return status for this
        stderr_buffer = self.nb_read_stderr()
        if stderr_buffer == "":
            return False, ''
        for bad_response in self.error_list:
            # I removed this assert because it should be able to handle the
            # fault because \006 is received even if there is an error, but
            # still want to know it happened.
            # assert bad_response not in return_buffer
            if bad_response in stderr_buffer:
                print("error in response from brick")
                print(f"{bad_response} in {stderr_buffer}")
                return True, bad_response

        return True, stderr_buffer

    def len_queue(self):
        """get length of the reply queue we are waiting for"""
        return len(self.queue_in)

    def nb_read(self):
        """non-blocking read
        returns whatever in stdout, up to 1024 bytes"""
        buffer = ""
        # Only get data if there is data to read in the channel
        if self.stdout.channel.recv_ready():
            rl, wl, xl = select.select([self.stdout.channel], [], [], 0.0)
            if len(rl) > 0:
                buffer = self.stdout.channel.recv(1024).decode("utf-8")

        return buffer

    def nb_read_stderr(self):
        """ non-blocking read of stderr"""
        buffer = ""
        # Only get data if there is data to read in the channel
        if self.stderr.channel.recv_stderr_ready():
            buffer = self.stderr.channel.recv_stderr(1024).decode("utf-8")
            self.d_print(f"received(stderr): {buffer}")
        return buffer

    def send_receive_list(self, cmd_list, timeout=0):
        """send and receive a list with wait,
        you can't use this if there is a pending receive."""
        self.send_list(cmd_list)

        # make sure it all gets sent before waiting for replies
        self.stdin.flush()

        num_replies = len(cmd_list)
        response_list = self.receive_dict(num_replies=num_replies,
                                          wait=True, timeout=timeout)
        return response_list

    def send_receive(self, cmd, timeout=0):
        """send and receive a single variable with wait,
        you can't use this if there is a pending receive."""
        self.send(cmd)

        # make sure it all gets sent before waiting for replies
        self.stdin.flush()

        response = self.receive(wait=True, timeout=timeout)
        # this used to return success
        # now its #[cmd, response] pair
        return response

    def flush(self):
        """because buffering is used to speed performance,
        you want to send flush to make sure it is sent instead of sitting 
        in the buffer
        buffering only affects write"""
        self.stdin.flush()

    def start_motion_program(self, cs_num, motion_program):
        """ this starts a motion program"""
        self.d_print(f"executing {motion_program}..")
        __cmd, reply = self.send_receive(f"&{cs_num} start {motion_program}")
        time.sleep(0.01)

        return reply

    def close(self):
        """close the gpascii and ssh channel"""
        # print("disconnecting gpascii..")

        # send CTRL-C to close gpascii
        # self.stdin.write('\x03')
        # time.sleep(0.1)

        # try to wait for it to actually finish;
        # start_time = time.time()
        # this waits forever for it to finish, and returns exit status.
        # exit_status = self.stdout.channel.recv_exit_status() 
        # exit_ready = self.stdout.channel.exit_status_ready()
        # w hile not exit_ready and (time.time() - start_time) < 10:
        #    exit_ready = self.stdout.channel.exit_status_ready()

        # I checked and these close methods seem not to leave any
        # open connections to the brick or processes running on the brick

        self.stdout.close()
        self.stdin.close()
        self.stderr.close()

        # if self.gpascii_paramiko_session is not None:
        self.paramiko_session.close()
        #   self.gpascii_paramiko_session = None
        self.d_print("force disconnected gpascii.")
        # else:
        #    print("CTRL-C disconnected gpascii.")

        self.connected = False

    def d_print(self, msg):
        """ use to print a debug message"""
        if self.debug:
            print(msg)

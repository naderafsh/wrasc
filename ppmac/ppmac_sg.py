# $File: //ASP/Personal/baldwinb/SR03BM01MCIOC23/py/ppmac.py $
# $Revision: #1 $
# $DateTime: 2019/07/31 10:28:38 $
# Last checked in by: $Author: baldwinb $
#
# $File: //ASP/Personal/baldwinb/SR03BM01MCIOC23/py/ppmac.py $
# $Revision: #1 $
# $DateTime: 2019/07/31 10:28:38 $
# Last checked in by: $Author: baldwinb $
#
# ppmac class
# for talking to the powerbrick via python
# somewhat based on gpasciicommander gpasciicommunicator from psi
#
# uses asyncio queues to send/receive to the brick and allow immediate return of current status pvs

from typing import List
import paramiko  # ssh library
import sys, time
import queue, threading
import asyncio  # for commands to interface to caproto


# multi-threaded version of ppmac_tool
#
#   caproto IOC <> helper_thread <> ppmac_send_receive_thread
#
# - the first read command from caproto adds the command to the status dictionary,
#     and has a priority(fast/slow), readback status ok/failed, and somewhere for the readback value to be saved
# -the helper thread sends one command at a time, and saves response, and response status to the command dictionary
# -each time a queue read is added to the queue
# - the helper thread will poll all the status pvs at a fixed rate
# -
# -class maintains a list of readback commands, a caproto IOC read request will return immediately
# -asyncio access
# - these functions know nothing of pv's, in the hope that this can also be used for epics independent qt gui
class PpmacToolMt:
    """ Communicates with the powerPMAC Delta Tau gpascii program
       via ssh.
       Connect opens a connection to ppmac and starts thread queues to send/receive
       registers.
       Interface with this via  """

    host = None
    gpascii_ack = "\x06\r\n"
    gpascii_inp = "Input\r\n"
    ssh_prompt = "ppmac# "
    timeout = 5
    ppmac_ssh = None  # paramiko connection for send/receive.
    ppmac_ssh_paramiko = None  # paramiko connection for send/receive.
    connected = False
    queue_to_ppmac = None  # queue for sending to ppmac (thread started in CONN_STS)
    queue_from_ppmac = (
        None  #  queue for receiving from ppmac (thread started in CONN_STS)
    )
    thread = None

    # status_cmd_list = [] # this is used in the thread, and is not thread safe, don't write to it during run time

    # things that are in return from gpascii indicating something wrong
    gpascii_error_list = [
        "MOTOR NOT ACTIVE",
        "ILLEGAL CMD",
        "ILLEGAL PARAMETER",
        "NOT READY TO RUN",
        "PROGRAM RUNNING",
        "OUT OF RANGE NUMBER",
    ]

    def __init__(self, host=None):
        self.host = host

    def connect(self, username="root", password="deltatau", prompt="ppmac# "):
        "ssh to PowerBrick and run gpascii"
        success = 0

        if self.host is not None:
            i = 1

            while True:

                print("Trying to connect to ppmac at {:}..".format(self.host))
                try:
                    self.ppmac_ssh_paramiko = paramiko.SSHClient()
                    self.ppmac_ssh_paramiko.set_missing_host_key_policy(
                        paramiko.AutoAddPolicy()
                    )
                    self.ppmac_ssh_paramiko.connect(
                        self.host, username=username, password=password
                    )  # , timeout=self.TIMEOUT)
                    print("Success, connected.")
                    success = 1
                    break
                except paramiko.AuthenticationException:
                    print(
                        "Authentication failed when connecting to {:}".format(self.host)
                    )
                    sys.exit(1)
                except Exception as e:
                    print("Exception was: {:}".format(e))
                    print(
                        "Could not SSH to {:}, waiting for it to start".format(
                            self.host
                        )
                    )
                    i += 1
                    time.sleep(2)

                # If we could not connect within 60s time limit
                if i == 30:
                    print("Could not connect to {:}. Giving up".format(self.host))
                    sys.exit(1)

            # Create a raw shell
            self.ppmac_ssh = self.ppmac_ssh_paramiko.invoke_shell()

            # wait for the "ppmac#"?
            buffer = ""
            for i in range(10):
                if self.ppmac_ssh.recv_ready():
                    buffer += self.ppmac_ssh.recv(4096).decode()
                # print(buffer)
                if self.ssh_prompt in buffer:
                    success = 1
                    print("now at linux shell.")
                    break
                time.sleep(1)

            if success != 1:
                print("linux shell failed to start.")

            success = 0

            self.ppmac_ssh.send("gpascii -2\n")

            print("sent gpascii.")

            # wait for the "INPUT" end of line
            buffer = ""
            for i in range(10):
                if self.ppmac_ssh.recv_ready():
                    buffer += self.ppmac_ssh.recv(4096).decode()
                # print(buffer)
                if self.gpascii_inp in buffer:
                    success = 1
                    self.connected = True
                    print("gpascii started ok.")
                    break
                time.sleep(1)

            if success != 1:
                print("gpascii failed to start.")

        # startup a new thread and make in/out queues
        self.queue_to_ppmac = queue.Queue()  # async_lib.ThreadsafeQueue()
        self.queue_from_ppmac = queue.Queue()  # async_lib.ThreadsafeQueue()
        self.thread = threading.Thread(target=self.ppmac_helper_thread, daemon=True)
        self.thread.start()

        return success

    # sends one command to the ppmac via the other thread
    # calls from caproto are via asyncio
    def async_write(self, send_cmd, cmd_type):
        # add to the list of things to be sent by writing it to the queue
        self.queue_to_ppmac.put({"RW": "W", "CMD": send_cmd, "CMD_TYPE": cmd_type})

    def async_add_status_cmd(self, send_cmd):
        # add to the list of things to be sent by writing it to the queue
        self.queue_to_ppmac.put({"RW": "R", "CMD": send_cmd})

    # returns the latest status_dict of all values in the status list
    # calls from caproto are via asyncio
    async def get_status(self):
        # status_dict = await self.queue_from_ppmac.get() # await??? blocking without await (?).
        # self.queue_from_ppmac.task_done() # remove queue entry
        status_dict = {}
        while True:
            try:
                status_dict = self.queue_from_ppmac.get_nowait()
            except queue.Empty:
                # empty queue is ok =  #exception Queue.Empty
                # keep waiting
                pass
            if len(status_dict) != 0:
                self.queue_from_ppmac.task_done()  # remove from queue
                break
            else:
                await asyncio.sleep(0.01)  # relinquish control for a while

        return status_dict

    # this is run in a thread from CONN_STS startup to maintain communication with the brick
    # this thread runs concurrently with the main thread.
    # data is passed in on the queue_to_ppmac such as which register to read or write
    # data is returned on the queue_from_ppmc such as
    def ppmac_helper_thread(self):
        status_cmd_list = (
            []
        )  # only local, class level self.get_status_list doesn't work and is not thread safe.

        while True:
            if self.connected == 1:

                status_dict = {}  # this captures the output values
                if len(status_cmd_list) != 0:
                    success, received = self.get_status_list(
                        status_cmd_list, 0.1
                    )  # 0.3)
                    # larger timeout for long smargon status.

                    # TODO: check number received back equals number of PVs in status_dict
                    if success == 1:
                        i = 0
                        for cmd_name in status_cmd_list:
                            status_dict[cmd_name] = received[i]
                            i += 1
                    else:
                        print("failed send/receive, received: " + str(received))
                        print("connection status: {self.connected}")
                        print(" check your yaml")

                    # return status_dict
                    self.queue_from_ppmac.put(status_dict)

                # put anything in the send queue to the brick
                # if self.queue_to_ppmac.empty() is False:
                cmd_to_send = None
                cmd_type = None
                try:
                    # queue_entry = ["RW":"R", "CMD":"cmd"] < will add to status list
                    # queue_entry = ["RW":"W","CMD":"cmd"] < will immediately send the command and ignore result

                    queue_entry = self.queue_to_ppmac.get_nowait()
                    if queue_entry["RW"] == "R":
                        # check not already in the list
                        if queue_entry["CMD"] not in status_cmd_list:
                            status_cmd_list.append(queue_entry["CMD"])
                            self.queue_to_ppmac.task_done()  # remove from queue
                    elif queue_entry["RW"] == "W":
                        cmd_to_send = queue_entry["CMD"]
                        cmd_type = queue_entry["CMD_TYPE"]
                except queue.Empty:
                    # empty queue is ok =  #exception Queue.Empty
                    pass

                if cmd_to_send is not None:
                    print(f"cmd out requested. sending: {cmd_to_send}")
                    # TODO: update timeout
                    # TODO: add success status of write cmds to return status queue(?)
                    # TODO: add individual success return for status reads
                    if cmd_type != "None":
                        success = self.send_online(
                            cmd_to_send, 0.01
                        )  # just using this to send everything, expecting one reply.

                    # if cmd_type == "online":
                    #    success = self.send_online(cmd_to_send, 0.01)  # normally replies with what you send
                    # if cmd_type == "online_no_reply":
                    #    success = self.send_online(cmd_to_send, 0.01)  # normally time out waiting for a reply
                    # elif cmd_type == "register":
                    #    success, received = self.send_receive(cmd_to_send, 0.01)  # normally replies with what you send
                    self.queue_to_ppmac.task_done()  # remove from queue

            else:
                print("disconnected")
                time.sleep(1)
                # threading.Thread.sleep(100) # sleep for 100ms
                # self.thread.sleep(100) # sleep for 100ms
                # TODO: reconnect?

    # TODO: combine/rationalise the get_status_list, send_online, and send_receive functions
    #  together as they do similar things
    # lines list:
    # example good multiple return values:
    # send: "#1p #2p Motor[1].JogSpeed"
    # receive:
    # 0
    # -11.49609375
    # Motor[1].JogSpeed=2001
    # example bad multiple return values:
    # send: "#1p #2p gooble"
    # receive:
    # stdin:4:10: error #20: ILLEGAL CMD: #1p #2p gooble
    # 0
    # -11.49609375
    # No data to display
    # this will strip any characters that may cause a problem for one line multiple values,
    # but will not detect for example if you are trying to send "cpx &1 X 500" for example which is single line
    # motion program - that should be done using single line put function.
    def get_status_list(self, cmd_list: List[str], timeout):
        success = 0
        return_lines = [""]
        if self.connected:
            # make the string to send since this should be done in "send" function,
            # and strip out any characters , and gives strange return vals.
            send_string = ""
            number_sent = 0
            for cmd in cmd_list:
                temp_string = cmd.strip("= \r\n")
                if len(temp_string) != 0:
                    send_string += temp_string + " "
                    number_sent += 1
            # print("sending: "+send_string+"\n") #for debugging
            self.ppmac_ssh.send(send_string + "\n")

            # now we expect to get back the same number.
            buffer = ""

            for i in range(100):
                if self.ppmac_ssh.recv_ready():
                    buffer += self.ppmac_ssh.recv(
                        8192
                    ).decode()  # 4096).decode() # seems to get partial reply back if use small value here..
                    return_lines = buffer.split("\r\n")
                # print(buffer)

                # often there are  additional "\\x06" characters
                # or empty lines that should be stripped out.
                # especially with adding "\r\n" to the command
                j = 0
                while j < len(return_lines):
                    if "\x06" in return_lines[j] or return_lines[j] == "":
                        del return_lines[j]
                    else:
                        j += 1

                if (
                    len(return_lines) > number_sent and "@" not in buffer
                ):  # what happens with other lengths/lines?
                    success = 1
                    break
                # elif len(return_lines) >= number_sent and "@" not in buffer:  # what happens with other lengths/lines?
                #    success = 1
                #    break

                time.sleep(timeout)

            # print("received: " + str(return_lines) + "\n") #for debugging

            # strip out any "=" and what comes before it
            # ie "#1p" returns just the value, but another example is Motor[1].JogSpeed=2001
            for i in range(len(return_lines)):
                if "=" in return_lines[i]:
                    return_lines[i] = return_lines[i].split("=")[1]

            if "@" in buffer:
                # we are probably now at the linux prompt
                success = 0
                self.connected = False

            # check for response like "stdin:0:7: error #20: ILLEGAL CMD: #1p #1j #2p #2j "
            for bad_response in self.gpascii_error_list:
                if bad_response in buffer:
                    print("error in response from brick")
                    print(bad_response + "in " + buffer)
                    success = 0

            # TODO: recover from/detect loss of connection or poor connection? Eg error on timeout?

            # clear anything else left in the buffer?
            # and what to do if it is longer or shorter than it is supposed to be?

            # remove lines of invalid response? or status per line?
            # example of invalid response;
            # gooble
            # stdin:2:2: error #20: ILLEGAL CMD: gooble
            # No data to display

            return (
                success,
                return_lines[1:],
            )  # we throw away the first line as it is what we sent to it
        return success, [""]

    #

    # use this function for sending  "online commands", has success return and no value.
    # eg:
    #   "#2j=1" or "Coord[1].Tm=-1" , the brick returns with what you sent it for success, or error for fail
    #   "cpx",  the brick has no reply for success, or error for fail (sending this command will mean that timeout
    #     is needed to detect a reply)
    def send_online(self, command, timeout):
        # what if the connection was closed, or brick has crashed/turned off?
        # ie if receive back "ppmac#" then gpascii has closed..
        success = 0
        return_lines = [""]
        if self.connected:
            # if self.ppmac_ssh !=None:
            # print(f"sending: {command}")  # for debug
            self.ppmac_ssh.send(command + "\n")

            buffer = ""

            for i in range(10):  # try 10 times (?)
                if self.ppmac_ssh.recv_ready():
                    buffer += self.ppmac_ssh.recv(4096).decode()
                    return_lines = buffer.split("\r\n")
                # print(buffer)

                # often there are  additional "\\x06" characters
                # or empty lines that should be stripped out.
                # especially with adding "\r\n" to the command
                j = 0
                while j < len(return_lines):
                    if "\x06" in return_lines[j] or return_lines[j] == "":
                        del return_lines[j]
                    else:
                        j += 1

                if (
                    len(return_lines) >= 1 and "@" not in buffer
                ):  # what happens with other lengths/lines?
                    success = 1
                    break

                time.sleep(timeout)  # time.sleep(1)

            if "@" in buffer:
                success = 0
                # we are probably now at the linux prompt
                self.connected = False

            for bad_response in self.gpascii_error_list:
                if bad_response in buffer:
                    print("error in response from brick")
                    print(f"sent: {command}")  # for debug
                    print(f"received '{bad_response}' in buffer:\n \"{buffer}\"")
                    success = 0

            # clear anything else left in the buffer?

            # example of invalid response;
            # gooble
            # stdin:2:2: error #20: ILLEGAL CMD: gooble
            # No data to display

            # more examples;
            # good:
            # motor[2].JogSpeed
            # Motor[2].JogSpeed = 10
            # bad:
            # motor[2].JogSpee
            # stdin: 12:1: error  # 21: ILLEGAL PARAMETER: motor[2].JogSpee

            # print(f"received:\n {buffer}\n")
        return success

    # basic send single string/command and wait and return single string/ reply
    # this doesn't check if you have tried to include multiple values using whitespace or "=" signs.. so don't
    def send_receive(self, command, timeout):
        # what if the connection was closed, or brick has crashed/turned off?
        # ie if receive back "ppmac#" then gpascii has closed..
        success = 0
        return_lines = [""]
        if self.connected:
            # if self.ppmac_ssh !=None:
            print(f"sending: {command}")  # for debug
            self.ppmac_ssh.send(command + "\n")

            buffer = ""

            for i in range(10):  # try 10 times (?)
                if self.ppmac_ssh.recv_ready():
                    buffer += self.ppmac_ssh.recv(4096).decode()
                    return_lines = buffer.split("\r\n")
                # print(buffer)

                # often there are  additional "\\x06" characters
                # or empty lines that should be stripped out.
                # especially with adding "\r\n" to the command
                j = 0
                while j < len(return_lines):
                    if "\x06" in return_lines[j] or return_lines[j] == "":
                        del return_lines[j]
                    else:
                        j += 1

                if (
                    len(return_lines) >= 2 and "@" not in buffer
                ):  # what happens with other lengths/lines?
                    success = 1
                    break

                time.sleep(timeout)  # time.sleep(1)

            if "@" in buffer:
                success = 0
                # we are probably now at the linux prompt
                self.connected = False

            for bad_response in self.gpascii_error_list:
                if bad_response in buffer:
                    print("error in response from brick")
                    print(bad_response + "in " + buffer)
                    success = 0

            # clear anything else left in the buffer?

            # example of invalid response;
            # gooble
            # stdin:2:2: error #20: ILLEGAL CMD: gooble
            # No data to display

            # more examples;
            # good:
            # motor[2].JogSpeed
            # Motor[2].JogSpeed = 10
            # bad:
            # motor[2].JogSpee
            # stdin: 12:1: error  # 21: ILLEGAL PARAMETER: motor[2].JogSpee

            print(f"received:\n {buffer}\n")
            print(f"lines:\n {return_lines}\n")
        return success, return_lines[1]

    def disconnect(self):
        print("disconnecting..")

        # send CTRL-C to close gpascii
        self.ppmac_ssh.send(bytearray("\u0003", "utf-8"))
        success = 0
        buffer = ""
        for i in range(10):
            if self.ppmac_ssh.recv_ready():
                buffer += self.ppmac_ssh.recv(4096).decode()

            if self.ssh_prompt in buffer:
                success = 1
                break
            time.sleep(1)

        # send "logout" to close ssh (locally or remotely)
        self.ppmac_ssh.send("logout\n")
        success = 0
        buffer = ""
        for i in range(10):
            if self.ppmac_ssh.recv_ready():
                buffer += self.ppmac_ssh.recv(4096).decode()

            if self.ssh_prompt in buffer:
                success = 1
                break
            time.sleep(1)

        # print(buffer)
        if self.ppmac_ssh_paramiko is not None:
            self.ppmac_ssh_paramiko.close()
            self.ppmac_ssh_paramiko = None
        print("disconnected.")
        return success

